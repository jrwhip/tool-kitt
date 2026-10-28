## Audit Report - REQ-ARC-3 Game rules and server authority
### Date / Auditor: 2026-10-28 / crew-auditor / Build: `tsc -p amplify/tsconfig.json` clean; `ng build` FAILS (environmental, see W1) / Test Results: 86 passed, 0 failed (2 files; 84 in game-rules.spec.ts)

## PR Readiness Verdict: UNBLOCKED
Zero BLOCKERs. Warnings below should be routed before or with the commit.

### BLOCKERS
None.

### WARNINGS
- **W1. `ng build` fails; recorded `gate: PASS` waives coder-spec gate condition 1 without saying so.** `src/main.ts:3` imports `../amplify_outputs.json` (TS2307). Independently verified: `src/main.ts` is unmodified vs HEAD, `amplify_outputs.json` is not tracked, and coder-spec "Source Layout" says it is generated and not committed. The failure is therefore pre-existing, environmental and not attributable to REQ-ARC-3. The operator forbids `ampx`, so it cannot be cleared here. Classification: WARNING (not BLOCKER). The log discloses the failure honestly, but `coverage_status ... gate: PASS` (implementation-tracking.md:84) should read "PASS, condition 1 (ng build) waived: missing generated amplify_outputs.json". Re-run `ng build` once the outputs file exists.
- **W2. `WINNING_LINES` is not frozen and `applyMove` aliases its entries into the returned state** (`amplify/shared/game-rules.ts:41`, `:119`). `result.line` in an accepted-move state is the module's own array element. A caller who mutates it at runtime (the `readonly` is type-level only) corrupts win detection for every later game in that process. This undercuts the "server is sole authority" intent and is inconsistent with `readAuthoritativeState`, which deep-copies and freezes. No test catches it, since `line` is only compared with `toEqual`. Fix: freeze the table and its rows, or copy the line in `applyMove`.
- **W3. AC5 is only partly delivered, but REQ-ARC-3 is marked whole `Implemented`.** The "source of truth over any live notification" clause has no code or test here. The scoping is honest and consistent: the scout contract and the log both call it a server-layer concern. But the status cell (implementation-tracking.md:58) carries no deferral note. Record explicitly that this clause (and the persisted "read at any time" surface) is deferred to the REQ that adds the read/subscription operations (REQ-ARC-4 per coder-spec API rule 3). Ready to merge as a pure-module REQ only on that understanding.
- **W4. Stale/contradictory tracking text.**
  - Header `Last updated: 2026-09-26 (fresh rebuild; baseline set, nothing built)` (line 3) contradicts the implemented REQ.
  - Gap Analysis row (line 73) has Baseline cell `✅ Implemented`, while its own narrative says the scout found it ALIGNED with `⏳ Pending`. The cell and narrative disagree (checklist item 1).
  - Line 75 says `Run mode: gap_analysis` for a crew run.

### SUGGESTIONS
- S1. `tsconfig.spec.json` is outside the scout's `files_touched` (the scout only anticipated `angular.json`). The change is minimal and justified (type-checks the amplify specs under the spec tsconfig), but record it as accepted drift.
- S2. Propose spec amendments (spec_writes OFF): tester spec should name the `angular.json` test `include` (`"../amplify/**/*.spec.ts"`, globs resolve relative to `sourceRoot`) and a Test File Layout row for `amplify/shared/*.spec.ts`; coder-spec Source Layout needs an `amplify/shared/` row; both specs say `wopr.yml` where the repo uses `kitt.yml`; coder-spec build gate should say what to do when `amplify_outputs.json` is absent.
- S3. `applyMove` trusts runtime shape (`playerId` non-string, `cell` undefined). The cell check covers `undefined` via `Number.isInteger`, and the participant check covers other types. Behavior is safe as is; no action.

### PASSED
- Item 1 (traceability, status vs reality): module and spec exist and match the Implemented claim, except the W3/W4 notes.
- Item 2 (pattern compliance): no Angular/GraphQL anti-patterns apply; no generated files touched; `amplify/data/resource.ts` unchanged. `.spec.ts` naming, Vitest imports, no network, no snapshots, no `it.skip`.
- Item 3 (coverage honesty): fresh `npx ng test --watch=false --coverage` gives 2 files / 86 passed. Overall 100% statements (43/43), branches (50/50), functions (6/6), lines (36/36), matching the recorded 100/100. Diagnostic only. `tsc -p amplify/tsconfig.json --noEmit` clean; `ng lint` "All files pass linting".
- Item 4 (spec integrity): no endpoints in this REQ; no schema change. Not applicable beyond that.
- Item 5: no handoff contract in scope; no API-surface change.
- Item 6: Migration Context is "net-new"; consistent. The 2026-10-28 intake is recorded.
- Item 7: no CI workflows in the repo; skipped. The `angular.json` test target now actually runs the amplify spec (count: 84 amplify tests, 2 app tests).
- Item 8 (traceability): every AC maps to named tests; I spot-read them. AC1: out-of-turn, occupied, 6 invalid cells, boundaries 0/8, with deep-equal state snapshot on every rejection. AC2: outsider on fresh/in-progress/finished, case-sensitivity, empty id. AC3: 8 lines x 2 marks at both `findWinningLine` and `applyMove`, with expected lines written independently, plus draw and win-on-ninth. AC4: won and drawn games, both players, invalid cell. AC5: copy/frozen/rejection-invariance tests exercise `readAuthoritativeState` directly (see W3 for the notification clause).
- Item 9 (maintainability): production file 151 lines, small functions. Comment-policy grep (`LRN-\d{4}`, `ruling`, `gate-failure`, ISO dates, `REQ-`) over `game-rules.ts`: zero hits.
- Item 10 (falsifiability): defects reintroduced in a throwaway copy (removed after), working tree untouched. Each is caught: `cell > 9` bound, 1 failed; diagonal `[2,4,5]`, 5 failed; finished-game check removed, 8 failed; draw check removed, 5 failed; turn check removed, 3 failed. Pins discriminate.
- Items 11, 12: appearance not in scope (no `design_spec`); single-project run (`git status` shows only the expected files; `LEARNINGS.embeddings.npz` is a tool sidecar, not crew output).
- `readAuthoritativeState` has no in-sample consumer by design (scout handoff note 6): accepted, not dead code.
- REQ-ARC-2 pending: accepted per intake, not a finding.

### Resolution Summary
First audit of this REQ; no prior report. The coder's gate-fix (`ng test` discovery) is verified working.

### Spec amendments
Proposed (spec_writes OFF), see S2. No spec files edited.

### Learnings (not persisted)
Persisted via `append_learnings` (see the orchestrator summary); if that call failed, the single entry is "Aliased module-level constant tables returned inside 'pure' results".
