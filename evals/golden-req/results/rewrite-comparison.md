# Crew skill rewrite: eval-gate comparison

The 473-line `kitt-run-crew/SKILL.md` was rewritten to 119 lines (75% cut). Per the slimming method, the rewrite only lands because these four golden-REQ runs prove no behavioral regression. All four runs: same fixture REQ, empty learnings corpus, identical dispatch method, same models per role.

## Pass condition (from baseline-summary.md) and result

| Condition | Required | Post-rewrite result |
|---|---|---|
| Auditor verdict | UNBLOCKED both runs | UNBLOCKED both runs ✔ |
| Coverage gate | PASS | PASS both runs ✔ |
| New blocker classes | none | none ✔ |
| Dispatches per run | <= 5 | 4 ✔ |
| Subagent tokens per run | <= ~250k | 208,733 / 201,431 ✔ |

## Before / after

| Metric | Baseline (473-line skill) | Post-rewrite (119-line skill) | Delta |
|---|---|---|---|
| SKILL.md lines | 473 | 119 | -75% |
| Agent dispatches per run | 5 | 4 | -1 (merged Phase-0/Step-1 scout) |
| Scout-phase tokens | 75,402 / 70,047 | 39,428 / 37,389 | -47% avg |
| Total subagent tokens per run | 253,287 / 248,320 | 208,733 / 201,431 | -18% avg |
| Auditor warnings | 1 / 2 | 0 / 0 | structural fix landed |
| Acceptance criteria verified | 9/9 both | 9/9 both | unchanged |
| Role-boundary violations | 0 | 0 | unchanged |
| Routing evals | 172/172 | 172/172 | unchanged (description tightened, triggers intact) |

## What the rewrite changed and the evidence for each change

1. **Merged Phase 0 into Step 1 (one scout dispatch).** Baseline evidence: in both baseline runs the Phase-0 scout exceeded its mode and wrote the Step-1 contract anyway, then the Step-1 scout redid overlapping discovery. Post-rewrite: one dispatch, same verdict, same validated contract, half the scout tokens.
2. **Orchestrator flips REQ status and closes the Gap Analysis row after the gate.** Baseline evidence: the prescribed coder round-trip for a one-line status change was skipped as absurd in both baseline runs, and baseline run 2's auditor flagged the stale Gap Analysis row as a self-contradiction. Post-rewrite: both audits found zero stale-row findings.
3. **CRAG pre-step once per run with a 5-candidate evaluator bypass.** Baseline evidence: all 4 prescribed per-step retrievals short-circuited identically on the small corpus. The evaluator remains, threshold-gated, as the independent circuit-breaker for corpus sizes where selection pressure exists (rationale in docs/perpetual-learning.md lineage; over-verification guidance argues for removal, loop-topology argument keeps it above threshold).
4. **Cut without behavioral counterpart:** role-play sermon (the Task-tool rule survives as one line and held in all four runs), hook-wiring interview (now a two-line pointer), Migration Context seven-category interview (now one intake step), verbosity throughout. Stale quarry paths and the scrubbed-client stack heuristic replaced with in-repo paths and generic detection.

## Caveats, honestly stated

- One golden REQ on a tiny greenfield FastAPI fixture. The blocker-fix, frontend-handoff, jira-source, and above-threshold CRAG paths are NOT exercised by this eval; they were compressed, not removed, and should be exercised before the conference demo relies on them (the demo exercises jira-source and multi-REQ at rehearsal).
- Coverage floors were trivially met (handler has no branches). A harder golden REQ would strengthen the gate; candidate for a second fixture later.
- Baseline used the fixture with the ruff dep missing; post-rewrite used the fixed fixture. Ruff-related variance between the pairs is a fixture artifact, excluded from comparison.
