from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Lets staff see reports until the moderator queue (RH-14) exists.

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
