# Stage Scheduler

Demo-ready MVP for deterministic theatre rehearsal scheduling. The application
works without an LLM: scripts become reviewable structured data, schedule edits
are validated by Python, and calendar publication always requires explicit stage
manager approval.

## Release Candidate Scope

- React + TypeScript production, cast, scene, availability, schedule, and publish UI.
- FastAPI validation, deterministic script analysis, and calendar APIs.
- Pure Python availability, cast requirement, conflict, scoring, and CP-SAT services.
- Efficient, balanced, and scene-priority solver modes from one weighted solver.
- Editable script analysis followed by explicit import confirmation.
- Automatic TXT, SCRIPT, Fountain, Markdown, and text-based PDF upload analysis.
- Manual session move, duration, delete, and add operations revalidated by Python.
- Calendar event preview, approval gate, fake publisher, and Google publisher interface.
- Google OAuth callback, refresh-token storage, and free/busy availability import.
- Blocking notebook with ordered beats, stage positions, movements, cues, and Python validation.
- One-click complete demo production.
- Pytest, Hypothesis, Vitest, Playwright, mypy, Ruff, ESLint, and Prettier coverage.

## Run Locally

Install once from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
cd frontend && npm install
```

Run the API:

```bash
.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend in a second terminal:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. Vite proxies `/api` to FastAPI on port 8000.

### Google Calendar availability

The local OAuth client reads credentials from
`~/.config/stage-scheduler/google-oauth.json` and stores the authorized refresh
token in `~/.config/stage-scheduler/google-token.json`. Both files stay outside
the repository and are written with owner-only permissions.

The configured redirect URI is:

```text
http://localhost:8000/api/calendar/oauth/callback
```

Start both servers, add actor email addresses, connect Google from the
Availability section, and select `[ MATCH WITH GOOGLE AVAILABILITY ]`. The
connected account must be allowed to view each actor calendar's free/busy data.
Calendars that are not shared are reported and do not overwrite manual windows.

Optional environment overrides are `GOOGLE_OAUTH_CONFIG`,
`GOOGLE_OAUTH_TOKEN_FILE`, `GOOGLE_REDIRECT_URI`, and
`GOOGLE_OAUTH_SUCCESS_REDIRECT`.

### Actor spreadsheets and matching

In **Actor Windows**, download the CSV template (opens in Excel), fill it in,
and upload `.xlsx` or UTF-8 `.csv`. Add the actors to the cast first. Each sheet
needs `actor` (exact name), `email`, or `actor_id`, plus `start` and `end`.
Names/emails ignore case and surrounding spaces; ambiguous names need an email
or ID. If multiple identifiers are supplied, they must agree.

Use ISO datetimes (`2026-11-02T18:00`), or a `date` column (`2026-11-02`) with
start/end times (`18:00`). Native Excel date/time cells work too. Optional `type`
is `AVAILABLE` (default), `PREFERRED`, or `BUSY`. Times use the browser timezone.
Formula cells and ambiguous DST times are rejected. Old `.xls` files must be
saved as `.xlsx`. Limits: 5 MB upload, 25 MB expanded workbook, 10,000 windows.
Every nonempty sheet must follow this format; arbitrary weekly grid layouts
are not supported.

Review the matched rows, then choose **Add imported windows**. Invalid rows
reject the whole file with sheet/row errors. Repeated identical windows are
not added twice. Existing windows are kept, so import spreadsheets **before**
matching Google. Use available rows to define rehearsal hours and busy rows to
exclude commitments. Busy-only actors need Google free time or manual available
windows before they can be scheduled.

Google matching is enabled by default: it narrows existing availability to
Google free time, preserves busy exclusions, and leaves inaccessible actors
unchanged. With no existing positive availability, it starts from Google free
time within production hours. Uncheck matching to explicitly replace windows.
Imports are snapshots, not continuous sync; repeated matching can only narrow
existing positive windows. To restore removed availability, explicitly replace
with Google data and reimport the actor sheet, then match again. An actor with
no overlap receives a busy block over the import range to preserve that result.
Imports clear generated schedules and calendar approval; regenerate to find
shared rehearsal windows for each scene's required actors.

## Deploy To Vercel

The root `app.py` entrypoint serves the built Vite frontend and the FastAPI API
from one deployment. The Vercel build command is configured in `pyproject.toml`.

Set these encrypted environment variables for a single connected stage-manager
calendar before deploying:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI=https://YOUR_PROJECT.vercel.app/api/calendar/oauth/callback
GOOGLE_OAUTH_SUCCESS_REDIRECT=https://YOUR_PROJECT.vercel.app/#availability
GOOGLE_OAUTH_REFRESH_TOKEN
```

`GOOGLE_OAUTH_REFRESH_TOKEN` avoids relying on Vercel's temporary function
filesystem. Mark the client secret and refresh token as sensitive. The deployed
app can then refresh access tokens in memory without writing credentials into
the repository or deployment image.

Deploy from the repository root:

```bash
npm --prefix frontend run build -- --outDir ../public
vercel
vercel --prod
```

The local frontend build must run before `vercel` so the Python function bundle
contains the hashed files referenced by `public/index.html`.

## Demo Flow

1. Select `[ LOAD DEMO PRODUCTION ]`.
2. Upload a script file or analyze the included text, then review detected records.
3. Generate the three schedules and review the balanced plan.
4. Move a rehearsal outside availability to show Python conflict detection, then restore it.
5. Preview calendar events, approve the selected schedule, and publish through the demo publisher.
6. Create a blocking beat, place and move an actor, add a cue, and validate the notebook.

The demo publisher makes no external calls. The configured Google scope is
read-only free/busy access; Google event publishing requires a separate
`calendar.events` authorization and verification review. See
[Known Limitations](docs/KNOWN_LIMITATIONS.md).

## Release Checks

```bash
.venv/bin/pytest backend/tests
.venv/bin/mypy backend/app
.venv/bin/ruff check backend
cd frontend
npm run test
npm run lint
npm run build
npm run format
npm run e2e
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Scheduling and scoring](docs/ALGORITHM.md)
- [Test strategy](docs/TESTING.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
