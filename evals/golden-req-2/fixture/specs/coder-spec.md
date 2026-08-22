# Coder Spec - WOPR Golden Fixture

> **Target stack:** Python 3.11 + FastAPI + uvicorn, managed with uv
> **Legacy stack:** none; greenfield fixture
> **Project:** wopr-golden-fixture. A deterministic, minimal FastAPI app used as the WOPR crew skill's golden-REQ evaluation fixture. Not a product codebase.

---

## Pattern Reference Projects

Not applicable to this fixture: the project is intentionally too small to warrant an external calibration reference. `app/main.py` is the only pattern the coder needs to match.

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Compile or type-check | `uv run python -c "import app.main"` (no separate type-check step configured) |
| Run unit tests | `uv run pytest` |
| Run component or integration tests | Not applicable to this fixture: unit and component tests are not split; all tests live in `tests/` and run through `pytest`. |
| Run the full test suite | `uv run pytest` |
| Lint or format | `uv run ruff check .` |
| Build a deployable artifact | Not applicable to this fixture: the fixture is never deployed. `uv run uvicorn app.main:app` runs it locally if needed. |

---

## Package and Directory Structure

```
app/
├── __init__.py
└── main.py          # FastAPI app instance and all route handlers
tests/
├── __init__.py
└── test_*.py         # one test file per route module, see tester spec
requirements/
└── REQ-*.md           # one REQ per file, the requirements source for this project
specs/
├── coder-spec.md
└── tester-spec.md
```

Route handlers live directly in `app/main.py` as plain functions decorated
with `@app.get(...)` / `@app.post(...)` etc. If `app/main.py` grows past a
handful of routes, split by resource into `app/routes/<resource>.py` and
include each router with `app.include_router(...)`. No service layer, no
repository layer, no ORM: this fixture has no persistence and is not meant
to grow one.

---

## Migration Context

No structural changes this session; implement REQs as written. This is a
greenfield fixture, not a migration.

---

## 1. Exception Handling

**This stack:**

- Use FastAPI's built-in request validation (Pydantic-backed query/path/body
  parameter typing). Do not write custom exception handlers for validation
  failures; FastAPI's default `422` response is the required behavior for
  this fixture.
- Domain-level exceptions and centralized exception mapping: not applicable
  to this fixture. There is no domain logic complex enough to raise
  domain-specific exceptions.

---

## 2. Authentication and Authorization

Not applicable to this fixture: no endpoint requires an authenticated
principal. All routes are public.

---

## 3. Logging Convention

Not applicable to this fixture: no logging is configured. `print` and
similar are still forbidden in `app/` if the crew adds any; use the
standard library `logging` module at INFO level for anything genuinely
needed, but do not add logging as a REQ side effect unless the REQ asks
for it.

---

## 4. API Spec and Client Generation

### 4a. Backend: spec production

- **Spec generation tool and version:** FastAPI itself generates the
  OpenAPI document from route decorators and type-annotated parameters;
  there is no separate annotation library (no springdoc equivalent). Pinned
  version: `fastapi 0.141.1` (see `wopr.yml` `openapi.pinned_generator_version`).
- **Annotation syntax:** plain FastAPI path-operation decorators plus
  standard Python type hints and `Query(...)` / `Path(...)` / Pydantic
  models for request and response shapes. No extra annotation layer.
- **Where served at runtime:** `/openapi.json` (interactive docs at
  `/docs`).
- Every endpoint should have documented 2xx and 422 responses at minimum;
  FastAPI derives these automatically from the handler's type hints and
  raised `HTTPException`s. No manual docstring duplication of the field
  name.
- **Static export step:** not applicable to this fixture. There is no CI
  and no published static `openapi.json` artifact; the spec is read live
  from the running app during a crew run (`GET /openapi.json`).

### 4b. Frontend: client consumption

Not applicable to this fixture: there is no frontend and no generated
client. Backend-only project.

### 4c. Post-generation customization via Mustache templates

Not applicable to this fixture: no code generation step exists to
customize.

---

## 5. Configuration and Secrets

Not applicable to this fixture: the app has no configuration and no
secrets. Do not add environment variable plumbing unless a REQ requires
it.

---

## 6. Data Access

Not applicable to this fixture: no database, no ORM, no persistence layer.
If a future REQ needs state, prefer an in-memory structure local to the
module and flag the pattern decision to the operator before adding one.

---

## 7. Model Naming (Request, Response, Entity)

**This stack:**

- Response shapes use plain `dict[str, ...]` return types for endpoints
  this small, OR a Pydantic `BaseModel` when a response has more than two
  fields or needs field-level validation/documentation. Prefer Pydantic
  models once a REQ's response shape grows past a trivial dict literal.
- Naming: `<Resource>Response` for response models (e.g. `GameResponse`),
  no separate request model needed when the only inputs are query
  parameters typed inline via `Query(...)`.
- No "DTO" suffix.

---

## 8. Entity and Domain Naming

Not applicable to this fixture: no entities, no domain model.

---

## 9. Explicit Type Mapping

Not applicable to this fixture: no entity-to-model mapping exists because
there is no entity layer.

---

## 10. RESTful API Naming

**This stack:**

- No versioned base path (`/api/v1` etc.) for this fixture; routes are
  mounted at the app root (e.g. `/health`, `/games`) to keep it minimal.
- Verb-free paths still apply: `/games`, not `/createGame`.
- No status-code policy beyond FastAPI defaults: `200` for successful
  `GET`, `422` for validation failures.
- No custom headers required.

---

## 11. Service Layer Method Flow

Not applicable to this fixture: route handlers in `app/main.py` are the
entire implementation. There is no separate service layer to route
through. Keep handler bodies short (read inputs, compute, return); if a
handler's logic grows complex enough to need its own tests independent of
the route, extract a plain function in the same file, not a service class.

---

## 12. Frontend Handoff Contract (UI Change Notification)

Not applicable to this fixture: no frontend consumes this API.

---

## 13. Legacy Requirements Reference

- **Requirements source path:** `requirements/` (one file per REQ, e.g.
  `requirements/REQ-GOLD-2.md`). Every REQ the coder implements must trace
  back to a file there.

---

## 14. Implementation Tracking

- **Tracking document path:** `implementation-tracking.md`

See that file for the current Requirements Baseline.

---

## 15. Stack-Specific Best Practices

- Use `Annotated[str, Query(min_length=1, max_length=200)]` (or the
  equivalent `Query(..., min_length=1, max_length=200)` default-value
  form) for constrained query parameters. Do not hand-roll length checks
  inside the handler body; let FastAPI/Pydantic validation produce the
  `422`.
- Do not use FastAPI's deprecated `@app.on_event(...)` startup/shutdown
  hooks; this fixture has none, and none should be added without a REQ
  requiring one.
- Do not return raw framework objects (`Response`, `JSONResponse`) unless
  a REQ specifically needs custom headers or status codes outside what a
  typed return value produces.

---

## 16. Build Configuration Discipline

- `pyproject.toml` is the single build file. Dependencies are pinned with
  compatible-release ranges (`>=`, `<`), not exact pins, except in
  `uv.lock`, which pins exact resolved versions for reproducibility.
- Dev-only dependencies (`pytest`, `httpx`, `pytest-cov`) live in
  `[dependency-groups.dev]`, never in `[project.dependencies]`.
- No new runtime dependency without a REQ that needs it.

---

## 17. Schema-Driven Entity Design

Not applicable to this fixture: no schema, no entities.

---

## 18. Class and Method Naming

- No classes needed for route handlers; plain functions named after the
  action, e.g. `get_health`, `create_game`.
- Pydantic response models, if used, are named `<Noun>Response`.
- Forbidden names: `helper`, `utils`, `do_stuff`, or any catch-all module.

---

## 19. Code Comments

**Universal rule applies as written.** No stack-specific additions;
module and function docstrings are enough for a project this size.

---

## 20. Time Zone and Localization Handling

Not applicable to this fixture: no datetime handling exists or is
expected.

---

## 21. Additional Stack-Specific Patterns

Not applicable to this fixture: no file upload, websocket, background job,
multi-tenant, feature-flag, or observability concerns exist at this size.

---

## 22. Coverage Gate

A REQ does not advance from `🔄 In Progress` to `✅ Implemented` until all
five conditions are met:

1. **Build passes.** `uv run python -c "import app.main"` exits 0 (the
   app module imports cleanly).
2. **Tests pass.** `uv run pytest` exits 0. Zero new failures.
3. **Coverage thresholds met** per the tester spec: line coverage ≥ 90%,
   branch coverage ≥ 80%. See `specs/tester-spec.md` section 6.
4. **Handoff contract current.** Not applicable to this fixture: no
   frontend consumes this API, so no handoff-contract entry is ever
   required. This condition is always satisfied by default.
5. **Static-analysis quality gate passes.** No SonarCloud/SonarQube
   platform is configured for this fixture; that would be disproportionate
   tooling for a project this small. Instead, condition 5 is satisfied by
   `uv run ruff check .` reporting zero errors. Any ruff error introduced
   by a REQ's change counts as a failure of this condition.

If any condition fails, the REQ stays `🔄` and the failure is logged in
`implementation-tracking.md`'s `coverage_status` field for that log entry.

**This stack (static-analysis gate):**

- **Platform:** ruff (local static analysis; no hosted platform).
- **Project key:** not applicable; single local project.
- **How the scan runs:** `uv run ruff check .` from the project root.
- **Where the gate result is fetched from:** the command's exit code and
  stdout; 0 findings and exit code 0 is `PASS`, anything else is `FAIL`.
- **Which severities count as failures:** all ruff findings (this fixture
  has no severity tiers configured; every finding blocks).
- **Who configures the platform-side settings:** the `[tool.ruff]` table
  in `pyproject.toml`; the operator, not the crew, changes ruff
  configuration.

---

## Key Files

- `app/main.py` - the entire application: FastAPI instance and all route
  handlers.
- `pyproject.toml` - dependencies, ruff config, pytest config.
- `wopr.yml` - project configuration read by every crew agent.
