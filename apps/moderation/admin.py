from django.contrib import admin

from .models import ModAction, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Lets staff look up reports. Moderators work from the queue at /moderation/queue/.

    Everything a student submitted is read-only; only ``status`` can change.
    """

    list_display = ["created_at", "target_type", "target_id", "reason", "reporter", "status"]
    list_filter = ["status", "target_type", "reason"]
    readonly_fields = [
        "reporter",
        "target_type",
        "target_id",
        "parent_id",
        "reason",
        "note",
        "created_at",
    ]


@admin.register(ModAction)
class ModActionAdmin(admin.ModelAdmin):
    """The moderation log, read-only: an audit trail nobody should be able to edit."""

    list_display = ["created_at", "actor", "action", "target_type", "target_id"]
    list_filter = ["action", "target_type"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
