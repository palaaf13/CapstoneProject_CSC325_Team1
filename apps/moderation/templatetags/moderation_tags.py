"""
``{% report_link obj %}`` — the Report button for a post, comment, or rating.

    {% load moderation_tags %}
    {% report_link post %}
    {% report_link row.comment post=post %}   {# a comment needs its post #}
    {% report_link rating %}

Draws nothing for signed-out visitors, on your own content, and on removed
content; shows "Reported" for things you already reported. Those decisions
live in services.py, so templates never repeat them. The server enforces the
same rules again when the form is submitted.

``{% if user|can_moderate %}`` — whether to show moderator-only links. The
rule lives in ``queue.can_moderate``; the views check it again.
"""

from django import template

from apps.moderation import queue, services

register = template.Library()


@register.inclusion_tag("moderation/partials/report_link.html", takes_context=True)
def report_link(context, obj, post=None) -> dict:
    request = context.get("request")
    if request is None:
        return {"show": False}
    target = services.target_for(obj, post=post)
    if not services.can_report(request.user, target):
        return {"show": False}
    return {
        "show": True,
        "target": target,
        "already": (target.type, target.id) in services.reported_keys(request),
    }


@register.filter
def can_moderate(user) -> bool:
    return queue.can_moderate(user)
