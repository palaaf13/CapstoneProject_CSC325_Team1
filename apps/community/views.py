"""
Feed pages. Views parse the request, call a service, and render.

Reading the feed is public for now, like the directories; Phase 2 puts the
whole site behind the college-email gate. Every write needs a signed-in user,
and ownership is checked in services.py.

Interactions follow the directories' contract: a plain form first, so it all
works with JavaScript off, with HTMX swapping partials on top. Voting is the
one HTMX fragment endpoint; everything else is a form post and a redirect.
"""

from collections.abc import Callable
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import services
from .forms import SORTS, CommentForm, FeedQuery, FeedQueryForm, PostForm, VoteForm
from .models import Comment, Post, PostKind


def login_url() -> str:
    """The sign-in page. Accounts (Phase 2) will add one; until then, the admin's."""
    for name in ("login", "accounts:login"):
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return reverse("admin:login")


def login_required_for_feed(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        if request.headers.get("HX-Request") == "true":
            # A redirect would be swapped into the page; tell htmx to navigate.
            response = HttpResponse(status=204)
            response["HX-Redirect"] = (
                f"{login_url()}?{urlencode({'next': reverse('community:feed')})}"
            )
            return response
        return redirect_to_login(request.get_full_path(), login_url())

    return wrapper


def _post_or_404(post_id: str) -> Post:
    post = services.get_post(post_id)
    if post is None:
        raise Http404("No such post.")
    return post


def _page_url(query: FeedQuery, page_number: int) -> str:
    params = {k: v for k, v in query._asdict().items() if v and k != "page"}
    params["page"] = page_number
    return "?" + urlencode(params)


# -- reading ---------------------------------------------------------------
def feed(request: HttpRequest) -> HttpResponse:
    query = FeedQueryForm(request.GET).to_query()
    page = Paginator(services.feed_posts(query), services.PAGE_SIZE).get_page(query.page)
    my_votes = services.votes_by(request.user, page.object_list)
    rows = [{"post": p, "my_vote": my_votes.get(p.pk, 0)} for p in page.object_list]

    context = {
        "query": query,
        "rows": rows,
        "page_obj": page,
        "total": page.paginator.count,
        "sorts": SORTS,
        "kinds": PostKind.choices,
        "is_filtered": bool(query.q or query.kind or query.tag),
        "clear_url": reverse("community:feed"),
        "prev_url": _page_url(query, page.previous_page_number()) if page.has_previous() else None,
        "next_url": _page_url(query, page.next_page_number()) if page.has_next() else None,
        "login_url": login_url(),
    }
    is_htmx = request.headers.get("HX-Request") == "true"
    is_restore = request.headers.get("HX-History-Restore-Request") == "true"
    template = (
        "community/partials/feed_results.html"
        if is_htmx and not is_restore
        else "community/feed.html"
    )
    return render(request, template, context)


def _detail_context(request: HttpRequest, post: Post, form: CommentForm | None = None) -> dict:
    authors = services.comment_authors(post)
    comments = [
        {
            "comment": c,
            "author_name": services.display_name(authors.get(c.author_id)),
            "can_remove": services.can_remove_comment(request.user, c),
        }
        for c in post.comments
    ]
    return {
        "post": post,
        "comments": comments,
        "comment_form": form or CommentForm(),
        "my_vote": services.votes_by(request.user, [post]).get(post.pk, 0),
        "can_edit": services.can_edit(request.user, post),
        "can_remove": services.can_remove(request.user, post),
        "is_own": request.user.is_authenticated and post.author_id == request.user.pk,
        "login_url": login_url(),
    }


def post_detail(request: HttpRequest, post_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    return render(request, "community/post_detail.html", _detail_context(request, post))


# -- writing ---------------------------------------------------------------
@login_required_for_feed
def post_create(request: HttpRequest) -> HttpResponse:
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        post = services.create_post(author=request.user, **form.cleaned_data)
        return redirect("community:post_detail", post_id=post.pk)
    return render(request, "community/post_form.html", {"form": form, "post": None})


@login_required_for_feed
def post_edit(request: HttpRequest, post_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    if not services.can_edit(request.user, post):
        raise PermissionDenied
    initial = {
        "kind": post.kind,
        "title": post.title,
        "body": post.body,
        "tags": ", ".join(post.tags),
    }
    form = PostForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        services.edit_post(request.user, post, **form.cleaned_data)
        return redirect("community:post_detail", post_id=post.pk)
    return render(request, "community/post_form.html", {"form": form, "post": post})


@require_POST
@login_required_for_feed
def post_remove(request: HttpRequest, post_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    services.remove_post(request.user, post)
    return redirect("community:post_detail", post_id=post.pk)


@require_POST
@login_required_for_feed
def comment_create(request: HttpRequest, post_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    form = CommentForm(request.POST)
    if not form.is_valid():
        context = _detail_context(request, post, form)
        return render(request, "community/post_detail.html", context, status=400)
    comment = services.add_comment(request.user, post, form.cleaned_data["body"])
    return redirect(
        reverse("community:post_detail", args=[post.pk]) + f"#comment-{comment.comment_id}"
    )


@require_POST
@login_required_for_feed
def comment_remove(request: HttpRequest, post_id: str, comment_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    try:
        services.remove_comment(request.user, post, comment_id)
    except Comment.DoesNotExist:
        raise Http404("No such comment.") from None
    return redirect(reverse("community:post_detail", args=[post.pk]) + "#comments")


@require_POST
@login_required_for_feed
def post_vote(request: HttpRequest, post_id: str) -> HttpResponse:
    post = _post_or_404(post_id)
    form = VoteForm(request.POST)
    if not form.is_valid():
        return HttpResponse("Invalid vote.", status=400)
    value = form.cleaned_data["value"]
    services.cast_vote(request.user, post, value)

    if request.headers.get("HX-Request") == "true":
        return render(request, "community/partials/vote.html", {"post": post, "my_vote": value})
    next_url = form.cleaned_data["next"]
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("community:post_detail", args=[post.pk])
    return redirect(next_url)
