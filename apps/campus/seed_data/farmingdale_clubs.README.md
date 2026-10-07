# Farmingdale State College — Club Export

**File:** `farmingdale_clubs.ndjson`
**Records:** 119 (one JSON object per line, UTF-8)
**Source:** https://farmingdale.campuslabs.com/engage/organizations — "RamCentral"
**Retrieved:** 2026-10-06

## Why RamCentral and not farmingdale.edu

The college's own page, [Getting Involved](https://www.farmingdale.edu/student-activities/gettinginvolved.shtml),
lists clubs by name only — 62 of them — and was a year out of date when this was
pulled ("current as of October 3rd … active through the Fall 2025"). It says so
itself: *"For an up-to-date listing, please check RamCentral."*

RamCentral is that listing. It is the college's student-engagement platform
(hosted by Campus Labs / Anthology), `farmingdale.edu/ramcentral` redirects to
it, and it is where clubs register each semester. Its directory is public: no
sign-in is needed to see any field exported here.

## How it was collected

`scrape_clubs.py`, beside this file, regenerates the export. Read its docstring
before a refresh. The short version:

- RamCentral's `robots.txt` **disallows `/engage/api/`** and allows the
  organization pages. The script only ever requests
  `/engage/organization/<key>`, one page per organization, three seconds apart,
  and reads the record embedded in that page's HTML.
- Because the API is off limits, two things could not be scripted and were
  captured by hand from the public directory page in a browser:
  `ramcentral_keys.txt` (which organizations exist) and
  `ramcentral_categories.json` (which category each one is filed under).
  The script's docstring has the console snippet to refresh both.
- A third file here, `ramhub_categories.json`, is **not** from RamCentral. It
  is RamHub's own grouping and has its own section below.

## Fields

| field | type | notes |
|---|---|---|
| `slug` | string | RamCentral's own key for the organization. Unique. Stable across renames, which is why it is the import's natural key and the club's URL. |
| `name` | string | As printed on RamCentral. |
| `short_name` | string | Abbreviation, e.g. `SGA`. Blank for 22. Sometimes just repeats the name. |
| `summary` | string | RamCentral's one-paragraph blurb, 254 characters at most. A required field upstream, so a few hold placeholders — see below. |
| `description` | string | The organization's own "About" text, converted from rich text to plain text. Paragraph breaks kept; list items start with `- `. Blank for 4. |
| `org_type` | string | RamCentral's organization type, verbatim. 9 values. |
| `categories` | string[] | RamCentral's categories for the organization. 12 values; an organization can have several, and 34 have none. |
| `status` | string | `Active` for all 119. |
| `contact_email` | string | The organization's contact email, as printed on its page. Blank for 32. |
| `phone` | string | Blank for 85. |
| `location` | string | The address lines on the page, joined. Blank for 77. Free text. |
| `website` | string | The organization's "external website". Often a GroupMe or Linktree link rather than a site. Blank for 77. |
| `links` | object | Social links, keyed `instagram` / `facebook` / `linkedin` / `youtube` / `twitter`. 94 organizations have an Instagram. |
| `logo_url` | string | The organization's profile picture on RamCentral's image server. **Stored, never displayed** — see below. |
| `ramcentral_id` | int | RamCentral's numeric id. |
| `source_url` | string | The organization's public RamCentral page. |
| `source_modified` | string | Date the organization last edited its RamCentral record. |
| `source` / `source_retrieved` | string | Provenance. |

## What is deliberately not here

- **Officers and members.** RamCentral's page data includes a `primaryContact`
  — a named student and their campus email. The public page hides that behind
  "Sign in to view officers", so the scraper never reads it, and a test
  (`test_the_export_carries_no_officers` in `tests/test_club_export.py`) fails
  if any unexpected field turns up in this file. The raw pages are cached
  outside the repository for the same reason.
- **Meeting times.** RamCentral has no field for a regular meeting time, only
  dated events, which would be stale within a week. Nothing is exported and the
  club page says so rather than guessing.
- **Events, news, documents, and galleries.** Out of scope.

## What `import_clubs` does with it

- **Skips 12 records that are not clubs** — the types `Offices / Departments`
  (10, e.g. Residence Life, Student Travel Office) and `Branch` (2). Pass
  `--include-offices` to load them. This follows RamCentral's own type, so RAM
  Motorsports, which RamCentral files as an office, is skipped too. That leaves
  **107 clubs**.
- **Folds some organization types into the categories**, so the directory's
  filter is complete. RamCentral types 14 organizations `Club Sports` but gives
  only 8 the category; the four fraternities and four sororities have Greek
  types and no category at all. See `TYPE_CATEGORY` in the command. After that,
  22 clubs still have no category.
- **Adds RamHub's own "Technology" category to 12 clubs** — see the next section.
  That leaves 18 clubs in no category, which the directory lists under "Other".
- **Stores placeholder text as blank.** Eight summaries are `PLEASE FILL THIS
  OUT`, `xxx`, `N/A`, `.`, `...`, or a `**New for Fall 2026**` marker. They are
  left exactly as published in this file and blanked on import, so a card shows
  the start of the club's description instead. Two clubs (Bowling Club,
  ColorStack at FSC) have nothing else and show no blurb at all.

## RamHub's own grouping: "Technology" and "Other"

Everything above is RamCentral's data, imported as published. **This section is
the one exception: it is RamHub's grouping, not RamCentral's and not the
college's.**

- **`ramhub_categories.json`** maps a club's slug to categories RamHub adds on
  top of RamCentral's. Today it holds one category, **Technology**, for the
  computing, AI, robotics and engineering-technology clubs: the Artificial
  Intelligence Club, ColorStack at FSC, the Cybersecurity Club, GDG on Campus,
  the IEEE Student Branch, Rambots, Supporting Women in Computing, ASME, ASCE,
  Architecture Construction Technology, NSBE and SHPE.
- **Why it exists.** RamCentral has no technology category. Those twelve clubs
  were spread across Academic, Pre-Professional, Social Awareness and Special
  Interest, and four of them — the AI club among them — were in no category at
  all, so no filter led to them.
- **How each club was chosen.** From the club's own name or description on
  RamCentral. The one judgment call is ColorStack at FSC, which published no
  description (`xxx`); it is included because ColorStack is a national
  community for computer science students. Aviation clubs are not included.
- **It only ever adds.** A club keeps every category RamCentral gave it. The
  file never removes or renames one, and a test fails if "Technology" ever
  becomes a RamCentral category too, because then nobody could tell which
  clubs the college filed there and which ones we did.
- **"Other" is not a category.** It is the directory's filter for the 18 clubs
  that still sit in no category — RamCentral's or ours. Nothing is stored on
  those clubs; `services.OTHER` just selects the ones with an empty list. It is
  there so that every club is reachable through some filter.
- **To change it,** edit `ramhub_categories.json` and re-run
  `manage.py import_clubs`. Keep it small. A test fails if a slug in it is not
  a club in the export, so a refresh cannot leave a dead entry behind.

## Notes for the downstream agent

- **This is the organization's own text.** Summaries and descriptions are
  written by students, are not proofread, and a few name their officers in
  the About text. They are reproduced as published, and escaped on output.
- **Some categories are wrong upstream and are reproduced as-is.** Badminton
  Club is listed under Performing Arts (its record was reused from a dance
  group — hence the slug `farmingdale-xpressions`), Bowling Club's slug is
  `wrestling-club`, and Flag Football is filed under Academic. Fix these on
  RamCentral, not here: a local correction is overwritten by the next import.
- **Some short names are stale upstream.** A record that gets renamed keeps its
  old short name: the Artificial Intelligence Club's is still `cs`, and the
  RamChella Committee's is `Concert`. The export keeps them as published and
  search still matches them, but `Club.abbreviation` does not display a short
  name that starts with a different letter than the club's name (Greek-letter
  organizations excepted), so the AI club's tile reads AIC rather than CS.
- **One contact email is mistyped upstream** (`…@farmingdale.edi`). It is kept
  as published rather than "corrected" by guessing.
- **34 contact emails are Gmail addresses and 52 are `farmingdale.edu`**, some
  of which look like an individual's mailbox rather than a shared one. Each is
  the address the club chose to print on its public page.
- **Logos are not displayed.** Several contain the college's own marks, and
  CLAUDE.md says to ask before using one. The URL is kept so that turning them
  on later is a template change, not a re-scrape.
- **Refresh once a semester.** Clubs re-register every term, so this goes stale
  faster than the catalog or the directory. Match on `slug`.
- **Terms of use.** Public pages, read at a crawl delay and in line with
  `robots.txt`, for a student project. Do not redistribute commercially.
