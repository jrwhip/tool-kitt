# Coder Spec - TODO: project name

> **Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.x async, pytest, uv or pip.
> **This file:** stack-pre-filled starting point.
> **For the deep version:** the generic `coder-spec.template.md` in the crew pack's templates (fetch via `get_pack_template`, `pack="crew"`, `name="coder-spec.template.md"`).

---

## Migration Context

`[TODO if applicable, else write: No structural changes this session; implement REQs as extracted.]`

---

## Build and Test Commands

| Purpose | Command |
|---|---|
| Install dependencies | `uv sync` (or `pip install -e .[dev]`) |
| Type-check | `uv run mypy src/` |
| Lint | `uv run ruff check src/ tests/` |
| Format | `uv run ruff format src/ tests/` |
| Run tests | `uv run pytest` |
| Run with coverage | `uv run pytest --cov=src --cov-report=term-missing` |
| Run the server (dev) | `uv run uvicorn <app_module>:app --reload` |

If the project uses pip directly, replace `uv run <cmd>` with `<cmd>` inside the venv.

---

## Source Layout

| Concern | Path |
|---|---|
| Source | `src/<package_name>/` |
| Tests | `tests/` |
| Pyproject | `pyproject.toml` |
| OpenAPI schema | served at `/openapi.json` by FastAPI; export to `src/<package>/openapi.json` if pinned |

---

## Architecture Patterns

### Module structure
- `routers/` - FastAPI APIRouter modules. Only request/response wiring.
- `services/` - business logic. Pure Python, no FastAPI imports.
- `models/` - SQLAlchemy ORM models.
- `schemas/` - Pydantic request/response models.
- `db/` - session factory, dependency for `get_db()`.
- `core/` - settings (Pydantic BaseSettings), security, cross-cutting concerns.

### Dependency injection
- FastAPI `Depends()` for request-scoped wiring (db sessions, current user).
- Module-level singletons for stateless services.
- Never share `AsyncSession` across requests.

### Schemas
- Pydantic v2 (`BaseModel` with `model_config`).
- Request schemas separate from response schemas; do not reuse a single model for both.
- `Field(..., description="...", examples=[...])` on every public field so the generated OpenAPI carries documentation.

### Async vs sync
- All I/O is async. Database sessions are `AsyncSession`.
- Never `time.sleep` in an async function. Use `asyncio.sleep`.
- Never run sync database code in an async route.

### Configuration
- `pydantic_settings.BaseSettings` for environment variables.
- Settings is a singleton, loaded once at startup.
- No `os.environ.get(...)` scattered through the codebase.

---

## OpenAPI

FastAPI generates the OpenAPI spec automatically from routes + Pydantic schemas. The pinned spec version lives in `wopr.yml` (`openapi.pinned_generator_version`).

- Every router endpoint has `summary` and `description`.
- Every public Pydantic field has `description` and `examples`.
- Status codes via `status_code=` on the route decorator or `HTTPException(status_code=...)`.
- A static spec snapshot at `src/<package>/openapi.json` is regenerated whenever the API surface changes; commit it in the same change.

---

## Anti-Patterns (auditor surfaces these as BLOCKERs)

- Synchronous DB calls in async routes (`session.execute(...)` without `await`).
- Business logic in routers.
- HTTP concerns leaking into services (raising `HTTPException` from a service is a smell; raise a domain exception, map to HTTP in the router).
- Sharing `AsyncSession` across requests.
- Mutable default arguments (`def f(x=[])`).
- `print` for logging. Use `logging.getLogger(__name__)`.
- Pydantic v1 syntax (`Config` class, `validator`) in new code; project uses v2 (`model_config`, `field_validator`).
- Type hints lying. If mypy says it's wrong, fix the code; do not `# type: ignore`.

---

## Coverage Gate

The five-condition gate (the orchestrator owns and enforces it; the tester records `coverage_status`; the auditor independently re-verifies):

1. `uv run pytest` exits 0.
2. Zero new failures.
3. Line coverage >= **TODO: floor (start at 80)**, branch coverage >= **TODO: floor (start at 70)**.
4. If the REQ touched the API surface, the frontend handoff contract has a line item with a JSON Pointer.
5. Quality Gate is `Passed` for the relevant commit.

---

## Spec Maintenance

When `spec_writes` is ON, amend this spec when new patterns emerge. Examples: a new async session pattern, a new exception-mapping idiom, a new Pydantic settings convention.
