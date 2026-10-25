"""Tests for preserving existing auth accounts during the custom-user cutover."""

from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

pytestmark = pytest.mark.django_db


def migration_context():
    """Build the historical models the data migration receives from Django."""
    state = MigrationLoader(None).project_state(("accounts", "0002_copy_legacy_auth_users"))
    return state.apps


def create_legacy_user(legacy_user_model, username, email):
    return legacy_user_model._base_manager.create(
        username=username,
        email=email,
        password=make_password("migration-test-password"),
        date_joined=timezone.now(),
    )


def run_copy_migration(apps):
    migration = import_module("apps.accounts.migrations.0002_copy_legacy_auth_users")
    migration.copy_legacy_auth_users(apps, SimpleNamespace(connection=connection))


def mongo_collection(name):
    connection.ensure_connection()
    database = connection.connection[connection.settings_dict["NAME"]]
    return database[name]


def test_copy_preserves_user_identity_and_permissions():
    apps = migration_context()
    LegacyUser = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    unique_id = uuid4().hex
    username = f"legacy-{unique_id}"
    legacy_user = create_legacy_user(LegacyUser, username, f"{username}@farmingdale.edu")
    group = Group._base_manager.create(name=f"Legacy group {unique_id}")
    content_type = ContentType._base_manager.create(
        app_label="accounts", model=f"migration_{unique_id}"
    )
    permission = Permission._base_manager.create(
        name=f"Can review migration {unique_id}",
        codename=f"review_migration_{unique_id}",
        content_type=content_type,
    )

    # Swapped auth.User models have no ORM through model, so seed their
    # historical collections directly as existing deployments store them.
    group_links = mongo_collection("auth_user_groups")
    permission_links = mongo_collection("auth_user_user_permissions")
    group_links.insert_one({"user_id": legacy_user.pk, "group_id": group.pk})
    permission_links.insert_one({"user_id": legacy_user.pk, "permission_id": permission.pk})
    try:
        run_copy_migration(apps)

        migrated_user = get_user_model()._base_manager.get(pk=legacy_user.pk)
        assert migrated_user.password == legacy_user.password
        assert migrated_user.groups.filter(pk=group.pk).exists()
        assert migrated_user.user_permissions.filter(pk=permission.pk).exists()
        assert LegacyUser._base_manager.filter(pk=legacy_user.pk).exists()
    finally:
        group_links.delete_many({"user_id": legacy_user.pk})
        permission_links.delete_many({"user_id": legacy_user.pk})


def test_duplicate_legacy_emails_abort_before_copying_users():
    apps = migration_context()
    LegacyUser = apps.get_model("auth", "User")
    unique_id = uuid4().hex
    first = create_legacy_user(
        LegacyUser, f"legacy-one-{unique_id}", f"duplicate-{unique_id}@farmingdale.edu"
    )
    create_legacy_user(
        LegacyUser, f"legacy-two-{unique_id}", f"duplicate-{unique_id}@farmingdale.edu"
    )

    with pytest.raises(RuntimeError, match="multiple auth users share an email"):
        run_copy_migration(apps)

    assert get_user_model()._base_manager.filter(pk=first.pk).count() == 0
