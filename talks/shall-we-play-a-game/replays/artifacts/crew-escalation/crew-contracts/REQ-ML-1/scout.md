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
    signature: "export class MissionList { protected readonly missions: Signal<Mission[] | undefined>; protected readonly filter: WritableSignal<StatusFilter>; protected readonly visible: Signal<Mission[]>; }"
  - name: StatusFilter
    file: src/app/missions/mission-list.ts
    signature: "export type StatusFilter = 'all' | 'open' | 'done';"
package_structure: |
  Feature code stays under src/app/missions/ (flat, no new subdirectories).
  - mission-list.ts: existing MissionList component (OnPush, inject(), toSignal over MissionsService.listMissions()). Add the StatusFilter type, a filter signal (default 'all'), and a computed visible list derived from the single toSignal result. Do not add a second listMissions() call.
  - mission-list.html: keep the existing @let / @if / @else chain. The filter control and count line belong inside the non-empty @else branch, so they are absent for the empty-array case (criterion 6) and absent during loading.
  - mission-list.css: styles for the filter control and count line only; reuse existing class conventions.
  - mission-list.spec.ts: extend the existing spec. Keep the four existing tests; add tests for criteria 1 through 7. Import Mission from '../../api' (generated types); no hand-written copies.
  No new files outside these four. src/api/ and api/openapi.json are read-only for this REQ.

---

## Requirements Status

- REQ-ML-1 baseline status: `⏳ Pending` (tracking document, Requirements Baseline). Approved by the operator as written.
- Current state: not started. No filter control, count line, or filter-related code or tests exist in src/app/missions/.
- Gap Analysis verdict: **ALIGNED**. Written to the Gap Analysis (Latest Session) table, with "Last run" set to 2026-10-27.

## Relevant File Paths

- Component: `src/app/missions/mission-list.ts`, `src/app/missions/mission-list.html`, `src/app/missions/mission-list.css`.
- Tests: `src/app/missions/mission-list.spec.ts` (only spec in the feature folder; `src/app/app.spec.ts` covers the masthead only and is not touched).
- Generated client (read-only): `src/api/models.ts` (MissionStatus, Mission, MissionStatusUpdate), `src/api/missions.service.ts` (MissionsService.listMissions, GET /api/missions), `src/api/index.ts` (barrel). Do not edit.
- Contract (read-only): `api/openapi.json`.
- Requirement: `requirements/REQ-ML-1.md`.
- Layers: no service, store, route, or model layer exists for missions beyond the generated client. Routes are in `src/app/app.routes.ts` but the mission list is not wired through a feature route file in this REQ's scope; the coder should not add one.

## Contract and Legacy Schema References

Contract: `api/openapi.json` (OpenAPI 3.1.0, info.version 1.2.0). Pointers below are JSON Pointers into that file (`/` escaped as `~1`).

- Operation used by the REQ: `listMissions`, GET /api/missions. Pointer: `/paths/~1api~1missions/get`. Response 200 schema is an array of Mission: `/paths/~1api~1missions/get/responses/200/content/application~1json/schema`.
- Mission model: `/components/schemas/Mission`. Required keys: id, title, status, priority. Status property: `/components/schemas/Mission/properties/status` (`$ref` to MissionStatus).
- Status values (the filter's domain): `/components/schemas/MissionStatus/enum` = `["open", "done"]`. Matches generated `MissionStatus = 'open' | 'done'` in `src/api/models.ts`. Consistent; no drift.
- Not used by this REQ: `updateMissionStatus`, PATCH `/api/missions/{id}` (`/paths/~1api~1missions~1{id}/patch`), `/components/schemas/MissionStatusUpdate`. The REQ forbids API changes.
- `uniqueItems: true`: none in the contract. No Set-typed containers; arrays are plain `Mission[]`.
- No operation the REQ needs is missing from the contract. No BLOCKER.
- Legacy schema: not applicable (no legacy-migration block in kitt.yml).

## Test Coverage Gaps

`src/app/missions/mission-list.spec.ts` (existing, 4 tests):
- Covered: loading row before response; one `li.mission` per mission; `done` class on done rows; `.empty` shown for an empty array.
- Not covered (all of criteria 1 through 7): filter control presence and its three options; "All" default selection; Open and Done filtering; count line text (including the 0-match case); "No missions match this filter." text; empty-array case with no filter control; no second HTTP request on filter change.
- `src/app/app.spec.ts`: masthead only; no impact.
- No coverage provider is installed (tester spec: record `coverage: n/a (no provider)`).

## Handoff Notes

1. **Verdict ALIGNED.** Baseline and code agree (REQ-ML-1 pending, nothing implemented). No REQ state change, so no baseline row or requirements file was edited.
2. **Date anomaly.** implementation-tracking.md "Last updated" and the REQ-ML-1 review note both say 2026-10-28, which is after today's date (2026-10-27). Operator should confirm; left unchanged.
3. **Fetch-once (criterion 7).** `MissionList` calls `listMissions()` once in a field initializer via `toSignal`. Derive the filtered list with `computed()` from that signal and the filter signal. Do not call the service again on filter change.
4. **Empty-array branch (criterion 6).** The current template's `list.length === 0` branch must stay as is, with the filter control only in the else branch. The coder should not render the control above the `@if`.
5. **Zero-match count (criterion 5).** The count line must still render when the filtered list is empty ("Showing 0 of M missions"), so put it outside the inner list branch and show "No missions match this filter." in place of the `<ul>`.
6. **Literal count text (criterion 4).** Use the exact text "Showing N of M missions", including for N or M equal to 1 (no pluralisation). This is a literal-text acceptance criterion.
7. **Filter control (criterion 1).** The REQ does not name the control type. A native `<select>` with three `<option>` elements (values all/open/done, labels All/Open/Done) is the most literal match; "All" should be the default. Accessibility label on the control is at coder discretion. If the control is a form, the coder spec prefers signal-based forms, but a plain signal-bound `<select>` needs no forms module.
8. **Loading state.** Criterion 1 does not say whether the filter shows while loading. Recommendation: render it only in the loaded branch (no M to count yet). Confirm with operator if they want it visible during loading.
9. **Order (criterion 2).** The contract's 200 response description says "newest first". Filtering must preserve the array order it receives; do not sort.
10. **Not triggered: LRN-2026-08-21-c.** No codegen or openapi-typescript run is needed, so the TypeScript 5 peer issue does not apply. Do not run `npm run generate-api`.
11. **Spec and doc drift (spec_writes is off; flagged only, not edited):**
    - `specs/coder-spec.md` says component-scoped SCSS; the project uses `.css` (`styleUrl: './mission-list.css'`). Proposal: change the coder spec to match, or note CSS as the project exception.
    - `specs/coder-spec.md` and `specs/tester-spec.md` name test files `<name>.component.spec.ts`; the project uses `mission-list.ts` / `mission-list.spec.ts`. Coder and tester should follow the existing `mission-list.spec.ts` naming. Proposal: update the spec examples.
    - `specs/tester-spec.md` refers to `IMPLEMENTATION_TRACKING.md`; the file is `implementation-tracking.md`. Proposal: fix the reference.
    - `src/api/README.md` says `npm run generate-api` regenerates the client, but the script in `package.json` only echoes a message. Out of scope for this REQ (no API change); operator should fix or document it.
12. **Gate tooling.** The existing Vitest (^5.0.0) and jsdom (^30.0.0) setup is sufficient. No manifest changes are needed, so package.json is not in files_touched.
13. **Single project.** Not workspace mode; no also_writes entries and no cross-member reads.
