# Tester Spec - TODO: project name

> **Stack:** Python 3.12+, pytest, httpx, pytest-asyncio, coverage.py, uv.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** `catalog/crew/templates/by-stack/_generic/tester-spec.md`.

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Run tests | `uv run pytest` |
| Run with coverage | `uv run pytest --cov=src --cov-report=term-missing --cov-report=xml` |
| Run a single test file | `uv run pytest tests/test_foo.py` |
| Run a single test | `uv run pytest tests/test_foo.py::test_bar` |

---

## Test File Layout

| Type | Location | Naming |
|---|---|---|
| Unit test | `tests/` | `test_<module>.py` |
| Integration test (uses real DB) | `tests/integration/` | `test_<feature>.py` |
| API test (uses TestClient) | `tests/api/` | `test_<route>.py` |

`pytest` discovers `test_*.py` files and `test_*` functions. Class-based grouping (`TestFoo` with `def test_bar(self)` methods) is acceptable for related tests.

---

## What to Test

Every service function:
- Happy path
- Validation failure
- Empty / null input
- Business-rule edge cases

Every router endpoint (via httpx `AsyncClient`):
- 200 / 201 success
- 4xx validation, not-found, conflict
- 5xx unexpected error (when applicable)
- Authentication: missing token, invalid token, expired token, wrong role

Every Pydantic schema:
- Valid input round-trips
- Invalid input raises `ValidationError` with the expected error path

---

## Fixtures and Mocks

### Use the project's own schemas
Test fixtures import Pydantic models from the project:
```python
from <package>.schemas import CaseResponse
fixture = CaseResponse(id=1, status="open", ...)
```
Never declare shape-only copies in test files.

### Database fixtures
- `@pytest.fixture` providing an `AsyncSession` over a fresh test database (SQLite in-memory or Testcontainers Postgres).
- One fixture per test, rolled back after.

### HTTP fixtures
- `httpx.AsyncClient(app=app, base_url="http://testserver")` for in-process testing without a network listener.

### Coverage exclusions
- `tests/` (the tests themselves)
- `<package>/migrations/` (Alembic auto-generated)
- Any generated client code

The exclusion list lives in `pyproject.toml` under `[tool.coverage.run] omit = [...]`.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- Sync test functions for async code paths. Async routes need `@pytest.mark.asyncio` (or `asyncio_mode = "auto"` in `pytest.ini`/`pyproject.toml`).
- `requests.get(...)` against the running app. Use `httpx.AsyncClient(app=...)`.
- Tests that hit a real external service. Mock at the HTTP boundary (`respx`) or use a fake.
- Tests that depend on system time. Use `freezegun` or inject a clock.
- `assert x == y` without a helpful message when the failure mode is non-obvious.
- Importing `<package>.main.app` at module scope. Use a fixture; module-scope app construction makes tests order-dependent.

---

## Coverage Gate

After tests pass, record on the REQ's implementation-tracking log entry:

```
coverage_status: line XX% / branch YY% / static_analysis: PASS / gate: PASS
```

PASS means:
- `uv run pytest --cov` exits 0.
- Zero new failures.
- Line >= `[TODO: floor]`, branch >= `[TODO: floor]`.
- Quality Gate is `Passed` for the relevant commit.

---

## Spec Maintenance

When `spec_writes` is ON, amend this spec when a new fixture, coverage rule, or test idiom emerges.
