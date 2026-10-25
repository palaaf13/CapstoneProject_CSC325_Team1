"""Form validation. No database needed."""

from apps.community.forms import CommentForm, FeedQueryForm, PostForm, VoteForm, normalize_tag


def test_normalize_tag():
    assert normalize_tag("  #Study Group! ") == "study-group"
    assert normalize_tag("CSC325") == "csc325"
    assert normalize_tag("!!!") == ""


def test_post_form_cleans_and_dedupes_tags():
    form = PostForm({"kind": "notes", "title": "Exam 1 notes", "tags": "CSC325, csc325, #Midterm"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["tags"] == ["csc325", "midterm"]


def test_post_form_limits_tags():
    form = PostForm({"kind": "discussion", "title": "Hi", "tags": "a,b,c,d,e,f"})
    assert not form.is_valid()
    assert "tags" in form.errors


def test_post_form_requires_a_title_and_a_real_kind():
    form = PostForm({"kind": "rant", "title": "   "})
    assert not form.is_valid()
    assert {"kind", "title"} <= set(form.errors)


def test_comment_form_rejects_blank():
    assert not CommentForm({"body": "   "}).is_valid()


def test_vote_form_only_accepts_up_down_or_none():
    assert VoteForm({"value": "1"}).is_valid()
    assert VoteForm({"value": "0"}).is_valid()
    assert not VoteForm({"value": "5"}).is_valid()


def test_feed_query_falls_back_to_defaults():
    query = FeedQueryForm(
        {"sort": "bogus", "kind": "rant", "page": "-3", "tag": "#CSC325"}
    ).to_query()
    assert query.sort == "new"
    assert query.kind == ""
    assert query.page == 1
    assert query.tag == "csc325"  # one bad parameter does not reset the others


def test_feed_query_keeps_valid_values():
    query = FeedQueryForm(
        {"sort": "top", "kind": "question", "tag": "#CSC325", "q": " notes "}
    ).to_query()
    assert query == ("notes", "question", "csc325", "top", 1)
