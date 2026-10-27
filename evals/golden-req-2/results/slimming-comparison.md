# Agent-spec slimming: eval-gate comparison

Crew agent specs cut 1,016 to 324 lines (auditor 291->64, scout 188->59, coder 109->50, tester 107->45; evaluator unchanged; the 215-line kitt-crew.md agent-mode duplicate deleted). Gate: 2 golden-REQ-2 runs before and after, plus a REQ-1 smoke.

## Verdict: PASS, with one disclosed caveat

| Metric | Baseline (1,016 lines) | Post-slim (324 lines) |
|---|---|---|
| Final verdict | UNBLOCKED x2 | UNBLOCKED x2 (each after one blocker-fix cycle) |
| Criteria verified | 12/12 both | 12/12 both |
| Gate | PASS 100%/100% both | PASS 100%/100% both |
| Core 4-dispatch tokens | 270,106 / 268,768 | 269,250 / 253,992 |
| Tokens incl. remediation | n/a | 329,317 / 317,343 |
| Role-boundary violations | 0 | 0 (incl. two coders overriding contract suggestions to write tests) |
| REQ-1 smoke | (prior runs 208.7k / 201.4k) | 211,998, UNBLOCKED, 0 warnings |

**The caveat, honestly:** both post-slim runs went BLOCKED on first audit and needed a remediation cycle, so total tokens including remediation exceeded baseline. Root cause is orchestrator-owned, not spec-owned: the orchestrator's close-out edits repeatedly missed gap-table rows because scout-authored gap tables vary in shape, and the slimmed auditor spec enforces row consistency harder (the rule was added FROM baseline findings). The blocker class ("tracking status contradiction") exists in the old spec's checklist too; baselines simply never tripped it because their tables happened to match the close-out regex. Remediation itself worked exactly as designed: one-row fix, resolution-pass audit with Resolution Summary, prior findings carried forward correctly.

## Quality: the slimming IMPROVED behavior where lessons became rules

1. Both post-slim testers independently wrote state re-fetch assertions on rejected/terminal requests (baseline's deepest audit finding, now structurally prevented) and derived win-line ground truth independently of the production constant (baseline's two testers codified contradictory rules here; post-slim both converged on the correct one).
2. One of two post-slim scouts enumerated all 3 public models in class_inventory (baseline: 1 entry in both runs). Improvement on average, not deterministic.
3. Auditors kept full rigor at 64 lines: live OpenAPI fetches, hand-traced draw boards, mtime-scoped drift checks on re-audit, correct zero-learnings gating, and honest handling of a missing MCP tool (verified absence, declined to fabricate, recorded in report).

## Follow-ups routed to the ledger

- Tracking template: dual status tables (Requirements Baseline + Gap Analysis) invite divergence; single-source the status or generate the gap table. (From post-2 auditor's proposed learning.)
- Orchestrator close-out discipline: read the actual rows and edit exactly; never bulk-regex a table whose shape a scout authored. (Recorded in the skill's close-out sentence already; the eval proved why.)
