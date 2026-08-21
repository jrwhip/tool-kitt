# Golden-REQ baseline summary (pre-rewrite)

Two full crew runs against the unmodified 473-line `wopr-run-crew/SKILL.md` (commit 44aae80), REQ-GOLD-1, empty learnings corpus, models per the skill's table (scout haiku, coder/tester/auditor sonnet), dispatched as fresh subagents reading their agent specs.

## Outcomes (the comparison baseline for the rewrite)

| Metric | Run 1 | Run 2 |
|---|---|---|
| Auditor verdict | UNBLOCKED | UNBLOCKED |
| Coverage gate | PASS (100% line / 100% branch) | PASS (100% line / 100% branch) |
| Acceptance criteria verified | 9/9 | 9/9 |
| Blockers | 0 | 0 |
| Auditor warnings | 1 | 2 |
| Agent dispatches | 5 | 5 |
| Evaluator dispatches | 0 (short-circuit) | 0 (short-circuit) |
| Subagent tokens total | 253,287 | 248,320 |

Pass condition for the post-rewrite runs: same verdict (UNBLOCKED), gate PASS, no new blocker class, dispatch count and tokens at or below baseline.

## Baseline behaviors that motivate the rewrite (cite these in the ledger)

1. **Phase-0/Step-1 scout duplication.** In both runs the Phase-0 gap_analysis scout also wrote the Step-1 contract, and the Step-1 scout then redid overlapping discovery. Two dispatches (63k-82k tokens combined) did roughly one dispatch's work. The 473-line skill's mode boundary text did not prevent this.
2. **Status-flip round-trip.** The skill prescribes re-dispatching the coder solely to change one status emoji after the gate passes. Skipped in both runs as over-orchestration; the rewrite should assign the flip to the orchestrator.
3. **4x CRAG pre-step ceremony.** All four pre-steps short-circuited identically on the empty corpus. The prescribed per-step retrieval buys nothing at small corpus sizes; supports the planned 1x-per-run retrieval with a small-corpus evaluator bypass.
4. **What held and must be preserved:** role separation was never violated (coder wrote no tests, tester touched no production code); both auditors independently re-ran every gate condition instead of trusting recorded values; the scout-contract validator gate caught nothing this time but cost nothing.
5. **Benign variance to expect:** implementation shape within spec (Pydantic model vs plain dict), scope judgment on adjacent defects (flag vs fix), warning counts.

## Fixture notes

- The fixture shipped without ruff in its dev dependency group while the gate's condition 5 requires it; fixed in the fixture after these runs. Baseline workaround behavior around ruff is a fixture artifact, not skill behavior; ignore it in pre/post comparisons.
- Run 2's auditor proposed 2 learnings entries (recorded in baseline-run-2.md). Not appended anywhere: baseline runs must not seed the corpus.
