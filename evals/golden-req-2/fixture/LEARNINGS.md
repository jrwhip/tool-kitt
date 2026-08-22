## LRN-2026-03-04-a: Range checks on request fields belong to the schema, not the handler

```meta
date: 2026-03-04
project: _seed
stack: [fastapi, pydantic]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A handler accepted a pair of integer coordinates and checked their bounds itself, returning a 400 with a hand-written body. The rest of the API returned FastAPI's own 422 validation envelope, so clients had to handle two error shapes for the same class of mistake.

**Why it matters.** Out-of-range input is a validation failure, and FastAPI already has one answer for validation failures. A handler that invents a second answer splits the contract and the split shows up in the OpenAPI document as an undocumented status code.

**Pattern to encode.** Constrain the field in the Pydantic model (`Field(ge=0, le=2)`, `conint`, or an annotated type) and let the framework produce 422. Handlers only decide things the schema cannot express.

## LRN-2026-03-19-a: A state conflict is a domain error with a stable code, not a bare 409

```meta
date: 2026-03-19
project: _seed
stack: [fastapi, http]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** Three different conflict conditions all raised `HTTPException(409, detail="conflict")`. Clients could tell that something was wrong but not which rule they broke, so the UI showed one generic message for every case and the tests asserted only on the status code.

**Why it matters.** 409 is a category, not a reason. When several rules share a status code, the machine-readable reason has to live in the body, otherwise every caller reimplements guessing from prose.

**Pattern to encode.** Each conflict rule gets its own domain exception carrying a stable snake_case error code. One exception handler maps the family to 409 and serializes the code into a named response schema. Tests assert on the code, not the prose.

## LRN-2026-04-08-a: In-memory stores leak state between tests without an explicit reset

```meta
date: 2026-04-08
project: _seed
stack: [fastapi, pytest]
req: []
auditor_run: seed@fastapi
severity: blocker
seed: true
```

**What happened.** A module-level dict held created resources. Each test passed alone. Run together, a test that asserted "no resources yet" failed because an earlier test in the same process had already created one.

**Why it matters.** A module-level dict lives for the life of the interpreter, not the test. Order-dependent failures like this one get blamed on the newest test rather than on the shared state, and they reproduce only under the full suite.

**Pattern to encode.** Either clear the store in an autouse fixture, or expose it through a dependency the tests override per test. Never rely on tests happening to run in an order where the leakage does not show.

## LRN-2026-04-27-a: An untyped dict response makes the OpenAPI document useless

```meta
date: 2026-04-27
project: _seed
stack: [fastapi, openapi]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** Routes returned plain dictionaries and declared no `response_model`. The generated OpenAPI document listed the paths with empty object schemas, so a generated client had no field names and every consumer read the handler source instead.

**Why it matters.** The OpenAPI document is the API's contract with everything that is not this codebase. A route with no declared response schema publishes a contract that promises nothing, and nothing downstream can be generated from it.

**Pattern to encode.** Every route declares `response_model=<NamedModel>` and every field on that model is typed. Nullable fields are declared nullable rather than omitted. Reviewers read the generated document, not just the handler.

## LRN-2026-05-14-a: Parametrize the cases instead of looping inside one test

```meta
date: 2026-05-14
project: _seed
stack: [fastapi, pytest]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** One test iterated over every combination in a for loop with an assertion inside. When a single combination regressed, the failure named the test, not the combination, and the loop stopped before checking the rest.

**Why it matters.** A loop collapses N cases into one pass or fail. Debugging then starts with reproducing which iteration failed, which is information the runner could have printed for free.

**Pattern to encode.** Use `@pytest.mark.parametrize` with one entry per case and readable ids. Every case runs and reports independently, and the failure output names the exact input.

## LRN-2026-06-02-a: Line coverage hides the branch that was never taken

```meta
date: 2026-06-02
project: _seed
stack: [fastapi, coverage]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A module reported full line coverage while an early-return guard had only ever been exercised in the false direction. The untested direction contained an inverted comparison that shipped.

**Why it matters.** Line coverage counts whether a line executed, not whether each decision went both ways. A guard clause, a ternary, and a short-circuiting `or` all reach full line coverage from a single path through them.

**Pattern to encode.** Turn on branch coverage (`--cov-branch`, or `branch = true` under `[tool.coverage.run]`) and set a branch floor alongside the line floor. Treat a branch-coverage drop as a test gap, not as a reporting artifact.

## LRN-2026-06-23-a: Translate IntegrityError at the repository boundary

```meta
date: 2026-06-23
project: _seed
stack: [fastapi, postgres]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A unique-constraint violation escaped the repository as a raw SQLAlchemy `IntegrityError` and reached the router, which turned every database error into a 500. A duplicate signup therefore looked identical to a broken connection.

**Why it matters.** The database is an implementation detail of the repository. Letting its exception types travel upward means the router has to know constraint names to say anything useful, and it usually gives up and returns 500 instead.

**Pattern to encode.** The repository catches `IntegrityError`, inspects the constraint, and raises a domain exception (`DuplicateEntityError`). Callers above the repository never import from the driver or the ORM.

## LRN-2026-07-15-a: Alembic autogenerate does not see every change

```meta
date: 2026-07-15
project: _seed
stack: [fastapi, alembic]
req: []
auditor_run: seed@fastapi
severity: warning
seed: true
```

**What happened.** A model changed a column default and the autogenerated migration came back empty. The change worked locally, where the table had been recreated by hand, and did nothing in any environment that ran migrations.

**Why it matters.** Autogenerate compares a limited set of properties by default. Server defaults, column type widenings, and constraint renames are among the things it can miss, and an empty migration reads like confirmation that nothing needed doing.

**Pattern to encode.** Enable `compare_type` and `compare_server_default` in the Alembic env, and read every generated migration before committing it. A migration that comes back empty after a schema edit is a signal to check, not a result.
