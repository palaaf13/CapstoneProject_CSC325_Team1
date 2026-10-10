"""
Regenerate farmingdale_clubs.ndjson from RamCentral, the college's club directory.

    python scrape_clubs.py                 # ~6 minutes at the crawl delay
    python scrape_clubs.py --cache /tmp/rc # keep the fetched pages between runs

This is a data-prep tool, not part of the app — the committed .ndjson is what
`manage.py import_clubs` reads. Run it once a semester (clubs re-register every
term), then review the diff before committing.

Source: https://farmingdale.campuslabs.com/engage/ — "RamCentral", which
farmingdale.edu/ramcentral redirects to and which the Office of Student
Activities names as the up-to-date club listing. Each organization has a public
page, and that page's HTML carries the record as JSON in `initialAppState`.

Three rules this script keeps, and a refresh must keep too:

1. **It never calls /engage/api/.** RamCentral's robots.txt disallows that path
   and allows the organization pages, so this reads the pages. The cost is that
   the list of organizations cannot be fetched by script — the directory page
   fills itself in from the API. ramcentral_keys.txt is that list, captured by
   hand: open https://farmingdale.campuslabs.com/engage/organizations, press
   "Load More" until every organization is showing, then run this in the
   browser console and paste the output over the keys in the file:

       copy([...document.querySelectorAll('a[href*="/engage/organization/"]')]
         .map(a => a.getAttribute('href').split('/organization/')[1]).join('\\n'))

   Categories have the same limit: an organization page does not say which
   categories it is filed under, only the directory's Categories filter does.
   ramcentral_categories.json is that mapping, captured the same way — pick one
   category in the filter, "Load More" to the end, run the snippet, repeat.

2. **It only exports what the public page shows.** The embedded JSON also holds
   a `primaryContact` — a named student and their campus email — which the page
   itself hides behind "Sign in to view officers". That block is never read.
   The contact email exported here is the organization's own, printed on the
   page under "Contact Email".
3. **It does not guess.** A blank field upstream is blank here. RamCentral
   records no meeting time, so there is no meeting field to export.
"""

import argparse
import html
import json
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS_FILE = HERE / "ramcentral_keys.txt"
CATEGORIES_FILE = HERE / "ramcentral_categories.json"
OUT_FILE = HERE / "farmingdale_clubs.ndjson"

BASE_URL = "https://farmingdale.campuslabs.com/engage/organization/"
USER_AGENT = "RamHub-capstone/1.0"
# robots.txt sets no Crawl-Delay for this host; farmingdale.edu asks for 5s, so
# stay in that neighbourhood rather than hammering a shared service.
CRAWL_DELAY_SECONDS = 3

STATE_RE = re.compile(r"window\.initialAppState\s*=\s*(\{.*?\});\s*</script>", re.S)

# socialMedia keys worth keeping, in display order. externalWebsite is exported
# separately as `website`; the calendar and dead-network keys are dropped.
SOCIAL_KEYS = {
    "instagramUrl": "instagram",
    "facebookUrl": "facebook",
    "linkedInUrl": "linkedin",
    "youtubeUrl": "youtube",
    "twitterUrl": "twitter",
}

BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


class _TextExtractor(HTMLParser):
    """Rich-text description -> plain text, keeping paragraph and list breaks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def to_text(fragment: str | None) -> str:
    """Strip markup and collapse whitespace; paragraphs stay one blank line apart."""
    if not fragment:
        return ""
    parser = _TextExtractor()
    parser.feed(fragment)
    text = html.unescape("".join(parser.parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    # An emptied list item ("- ") is a formatting artefact, not content.
    lines = ["" if line == "-" else line for line in lines]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def plain(value: str | None) -> str:
    """A one-line text field. A few arrive HTML-escaped ("Ski &amp; Snowboard Club")."""
    return html.unescape(value or "").strip()


def clean_url(value: str | None) -> str:
    """A usable http(s) URL, or "". Upstream fields are free text."""
    value = (value or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        # "www.example.org" and "instagram.com/club" are common; bare handles
        # and stray words are not links and are dropped rather than guessed at.
        if not re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", value):
            return ""
        value = "https://" + value
    return value


def location_of(contact_info: list[dict]) -> str:
    """Join the address lines the page prints under "Address"."""
    if not contact_info:
        return ""
    first = contact_info[0]
    parts = [first.get(key) for key in ("street1", "street2", "city", "state", "zip")]
    return ", ".join(part.strip() for part in parts if part and part.strip())


def load_categories(path: Path) -> dict[str, list[str]]:
    """Invert {category: [keys]} into {key: [categories]}."""
    by_key: dict[str, set[str]] = {}
    for category, keys in json.loads(path.read_text(encoding="utf-8")).items():
        if category.startswith("_"):
            continue
        for key in keys:
            by_key.setdefault(key, set()).add(category)
    return {key: sorted(names) for key, names in by_key.items()}


def record_from(org: dict, categories: list[str], image_base: str, retrieved: str) -> dict:
    """Pick the public fields out of one organization. Never reads primaryContact."""
    social = org.get("socialMedia") or {}
    contact = org.get("contactInfo") or []
    links = {
        label: url for key, label in SOCIAL_KEYS.items() if (url := clean_url(social.get(key)))
    }
    picture = org.get("profilePicture")
    return {
        "slug": org["websiteKey"],
        "name": plain(org.get("name")),
        "short_name": plain(org.get("shortName")),
        "summary": to_text(org.get("summary")),
        "description": to_text(org.get("description")),
        "org_type": ((org.get("organizationType") or {}).get("name") or "").strip(),
        "categories": categories,
        "status": (org.get("status") or "").strip(),
        "contact_email": (org.get("email") or "").strip().lower(),
        "phone": ((contact[0].get("phoneNumber") if contact else "") or "").strip(),
        "location": location_of(contact),
        "website": clean_url(social.get("externalWebsite")),
        "links": links,
        "logo_url": f"{image_base}{picture}" if picture else "",
        "ramcentral_id": org.get("id"),
        "source_url": BASE_URL + org["websiteKey"],
        "source_modified": (org.get("modifiedOn") or "")[:10],
        "source": "farmingdale.campuslabs.com/engage (RamCentral)",
        "source_retrieved": retrieved,
    }


def fetch(key: str, cache: Path) -> str:
    """One organization page. Cached, so an interrupted run resumes politely."""
    cached = cache / f"{key}.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    request = urllib.request.Request(BASE_URL + key, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        page = response.read().decode("utf-8", errors="replace")
    cached.write_text(page, encoding="utf-8")
    time.sleep(CRAWL_DELAY_SECONDS)
    return page


def read_keys(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--cache",
        default=str(Path(tempfile.gettempdir()) / "ramhub_ramcentral_cache"),
        help="Where fetched pages are kept. Outside the repo on purpose: the raw "
        "pages contain student contact details that must not be committed.",
    )
    parser.add_argument("--out", default=str(OUT_FILE))
    args = parser.parse_args()

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    retrieved = date.today().isoformat()
    categories = load_categories(CATEGORIES_FILE)

    records, skipped = [], []
    for key in read_keys(KEYS_FILE):
        try:
            page = fetch(key, cache)
        except (urllib.error.URLError, TimeoutError) as exc:
            skipped.append(f"{key}: {exc}")
            continue
        match = STATE_RE.search(page)
        state = json.loads(match.group(1)) if match else {}
        org = (state.get("preFetchedData") or {}).get("organization")
        if not org:
            # Renamed, deleted, or switched to members-only since the key was captured.
            skipped.append(f"{key}: no public organization on the page")
            continue
        records.append(
            record_from(
                org, categories.get(key, []), state.get("imageServerBaseUrl") or "", retrieved
            )
        )

    records.sort(key=lambda r: r["name"].lower())
    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8"
    )
    print(f"organizations written: {len(records)}", file=sys.stderr)
    for line in skipped:
        print(f"skipped {line}", file=sys.stderr)


if __name__ == "__main__":
    main()
