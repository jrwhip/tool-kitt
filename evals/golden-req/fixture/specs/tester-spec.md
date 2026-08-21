# Tester Spec - WOPR Golden Fixture

> **Target stack:** Python 3.11 + FastAPI
> **Test framework:** pytest + `fastapi.testclient.TestClient` (backed by `httpx`)
> **Coverage tool:** `pytest-cov` (coverage.py under the hood)

---

## Requirements Sources

| Document | Path | What it tells the tester |
|---|---|---|
| Implementation tracking | `implementation-tracking.md` | Which REQs need coverage. Carries the pinned `spec_version` and `generator_version`. |
| Requirements source | `requirements/REQ-*.md` | Acceptance criteria for each REQ. |
| Coder spec | `specs/coder-spec.md` | What the production code looks like, and the coverage gate definition (section 22). |
| OpenAPI spec | `/openapi.json` (served at runtime) | Source of truth for endpoint shapes and status codes. |

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Run unit tests only | Not applicable to this fixture: all tests are unit-level HTTP tests through `TestClient`, no split exists. |
| Run component or integration tests only | Not applicable to this fixture: same reason as above. |
| Run the full suite | `uv run pytest` |
| Run tests for a single file | `uv run pytest tests/test_echo.py` |
| Generate coverage report | `uv run pytest --cov=app --cov-branch --cov-report=term-missing` |
| View coverage report | Terminal output from the command above; no HTML report configured for this fixture. |

---

## Coverage Configuration

- **Tool:** pytest-cov (coverage.py)
- **Targets:** line coverage ≥ 90%, branch coverage ≥ 80%, no per-package excludes (the whole `app/` package is in scope; it is one module).
- **Scope:** `app/` only. `tests/` itself is not measured for coverage.
- **CI enforcement:** not applicable to this fixture: no CI is configured. The tester agent enforces the floor locally on every run.

---

## Generated Types and Spec-Driven Fixtures

Not applicable to this fixture: there is no generated client (backend-only
project, no consuming frontend). Tests construct request query strings and
assert on raw JSON response bodies directly; there are no generated model
types to import.

---

## Directory Structure

```
tests/
├── __init__.py
├── test_health.py     # tests for GET /health
└── test_echo.py       # tests for GET /echo (added under REQ-GOLD-1)
```

Rules:

- One test file per route module, named `test_<route-name>.py`.
- All tests are flat in `tests/`; no `unit/` vs `component/` split for a
  project this size. Every test in `tests/` uses `TestClient` and exercises
  the full request-to-response path, which is effectively the fixture's
  only meaningful test shape.

---

## 1. Shared Test Configuration

Not applicable to this fixture: no shared fixture module, no test-only
bean registry. Each test file constructs its own `TestClient(app)` at
module scope; that is enough for a project this small.

---

## 2. Test Properties and Fixtures

Not applicable to this fixture: no config files, no test database, no
mock auth. The app has no configuration surface.

---

## 3. Unit Test Pattern

Not applicable to this fixture: there is no isolated-unit layer beneath
the route handlers to test in isolation (no service or repository
classes to mock). All tests exercise routes through `TestClient`, which
plays the role both of "unit test for the handler" and "component test
for the HTTP path" at this project's size. See section 4 for the pattern
actually used.

---

## 4. Component / Integration Test Pattern

**Universal rules apply as written**, adapted below.

**Stack-specific:**

- **HTTP test client:** `fastapi.testclient.TestClient`, instantiated
  once per test module as `client = TestClient(app)`.
- **Test slicing:** not applicable; the full `app` object from
  `app.main` is used directly, no slicing annotation exists in FastAPI.
- **Seeding test data:** not applicable; no persistence layer.
- **Teardown between tests:** not applicable; the app is stateless, no
  teardown is required.

**Required coverage per endpoint:**

| HTTP status | Required? | Notes |
|---|---|---|
| 2xx success | Always | `200` for both `/health` and `/echo` |
| 4xx client error | Always for `/echo` | `422` for missing/invalid `msg`; FastAPI's default validation response, not a custom error body |
| 5xx server error | Not applicable to this fixture | No handler in this project has a plausible 5xx path; nothing to mock a failure into |

---

## 5. Time Zone Test Anchoring

Not applicable to this fixture: no datetime handling exists.

---

## 6. Coverage Standards

- **Line coverage floor:** 90%
- **Branch coverage floor:** 80%
- **Excluded classes or files:** none; `app/` is small enough that nothing
  is excluded.
- **Generated code exclusion:** not applicable to this fixture; there is
  no generated code.

### Coverage gate (contract with the coder and auditor)

Same five-condition contract as coder spec section 22. On every tester-agent
run:

1. Run `uv run pytest --cov=app --cov-branch --cov-report=term-missing`
   after writing tests; confirm line ≥ 90% and branch ≥ 80%.
2. Record the measured coverage in `implementation-tracking.md`'s
   `coverage_status` field for the current REQ's log entry. Format:
   `line XX% / branch YY% / gate: PASS` or
   `line XX% / branch YY% / gate: FAIL (reason)`.
3. Do not mark a REQ's tests complete until coverage meets the floor. If
   short, either add tests to close the gap or record the concrete gap
   (e.g., "REQ-GOLD-1 missing: 200-boundary test at msg length 200").

The auditor cross-checks the tracking document's `coverage_status` against
a fresh coverage run. Drift is a BLOCKER finding.

---

## 7. Static-Analysis Quality Gate

Condition 5 of the coverage gate (coder spec section 22) is satisfied for
this fixture by `ruff`, not a hosted SonarCloud/SonarQube platform.

**This stack:**

- **Platform:** ruff (local static analysis only).
- **Project key:** not applicable.
- **Local scan command:** `uv run ruff check .`
- **CI scan workflow:** not applicable to this fixture: no CI configured.
- **Quality Gate fetch:** the tester runs the command above directly; exit
  code 0 and empty output means `PASS`, any finding means `FAIL`.
- **Severity thresholds for this gate:** every ruff finding fails the
  gate; there is no severity tiering configured (`--select`/`--ignore` are
  left at ruff defaults per `[tool.ruff]` in `pyproject.toml`).
- **Required token environment variables:** none; ruff runs locally with
  no auth.

**What the tester does:**

1. After the test suite passes and coverage floors are met, run
   `uv run ruff check .`.
2. Record the result in `coverage_status` using the format
   `line XX% / branch YY% / ruff: PASS|FAIL (reason) / gate: PASS|FAIL`.
3. If ruff fails, treat it the same as a coverage-floor failure: REQ stays
   `🔄`, gap described concretely, coder addresses it before re-entry.

---

## 8. Test Naming Convention

**Stack-specific:**

- Naming template: `test_<behavior_under_test>` in `snake_case`,
  describing the expected outcome and condition, not the function called.
- Required prefix: `test_` (pytest discovery default). File names:
  `test_<route_name>.py`.

**Examples for this stack:**

| Under test | Condition | Test method name |
|---|---|---|
| `GET /echo` | valid `msg` | `test_echo_returns_200_with_echo_and_length` |
| `GET /echo` | `msg` missing | `test_echo_missing_msg_returns_422` |
| `GET /echo` | `msg` empty string | `test_echo_empty_msg_returns_422` |
| `GET /echo` | `msg` length 201 | `test_echo_msg_over_max_length_returns_422` |
| `GET /echo` | `msg` length 1 | `test_echo_msg_min_length_returns_200` |
| `GET /echo` | `msg` length 200 | `test_echo_msg_max_length_returns_200` |

---

## Key Files

- `tests/test_health.py` - existing baseline test; must stay green.
- `tests/test_echo.py` - added under REQ-GOLD-1; covers acceptance
  criteria 1 through 6.
- No shared fixture or factory class exists yet; add one only if a future
  REQ needs shared setup across more than two test files.
