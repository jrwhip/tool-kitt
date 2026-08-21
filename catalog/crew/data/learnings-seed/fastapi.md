## LRN-2024-01-03-a: Sync DB calls in async routes block the event loop

```meta
date: 2024-01-03
project: _seed
stack: [fastapi]
req: []
auditor_run: seed@fastapi
severity: blocker
seed: true
```

**What happened.** An async route called a synchronous `Session.execute(...)` (SQLAlchemy 1.x sync session) instead of awaiting an `AsyncSession.execute(...)`. The route was functionally correct but every request blocked the event loop for the duration of the query, starving other requests.

**Why it matters.** FastAPI's concurrency model depends on routes yielding the event loop on I/O. A single blocking call in an async route serializes the whole worker.

**Pattern to encode.** All DB operations in async code use `AsyncSession` and `await`. Never `Session.execute(...)` in an async function. Never `time.sleep` (use `asyncio.sleep`). Auditor BLOCKS on sync I/O in async paths.


## LRN-2024-01-03-b: AsyncSession instances are per-request, not shared

```meta
date: 2024-01-03
project: _seed
stack: [fastapi]
req: []
auditor_run: seed@fastapi
severity: blocker
seed: true
```

**What happened.** A module-level singleton wrapped an `AsyncSession`. Two concurrent requests using the singleton hit a "SQLAlchemy session already in use" error, intermittent and load-dependent.

**Why it matters.** `AsyncSession` instances carry per-request state. Sharing one across concurrent requests produces race conditions that are invisible at low traffic and catastrophic under load.

**Pattern to encode.** `AsyncSession` is provided per request via `Depends(get_db)`. The dependency yields a session, the route uses it, the dependency closes it. No module-level session, no class-level session.


## LRN-2024-01-03-c: HTTPException raised from a service is a layering smell

```meta
date: 2024-01-03
project: _seed
stack: [fastapi]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A service function raised `HTTPException(status_code=404, detail="not found")` when an entity wasn't found. A non-HTTP caller (a background worker) couldn't handle the exception meaningfully and crashed.

**Why it matters.** HTTP concerns leaking into the service layer makes the service unusable outside HTTP contexts. The service should signal "not found" via a domain exception; the router maps it to 404.

**Pattern to encode.** Services raise project-specific exceptions (`<Entity>NotFoundError`, `<Domain>ValidationError`). Routers catch them and translate to `HTTPException`. Or use FastAPI's `@app.exception_handler(...)` to handle the mapping centrally.


## LRN-2024-01-03-d: Pydantic v2 is the project default

```meta
date: 2024-01-03
project: _seed
stack: [fastapi]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A new model used the v1 `Config` inner class with `orm_mode = True` and `@validator(...)`. The model worked because Pydantic v2 ships a v1 compatibility shim, but the deprecation warnings flooded the test output and the model couldn't be used with v2 features (`model_config`, `field_validator`, `computed_field`).

**Why it matters.** Mixed v1 and v2 syntax in a single codebase is a maintenance trap. New maintainers cannot tell which is the convention; the compat shim will eventually be removed.

**Pattern to encode.** New Pydantic models use v2 syntax exclusively: `model_config = ConfigDict(from_attributes=True)`, `@field_validator(...)`, `@computed_field`. Existing v1 models migrate as they're touched.


## LRN-2024-01-03-e: Mutable default arguments are still a Python footgun

```meta
date: 2024-01-03
project: _seed
stack: [fastapi]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A helper function had `def f(items: list[str] = []) -> ...`. Tests passed in isolation. Running the suite serially revealed the function's default list accumulated entries across calls.

**Why it matters.** Python evaluates default arguments once at function-definition time. A mutable default is shared across every call that omits the argument. The bug only surfaces when tests run in a specific order.

**Pattern to encode.** Default values for mutable arguments are always `None`, then constructed inside the function body. `def f(items: list[str] | None = None): items = items or []`.
