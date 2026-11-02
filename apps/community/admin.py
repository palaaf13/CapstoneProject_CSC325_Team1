from django.contrib import admin

from .models import Post, Vote


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "author", "score", "comment_count", "created_at", "is_removed"]
    list_filter = ["kind", "is_removed"]
    search_fields = ["title"]
    # Denormalized counters belong to services.py; editing them here would drift them.
    readonly_fields = ["score", "comment_count", "created_at", "edited_at"]


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "target_type", "target_id", "value"]
