"""The landing page: real data, honest attribution, and motion kept to this page."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


@pytest.mark.django_db
def test_landing_is_the_front_door(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.templates[0].name == "pages/home.html"


@pytest.mark.django_db
def test_feed_moved_off_the_root(client):
    assert reverse("community:feed") == "/feed/"
    assert client.get("/feed/").status_code == 200


@pytest.mark.django_db
def test_landing_shows_real_counts_not_marketing_numbers(client, make_course, make_professor):
    make_course(code="CSC 229", title="Data Structures & Algorithms I")
    make_course(code="MTH 150", title="Calculus I", department="Mathematics")
    make_professor(first_name="Ada", last_name="Lovelace")

    response = client.get("/")

    assert response.context["course_count"] == 2
    assert response.context["professor_count"] == 1
    assert b'data-count="2"' in response.content
    assert b"Data Structures &amp; Algorithms I" in response.content


@pytest.mark.django_db
def test_featured_professor_rating_is_attributed_to_rmp(client, make_professor):
    """CLAUDE.md: anywhere an RMP number appears, it must say where it came from."""
    from apps.catalog.models import ProfessorRatingSummary

    make_professor(
        first_name="Karen",
        last_name="Bottalico",
        rating_summary=ProfessorRatingSummary(
            avg_overall=4.9, count=226, source="rmp", rank_score=4.85
        ),
    )

    response = client.get("/")

    assert b"Karen Bottalico" in response.content
    assert b"ratings on Rate My Professors" in response.content


@pytest.mark.django_db
def test_landing_renders_with_an_empty_database(client):
    """A fresh clone before seed_demo must not crash the front door."""
    assert client.get("/").status_code == 200


@pytest.mark.django_db
def test_motion_libraries_load_only_on_the_landing_page(client):
    """The directories stay on htmx + vanilla JS (CLAUDE.md)."""
    assert b"gsap.min.js" in client.get("/").content
    for url in ("/courses/", "/professors/", "/feed/"):
        body = client.get(url).content
        assert b"gsap" not in body and b"lenis" not in body, url


@pytest.mark.django_db
def test_hero_content_is_in_the_html_without_javascript(client):
    """Motion is an enhancement: the words must be there before any script runs."""
    body = client.get("/").content
    assert b"Know the class" in body
    assert b"before you take it." in body


def test_no_template_uses_a_multiline_hash_comment():
    """
    Django's {# #} comment is single-line only. Spread over several lines it
    renders as visible text — this shipped briefly into the nav during the
    landing page work. Use {% comment %} for anything longer than a line.
    """
    offenders = [
        f"{path.relative_to(TEMPLATES)}:{number}"
        for path in TEMPLATES.rglob("*.html")
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if "{#" in line and "#}" not in line
    ]
    assert not offenders, offenders


def test_landing_css_is_scoped_so_it_cannot_leak_into_directories():
    css = (Path(__file__).resolve().parent.parent / "static/src/input.css").read_text()
    landing = css[css.index("Landing page\n") :]
    selectors = re.findall(r"^\s{2}(\.[a-z][\w-]*)", landing, flags=re.M)
    assert selectors, "expected landing selectors"
    # every landing component is namespaced to landing-only class names
    generic = [s for s in selectors if s in {".card", ".row-link", ".btn-primary", ".badge"}]
    assert not generic, generic


# -- Rambo -------------------------------------------------------------------
@pytest.mark.django_db
def test_rambo_section_renders_as_an_accessible_button(client):
    body = client.get("/").content
    assert b'data-rambo aria-label="Say hi to Rambo, the RamHub mascot"' in body
    assert b"<button" in body
    assert b"Meet" in body and b"Rambo." in body


@pytest.mark.django_db
def test_rambo_is_labelled_as_original_artwork(client):
    """The roadmap: an original character, not the college's official mark."""
    assert b"not an official college mark" in client.get("/").content


@pytest.mark.django_db
def test_rambo_lines_are_embedded_as_safe_json(client, make_course):
    make_course(code="CSC 229", title="Data Structures & Algorithms I")

    body = client.get("/").content.decode()

    assert 'id="rambo-lines"' in body
    assert (
        "Hi, I&#x27;m Rambo." in body or "Hi, I\\u0027m Rambo." in body or "Hi, I'm Rambo." in body
    )


@pytest.mark.django_db
def test_rambo_only_says_things_the_database_backs_up(make_course):
    from apps.catalog.landing import rambo_lines

    course = make_course(code="CSC 229", title="Data Structures & Algorithms I")

    lines = rambo_lines(course_count=1785, department_count=67, featured_course=course)

    assert lines[0] == "Hi, I'm Rambo."
    assert any("1,785 courses" in line for line in lines)
    assert any("67 departments" in line for line in lines)
    assert any("CSC 229" in line for line in lines)
    # the assistant is not built, and Rambo must not imply that it is
    assert any("soon" in line for line in lines)


def test_rambo_lines_cope_with_an_empty_catalog():
    from apps.catalog.landing import rambo_lines

    lines = rambo_lines(course_count=0, department_count=0, featured_course=None)

    assert lines and not any("None" in line for line in lines)


def test_the_old_mascot_name_is_gone_everywhere():
    root = Path(__file__).resolve().parent.parent
    offenders = [
        str(path.relative_to(root))
        for folder in ("templates", "apps", "static/js", "static/src", "config")
        for path in (root / folder).rglob("*")
        if path.is_file()
        and path.suffix in {".html", ".py", ".js", ".css"}
        and "rammy" in path.read_text(errors="ignore").lower()
    ]
    assert not offenders, offenders


@pytest.mark.django_db
def test_interactive_scripts_load_only_on_the_landing_page(client):
    assert b"js/cursor.js" in client.get("/").content
    assert b"js/rambo.js" in client.get("/").content
    for url in ("/courses/", "/professors/", "/feed/"):
        body = client.get(url).content
        assert b"cursor.js" not in body and b"rambo.js" not in body, url


# -- cursor aura -------------------------------------------------------------
STATIC = TEMPLATES.parent / "static"


def test_cursor_is_a_shifting_gradient_not_a_ring():
    script = (STATIC / "js" / "cursor.js").read_text()
    css = (STATIC / "src" / "input.css").read_text()

    assert "cursor-aura" in script
    assert "cursor-follower" not in script and "cursor-cut" not in script
    assert "prefers-reduced-motion: reduce" in script
    # Continuous 8s shift, animating only transform and opacity.
    assert re.search(r"animation: aura-shift 8s ease-in-out infinite", css)
    for name in ("aura-shift", "aura-shift-b"):
        body = re.search(rf"@keyframes {name} \{{(.*?)\n  \}}", css, re.S).group(1)
        properties = set(re.findall(r"([a-z-]+):", body))
        assert properties == {"transform", "opacity"}, (name, properties)


def test_cursor_aura_never_blocks_the_page():
    css = (STATIC / "src" / "input.css").read_text()
    aura = re.search(r"\.cursor-aura \{(.*?)\}", css, re.S).group(1)

    assert "pointer-events-none" in aura
    assert re.search(
        r"prefers-reduced-motion: reduce\) \{\s*\.cursor-aura \{ display: none; \}", css
    )


# -- feature strip -----------------------------------------------------------
@pytest.mark.django_db
def test_strip_links_to_every_section_of_the_site(client):
    from config.context_processors import NAV_TABS

    response = client.get("/")

    features = response.context["features"]
    assert len(features) == len(NAV_TABS)
    assert {f["url_name"] for f in features} == {t["url_name"] for t in NAV_TABS}
    for feature in features:
        assert reverse(feature["url_name"]).encode() in response.content


@pytest.mark.django_db
def test_every_strip_link_resolves_to_a_real_page(client):
    for feature in client.get("/").context["features"]:
        assert client.get(reverse(feature["url_name"])).status_code == 200


@pytest.mark.django_db
def test_strip_counts_come_from_the_database(client, make_course, make_professor):
    make_course(code="CSC 229")
    make_course(code="MTH 150", department="Mathematics")
    make_professor(first_name="Ada", last_name="Lovelace")

    features = {f["label"]: f for f in client.get("/").context["features"]}

    assert "2 courses" in features["Courses"]["detail"]
    assert "2 departments" in features["Courses"]["detail"]
    assert "1 instructors" in features["Professors"]["detail"]


@pytest.mark.django_db
def test_strip_does_not_claim_data_it_does_not_have(client):
    """
    Courses and Professors hold real college data, and the Jobs, Parking, and
    Facilities guides carry facts from official pages. Clubs and the feed stay
    "building" until their data is loaded, and nothing is loaded here. The
    card must not imply otherwise in either direction.
    """
    features = {f["label"]: f for f in client.get("/").context["features"]}

    for label in ("Courses", "Professors", "Jobs", "Parking", "Facilities"):
        assert features[label]["status"] == "live", label
    for label in ("Clubs", "Feed"):
        assert features[label]["status"] == "building", label


@pytest.mark.django_db
def test_clubs_card_goes_live_only_once_clubs_are_loaded(client, make_club):
    """The card reads the database, so it is true on a fresh clone and after an import."""
    before = {f["label"]: f for f in client.get("/").context["features"]}
    assert before["Clubs"]["status"] == "building"

    make_club("Chess Club")
    make_club("Gaming Club")

    after = {f["label"]: f for f in client.get("/").context["features"]}
    assert after["Clubs"]["status"] == "live"
    assert "2 student organisations" in after["Clubs"]["detail"]


@pytest.mark.django_db
def test_strip_is_usable_without_javascript(client):
    """
    The stage is only pinned once strip.js adds .strip-pinned. Until then the
    markup is a plain list of links inside a scrollable viewport.
    """
    body = client.get("/").content

    assert b"strip-viewport" in body
    assert b"strip-pinned" not in body, "pinning must be added by JS, never rendered"
    assert body.count(b"strip-card") >= 7


@pytest.mark.django_db
def test_strip_script_loads_only_on_the_landing_page(client):
    assert b"js/strip.js" in client.get("/").content
    for url in ("/courses/", "/professors/", "/feed/"):
        assert b"strip.js" not in client.get(url).content, url


# -- Galaxy, drum roll, impact -------------------------------------------------
@pytest.mark.django_db
def test_galaxy_opens_the_page_and_reads_without_javascript(client):
    """The headline and button are plain HTML; the galaxy only decorates them."""
    body = client.get("/").content.decode()
    assert body.index("data-galaxy") < body.index("data-hero"), "galaxy comes first"
    assert '<h1 id="galaxy-heading" class="galaxy-title">RamHub</h1>' in body
    assert body.count("<h1") == 1, "one page title; the old hero headline is an h2"
    galaxy = body[body.index("data-galaxy") : body.index("data-hero")]
    assert f'href="{reverse("catalog:courses")}"' in galaxy


@pytest.mark.django_db
def test_three_js_loads_only_on_the_landing_page(client):
    body = client.get("/").content
    assert b"three@0.170.0" in body, "pinned version, never a floating tag"
    assert b"js/galaxy.js" in body
    for url in ("/courses/", "/professors/", "/feed/"):
        page = client.get(url).content
        assert b"three@" not in page and b"galaxy.js" not in page, url


@pytest.mark.django_db
def test_drum_roll_words_are_in_the_html(client):
    body = client.get("/").content
    for word in (b"Learn.", b"Connect.", b"Discover.", b"Belong."):
        assert word in body


@pytest.mark.django_db
def test_scroll_stages_are_only_pinned_by_javascript(client):
    """Without JS each stage is one screen tall, so nothing is a dead scroll."""
    body = client.get("/").content
    assert b"galaxy-pinned" not in body
    assert b"roll-pinned" not in body


def test_galaxy_uses_the_design_tokens_not_stray_colours():
    script = (Path(__file__).resolve().parent.parent / "static/js/galaxy.js").read_text()
    css = (Path(__file__).resolve().parent.parent / "static/src/input.css").read_text()
    for token in ("--color-accent-200", "--color-accent-400", "--color-neutral-950"):
        assert token in script, token
    tokens = {
        "#a3d7b8": "--color-accent-200: #a3d7b8",
        "#3f9e6d": "--color-accent-400: #3f9e6d",
        "#0d0f12": "--color-neutral-950: #0d0f12",
    }
    for hex_value, declaration in tokens.items():
        assert hex_value in script.replace("0x0d0f12", "#0d0f12"), hex_value
        assert declaration in css, declaration
