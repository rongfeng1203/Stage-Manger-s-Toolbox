# Architecture

## Runtime Flow

```text
SCRIPT OR MANUAL INPUT
        |
        V
REVIEWED SCENES + CHARACTERS
        |
        V
CAST + AVAILABILITY + TARGETS
        |
        V
RANKED SCHEDULE OPTIONS
        |
        V
PYTHON CONFLICT VALIDATION
        |
        V
EXPLICIT APPROVAL
        |
        V
CALENDAR PREVIEW + PUBLISH REPORT
```

## Boundaries

- `frontend/src/App.tsx` owns the current in-browser production workflow and
  release demo state.
- `frontend/src/api.ts` is the only browser HTTP boundary.
- `backend/app/api/` converts JSON payloads to service inputs and serializes results.
- `backend/app/services/` contains framework-independent business logic.
- `backend/app/models/` contains SQLModel persistence entities.
- `backend/tests/fixtures/` contains named adversarial scheduling productions.

The scheduler, conflict engine, parser, scoring functions, and calendar publisher
interfaces do not depend on FastAPI. Manual schedule edits never reproduce
conflict rules in React; the frontend displays the result from
`POST /api/schedules/validate`.

## API Surface

- `GET /health`
- `POST /api/scripts/analyze`
- `POST /api/scripts/upload`
- `POST /api/schedules/validate`
- `GET /api/calendar/status`
- `POST /api/calendar/preview`
- `POST /api/calendar/publish`

## Calendar Providers

`CalendarPublisher` defines the publication contract. `FakeCalendarPublisher`
supports deterministic tests and the local demo. `GoogleCalendarPublisher`
creates the same event payloads through an injected transport, keeping Google
network calls out of unit tests.

## Script File Extraction

`extract_script_text()` accepts UTF-8 or Windows-1252 text files with `.txt`,
`.text`, `.script`, `.fountain`, or `.md` extensions. PDFs are extracted with
PyPDF before entering the same deterministic parser. Uploads are limited to 10 MB.
Headerless screenplay transcripts use explicit `NAME:` cues and infer scene
boundaries from transitions such as `Cut to`, `Dissolve`, and camera transitions.
Inferred boundaries are always returned with an `INFERRED_SCENES` warning and
remain editable before import.
