"""Admin for campus data. Shaped for eyeballing imported records, not for data entry."""

from django.contrib import admin

from .models import Club


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name", "org_type", "category_list", "source_retrieved"]
    list_filter = ["org_type"]
    search_fields = ["name", "short_name"]
    ordering = ["sort_name"]

    @admin.display(description="Categories")
    def category_list(self, obj: Club) -> str:
        return ", ".join(obj.categories) or "none"
