# Golden-REQ-2 baseline summary (current agent specs)

Two crew runs on REQ-GOLD-2 (branchy REST engine) with the landed 119-line orchestrator held constant and the CURRENT agent specs (auditor 291 / scout 188 / coder 109 / tester 107 lines) as the variable under test for the coming slimming.

## Outcomes (pass condition for the post-slimming runs)

| Metric | Run 1 | Run 2 |
|---|---|---|
| Verdict | UNBLOCKED | UNBLOCKED |
| Gate | PASS 100%/100% (18 br) | PASS 100%/100% (16 br) |
| Criteria verified | 12/12 | 12/12 |
| Blockers | 0 | 0 |
| Warnings | 2 | 5 |
| Dispatches | 4 | 4 |
| Total subagent tokens | 270,106 | 268,768 |

Pass condition post-slimming: UNBLOCKED both runs, gate PASS, 12/12 criteria, no new blocker class, auditor still independently re-verifies (spot-check its report for fresh measurements), tokens at or below baseline.

## Baseline behaviors worth preserving (the slimming must not lose these)

1. Auditors re-ran everything fresh; run 2's went to a live uvicorn /openapi.json fetch and hand-verified the draw sequence. Independent re-verification is the role's core and survived a 291-line spec; it must survive a ~120-line one.
2. Role boundaries held perfectly in all 4 dispatches.
3. Deep-quality findings appeared at audit (missing-assertion-behind-100%-coverage; sync-guard ground-truth rule): evidence the auditor role adds value beyond the mechanical gate on branchy REQs.

## Baseline variance (expected post-slimming too)

- Implementation depth: typed ErrorResponse bodies + responses={} (run 1) vs plain HTTPException details (run 2); both spec-compliant.
- spec_writes usage: run 1 coder amended twice, run 2 coder zero; testers amended contradictory rules about win-line enumeration (run 1: drift-guard coupling to production constant; run 2: independence to prevent self-validation). Run 1's auditor adjudicated the coupling as sound-but-bounded. Contradictory spec amendments across runs are a REAL crew phenomenon the demo narrative can use.
- Warning counts vary with auditor depth (2 vs 5), not with correctness.

## Orchestrator lesson (fix in the skill during the slimming pass)

Run 1's auditor caught the orchestrator's own close-out sloppiness: flipping the gap row's status columns while leaving stale narrative in the Notes cell creates an in-row self-contradiction. The skill's close-out sentence should say the row's narrative updates too, not just statuses.
