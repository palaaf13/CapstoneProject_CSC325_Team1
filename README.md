# RamHub

A private, school-email-only community website for students of **Farmingdale State
College**. Look up any course or professor, read honest advice from students who
actually took it, and add your own.

**Team 1, CSC 325:** Axel, Cole, Nick, Sara, Sinan, Shil. The original project proposal is in [docs/PROPOSAL.md](docs/PROPOSAL.md).

Read [CLAUDE.md](CLAUDE.md) before contributing — it holds the architecture
decisions, MongoDB constraints, and conventions this project is built on.

---

## Architecture

RamHub is a **server-rendered, layered web application**. There is no separate
frontend: Django renders HTML, HTMX swaps fragments of it, and the browser never
holds application state. One deployment serves everything.

```
Browser
   │  HTML over HTTP, plus HTMX fragment requests
   ▼
URL routing            config/urls.py → apps/<app>/urls.py
   ▼
Presentation           templates/ · Tailwind tokens in static/src/input.css
   ▼
Views                  apps/<app>/views.py — parse the request, call a service,
                       render a template. No business logic lives here.
   ▼
Validation             apps/<app>/forms.py — every query string and form body
                       is validated before it reaches a query
   ▼
Services               apps/<app>/services.py — all business logic: search,
                       filtering, sorting, resolving relationships
   ▼
Models                 apps/<app>/models.py — documents, embedded summaries,
                       indexes, constraints
   ▼
MongoDB Atlas          via django-mongodb-backend
```

**The layering rule:** a view may call a service; a service may touch models; a
template only displays what it is handed. A query in a view or logic in a
template is a bug, not a shortcut.

### Applications

The project is split by domain rather than by technical role, so each feature
owns its models, views, services, and tests together.

| App | Responsibility | State |
| --- | --- | --- |
| `catalog` | Course and Professor, both directories, detail pages, data imports | Built |
| `accounts` | Custom user, FSC email verification, profiles | Planned |
| `ratings` | Course and professor ratings, summary recomputation | Planned |
| `community` | Posts, embedded comments, votes, tags, the feed | Planned |
| `campus` | Clubs, jobs, parking, facilities | Placeholder pages |
| `saved` | The filing cabinet: collections and saved items | Planned |
| `assistant` | Retrieval index and the Rambo assistant | Planned |
| `moderation` | Reports, moderator actions, the queue | Planned |

`config/` holds settings (split into `base`, `dev`, `prod`), the root URL
configuration, and the site-level pages.

### Data layer

MongoDB is a document store, so the model design is not relational:

- **Embedding over joins.** A course's rating summary lives inside the course
  document, because it is always read with it.
- **ObjectId arrays instead of many-to-many tables.** `Course.professor_ids` and
  `Professor.course_ids` hold each other's ids, resolved in a single query.
- **Denormalized summaries.** Averages are stored and recomputed on write, never
  aggregated live on a list page.

`CLAUDE.md` records the backend constraints that forced these choices, including
several that fail silently rather than erroring.

### Request styles

| Style | Returns | Used for |
| --- | --- | --- |
| Full page | A rendered template | Any normal navigation |
| HTMX partial | An HTML fragment | Live search, "Load more", inline updates |
| DRF endpoint under `/api/` | JSON | Reserved for voting, autocomplete, and the assistant |

Each feature picks one and stays consistent. Everything degrades without
JavaScript: the directories are plain GET forms, and the landing page is
complete with scripts blocked.

### Deployment

| Piece | Where it runs |
| --- | --- |
| Application | Vercel, as a single Python function on Fluid Compute |
| Static files | Collected at build time, served from Vercel's CDN |
| Database | MongoDB Atlas (free M0 replica set), shared by the team |
| CI | GitHub Actions: lint, Django checks, and the test suite on every push and PR |

Because the application runs serverless, there is no writable disk and no
long-running process. Migrations and data imports are run from a developer's
machine against Atlas, not on the server.

---

## Prototype

**Figma:** [RamHub Prototype](https://www.figma.com/design/YPd5HXGVtHgMErfYGxEDvd/RamHub-Prototype?node-id=0-1)
**Walkthrough video (1:50):** [RamHub — Figma UI/UX Prototype Walkthrough](https://www.youtube.com/watch?v=8xP8z4f6uhE)

The prototype follows our product goal: **a private, `@farmingdale.edu`-only
platform where FSC students look up courses and professors, read and share
honest advice from classmates, and find campus info in one place, so class
knowledge doesn't disappear when students graduate.**

### Personas

| Persona | Role | What they need |
| --- | --- | --- |
| **Maya Rios** (primary) | Transfer student | Does not know which professors to take, and has no classmates to ask |
| **Jordan Kim** (secondary) | Trained student moderator | Keeps content honest and safe |

### Context diagram

RamHub sits at the centre, surrounded by:

- **Actors:** Student, Moderator, Administrator, Advisor / prospective student
- **External systems:** FSC email and identity, AI language model service, Google
  Calendar API, cloud media storage, campus info sources and the LMS

### UI screens

Sign up · Check email · Home feed · Search results (CSC 325) · Professor page ·
Course advice thread · Filing cabinet · Clubs · Moderation queue

### UX flow

Maya's journey, clickable end to end in the Figma prototype:

```
Sign up → verify email → search CSC 325 → compare professors →
read the advice thread → save to the filing cabinet →
post her own tip after the semester
```

Each screen earns its place in that journey, and the two personas sit on either
side of the same goal: Maya puts knowledge in and takes it out, Jordan keeps it
trustworthy.

The design is built against the real system rather than ahead of it. The colours,
type scale, and components come from the design system in
`static/src/input.css`, which you can review at `/styleguide` on a running
instance.

---

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12+ | Built and tested on 3.13 |
| Node.js | 20+ | Only used to build the Tailwind CSS |
| MongoDB Atlas | any free cluster | A replica set — required for transactions |

**Versions are locked together.** `django-mongodb-backend` X.Y.* only works with
Django X.Y.*. We are on Django 6.1.1 + django-mongodb-backend 6.1.0. Upgrade
them in the same pull request or not at all.

---

## First-time setup

```bash
# 1. Python environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Node packages (Tailwind only)
npm install

# 3. Environment variables
cp .env.example .env              # then edit .env — see the table below

# 4. Build the stylesheet once
npm run tailwind:build

# 5. Create the collections Django needs
python manage.py migrate

# 6. Load real courses, faculty and clubs (runs the imports below)
python manage.py seed_demo
```

Everything is idempotent — run it as often as you like. `seed_demo` is a
convenience wrapper; you can run any import on its own:

| command | source | records |
|---|---|---|
| `import_catalog` | published [2025–26 course catalog](https://www.farmingdale.edu/course-offerings/catalog_2025_2026.html) | ~1,785 courses |
| `import_directory` | public [campus directory](https://www.farmingdale.edu/directory/) | ~913 teaching staff |
| `import_rmp` | [RateMyProfessors](https://www.ratemyprofessors.com/school/14046) export | ratings for ~517 of them |
| `import_clubs` | [RamCentral](https://farmingdale.campuslabs.com/engage/organizations), the college's club directory | ~107 student organizations |

The course, faculty and ratings exports live in `apps/catalog/seed_data/` and the
club export in `apps/campus/seed_data/`, each with a `.README.md` documenting
provenance and caveats. `scrape_catalog.py` regenerates the course export when a
new catalog year is published; `scrape_clubs.py` regenerates the club export,
which wants refreshing every semester because clubs re-register each term.

Rules the imports will not bend:

- **Courses are never rated by an import.** No course has a rating until a
  student leaves one.
- **Professor ratings come from RateMyProfessors for now**, by explicit decision.
  Every one is tagged `source="rmp"` and labelled as RMP data everywhere it is
  shown — do not strip that. A rating a student leaves on RamHub always wins:
  `import_rmp` never overwrites one. About 40% of faculty have no RMP match and
  correctly show no rating.
- **They never invent relationships.** A directory says who works here; a catalog
  says a course exists. Neither says who teaches what, so courses are not linked
  to professors. That needs real section/schedule data.
- **Clubs carry only what RamCentral shows the public.** No officers or members
  (RamCentral hides those behind a sign-in), and no meeting times (it does not
  publish any) — the club page says so and links to RamCentral instead of
  guessing. College offices listed there are skipped unless you pass
  `--include-offices`.
- **Two club filters are RamHub's grouping, not RamCentral's.** RamCentral has no
  technology category, so `apps/campus/seed_data/ramhub_categories.json` lists,
  by slug, the twelve computing, AI and engineering clubs that RamHub files
  under **Technology** — on top of whatever RamCentral gave them, never instead
  of it. **Other** is the filter for the clubs that are in no category at all,
  so that every club can be reached through one. Everything else about a club
  is RamCentral's data as published; this is the only place we add our own.
  The reasoning is in `apps/campus/seed_data/farmingdale_clubs.README.md`.

Use `--prune --yes` to drop records no longer in the exports.

### Database: local or Atlas

Either works — it is one line in `.env`. Local is faster to set up and works
offline; Atlas is what the team shares and what the assistant's vector search
will need later.

**Local (macOS, Homebrew):**

```bash
brew tap mongodb/brew && brew trust mongodb/brew
brew install mongodb-community
```

MongoDB only supports transactions on a replica set, and Atlas is always one, so
run local as a single-node replica set to keep behaviour identical. Add this to
`/opt/homebrew/etc/mongod.conf`:

```yaml
replication:
  replSetName: rs0
```

Then start it and initiate the set once:

```bash
brew services start mongodb-community
mongosh --eval "rs.initiate()"
```

`.env`:

```
MONGODB_URI=mongodb://127.0.0.1:27017/?replicaSet=rs0
MONGODB_NAME=ramhub
```

Handy: `brew services stop mongodb-community`, and `mongosh ramhub` for a shell.

### Environment variables

`.env` is gitignored. Never commit it, and never put a connection string in a
settings file.

| Variable | Required | What it is |
| --- | --- | --- |
| `SECRET_KEY` | prod | Django signing key. Dev falls back to an insecure default. |
| `DEBUG` | no | `True` locally, `False` everywhere else. |
| `ALLOWED_HOSTS` | prod | Comma-separated hostnames. |
| `MONGODB_URI` | **yes** | The full Atlas connection string. |
| `MONGODB_NAME` | no | Database name inside the cluster. Defaults to `ramhub`. |
| `COLLEGE_EMAIL_DOMAIN` | no | Domain allowed to register. Defaults to `farmingdale.edu`. |
| `EMAIL_HOST` | prod | SMTP server used to send confirmation emails. |
| `EMAIL_PORT` | no | SMTP port. Defaults to `587`. |
| `EMAIL_HOST_USER` | no | SMTP username, if required by the provider. |
| `EMAIL_HOST_PASSWORD` | no | SMTP password, if required by the provider. |
| `EMAIL_USE_TLS` | no | Whether SMTP uses TLS. Defaults to `True`. |
| `DEFAULT_FROM_EMAIL` | prod | Sender address authorized by the mail provider. |

In development, registration confirmation emails print in the `runserver`
terminal. Production uses SMTP and requires `EMAIL_HOST` and
`DEFAULT_FROM_EMAIL`; keep any SMTP credentials in the gitignored `.env`.

Generate a key for `.env` with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

**Atlas:**

1. In Atlas, create a free **M0** cluster.
2. **Database Access** → add a database user with a password.
3. **Network Access** → add your IP (or `0.0.0.0/0` while developing).
4. **Connect → Drivers → Python** → copy the connection string.
5. Paste it into `.env` as `MONGODB_URI`, replacing `<password>` with the real
   password. URL-encode any special characters in it.

```
MONGODB_URI=mongodb+srv://ramhub:REALPASSWORD@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
MONGODB_NAME=ramhub
```

The whole URI is passed straight through as the database `HOST`. Older
`django-mongodb-backend` tutorials call a `parse_uri()` helper — it no longer
exists in 6.1. Do not add it back.

---

## Running it

Two terminals:

```bash
# Terminal 1 — the site
source venv/bin/activate
python manage.py runserver
```

```bash
# Terminal 2 — rebuild CSS as you edit templates
npm run tailwind:watch
```

Then open <http://localhost:8000>. The front door is a cinematic landing page
(GSAP + ScrollTrigger + Lenis, vendored, loaded on that page only); the feed moved
to `/feed/`. The design system lives at
<http://localhost:8000/styleguide>.

If a class you added has no effect, the Tailwind watcher is not running.

---

## Checks

Both must pass before you open a pull request. CI runs them on every PR.

```bash
ruff check . && ruff format --check .
pytest
```

### Tests and the database

The tests run against a **real MongoDB**, in a separate database — pytest-django
creates and drops `test_<MONGODB_NAME>`, so your development data is never
touched. Your local MongoDB has to be running for `pytest` to work.

Any test that reads or writes needs `@pytest.mark.django_db`. That now includes
view tests for pages that only display things: the Courses and Professors pages
query on every request. The plain mark is enough — you do not need
`transaction=True` just because this is MongoDB. `conftest.py` explains why,
and what depends on MongoDB running as a replica set.

Useful extras:

```bash
python manage.py check          # Django system checks
ruff format .                   # apply formatting
python manage.py createsuperuser
```

---

## Test Plan Overview

Four categories of automated test, plus the manual checks that cover what we do
not yet automate. Everything runs with `pytest`, against a **real MongoDB** in a
throwaway `test_` database — never a mock and never your development data.

### 1. Unit tests — one function or model at a time

Scope: a single service function or model behaviour, with its data created
directly in the test.

| File | Cases | What it proves |
| --- | --- | --- |
| `apps/catalog/tests/test_services.py` | 29 | Search matches a code and a title, department filtering, every sort order, and both directions of the course↔professor link |
| `apps/catalog/tests/test_models.py` | 13 | ObjectId primary keys, embedded summaries, the unique constraint on course code, the Bayesian ranking score |

Example: a 5.0 rating from one student must not outrank a 4.9 from 226, so the
ranking function is tested directly rather than through a page.

### 2. Integration tests — a whole request, end to end

Scope: a real HTTP request through routing, the view, the service layer, the
database, and template rendering, using Django's test client.

| File | Cases | What it proves |
| --- | --- | --- |
| `apps/catalog/tests/test_views.py` | 21 | Both directories render, search narrows results, bad query strings degrade instead of erroring, unknown records return 404 |
| `tests/test_landing.py` | 22 | The landing page renders real counts, motion libraries load only there, the page works with JavaScript off |
| `tests/test_smoke.py` | 5 | Every page in the navigation returns 200 and the active tab is correct |
| `apps/catalog/tests/test_admin.py` | 4 | The admin renders for rated and unrated records |

These catch the failures unit tests cannot see: a template referencing a field
that no longer exists, or a URL that stopped resolving.

### 3. Data integrity tests — the imports

Scope: the commands that load official college data. This category exists
because the data describes **real people**, so the rules about it are enforced
by tests rather than by memory.

| File | Cases | What it proves |
| --- | --- | --- |
| `apps/catalog/tests/test_import_rmp.py` | 16 | Imported ratings are always tagged as RateMyProfessors data, student ratings are never overwritten, "no data" never renders as a zero |
| `apps/catalog/tests/test_import_directory.py` | 13 | Faculty import is idempotent, never writes ratings, never invents course assignments |
| `apps/catalog/tests/test_import_catalog.py` | 12 | Course import is idempotent, courses without a published credit value stay null |
| `apps/catalog/tests/test_seed_demo.py` | 5 | Running the full seed twice leaves identical data |

### 4. System and accessibility checks — currently manual

| Check | How | When |
| --- | --- | --- |
| Accessibility | axe (WCAG 2.1 A/AA) on each new page | Before a feature is called done |
| Responsive | Every screen at 375px and desktop | Before a feature is called done |
| Keyboard | Tab through the page; focus must always be visible | Before a feature is called done |
| Contrast | Ratios computed against the design tokens | When a colour token changes |

### Continuous integration

Every push and pull request runs `ruff check`, `ruff format --check`, Django's
system checks, and the full suite against MongoDB 8.0 started as a single-node
replica set. A dedicated step asserts that transactions are available, because a
standalone MongoDB would let the suite pass while silently weakening test
isolation.

### Known gaps

Stated plainly, because a test plan that claims full coverage is not useful:

- **No browser-level end-to-end tests.** Nothing drives a real browser, so the
  HTMX swaps and the landing page motion are verified by hand.
- **No load or performance testing.** Page timings have only been measured
  informally.
- **Accessibility is not automated.** axe is run manually; it should move into
  CI.
- **No tests for features not yet built** — accounts, ratings, the feed, and the
  assistant. Each should arrive with its own tests, per the definition of done.
- **Run the suite against a local MongoDB, not Atlas.** Pointing `.env` at the
  shared cluster makes every test a network round trip and slows the suite by
  roughly an order of magnitude.

---

## Layout

```
config/              settings/{base,dev,prod}.py, urls, views for site-level pages
  mongo_apps.py      MongoDB-compatible AppConfigs for Django's contrib apps
mongo_migrations/    regenerated admin/auth/contenttypes migrations (see its docstring)
  context_processors.py  builds the nav and marks the active tab
apps/                accounts, catalog, ratings, community, campus, saved,
                     assistant, moderation
apps/catalog/        Course + Professor, the two directories, and the detail
  services.py        pages. Query logic lives here, never in a view.
  forms.py           query-string validation for the directories
  seed_data/         demo_catalog.json — see its _meta block
apps/campus/         Club, the club directory at /clubs/ and the club pages.
  seed_data/         the RamCentral export, and the scraper that regenerates it

templates/           base.html, partials/, one directory per app
static/src/          input.css — every design token lives here
static/css/          built output (gitignored)
static/vendor/       htmx
tests/               project-level tests; per-app tests live in apps/*/tests/
```

Per CLAUDE.md, each app grows `views.py`, `urls.py`, `forms.py`,
`serializers.py`, `services.py`, `admin.py`, and `tests/` as it needs them.
Business logic goes in `services.py`, never in a view or a template.

---

## The design system

All tokens are defined in [`static/src/input.css`](static/src/input.css) and
rendered on `/styleguide`. **Never hardcode a color, size, or radius in a
template** — the default Tailwind color and type scales are deliberately cleared,
so if a utility does not exist, add the token first.

Shared patterns: `.btn-primary` `.btn-secondary` `.btn-ghost` `.btn-danger`,
`.field-input` `.field-input-error` `.field-label` `.field-hint` `.field-error`,
`.card` `.card-pad` `.row-link`, `.badge-neutral` `.badge-accent` `.badge-danger`,
`.rating-value`. The Clubs tab adds `.club-card`, `.club-mark` and the
`.club-filter-*` category filter.

Reusable partials: `partials/page_header.html`, `partials/empty_state.html`,
and the icon set in `partials/icons/`.

---

## HTMX

htmx 2.0.10 is vendored at `static/vendor/htmx.min.js`. `base.html` sets
`hx-headers` with Django's CSRF token on `<body>`, so POSTs work without any
per-form wiring.

An HTMX endpoint returns an **HTML fragment**, not JSON — see
`config.views.styleguide_htmx_demo` and `partials/htmx_demo_result.html` for the
pattern. JSON belongs in a DRF endpoint under `/api/`. Pick one per feature.
