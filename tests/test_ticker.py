"""The starry frame and the stock-board ticker on every page except the landing page."""

import pytest
from django.urls import reverse

from apps.campus.models import Club
from apps.catalog.models import CourseRatingSummary
from config import ticker

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(make_course, make_professor):
    make_course(
        code="CSC 325",
        title="Software Engineering",
        rating_summary=CourseRatingSummary(avg_usefulness=4.4, count=3),
    )
    make_professor(
        first_name="Ada", last_name="Lovelace", clarity=4.8, helpfulness=4.6, fairness=4.7, count=12
    )
    make_professor(
        first_name="Bob", last_name="Lowscore", clarity=2, helpfulness=2.5, fairness=2, count=4
    )
    Club.objects.create(
        name="Chess Club", slug="chess-club", org_type="Recognized Student Organizations"
    )


def test_items_read_like_a_stock_board(data):
    items = {i.symbol: i for i in ticker.build_items()}
    assert items["LOVELACE"].value == "4.7" and items["LOVELACE"].trend == "up"
    assert items["LOWSCORE"].trend == "down"
    assert items["CSC 325"].value == "useful 4.4" and items["CSC 325"].url == "/courses/CSC-325/"
    assert items["CLUBS"].value == "1" and items["CLUBS"].url == "/clubs/"


@pytest.mark.parametrize("url", ["/clubs/", "/professors/", "/courses/", "/facilities/", "/about/"])
def test_normal_pages_get_the_frame_and_the_ticker(client, data, url):
    body = client.get(url).content.decode()
    assert 'class="star-frame"' in body
    assert "flex min-h-full flex-col frame" in body
    assert 'class="frame-sheet' in body
    assert 'class="ticker"' in body and "LOVELACE" in body


def test_the_cursor_paints_the_frame_on_normal_pages_only(client, data):
    page = client.get("/clubs/").content.decode()
    assert "js/frame-cursor.js" in page
    assert "data-frame-glow" in page and "data-frame-aura" in page
    assert "frame-cursor.js" not in client.get(reverse("home")).content.decode()


def test_the_landing_page_keeps_its_own_look(client, data):
    body = client.get(reverse("home")).content.decode()
    assert "star-frame" not in body and 'class="ticker"' not in body


def test_the_loop_copy_is_hidden_from_screen_readers_and_keyboards(client, data):
    body = client.get("/clubs/").content.decode()
    first, copy = body.split('class="ticker-list"')[1:3]
    assert "aria-hidden" not in first.split(">")[0]
    assert copy.lstrip().startswith('aria-hidden="true"')
    assert 'tabindex="-1"' in copy and 'tabindex="-1"' not in first


def test_no_ticker_when_there_is_nothing_to_show(client):
    assert 'class="ticker"' not in client.get("/clubs/").content.decode()


def test_items_are_cached_between_pages(client, data, monkeypatch):
    calls = []
    real = ticker.build_items
    monkeypatch.setattr(ticker, "build_items", lambda: calls.append(1) or real())
    client.get("/clubs/")
    client.get("/professors/")
    assert len(calls) == 1


def test_htmx_partials_never_build_the_ticker(client, data, monkeypatch):
    calls = []
    monkeypatch.setattr(ticker, "build_items", lambda: calls.append(1) or [])
    response = client.get("/courses/?q=CSC", HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and "<html" not in response.content.decode()
    assert calls == []


def test_landing_page_rambo_leads_to_the_ai_chat(client):
    body = client.get(reverse("home")).content.decode()
    assert 'href="/rambo/" class="btn-luxe"' in body
    assert 'data-rambo-href="/rambo/"' in body
    assert "Ask Rambo, RamHub's AI assistant" in body
    assert "arrives in a later sprint" not in body
