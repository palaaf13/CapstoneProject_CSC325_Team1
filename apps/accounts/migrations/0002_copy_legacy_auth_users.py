"""Copy existing Django auth users into RamHub's custom user collection."""

from collections import Counter

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def legacy_membership_ids(
    schema_editor: BaseDatabaseSchemaEditor,
    legacy_user_table: str,
    relation_name: str,
    target_field: str,
    user_id: object,
) -> list[object]:
    """Read a swapped auth model's implicit MongoDB through-collection."""
    database_connection = schema_editor.connection
    database_connection.ensure_connection()
    mongo_client = database_connection.connection
    mongo_database = mongo_client[database_connection.settings_dict["NAME"]]
    collection = mongo_database[f"{legacy_user_table}_{relation_name}"]
    return collection.distinct(target_field, {"user_id": user_id})


def copy_legacy_auth_users(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Preserve user identity and permissions while switching user collections."""
    database = schema_editor.connection.alias
    LegacyUser = apps.get_model("auth", "User")
    User = apps.get_model("accounts", "User")

    legacy_users = list(LegacyUser._base_manager.using(database).all())
    legacy_email_counts = Counter(user.email for user in legacy_users)
    duplicate_email_count = sum(count > 1 for count in legacy_email_counts.values())
    if duplicate_email_count:
        raise RuntimeError(
            "Cannot copy legacy accounts: multiple auth users share an email. "
            "Resolve duplicate emails before applying this migration; no users "
            "were copied."
        )

    target_users = User._base_manager.using(database)

    # Check for conflicting records before writing so a partial copy cannot
    # silently assign one person's login details to another account.
    for legacy_user in legacy_users:
        existing_by_id = target_users.filter(pk=legacy_user.pk).first()
        if existing_by_id is not None:
            if existing_by_id.username != legacy_user.username:
                raise RuntimeError(
                    "Cannot copy legacy accounts: a custom user already has "
                    f"the ID for {legacy_user.username!r} but a different username."
                )
            continue

        if target_users.filter(username=legacy_user.username).exists():
            raise RuntimeError(
                "Cannot copy legacy accounts: a custom user already has "
                f"username {legacy_user.username!r} with a different ID."
            )
        if target_users.filter(email=legacy_user.email).exists():
            raise RuntimeError(
                "Cannot copy legacy accounts: a custom user already has "
                f"the email for {legacy_user.username!r} with a different ID."
            )

    for legacy_user in legacy_users:
        user = target_users.filter(pk=legacy_user.pk).first()
        if user is None:
            # Reusing the ObjectId keeps existing references, such as admin
            # log entries, attached to the same person after the cutover.
            user = User(
                pk=legacy_user.pk,
                password=legacy_user.password,
                last_login=legacy_user.last_login,
                is_superuser=legacy_user.is_superuser,
                username=legacy_user.username,
                first_name=legacy_user.first_name,
                last_name=legacy_user.last_name,
                email=legacy_user.email,
                is_staff=legacy_user.is_staff,
                is_active=legacy_user.is_active,
                date_joined=legacy_user.date_joined,
                role="ADMIN" if legacy_user.is_superuser else "STUDENT",
            )
            user.save(using=database, force_insert=True)

        # Add the old memberships to the custom user's separate through
        # collections. The source auth collections remain untouched.
        legacy_table = LegacyUser._meta.db_table
        group_ids = legacy_membership_ids(
            schema_editor, legacy_table, "groups", "group_id", legacy_user.pk
        )
        permission_ids = legacy_membership_ids(
            schema_editor,
            legacy_table,
            "user_permissions",
            "permission_id",
            legacy_user.pk,
        )
        user.groups.add(*group_ids)
        user.user_permissions.add(*permission_ids)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0001_initial"),
    ]

    operations = [
        # This is a copy, not a destructive move. The legacy collection remains
        # available for verification and rollback; reversing must not delete users.
        migrations.RunPython(copy_legacy_auth_users, migrations.RunPython.noop),
    ]
