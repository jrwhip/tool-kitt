---
req_id: REQ-ML-1
generated_at: 2026-10-27T00:00:00Z
files_touched:
  - src/app/missions/mission-list.ts
  - src/app/missions/mission-list.html
  - src/app/missions/mission-list.css
  - src/app/missions/mission-list.spec.ts
class_inventory:
  - name: MissionList
    file: src/app/missions/mission-list.ts
    signature: "export class MissionList { protected readonly missions: Signal<Mission[] | undefined>; protected readonly filter: WritableSignal<'all' | MissionStatus>; protected readonly visible: Signal<Mission[] | undefined>; setFilter(value: string): void }"
package_structure: |
  Feature code stays in src/app/missions/ (existing component, no new files required).
  - mission-list.ts: keep the existing toSignal(listMissions()) field as the only HTTP call (single fetch). Add a private type alias `type MissionFilter = 'all' | MissionStatus` (MissionStatus imported from '../../api' so the compiler checks the 'open' and 'done' literals against the generated model). Add `protected readonly filter = signal<MissionFilter>('all')` and a `computed` that derives the visible list from missions() and filter, preserving API order (filter only, no sort). Add a handler that maps the select value to filter. No FormGroup or FormControl; a single signal bound to a native select is the established signals pattern.
  - mission-list.html: keep the @let / @if structure. Loading branch and empty-log branch (`.empty`, "No missions on the board.") stay unchanged. In the list branch, render one native <select> with exactly three <option>s labelled All, Open, Done (All selected by default), then the count line "Showing N of M missions", then either the <ul class="missions"> or, when the filtered list is empty, a no-match element using a NEW class (e.g. `no-match`) containing "No missions match this filter.". Do not reuse class `empty` for the no-match text; the existing empty-log test queries `.empty`.
  - mission-list.css: add only rules for the new select, count line, and no-match element. Existing .missions, .mission, .done, .loading and .empty rules stay.
  - mission-list.spec.ts: extend the existing four tests' file with filter tests (criteria 1 through 7). Keep the existing four tests passing. Use HttpTestingController: one expectOne('/api/missions') per test, and expectNone('/api/missions') after changing the filter to prove no new request. Mission fixtures import Mission from '../../api'.
  Not in scope: src/api/ (never edit), api/openapi.json (must not change), app.ts / app.html / app.spec.ts (no change needed).
  No new dependencies. No gate-tooling manifest change is required: package.json already has vitest, jsdom, and @angular/build.
also_writes: []
---

## Discovery notes

### Verdict and baseline
- Gap analysis verdict: ALIGNED. Baseline row REQ-ML-1 is Pending; the code has no filter, count line, or no-match text. Recorded in implementation-tracking.md, Gap Analysis table.
- REQ-ML-1 body in requirements/REQ-ML-1.md matches the fresh body supplied by the orchestrator (ten acceptance criteria).

### Current code (what exists)
- `src/app/missions/mission-list.ts`: class `MissionList`, OnPush, `inject(MissionsService)`, `protected readonly missions = toSignal(this.missionsApi.listMissions())`. Field initializer, so exactly one GET per component instance. No filter state.
- `src/app/missions/mission-list.html`: `@let list = missions();` then `@if (list === undefined)` loading row (`p.loading`, role=status, "Loading missions…"); `@else if (list.length === 0)` empty row (`p.empty`, "No missions on the board." — already exists, criterion 6 text is present today); `@else` `ul.missions` with `li.mission` rows, `[class.done]`, priority span, title span, status span (raw "open"/"done" text).
- No occurrence of "Showing", "No missions match", or any select/radio/form control under `src/` (grep verified).
- `src/app/app.ts` renders `<app-mission-list>` via imports; `app.spec.ts` checks only the h1 masthead. Adding DOM inside MissionList does not affect it.

### Contract (api/openapi.json, version 1.2.0, openapi 3.1.0)
- Operation GET /api/missions, operationId `listMissions`. JSON Pointers:
  - Path: `/paths/~1api~1missions/get`
  - 200 response schema (array): `/paths/~1api~1missions/get/responses/200/content/application~1json/schema`, items `$ref` `#/components/schemas/Mission`.
- Mission schema: `/components/schemas/Mission`; required: `/components/schemas/Mission/required` (id, title, status, priority).
  - status property: `/components/schemas/Mission/properties/status`, `$ref` `#/components/schemas/MissionStatus`.
  - priority: `/components/schemas/Mission/properties/priority` (integer, 1 to 3).
- Status enum: `/components/schemas/MissionStatus`, `{ "type": "string", "enum": ["open", "done"] }`. This matches the REQ's `open` and `done` exactly. No contradiction found.
- `uniqueItems`: none declared anywhere in the document, so no Set-typed containers are generated for this REQ.
- No query parameters or pagination on listMissions. M in "Showing N of M missions" is therefore the array length from the single response.
- Generated client `src/api/models.ts` agrees with the contract: `export type MissionStatus = 'open' | 'done';` and `Mission { id; title; status: MissionStatus; priority: 1 | 2 | 3 }`. `src/api/missions.service.ts` exposes `listMissions(): Observable<Mission[]>` at `/api/missions`.
- The contract description for the 200 response says "newest first". The REQ says "API order" and forbids sorting; the filter must keep the array order as received. No conflict.

### Existing tests (src/app/missions/mission-list.spec.ts)
- Four tests: loading row before response; one `li.mission` per mission (3 fixtures); done rows get `.done`; empty log shows `.empty`.
- Shared fixture MISSIONS: m-1 open P1, m-2 done P2, m-3 open P3. Useful for criterion 3 and 4 examples ("3 returned, 2 open").
- `respond()` helper flushes `/api/missions` then calls detectChanges. `afterEach` runs `http.verify()`.

### Test runner and config
- `npm test` = `ng test`. angular.json test target uses builder `@angular/build:unit-test`. Vitest ^5.0.0 and jsdom ^30.0.0 are in devDependencies.
- No `vitest.config.ts` or `coverage` configuration file exists in the repo root (verified by glob).
- Tests were NOT run by the scout. Criterion 8 status is unverified.

### Subtle points for the coder
- Filter must be derived (computed) from the single toSignal result. Any second subscription or re-call of listMissions() breaks criterion 7.
- Keep `undefined` handling: while loading, no select and no count line.
- Use `<option value="all|open|done">` with labels "All", "Open", "Done". Bind the selected value to the signal so "All" is selected on first render.
- Count text should be "Showing {{ n }} of {{ m }} missions" built so textContent normalizes to the exact string (tests will compare normalized text).

## Test coverage gaps (current state)

### src/app/missions/mission-list.spec.ts
- Covered: loading row, row count, done class, empty-log state.
- Not covered: any filter control, option labels, default selection, filtered lists, count line, no-match state, no-new-request on filter change. All of REQ criteria 1 to 7 are uncovered today (expected for pre-implementation).
- Not covered (pre-existing): HTTP error path. `toSignal` without an error handler rethrows on read if the request fails; no test exercises it.

### src/app/app.spec.ts
- Covered: masthead h1 only. Not affected by this REQ.

### src/api/ (generated)
- No tests, by design. Coverage exclusion is required by tester-spec but cannot be applied (see Handoff Notes).

### src/app/missions/mission-list.ts
- No logic beyond the toSignal field. Logic added by this REQ will be new uncovered code until tests land.

## Handoff Notes

1. Verdict ALIGNED. No baseline row changes were needed, so the Requirements Baseline is untouched. The Gap Analysis table was overwritten with the verified state.
2. Tracking doc header says "Last updated: 2026-10-28", which is after today's date (2026-10-27). Left as-is; operator should check the header.
3. Open question, empty-log count line (criterion 6 vs 4): the REQ does not say whether "Showing 0 of 0 missions" appears when the API returns []. Scout recommends hiding the count line and the filter control in that state (consistent with the existing empty branch and with "no filter control is rendered"). Coder should confirm with the operator or the REQ author before implementing.
   **ORCHESTRATOR OVERRIDE (2026-10-27):** resolved without stopping the run. When the API returns [], render only the existing empty-log branch (`p.empty`, "No missions on the board."): no filter control AND no count line. The count line and filter appear only in the non-empty list branch. This is an orchestrator decision filling a REQ silence, not a REQ criterion; it is surfaced to the operator for REQ clarification after the run. Tests may pin this behavior but must not map it to a numbered acceptance criterion.
4. Plural wording: "Showing 1 of 1 missions" is the literal REQ text. Kept as written; the REQ does not ask for pluralization. Flag only if the operator wants "mission" for N = 1.
5. Naming and convention drift between specs and repo (repo convention wins):
   - tester-spec names the tracking file `IMPLEMENTATION_TRACKING.md`; the actual file is `implementation-tracking.md`.
   - tester-spec test file pattern is `<name>.component.spec.ts`; the repo uses `mission-list.spec.ts`.
   - coder-spec says component-scoped SCSS; the repo uses `.css` (`styleUrl: './mission-list.css'`).
6. Coverage gate cannot be measured as configured. tester-spec requires `src/api/**` excluded in a `vitest.config.ts` `coverage.exclude` list. No such file exists, and angular.json uses `@angular/build:unit-test` with no coverage options. Line and branch numbers (80% and 70%) cannot be recorded until this is resolved. This is not a REQ-ML-1 code change; the orchestrator or operator should decide where the config lives.
   **ORCHESTRATOR NOTE (2026-10-27):** per the crew coverage gate, line/branch coverage is a recorded diagnostic, not a pass metric; traceability (criterion -> named test) is the pass condition. The tester measures coverage with `ng test --coverage` (the `@angular/build:unit-test` builder accepts coverage flags, including excludes, on the command line) and records the numbers, or records why they could not be measured. Do not add a vitest.config.ts for this REQ; that is outside `files_touched`.
7. Pre-existing risk, out of scope for this REQ: `toSignal(listMissions())` has no error handling. A failed request makes reading `missions()` throw. Not required by REQ-ML-1; do not fix inside this REQ unless the operator asks.
8. No contract change is needed. REQ-ML-1 consumes only GET /api/missions. No handoff contract entry is required (frontend-only project). src/api/ and api/openapi.json must not change (criterion 10).
9. No contradictions found between REQ-ML-1 and the contract or code. Status values `open` and `done` match `MissionStatus` exactly.
10. Working tree state at scout time: implementation-tracking.md already had uncommitted changes before this run (git status "M"), and LEARNINGS.embeddings.npz is untracked. The scout edited the working-tree copy of implementation-tracking.md (Gap Analysis section only).
11. LRN-2026-08-21-c (openapi-typescript and TypeScript 6 peers) is not relevant: this REQ adds no dependencies and does not run codegen.
