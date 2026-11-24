#!/usr/bin/env python
"""Safely plan or apply the physical schema effects of accounts.0001_initial.

Default mode is read-only. This script never drops collections, modifies user
records, or runs migrations. Schema application and migration-history recording
are separate, explicitly confirmed operations.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.disable(logging.CRITICAL)

TARGET_DATABASE = "ramhub"
USER_TABLE = "accounts_user"
EXPECTED_MIGRATION = ("accounts", "0001_initial")
BSON_TYPE_MAP = {
    "objectId": {"objectId"},
    "string": {"string"},
    "bool": {"bool"},
    "date": {"date"},
    "int": {"int", "long"},
    "long": {"int", "long"},
    "double": {"double", "int", "long"},
    "array": {"array"},
    "object": {"object"},
    "binData": {"binData"},
    "decimal": {"decimal"},
}
INDEX_OPTIONS = {
    "unique",
    "sparse",
    "expireAfterSeconds",
    "partialFilterExpression",
    "collation",
    "hidden",
    "wildcardProjection",
    "weights",
    "default_language",
    "language_override",
    "textIndexVersion",
    "2dsphereIndexVersion",
    "bits",
    "min",
    "max",
    "bucketSize",
    "storageEngine",
}


class IndexCapture:
    """Capture backend-generated IndexModels without calling MongoDB writes."""

    def __init__(self, collection_name: str, captured: list[tuple[str, Any]]):
        self.collection_name = collection_name
        self.captured = captured

    def create_indexes(self, index_models):
        for index_model in index_models:
            self.captured.append((self.collection_name, copy.deepcopy(index_model)))


def json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "binary") and type(value).__name__ == "ObjectId":
        return str(value)
    if hasattr(value, "to_decimal"):
        return str(value)
    return value


def index_document(index_model):
    return copy.deepcopy(index_model.document)


def normalized_expected(document):
    return {
        "name": document["name"],
        "key": list(document["key"].items()),
        **{option: document[option] for option in INDEX_OPTIONS if option in document},
    }


def normalized_actual(name, spec):
    result = {"name": name, "key": list(spec.get("key", ())) }
    result.update({option: spec[option] for option in INDEX_OPTIONS if option in spec})
    return result


def collect_expected_indexes(connection, models):
    """Ask django-mongodb-backend to generate names/options; capture all calls."""
    collected: list[tuple[str, Any]] = []
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        original_get_collection = editor.get_collection
        for model in models:
            table = model._meta.db_table
            editor.get_collection = lambda name, table=table: IndexCapture(name, collected)
            editor._create_model_indexes(model)
        editor.get_collection = original_get_collection

    expected: dict[str, dict[str, Any]] = {}
    for model in models:
        table = model._meta.db_table
        expected[table] = {
            "_id_": {"name": "_id_", "key": {"_id": 1}},
        }
    for table, index_model in collected:
        document = index_document(index_model)
        name = document["name"]
        if name in expected[table]:
            raise RuntimeError(f"Backend generated duplicate expected index name for {table}.")
        expected[table][name] = document
    return expected


def expected_fields(connection, models):
    """Return expected physical field names and MongoDB BSON type families."""
    result = {}
    for model in models:
        fields = {"_id": {"types": {"objectId"}, "nullable": False, "has_default": False}}
        for field in model._meta.local_fields:
            column = field.column
            if column == "_id":
                continue
            db_type = field.db_type(connection)
            allowed = BSON_TYPE_MAP.get(db_type)
            if allowed is None:
                raise RuntimeError(
                    f"No BSON type mapping is defined for {model._meta.db_table}.{column}."
                )
            fields[column] = {
                "types": allowed,
                "nullable": field.null,
                "has_default": field.has_default(),
            }
        result[model._meta.db_table] = fields
    return result


def duplicate_counts(collection, document):
    key_fields = list(document["key"])
    if key_fields == ["_id"] or document.get("unique") is not True:
        return {"duplicate_groups": 0, "extra_documents": 0}
    pipeline = []
    if document.get("partialFilterExpression"):
        pipeline.append({"$match": document["partialFilterExpression"]})
    group_key = {f"k{index}": f"${field}" for index, field in enumerate(key_fields)}
    pipeline.extend(
        [
            {"$group": {"_id": group_key, "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {
                "$group": {
                    "_id": None,
                    "duplicate_groups": {"$sum": 1},
                    "extra_documents": {"$sum": {"$subtract": ["$n", 1]}},
                }
            },
        ]
    )
    rows = list(collection.aggregate(pipeline))
    if not rows:
        return {"duplicate_groups": 0, "extra_documents": 0}
    return {
        "duplicate_groups": rows[0]["duplicate_groups"],
        "extra_documents": rows[0]["extra_documents"],
    }


def document_shape(collection):
    pipeline = [
        {"$project": {"pairs": {"$objectToArray": "$$ROOT"}}},
        {"$unwind": "$pairs"},
        {
            "$group": {
                "_id": {"field": "$pairs.k", "bson_type": {"$type": "$pairs.v"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.field": 1, "_id.bson_type": 1}},
    ]
    rows = list(collection.aggregate(pipeline))
    return [
        {
            "field": row["_id"]["field"],
            "bson_type": row["_id"]["bson_type"],
            "count": row["count"],
        }
        for row in rows
    ]


def audit_collection(collection, expected_indexes, expected_field_map):
    total = collection.count_documents({})
    indexes = collection.index_information()
    shape = document_shape(collection)
    present_by_field = {}
    type_conflicts = []
    for row in shape:
        field_name = row["field"]
        present_by_field[field_name] = present_by_field.get(field_name, 0) + row["count"]
        expected = expected_field_map.get(field_name)
        if expected is None:
            type_conflicts.append(
                {"kind": "unexpected_field", "field": field_name, "bson_type": row["bson_type"]}
            )
        elif (row["bson_type"] == "null" and not expected["nullable"]) or (
            row["bson_type"] != "null" and row["bson_type"] not in expected["types"]
        ):
            type_conflicts.append(
                {
                    "kind": "unexpected_bson_type",
                    "field": field_name,
                    "bson_type": row["bson_type"],
                    "expected_types": sorted(expected["types"]),
                }
            )

    missing_required_fields = {}
    for field_name, definition in expected_field_map.items():
        missing_count = total - present_by_field.get(field_name, 0)
        if missing_count > 0:
            missing_required_fields[field_name] = missing_count
            if not definition["nullable"] and not definition["has_default"]:
                type_conflicts.append(
                    {"kind": "missing_required_field", "field": field_name, "document_count": missing_count}
                )

    existing_indexes = [normalized_actual(name, spec) for name, spec in indexes.items()]
    existing_names = set(indexes)
    expected_names = set(expected_indexes)
    conflicts = list(type_conflicts)
    missing_indexes = []
    present_indexes = []

    for actual in existing_indexes:
        if actual["name"] not in expected_names:
            conflicts.append({"kind": "unexpected_index", "index": json_safe(actual)})

    for name, expected_document in expected_indexes.items():
        expected_normalized = normalized_expected(expected_document)
        if name in existing_names:
            actual = normalized_actual(name, indexes[name])
            if actual != expected_normalized:
                conflicts.append(
                    {
                        "kind": "index_definition_mismatch",
                        "index_name": name,
                        "expected": json_safe(expected_normalized),
                        "actual": json_safe(actual),
                    }
                )
            else:
                present_indexes.append(json_safe(actual))
            continue
        same_key = [item for item in existing_indexes if item["key"] == expected_normalized["key"]]
        if same_key:
            conflicts.append(
                {
                    "kind": "same_key_different_index_name_or_options",
                    "expected": json_safe(expected_normalized),
                    "actual": json_safe(same_key),
                }
            )
        else:
            missing_indexes.append(json_safe(expected_normalized))

    duplicate_by_index = {}
    for name, expected_document in expected_indexes.items():
        if expected_document.get("unique") is True:
            duplicate_by_index[name] = duplicate_counts(collection, expected_document)
            if duplicate_by_index[name]["duplicate_groups"]:
                conflicts.append(
                    {
                        "kind": "duplicate_values_block_unique_index",
                        "index_name": name,
                        **duplicate_by_index[name],
                    }
                )

    duplicate_username_email_counts = {}
    if "username" in expected_field_map and "email" in expected_field_map:
        for field_name in ("username", "email"):
            matching = [
                counts
                for index_name, counts in duplicate_by_index.items()
                if expected_indexes[index_name].get("key") == {field_name: 1}
            ]
            duplicate_username_email_counts[field_name] = (
                matching[0] if matching else {"duplicate_groups": 0, "extra_documents": 0}
            )
    return {
        "exists": True,
        "document_count": total,
        "existing_indexes": [json_safe(item) for item in existing_indexes],
        "present_expected_indexes": present_indexes,
        "missing_expected_indexes": missing_indexes,
        "duplicate_counts_by_unique_index": duplicate_by_index,
        "duplicate_username_email_counts": duplicate_username_email_counts,
        "field_bson_type_counts": shape,
        "missing_field_document_counts": missing_required_fields,
        "conflicts": conflicts,
    }


def migration_state(connection):
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.recorder import MigrationRecorder

    loader = MigrationLoader(connection, load=True)
    state = loader.project_state([EXPECTED_MIGRATION])
    user_model = state.apps.get_model("accounts", "User")
    through_models = [field.remote_field.through for field in user_model._meta.local_many_to_many]
    models = [user_model, *through_models]
    tables = {model._meta.db_table for model in models}
    expected_tables = {"accounts_user", "accounts_user_groups", "accounts_user_user_permissions"}
    if tables != expected_tables:
        raise RuntimeError("The historical accounts migration resolves to unexpected collection names.")

    recorder = MigrationRecorder(connection)
    applied = recorder.applied_migrations()
    target_node = loader.graph.node_map.get(EXPECTED_MIGRATION)
    if target_node is None:
        raise RuntimeError("The expected accounts migration is missing from the migration graph.")
    target_dependencies = {parent.key for parent in target_node.parents}
    inconsistencies = []
    for key in applied:
        node = loader.graph.node_map.get(key)
        if node:
            for parent in node.parents:
                if parent.key not in applied:
                    inconsistencies.append((key, parent.key))
    return loader, recorder, applied, models, inconsistencies, target_dependencies


def build_plan(connection, database):
    loader, recorder, applied, models, inconsistencies, target_dependencies = migration_state(connection)
    expected = collect_expected_indexes(connection, models)
    fields = expected_fields(connection, models)
    collection_names = set(database.list_collection_names())
    plan = {
        "database": database.name,
        "mode": "read_only_plan",
        "migration": {
            "accounts_0001_applied": EXPECTED_MIGRATION in applied,
            "auth_0001_applied": ("auth", "0001_initial") in applied,
            "admin_0001_applied": ("admin", "0001_initial") in applied,
            "accounts_0001_dependencies": [
                {"app": app, "name": name}
                for app, name in sorted(target_dependencies)
            ],
            "accounts_0001_missing_dependencies": [
                {"app": app, "name": name}
                for app, name in sorted(target_dependencies - applied.keys())
            ],
            "migration_recorder_collection_exists": recorder.has_table(),
            "existing_dependency_inconsistencies": [
                {
                    "applied": {"app": item[0][0], "name": item[0][1]},
                    "missing_dependency": {"app": item[1][0], "name": item[1][1]},
                }
                for item in inconsistencies
            ],
        },
        "collections": {},
        "planned_changes": [],
        "blocking_conflicts": [],
        "safe_to_apply_schema": True,
        "schema_complete": True,
    }
    for model in models:
        table = model._meta.db_table
        collection_exists = table in collection_names
        if table == USER_TABLE and not collection_exists:
            plan["blocking_conflicts"].append(
                {"collection": table, "kind": "required_existing_user_collection_missing"}
            )
        if not collection_exists:
            item = {
                "exists": False,
                "document_count": 0,
                "existing_indexes": [],
                "present_expected_indexes": [],
                "missing_expected_indexes": [
                    json_safe(normalized_expected(doc))
                    for doc in expected[table].values()
                    if doc["name"] != "_id_"
                ],
                "duplicate_counts_by_unique_index": {
                    name: {"duplicate_groups": 0, "extra_documents": 0}
                    for name, doc in expected[table].items()
                    if doc.get("unique") is True
                },
                "field_bson_type_counts": [],
                "missing_field_document_counts": {},
                "conflicts": [],
            }
            plan["collections"][table] = item
            if table != USER_TABLE:
                plan["planned_changes"].append({"operation": "create_missing_m2m_collection", "collection": table})
            plan["schema_complete"] = False
        else:
            item = audit_collection(database[table], expected[table], fields[table])
            plan["collections"][table] = item
            if item["missing_expected_indexes"]:
                plan["schema_complete"] = False
                plan["planned_changes"].extend(
                    {
                        "operation": "create_missing_index",
                        "collection": table,
                        "index": index,
                    }
                    for index in item["missing_expected_indexes"]
                )
            if item["conflicts"]:
                plan["blocking_conflicts"].extend(
                    {"collection": table, **conflict} for conflict in item["conflicts"]
                )
    plan["safe_to_apply_schema"] = not plan["blocking_conflicts"]
    plan["schema_complete"] = plan["schema_complete"] and not plan["blocking_conflicts"]
    plan["migration_recording"] = "never automatic; requires a separate explicit invocation"
    return plan, expected


def apply_schema(connection, database, plan, expected):
    # A caller cannot apply a stale plan: repeat all collection, index, data,
    # and migration-graph checks immediately before performing schema writes.
    fresh_plan, fresh_expected = build_plan(connection, database)
    if not fresh_plan["safe_to_apply_schema"]:
        raise RuntimeError("Schema recovery is blocked by audit conflicts.")
    if not fresh_plan["migration"]["accounts_0001_dependencies"] or fresh_plan["migration"]["accounts_0001_missing_dependencies"]:
        raise RuntimeError("Schema recovery is blocked by unresolved accounts migration dependencies.")
    plan, expected = fresh_plan, fresh_expected
    for table, item in plan["collections"].items():
        if not item["exists"]:
            if table == USER_TABLE:
                raise RuntimeError("Refusing to create or replace accounts_user.")
            database.create_collection(table)
    for table, item in plan["collections"].items():
        collection = database[table]
        missing_names = {index["name"] for index in item["missing_expected_indexes"]}
        for name, index_model in expected[table].items():
            if name in missing_names and name != "_id_":
                collection.create_indexes([index_model])
    # Verify from fresh server metadata; do not record migration state here.
    fresh_plan, _ = build_plan(connection, database)
    if not fresh_plan["schema_complete"]:
        raise RuntimeError("Post-write verification did not find the complete expected schema.")
    return fresh_plan


def record_accounts_initial(connection, database, plan):
    from django.db.migrations.loader import MigrationLoader

    # Recording is a distinct explicitly selected operation. Re-audit the
    # physical schema and migration graph immediately before its one insert.
    plan, _ = build_plan(connection, database)
    if not plan["schema_complete"]:
        raise RuntimeError("Refusing to record accounts.0001_initial before schema verification is complete.")
    if plan["migration"]["accounts_0001_applied"]:
        raise RuntimeError("accounts.0001_initial is already recorded; refusing duplicate recording.")
    if plan["migration"]["accounts_0001_missing_dependencies"]:
        raise RuntimeError("Refusing to record accounts.0001_initial because a graph dependency is not applied.")
    if not plan["migration"]["migration_recorder_collection_exists"]:
        raise RuntimeError("Refusing to create the migration recorder collection during recovery.")

    loader = MigrationLoader(connection, load=True)
    applied = loader.applied_migrations
    inconsistencies = {
        (key, parent.key)
        for key in applied
        for parent in loader.graph.node_map[key].parents
        if parent.key not in applied
    }
    expected_inconsistencies = {
        (key, EXPECTED_MIGRATION)
        for key, node in loader.graph.node_map.items()
        if key in applied and EXPECTED_MIGRATION in {parent.key for parent in node.parents}
    }
    if inconsistencies != expected_inconsistencies:
        raise RuntimeError("Refusing to record: migration history has unexpected inconsistencies.")

    # MigrationRecorder.record_applied() inserts the applied row; it does not
    # execute migration operations. This mode is only valid after independent
    # physical-schema verification and is never called by schema-apply mode.
    from django.db.migrations.recorder import MigrationRecorder
    recorder = MigrationRecorder(connection)
    if not recorder.has_table():
        raise RuntimeError("Migration recorder collection disappeared before recording.")
    recorder.record_applied(*EXPECTED_MIGRATION)

    verification = MigrationRecorder(connection).applied_migrations()
    if EXPECTED_MIGRATION not in verification:
        raise RuntimeError("Migration record verification failed after record_applied().")
    return MigrationLoader(connection, load=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Apply only the planned missing indexes and M2M collections.",
    )
    mode.add_argument(
        "--record-accounts-0001",
        action="store_true",
        help="Separately record accounts.0001_initial after a fresh complete-schema audit.",
    )
    parser.add_argument("--confirm-accounts-schema-recovery", action="store_true")
    parser.add_argument("--confirm-record-accounts-0001", action="store_true")
    args = parser.parse_args(argv)
    if args.write and not args.confirm_accounts_schema_recovery:
        parser.error("--write requires --confirm-accounts-schema-recovery.")
    if args.confirm_accounts_schema_recovery and not args.write:
        parser.error("--confirm-accounts-schema-recovery is valid only with --write.")
    if args.record_accounts_0001 and not args.confirm_record_accounts_0001:
        parser.error("--record-accounts-0001 requires --confirm-record-accounts-0001.")
    if args.confirm_record_accounts_0001 and not args.record_accounts_0001:
        parser.error("--confirm-record-accounts-0001 is valid only with --record-accounts-0001.")
    return args


def main(argv=None):
    args = parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        import django
        django.setup()
        from django.db import connections
        connection = connections["default"]
        connection.ensure_connection()
        database = connection.connection[connection.settings_dict["NAME"]]
        if database.name != TARGET_DATABASE:
            raise RuntimeError("Configured database is not the required ramhub database.")
        plan, expected = build_plan(connection, database)
        plan["mode"] = "record_migration" if args.record_accounts_0001 else "apply_schema" if args.write else "dry_run"
        if args.record_accounts_0001:
            record_accounts_initial(connection, database, plan)
            plan["migration"]["accounts_0001_applied"] = True
            plan["migration_recording_result"] = "accounts.0001_initial recorded after physical-schema verification"
        elif args.write:
            if not plan["safe_to_apply_schema"]:
                raise RuntimeError("Recovery refused because blocking conflicts were found.")
            plan = apply_schema(connection, database, plan, expected)
            plan["mode"] = "apply_schema"
            plan["migration_recording_result"] = "not performed"
        print(json.dumps(json_safe(plan), indent=2, sort_keys=True))
        return 0 if plan["safe_to_apply_schema"] else 2
    except Exception as error:
        # Never print exception text: driver/settings errors can contain connection details.
        print(json.dumps({"result": "refused_or_failed", "error_type": type(error).__name__}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())

