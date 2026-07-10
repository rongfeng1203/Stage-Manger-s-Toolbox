# Testing

No function is complete until its test passes.

Day 1 verification commands:

```bash
.venv/bin/pytest backend/tests
.venv/bin/pytest backend/tests/services/availability
.venv/bin/pytest backend/tests/services/cast
.venv/bin/mypy backend/app
.venv/bin/ruff check backend
cd frontend
npm run test
npm run lint
npm run build
npm run e2e
```

Bug fixes require a regression test before the fix is considered complete.

Day 2 added direct unit tests for every public and private time-window function,
plus Hypothesis property tests for slot alignment and busy-window subtraction.

Day 3 added direct unit tests for cast requirement resolution, actor doubling,
optional scene characters, duplicate cast assignment policy, missing cast
warnings, unknown character warnings, and private validation helpers.
