# Stage Scheduler

Deterministic rehearsal scheduling system for stage managers.

The application must function without an LLM. AI may parse input later, but the
scheduler receives structured data and produces reproducible results.

## Day 1 Foundation

Current scope:

- React + TypeScript + Vite frontend.
- Python + FastAPI backend package.
- SQLite configured through SQLModel.
- Core production, scene, character, actor, availability, cast, and session models.
- Pure Python time and availability utilities.
- Pure Python cast requirement resolver.
- Pytest, Vitest, Playwright, Ruff, mypy, ESLint, and Prettier configured.

## Backend Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

## Frontend Setup

```bash
cd frontend
npm install
```

## Test And Quality Commands

Run from the repository root:

```bash
.venv/bin/pytest backend/tests
.venv/bin/pytest backend/tests/services/availability
.venv/bin/pytest backend/tests/services/cast
.venv/bin/mypy backend/app
.venv/bin/ruff check backend
```

Run from `frontend/`:

```bash
npm run test
npm run lint
npm run build
npm run e2e
```

## Development Order

1. Time and availability functions.
2. Cast requirement resolution.
3. Conflict detection.
4. Hard-constraint solver.
5. Scoring algorithm.
6. Three schedule modes.

Do not begin calendar publishing, LLM parsing, or blocking-system work before the
deterministic scheduler is reliable.
