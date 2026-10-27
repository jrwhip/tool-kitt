# Naked-Claude baseline (no harness)

- Date: 2026-08-21
- Condition: single sonnet agent per run (same tier as the crew's working agents), fixture stripped of all harness artifacts (kitt.yml, specs/, implementation-tracking.md, README removed; only app/, tests/, pyproject, uv.lock, requirements/REQ-GOLD-1.md remain). Prompt: implement the requirement, production quality, tests, suite green, lint clean, strong coverage.
- Purpose: third point on the harness curve (no harness / heavy harness / right-sized harness) for docs/harness-thesis.md.

## Runs

| | Run 1 | Run 2 |
|---|---|---|
| Tokens | 30,694 | 32,320 |
| Tool uses | 11 | 12 |
| Duration | 37 s | 41 s |
| Self-reported result | 8/8 tests, 100% coverage, ruff clean | 8/8 tests, 100% coverage, ruff clean |
| Orchestrator re-verification | confirmed | confirmed |
| Implementation shape | Query(...) constraints, dict return | Annotated Query constraints, dict return |

Both runs also added a 7th test checking /echo's presence in the OpenAPI schema, unprompted.

## Post-hoc independent review (paid separately, sonnet, ~35k tokens each)

Method: a fresh reviewer per run verified all 9 acceptance criteria directly against code (own TestClient probes, own edge cases: unicode, whitespace, duplicate params, exact boundaries), assessed whether the self-written tests genuinely discriminate (mutation reasoning), and returned an audit-style verdict.

| | Run 1 | Run 2 |
|---|---|---|
| Criteria | 9/9 PASS | 9/9 PASS |
| Test quality | genuinely discriminating (boundary values, exact-equality bodies) | genuinely discriminating |
| Verdict | WOULD PASS WITH WARNINGS | WOULD PASS WITH WARNINGS |
| Warnings | generic dict response schema (OpenAPI documents untyped object, not named fields); 422 tests assert status only, not which constraint fired | same two, plus untested unicode length regression and OpenAPI test not asserting minLength/maxLength |
| Review tokens | 37,825 | 32,777 |

## Findings

1. Naked Claude (sonnet tier) is ~8x cheaper than the crew on this REQ and functionally correct both times. Harness value on a trivial REQ is near zero for the happy path.
2. The assurance gap is real and repeatable: both runs shipped the identical warning pattern (loose response typing, undiscriminating 422 assertions). No artifact from the run tells a reader this; discovering it cost ~35k review tokens per run.
3. The audit cost moved rather than disappearing: naked run + post-hoc review is ~66k tokens and still yields no tracking trail, no learnings, and standards enforced by reviewer taste rather than a spec.
4. Caveat: the naked runs were handed excellent numbered acceptance criteria. Much real-world harness value is upstream of this eval (producing REQ files this good).
