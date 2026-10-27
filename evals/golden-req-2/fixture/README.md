# KITT Golden Fixture

A small, deterministic FastAPI project. Its only purpose is to act as the
golden-REQ evaluation fixture for the KITT crew skill (`kitt-run-crew`):
scout, coder, tester, auditor. Because the project is tiny and fixed, a
crew run against `REQ-GOLD-2` produces comparable results across different
versions of the crew skill. The point is a fast, cheap, repeatable run,
not a showcase of what the crew can build.

## Run procedure

1. Copy the entire directory to a scratch location, for example:
   `cp -r /tmp/kitt-golden-fixture /tmp/kitt-golden-fixture-run-001`
2. Run the crew (`kitt-run-crew` skill) against `REQ-GOLD-2` inside that
   scratch copy, not here.
3. Record whatever results you are comparing (coverage numbers, audit
   verdict, token/time cost, diffs produced) from the scratch copy.
4. Discard the scratch copy. Do not push its changes back into this
   directory.

## The corpus forces the evaluator path

`LEARNINGS.md` at the fixture root is part of the fixture, not leftover
state. It carries eight seed-marked entries tagged `fastapi`, which is
more than the five-candidate threshold at which `kitt-run-crew` stops
bypassing the grader. Every run against this fixture therefore includes
exactly one `crew-evaluator` dispatch in the retrieval pre-step, before
Step 1, and the run's cost and token counts include it.

That is deliberate. With an empty corpus the retrieval returned nothing,
the skill took its under-threshold bypass, and the CRAG path the crew
depends on was never exercised by the eval that exists to exercise the
crew. Compare golden runs only against other runs made with this corpus
present; a run recorded before it was added has one fewer agent
dispatch and is not comparable.

The entries mix deliberately: some speak directly to the REQ-GOLD-2
engine (validation status codes, conflict error codes, typed OpenAPI
responses), some are adjacent (test isolation, branch coverage), and
some are in-stack but off-topic (Postgres, Alembic, on a fixture with
no database). A grader that returns everything as HIGH, or nothing, is
visibly wrong.

## Rules

- This fixture directory itself must never be modified by a crew run. If a
  crew run edits files here directly instead of in a scratch copy, that is
  a setup mistake, not a result to record.
- `.venv`, `uv.lock`-adjacent build artifacts, `__pycache__`, and
  `.pytest_cache` are intentionally absent from the checked-in fixture.
  `uv run pytest` recreates what it needs in the scratch copy.
- `uv.lock` is kept so dependency versions are pinned identically across
  every scratch run; do not delete it when copying.
- `LEARNINGS.md` is copied like everything else and is expected to grow
  during a run: the auditor appends to the scratch copy's corpus at the
  end of the gate. Those appended entries stay in the scratch copy. The
  checked-in corpus is a fixed input, so a later run retrieves the same
  eight candidates the previous one did.
