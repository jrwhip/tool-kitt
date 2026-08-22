# WOPR Golden Fixture

A small, deterministic FastAPI project. Its only purpose is to act as the
golden-REQ evaluation fixture for the WOPR crew skill (`wopr-run-crew`):
scout, coder, tester, auditor. Because the project is tiny and fixed, a
crew run against `REQ-GOLD-2` produces comparable results across different
versions of the crew skill. The point is a fast, cheap, repeatable run,
not a showcase of what the crew can build.

## Run procedure

1. Copy the entire directory to a scratch location, for example:
   `cp -r /tmp/wopr-golden-fixture /tmp/wopr-golden-fixture-run-001`
2. Run the crew (`wopr-run-crew` skill) against `REQ-GOLD-2` inside that
   scratch copy, not here.
3. Record whatever results you are comparing (coverage numbers, audit
   verdict, token/time cost, diffs produced) from the scratch copy.
4. Discard the scratch copy. Do not push its changes back into this
   directory.

## Rules

- This fixture directory itself must never be modified by a crew run. If a
  crew run edits files here directly instead of in a scratch copy, that is
  a setup mistake, not a result to record.
- `.venv`, `uv.lock`-adjacent build artifacts, `__pycache__`, and
  `.pytest_cache` are intentionally absent from the checked-in fixture.
  `uv run pytest` recreates what it needs in the scratch copy.
- `uv.lock` is kept so dependency versions are pinned identically across
  every scratch run; do not delete it when copying.
