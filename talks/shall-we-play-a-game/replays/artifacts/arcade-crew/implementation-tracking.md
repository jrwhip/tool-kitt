# WOPR Arcade - Implementation Tracking

> **Last updated:** 2026-10-28 (REQ-ARC-3 crew run: rules module implemented, audit UNBLOCKED; all other REQs unbuilt)
> **Scope:** Full app per `requirements/REQ-ARC-1` through `REQ-ARC-10`.
> **Status legend:** `⏳ Pending`, `🔄 In Progress`, `✅ Implemented`, `❌ Out of Scope`
> **Spec version pinned:** `@aws-amplify/backend` (version recorded at scaffold)
> **Generator version pinned:** `aws-amplify 6.22.0`
> **Structural context:** Net-new build. Stack and rules are in `specs/coder-spec.md` (Migration Context). `requirements/` is operator-owned. Commit locally after each UNBLOCKED REQ; never push.

## Session Intake (2026-09-26)

- **Run type:** crew run (scout, designer, coder, tester, auditor). Light run never used.
- **Scope:** REQ-ARC-1 through REQ-ARC-10, in number order, one crew run per REQ.
- **Structural context:** none beyond the header above and the coder spec's Migration Context. Additional decisions made by the orchestrator, standing for the whole session:
  - Operator instruction: the orchestrator makes every decision without pausing; open questions are answered by the orchestrator and recorded here.
  - Models: every crew role runs on Opus (operator instruction), overriding the pack's haiku/sonnet defaults.
  - Visual baselines: the operator delegated baseline review to the orchestrator for this session. The orchestrator inspects the designer's candidate screenshots against `requirements/design-standard.md` before committing them, and records each approval in the implementation log.
  - Project hooks: prompt-log and git-branch-guard both declined. Work happens on `main`, one local commit per UNBLOCKED REQ, never pushed.
  - Backend deploys go to the Amplify sandbox in the default AWS profile (account 019918485675). Unit tests never touch the network; e2e tests run against the deployed sandbox.
  - JOSHUA is a reserved callsign from REQ-ARC-1 onward (REQ-ARC-10 AC8), so the identity layer refuses it from the start rather than retrofitting.

## Session Intake (2026-10-28) — supersedes the 2026-09-26 intake where they conflict

- **Run type:** (1) crew run (scout, coder, tester, auditor; no designer, `kitt.yml` declares no `specs.design_spec`).
- **Scope:** REQ-ARC-3 only.
- **Structural context (operator):**
  - This is a sample build in a scratch copy of the project at its setup commit. There is no AWS account, no Amplify sandbox, no deploy, and no `ampx` in this copy; never run any of them. (Overrides the 2026-09-26 sandbox/account and e2e-against-sandbox decisions.)
  - Implement REQ-ARC-3 as a pure TypeScript rules module under `amplify/shared/` (the module the server Lambdas will call), with unit tests run through Vitest in Node. A client-side move-handling layer is out of scope.
  - The dependency REQ-ARC-2 is pending by design in this sample; treat that as accepted, not as a blocker.
- **Models:** pack defaults per `kitt.yml` `crew.models` (scout haiku; coder, tester, auditor sonnet). The 2026-09-26 all-Opus instruction does not apply to this session.
- **Optional hooks:** prompt-log and git-branch-guard both declined; none registered.
- **spec_writes:** off.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Angular 22 (zoneless, standalone, signals) |
| Backend | AWS Amplify Gen 2, TypeScript Lambda functions |
| Database | DynamoDB |
| API contract | Amplify Data / AppSync GraphQL schema (`amplify/data/resource.ts`) |
| Auth | Cognito (email accounts, identity-pool guests) |
| Timers | EventBridge Scheduler |
| AI | Amazon Bedrock (Nova) for JOSHUA's live chat replies |
| Testing | Vitest, Playwright (4 browsers, 6 viewports) |
| Build | Angular CLI, npm, Node 24 via mise |

---

## Requirements Baseline

| REQ ID | Description | Status | Notes |
|---|---|---|---|
| REQ-ARC-1 | Identity and callsigns | ⏳ Pending | |
| REQ-ARC-2 | Matchmaking | ⏳ Pending | |
| REQ-ARC-3 | Game rules and server authority | ✅ Implemented | REQ review: approved 2026-10-28, 1 round. Coverage gate passed 2026-10-28; audit UNBLOCKED 2026-10-28 (`AUDIT_REPORT.md`). Scope: pure rules module `amplify/shared/game-rules.ts`. **Deferred:** AC5's "source of truth over any live notification" clause has no code here (no notification layer exists); it lands with whichever REQ builds the server/live-notification layer (operator to assign; REQ-ARC-4 "Live state" is the likely home). |
| REQ-ARC-4 | Live state and disconnect resilience | ⏳ Pending | |
| REQ-ARC-5 | Ratings, history, and leaderboard | ⏳ Pending | |
| REQ-ARC-6 | JOSHUA, the AI host | ⏳ Pending | |
| REQ-ARC-7 | Player chat | ⏳ Pending | |
| REQ-ARC-8 | Rematch | ⏳ Pending | |
| REQ-ARC-9 | Client experience and visual design | ⏳ Pending | |
| REQ-ARC-10 | Play against JOSHUA | ⏳ Pending | |

---

## Gap Analysis (Latest Session)

| REQ ID | Baseline status | Codebase reality (2026-10-28) | Verdict |
|---|---|---|---|
| REQ-ARC-3 | ⏳ Pending at scout time; now ✅ Implemented | Scout (2026-10-28, pre-build): no game code existed, ALIGNED with ⏳ Pending. Closed out 2026-10-28: `amplify/shared/game-rules.ts` + `amplify/shared/game-rules.spec.ts` (84 tests) landed; `ng test` discovers them via the `angular.json` test `include`; coverage gate passed. `amplify/data/resource.ts` unchanged (no schema change, by operator scope). REQ-ARC-2 (dependency) still pending, accepted per the 2026-10-28 intake. | ALIGNED (closed) |

**Verdict (REQ-ARC-3): ALIGNED at scout time; closed out as ✅ Implemented after the coverage gate on 2026-10-28.** Session run type: crew run; scout mode: `gap_analysis`; scope REQ-ARC-3 only.

---

## Current Implementation Log

### REQ-ARC-3 - Game rules and server authority (coder, 2026-10-28)

- **Status:** ✅ Implemented (orchestrator, 2026-10-28, after the coverage gate). Audit: UNBLOCKED 2026-10-28, 0 blockers / 4 warnings (`AUDIT_REPORT.md`); W1/W3/W4 (tracking-doc wording) fixed by the orchestrator in this doc; W2 (`WINNING_LINES` not frozen and returned by reference in `result.line`, `game-rules.ts:41`/`:119`) left open for an operator decision.
- **Gate waiver (explicit, audit W1):** gate condition 1 is WAIVED for the app build only. `ng build` fails on the missing, sandbox-generated `amplify_outputs.json` (pre-existing; `ampx` forbidden this session). REQ-scope build passes. This waiver applies to this sample copy only.
- **Accepted drift:** `tsconfig.spec.json` (gate-fix) was not in the scout contract's `files_touched`; accepted.
- **spec_version:** `specs/coder-spec.md` as of 2026-10-28 (unversioned file; Migration Context "Net-new project"). `coverage_status`: line 100% / branch 100% / static_analysis: PASS (eslint clean on game-rules.ts and game-rules.spec.ts; `tsc -p amplify/tsconfig.json --noEmit` clean) / gate: PASS after gate-fix (see below). History: the tester's first measurement was gate FAIL because `ng test` did not discover the amplify spec; resolved by the coder's gate-fix entry below.
- **Coverage gate (orchestrator re-check, 2026-10-28):** (1) Build: REQ-scope build `npx tsc -p amplify/tsconfig.json --noEmit` clean. App `npx ng build` FAILS, pre-existing and not attributable to this REQ: `src/main.ts` imports `../amplify_outputs.json`, which is generated only by `ampx sandbox`/deploy and was never committed at the setup commit; the operator's structural context forbids `ampx`, so it cannot be generated in this copy. Nothing this REQ changed touches `src/main.ts`. (2) `npx ng test --watch=false --coverage`: 2 files, 86/86 pass, 0 failures. (3) Traceability: AC1-AC5 each map to named tests (map below). (4) API surface untouched; no handoff entry needed. (5) Static analysis clean. → PASS.
  - Measurement (fresh, 2026-10-28): `npx vitest run amplify --coverage --coverage.include='amplify/shared/**'` -> 84/84 pass; game-rules.ts statements 100% (33/33), branches 100% (40/40), functions 100% (5/5), lines 100% (32/32). Root `npx vitest run` (all files): 84 pass, plus the 2 pre-existing `src/app/app.component.spec.ts` tests fail with "Need to call TestBed.initTestEnvironment() first" because raw Vitest skips the Angular builder's TestBed setup; those pass under `ng test`.
  - **Criterion -> test map** (all in `amplify/shared/game-rules.spec.ts`):
    - AC1: `applyMove turn and cell legality` > "lets the player whose turn it is take an empty cell and passes the turn", "alternates back to X after O moves", "does not mutate the input state on an accepted move", "rejects a participant moving out of turn...", "rejects the previous mover moving twice in a row", "rejects a move onto an occupied cell", "rejects the mover re-taking their own occupied cell", "rejects out-of-grid or non-integer cell %s" (-1, 9, 1.5, NaN, Infinity, 100), "accepts boundary cell %s" (0, 8), "reports wrong turn before an invalid cell". Every rejection goes through `expectRejected`, which deep-compares the input state with a pre-call snapshot.
    - AC2: `applyMove non-participants` > outsider on fresh game, in-progress game, finished game; outsider with an invalid cell; case-different id ('Alice'); empty id. Each asserts `not_a_participant` and an unchanged state.
    - AC3: `win detection` > "findWinningLine detects $label" and "applyMove names winner and line for $label" (16 cases each: 8 lines x X/O, expected lines written independently of `WINNING_LINES`), "returns null" cases, real X-win and O-win games; `WINNING_LINES` > "lists exactly the 3 rows, 3 columns and 2 diagonals"; `draw detection` > "declares a draw on a full board with no line", "does not declare a draw while a cell is still empty", "scores a line completed on the ninth move as a win, not a draw".
    - AC4: `finished games are immutable` > after a won game and after a drawn game: "rejects further moves from either participant and leaves the state unchanged", "rejects a participant move onto an occupied cell as finished", "rejects a finished-game move even with an invalid cell"; plus "rejects a move on a won game that still has empty cells" and "rejects a move when turn is null even if result is missing".
    - AC5: `readAuthoritativeState` > "returns fields equal to the source state for a fresh game", "reflects each accepted move", "is unchanged by a rejected move", "exposes the win result with winner and line", "exposes the draw result", "returns a deeply frozen copy", "freezes the draw result too", "throws when a caller writes to the returned copy, leaving the source intact", "is a copy: later mutation of the source board does not leak into the read". Not testable here: the "source of truth over a live notification" half of AC5 is a server-layer concern (no notification code exists in this module), per the scout contract.
    - Extra (not an AC): `createGame` > initial state and RangeError for empty or identical ids.
- **Files changed:** `amplify/shared/game-rules.ts` (new; types, `WINNING_LINES`, `createGame`, `findWinningLine`, `applyMove`, `readAuthoritativeState`).
- **Verification:** `npx tsc -p amplify/tsconfig.json --noEmit` clean; `npx eslint amplify/shared/game-rules.ts` clean. No ampx or AWS command run.
- **Gate-fix (coder, 2026-10-28, condition 2):** `ng test` now discovers `amplify/**/*.spec.ts`. Changes: `angular.json` `projects.*.architect.test.options.include` = `["**/*.spec.ts", "../amplify/**/*.spec.ts"]` (the unit-test builder resolves globs relative to `sourceRoot` = `src`, so a plain `amplify/**` pattern matched nothing; `../amplify` escapes it); `tsconfig.spec.json` `include` gained `"amplify/**/*.spec.ts"` so the specs are type-checked with the spec tsconfig. `vitest.config.ts` unchanged (generated-file coverage excludes kept). Result: `npx ng test --watch=false` -> 2 files, 86 tests pass; `--coverage` -> amplify/shared/game-rules.ts statements 100% (33/33), branches 100% (40/40), functions 100% (5/5), lines 100% (32/32); overall 100%. No spec or production file touched.
- **Contract surface:** no schema change; no handoff-contract entry.
- **Handoff Notes:** `PlayerId` is trusted input; the future server layer must derive it from a verified identity. `readAuthoritativeState` has no in-sample consumer by design (public read API for the server layer). `ng test` discovery of `amplify/shared/*.spec.ts` confirmed after the gate-fix. Spec amendment proposals (spec_writes off, operator decides): tester spec should name the `angular.json` test `include` for `amplify/**` specs; both specs say `wopr.yml` where the repo uses `kitt.yml`.

---

## Key Files

- `requirements/` (REQs, `design-standard.md`, `blocklist.json`)
- `specs/coder-spec.md`
- `specs/tester-spec.md`
- `amplify/data/resource.ts`
- `AUDIT_REPORT.md`
