---
req_id: REQ-ARC-3
generated_at: 2026-10-28T00:00:00Z
files_touched:
  - amplify/shared/game-rules.ts
  - amplify/shared/game-rules.spec.ts
class_inventory:
  - name: PlayerId
    file: amplify/shared/game-rules.ts
    signature: "export type PlayerId = string;"
  - name: Mark
    file: amplify/shared/game-rules.ts
    signature: "export type Mark = 'X' | 'O';"
  - name: Cell
    file: amplify/shared/game-rules.ts
    signature: "export type Cell = Mark | null;"
  - name: Board
    file: amplify/shared/game-rules.ts
    signature: "export type Board = readonly Cell[];"
  - name: WinningLine
    file: amplify/shared/game-rules.ts
    signature: "export type WinningLine = readonly [number, number, number];"
  - name: GameResult
    file: amplify/shared/game-rules.ts
    signature: "export type GameResult = { readonly outcome: 'win'; readonly winner: Mark; readonly winnerId: PlayerId; readonly line: WinningLine } | { readonly outcome: 'draw' };"
  - name: GameState
    file: amplify/shared/game-rules.ts
    signature: "export interface GameState { readonly board: Board; readonly turn: Mark | null; readonly participants: { readonly X: PlayerId; readonly O: PlayerId }; readonly result: GameResult | null; }"
  - name: Move
    file: amplify/shared/game-rules.ts
    signature: "export interface Move { readonly playerId: PlayerId; readonly cell: number; }"
  - name: MoveRejection
    file: amplify/shared/game-rules.ts
    signature: "export type MoveRejection = 'not_a_participant' | 'game_finished' | 'not_your_turn' | 'invalid_cell' | 'cell_occupied';"
  - name: MoveOutcome
    file: amplify/shared/game-rules.ts
    signature: "export type MoveOutcome = { readonly ok: true; readonly state: GameState } | { readonly ok: false; readonly reason: MoveRejection };"
package_structure: |
  amplify/shared/                       (directory does not exist today; created by this REQ)
    game-rules.ts                       production: types, WINNING_LINES, createGame,
                                        findWinningLine, applyMove, readAuthoritativeState
    game-rules.spec.ts                  Vitest, co-located with the module, runs in Node
  No other file is touched. amplify/data/resource.ts is NOT changed (no schema change).
  No angular.json, vitest.config.ts, tsconfig, or package.json change is expected.
---

## Discovery notes

**Baseline.** REQ-ARC-3 is pending. Nothing is built: `amplify/shared/` is absent, and `amplify/data/resource.ts` holds only the `Placeholder` model. Every file in this REQ is net-new.

**Existing test pattern.** The only spec is `src/app/app.component.spec.ts`. It uses Angular `TestBed`, so `ng test` runs the Angular unit-test builder in a DOM-like environment. Angular's default is not guaranteed to be Node. See "Vitest in Node" below.

### Module decisions (proposed names; the coder spec has no naming rules for this module)

- File: `amplify/shared/game-rules.ts`. One file. The Lambdas import it later. Signatures below are binding for the coder.
- Board index: `0..8`, row-major (`index = row * 3 + col`). Win lines are the 8 triples of indices.
- Marks: `'X'` moves first. Seats are `participants.X` and `participants.O`.
- Player identity: `PlayerId` is a plain string compared with `===`. The module trusts the id it receives. The server layer must derive it from a verified identity (see Handoff Notes).

### Function contract

```ts
export const WINNING_LINES: readonly WinningLine[];   // exactly 8 entries: 3 rows, 3 cols, 2 diagonals

export function createGame(participants: { readonly X: PlayerId; readonly O: PlayerId }): GameState;
// Empty board, turn 'X', result null. Recommended: throw RangeError when either id is '' or X === O.
// Not an AC, so at most one test if implemented.

export function findWinningLine(board: Board): { readonly mark: Mark; readonly line: WinningLine } | null;
// Scans WINNING_LINES in array order; returns the first all-same non-null line, else null.

export function applyMove(state: GameState, move: Move): MoveOutcome;
// Pure. Never mutates `state` or `move`. Returns a new GameState on success.
// On rejection returns { ok: false, reason } and NO state. The caller keeps its stored state.

export function readAuthoritativeState(state: GameState): GameState;
// Pure. Returns a deep-frozen copy of board, turn, participants, and result.
// Mutating the returned value must not change `state`.
```

### State invariants

- `turn` is `null` if and only if `result` is non-null.
- A win sets `result = { outcome: 'win', winner, winnerId, line }`, where `winnerId = participants[winner]` and `line` is the matching `WINNING_LINES` entry.
- A draw sets `result = { outcome: 'draw' }`. This happens only when the board is full and `findWinningLine` returns null.
- A move that completes a line on the 9th cell is a win, not a draw. The win check runs before the draw check.

### applyMove check order (first failure wins)

1. `not_a_participant`: `move.playerId` matches neither `participants.X` nor `participants.O`. This runs first so outsiders learn nothing about the game's status.
2. `game_finished`: `result !== null`.
3. `not_your_turn`: `participants[turn] !== move.playerId`.
4. `invalid_cell`: `!Number.isInteger(cell) || cell < 0 || cell > 8`.
5. `cell_occupied`: `board[cell] !== null`.

On success: place the mark, then `findWinningLine`. If a line exists, set the win result and `turn = null`. Otherwise, if no `null` cell remains, set the draw result and `turn = null`. Otherwise flip `turn`.

### Acceptance-criteria map (planned functions to tests)

| AC | Production function(s) | Tests the tester writes |
|---|---|---|
| AC1 | `applyMove` (checks 3, 4, 5; success path) | Turn owner moves to an empty cell: ok, board updated, turn flips. Wrong-turn participant: `not_your_turn`. Occupied cell: `cell_occupied`. Cells `-1`, `9`, `1.5`, `NaN`: `invalid_cell`. Every rejection leaves the input state deep-equal to a pre-call snapshot. |
| AC2 | `applyMove` (check 1) | Outsider on a fresh game, on an in-progress game, and on a finished game: `not_a_participant`, state unchanged. Case-different id (`'alice'` vs `'Alice'`): `not_a_participant`. |
| AC3 | `findWinningLine`, `applyMove` (win/draw branch) | `it.each` over all 8 `WINNING_LINES` for both marks (16 cases): `findWinningLine` returns that line and mark, and `applyMove` yields `result.outcome === 'win'` with the right `winner`, `winnerId`, and `line`. Full board with no line: `draw`, `turn === null`. Recommended draw sequence (X moves first): X0, O1, X2, O4, X3, O5, X7, O6, X8. Ends full with no line. Win on the 9th move: a win, not a draw. |
| AC4 | `applyMove` (check 2) | After a win and after a draw, a move by either participant to an empty cell: `game_finished`, state unchanged. |
| AC5 | `readAuthoritativeState`, plus `applyMove` for the rejection case | Returned fields equal the source's fields. Mutating the returned copy does not change the source (`Object.isFrozen` on the copy, and a strict-mode write throws). After a rejected move, the read equals the pre-move state. After each accepted move, the read reflects the new state. The notification-precedence half of AC5 belongs to the server layer and is out of scope here. |

## Test coverage gaps

- **Nothing covers game logic.** No spec under `amplify/` exists. `src/app/app.component.spec.ts` covers only the shell title.
- **Every new file is a gap until the tester writes it.** That covers `game-rules.ts` and `game-rules.spec.ts`.
- **Per-line coverage matters.** `findWinningLine` branches on each line. LRN-2026-08-22-i applies: test all 8 lines per mark, not one representative line. Line coverage alone cannot prove the win-line table is correct.

## Vitest in Node (answers the config question)

- **Root `npx vitest run`.** `vitest.config.ts` sets only `test.coverage.exclude`. It has no `include`, so Vitest's default `**/*.{test,spec}.?(c|m)[jt]s?(x)` applies. That default reaches `amplify/shared/game-rules.spec.ts`. The environment is unset, so the default is `node`. The root command works for `amplify/` files.
- **`ng test`.** The `test` target uses `@angular/build:unit-test` with `runnerConfig: vitest.config.ts`. The builder's default spec discovery is expected to be `**/*.spec.ts` under the project root (the root here is `""`), so the new spec should be found. This is not verified from source. The tester must confirm it on the first `ng test` run. If the spec is not listed, the fix is an `include` entry in the `test` target of `angular.json`, and `angular.json` then joins `files_touched`. Do not add it speculatively.
- **Environment directive.** Because the Angular builder may default to a DOM environment (the existing `TestBed` spec suggests it does), make the spec's first line `// @vitest-environment node`. This keeps the rules tests in Node regardless of runner. It is a Vitest directive, not a process comment.
- **Typecheck.** `amplify/tsconfig.json` has `"include": ["./**/*.ts"]`, so it covers `amplify/shared/*.ts` and the spec. `npx tsc -p amplify/tsconfig.json --noEmit` checks both. The root `tsconfig.spec.json` includes only `src/**`, so it does not cover these files. That is expected.
- **Imports.** The spec imports `describe`, `it`, `expect` from `'vitest'` explicitly. Do not rely on globals; `amplify/tsconfig.json` types only `node`.
- **Lint.** `angular.json` lint patterns include `amplify/**/*.ts`, so `ng lint` covers both files.

## Contract surface (api_contract)

- **No schema change.** The operator scoped REQ-ARC-3 to a pure rules module. `amplify/data/resource.ts` is not changed. The `Placeholder` model and `defineData` stay as they are.
- **No operation consumed.** No query, mutation, or subscription is needed for REQ-ARC-3. No `api_contract` JSON Pointer or GraphQL reference applies to this REQ.
- **No handoff-contract entry.** Gate 4 (single project, no handoff contract) is satisfied. Sandbox deploy and `ampx` are out of scope and must not run.
- **Future operations (not blockers).** The server Lambdas will later need a move mutation and a game-state read or subscription. Those belong to the REQ that adds them, not to this one.

## Handoff Notes

1. **Verdict ALIGNED.** The baseline and the codebase agree. REQ-ARC-2 is pending, which the 2026-10-28 intake accepts. It is not a blocker.
2. **Config mismatch, recorded.** `kitt.yml` sets `project.target_source_root` and `project.test_root` to `src/app`. This REQ lives in `amplify/shared/`, which is outside both paths. Agents must not infer the REQ's location from those keys. This follows the operator's scope.
3. **Spec naming drift.** `specs/coder-spec.md` and `specs/tester-spec.md` refer to `wopr.yml`. The repo's authoritative file is `kitt.yml`, and its keys are used here. `spec_writes` is false, so the coder must not amend either spec. The coder spec's Source Layout has no row for `amplify/shared/`. Leave it alone; the contract documents the location.
4. **Coder spec anti-patterns.** No REQ numbers, AC IDs, dates, or audit narratives in product source comments. Put the AC-to-test map in the tester log, not in `game-rules.ts`. Test titles should describe behavior.
5. **Identity trust (advisory for the future server REQ).** `PlayerId` is trusted input to this module. A Lambda that calls `applyMove` must take the id from a verified identity (for example, a verified token claim), not from a request-body field. This is the trust-model lesson in LRN-2026-08-24-c. It is not in REQ-ARC-3's ACs, so the module does not enforce it.
6. **Learnings applied.** The learnings file is advisory and its entries come from other projects (arcade-web, arcade-api), not this sample. Applied: LRN-2026-08-22-i (test every win line at `findWinningLine`, since it branches per line) and LRN-2026-08-22-c (the enumeration above is complete for supporting files). LRN-2026-08-22-a applies in reverse: `readAuthoritativeState` has no in-sample consumer. The auditor should treat it as a deliberate public read API for the server layer, not dead code, and the tester must test it directly.
7. **Ambiguities resolved in this contract.** Rejection order (participant check first). `turn` is `null` when finished. A win on the last cell is a win. Board is row-major `0..8`. Rejections return no state.
8. **Open verification (tester).** The `ng test` discovery of `amplify/shared/*.spec.ts` is expected from the builder defaults but not verified. The first run should list the spec. The fallback is the `angular.json` `include` change above.
9. **Scout did not run tests, builds, lint, or ampx.** Read-only except for the tracking doc gap table and this contract.
