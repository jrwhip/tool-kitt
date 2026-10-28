## Audit Report - REQ-ML-1 (Filter the mission list by status)

### Date / Auditor: 2026-10-28 / crew-auditor / Build / Test Results: `npm run build` exit 0; `npx ng test --no-watch` 2 files, 15 passed, 0 failed

## PR Readiness Verdict: BLOCKED

One BLOCKER: the criterion-2 "API order" pin does not discriminate against a sort-by-priority regression (checklist item 10).

---

### BLOCKERS

**B1. The criterion-2/3 "API order" pin stays green when an ascending-priority sort is reintroduced** (checklist 10, falsifiability). Owner: tester.
- `src/app/missions/mission-list.spec.ts:8-12`: the `MISSIONS` fixture lists missions in API order with priorities 1, 2, 3 and ids m-1, m-2, m-3. That means API order is the same as ascending priority order and ascending id order.
- `src/app/missions/mission-list.spec.ts:95` (AC2) and `:100` (AC3 "in API order") therefore cannot tell API order apart from either of those sorts.
- Evidence: in a throwaway copy I changed `mission-list.ts:32` to `[...(this.missions() ?? [])].sort((a, b) => a.priority - b.priority)`. Result: **15/15 tests passed.** The descending-priority sort was caught (AC2 and AC3 failed), so the pin catches some reorderings, but not the most plausible one.
- Why it matters: criterion 2 requires API order, the REQ body explicitly excludes sorting, the contract returns missions "newest first" (`api/openapi.json:11`), and priority is shown on every row, so a "helpful" priority sort is a realistic regression.
- Fix: reorder the fixture so API order differs from priority, id, and title order (for example priorities 2, 3, 1), then re-run.

### WARNINGS

**W1. The tracking document's "Orchestrator override" rests on a false premise** (checklist 3, static analysis). Owner: orchestrator.
- `implementation-tracking.md:77` claims that because `tsconfig.json` sets neither `strict` nor `strictTemplates`, "plain `ng build` is therefore not the strict build the tester spec assumes." That is wrong for this toolchain:
  - TypeScript 6.0.3 (`node_modules/typescript/lib/typescript.js:22256`, `getStrictOptionValue`) treats `strict` as on unless it is set to `false`.
  - Angular compiler-cli 22.2.3 (`node_modules/@angular/compiler-cli/bundles/chunk-HIDZX47I.js:4669`) returns `this.options.strictTemplates !== false`, so strict templates are also on by default.
- Empirical probe in a throwaway copy: I added an implicit-`any` parameter and `{{ missions().length }}` to the template. Plain `ng build` failed with TS7006 (implicit any) and TS2532 (possibly undefined, in the template).
- So the tester's original record, `static_analysis: ng build strict`, was accurate.
- I re-ran the orchestrator's out-of-band check (`npx ngc -p /tmp/ml-strict-check/tsconfig.strict.json`, which adds extendedDiagnostics as errors) and it is clean.
- The recorded `static_analysis: PASS` is therefore **confirmed**, and this is not a gate failure. The problems are:
  - the tracking doc records an incorrect technical claim;
  - it substitutes an ad hoc command for the spec's check;
  - it asks the operator for an unnecessary follow-up ("enable strict in tsconfig as its own REQ or amend the spec").
- Fix: correct the note to say the plain `ng build` is strict by default under TS 6 / Angular 22. Optionally make `strict` / `strictTemplates` explicit in `tsconfig.json` (operator decision) so the next reader does not draw the same conclusion.

**W2. The Gap Analysis section disagrees with itself and with the code** (checklist 1). Owner: orchestrator (or scout on re-run).
- `implementation-tracking.md:49` says "Last run: 2026-10-27 (scout, `gap_analysis`) ... Verdict: ALIGNED". But the row at `:53` records baseline `✅ Implemented` and "Implemented 2026-10-28". A scout pass dated 2026-10-27 cannot have observed a 2026-10-28 implementation; the row was rewritten after the gate without updating the run metadata.
- The same row says the filter derives its list "from the contract's `/components/schemas/MissionStatus/enum`". The code hard-codes the literals: `src/app/missions/mission-list.ts:6` (`'all' | 'open' | 'done'`), `:21-25`, `:39`. Nothing ties it to the generated `MissionStatus` type (`src/api/models.ts:5`).
- Statuses themselves are accurate in both directions (REQ-ML-1 is implemented and tested); only the narrative and metadata drift.

### SUGGESTIONS

**S1. Derive `StatusFilter` from the generated `MissionStatus` type.** Owner: coder.
- `src/app/missions/mission-list.ts:6` and `:39` duplicate the contract enum. `export type StatusFilter = 'all' | MissionStatus;` would make the compiler flag any status later added to the contract.
- This matches the scout's `class_inventory` signature as written, so it is not drift; I'm raising it as a durability improvement.

**S2. Process ID in a production comment.** Owner: coder.
- `src/app/missions/mission-list.ts:5`: `/** Status filter choices for the mission list (REQ-ML-1). ... */`.
- No mechanical comment-policy shape matched (no `LRN-`, "ruling", "gate-failure", or ISO date in production files). A REQ ID in a doc comment is still process narrative that ages badly; consider dropping `(REQ-ML-1)`.

**S3. A failed `http.verify()` cascades across the suite.** Owner: tester. This predates REQ-ML-1.
- `src/app/missions/mission-list.spec.ts:27` has `afterEach(() => http.verify())`. When it throws, TestBed teardown is skipped, and every later test fails with "Cannot configure the test module when the test module has already been instantiated".
- Seen under the re-fetch mutation: 8 failures, of which only 2 were real AC7 detections.
- Consider `TestBed.resetTestingModule()` safety, or verifying inside each test, so failures point at the cause.

**S4. Scout `class_inventory` omits two members.** Owner: scout.
- The coder added `filterOptions` and `onFilterChange` (`mission-list.ts:21`, `:37`), which are not in `class_inventory`. Both are logged in the tracking doc and stay within `files_touched`. No action needed beyond noting it.

**S5. Spec-to-repo drift the scout already flagged** (spec_writes OFF, so these are proposals; owner: operator):
- coder spec "Component-scoped SCSS" vs actual `.css`;
- `<name>.component.spec.ts` naming vs `mission-list.spec.ts`;
- tester spec `IMPLEMENTATION_TRACKING.md` vs `implementation-tracking.md`;
- tester spec "Specs import from 'vitest' (describe, it, expect, vi)" vs the project's `vitest/globals` setup (`tsconfig.spec.json`). The spec file imports only `vi` and uses globals, as the pre-existing tests do.

**S6. Pre-existing gaps outside REQ scope** (owner: operator):
- There is no error-state handling or test for a failed `listMissions()`. The tester spec's "Every component: handles loading and error states" is unmet, but this predates the REQ and is not in its acceptance criteria; candidate for its own REQ.
- `updateMissionStatus` (`/paths/~1api~1missions~1{id}/patch`) has no consuming app code and no explicit deferred entry in the tracking doc.

### PASSED

- **1. Requirements traceability (statuses).** REQ-ML-1 is `✅ Implemented` and that is true: code and tests are present and green. There are no other REQs in `requirements/`. Narrative issues are in W2.
- **2. Pattern compliance.**
  - `MissionList` keeps `OnPush` (`mission-list.ts:12`), `inject()` (`:15`), `signal`/`computed` (`:28`, `:31`), and the new control flow.
  - No NgModule, no FormGroup, no `subscribe()`, no `document`/`window`.
  - The API is called only through the generated `MissionsService`, once, via `toSignal` (`:18`).
  - Generated files are untouched: `git diff HEAD -- src/api api/openapi.json` is empty and `git status --porcelain` is clean for both paths.
  - Generator pin `openapi-generator-cli 7.21.0` is identical in `kitt.yml`, the tracking header (`implementation-tracking.md:15`), and `src/api/README.md:4`. Spec version 1.2.0 matches `api/openapi.json:3` and the tracking header.
  - Tester anti-patterns: none. Files are `.spec.ts`, there is no `@jest/globals`, no real network (`HttpTestingController`), no snapshots, no `it.skip`, and fixtures are typed from the generated `Mission`.
- **3. Coverage honesty.**
  - Fresh build exits 0 and the fresh suite passes 15/15, matching the recorded "2 files, 15 tests passed".
  - `coverage: n/a (no provider)` is correct; no provider is installed and the specs say not to install one in a feature REQ.
  - `gate: PASS` is accurate. `static_analysis: PASS` is independently confirmed by both the plain strict-by-default `ng build` and the orchestrator's extended-diagnostics `ngc` run (see W1 for the note's wording).
- **4. Spec integrity.** The only operation consumed is `listMissions`, at `/paths/~1api~1missions/get`, which is present in the contract. No new endpoints, no annotation-driven artifacts.
- **5. Handoff contract.** None in scope; the REQ does not touch the API surface.
- **6. Migration Context.** The coder spec says "No structural changes this session"; the tracking doc says "Session structural context ... none". Consistent.
- **7. Build and CI lockstep.** The build config is unchanged. The test target runs 15 real tests (counted). There are no CI workflows (`.github/` holds only `copilot-instructions.md`), so CI lockstep was skipped.
- **8. Criterion-to-test traceability.** I spot-read every test in the map:

  | AC | Test(s) | Verdict |
  |---|---|---|
  | 1 | `spec.ts:86` | Asserts one `select.status-filter`, option labels exactly `['All','Open','Done']`, value `all`, first option selected |
  | 2 | `spec.ts:95`, `:112` | Asserts full title list in order. Discrimination weakness is B1 |
  | 3 | `spec.ts:100`, `:106` | Open and Done subsets |
  | 4 | `spec.ts:119` | Literal "Showing 3/2/1 of 3 missions" |
  | 5 | `spec.ts:128` | No-match text, zero rows, "Showing 0 of 2 missions" |
  | 6 | `spec.ts:136` | Empty-state text, no select, no count, no no-match text |
  | 7 | `spec.ts:144` (`expectNone`) and `spec.ts:155` (`listMissions` spy called once) | Both pins |
  | 8 | Fresh run 15/15, pre-existing tests included | Verified |
  | 9 | Above | Verified |
  | 10 | git verification above | Verified |

  No criterion has zero tests.
- **9. Maintainability.** The coder spec defines no module-size or complexity ceilings; all touched files are small (component 43 lines). The comment-policy mechanical scan (`LRN-\d{4}`, `ruling`, `gate-failure`, ISO dates) over the changed production files found zero hits (S2 is advisory).
- **10. Falsifiability, the pins that held.** Throwaway copy at a gitignored scratch path, removed afterwards; the working tree was verified unchanged.

  | Mutation | Result |
  |---|---|
  | Re-fetch on filter change | Both AC7 pins failed |
  | Done filter returns open missions | AC3, AC4, AC5 failed |
  | Count's M uses the filtered length | AC4, AC5 failed |
  | Filter control rendered in the empty-array branch | AC6 failed |
  | Default filter `'open'` | AC1, AC2, AC4 failed, plus 2 pre-existing tests |
  | Descending-priority sort | AC2, AC3 failed |
  | Ascending-priority sort | **Survived (B1)** |
- **11. Appearance.** Not in scope (no `design_spec`).
- **12. Write scope.** Single-project run. Changes are confined to the scout's `files_touched` (4 files) plus `implementation-tracking.md`; `crew-contracts/` and `LEARNINGS.embeddings.npz` are crew artifacts.

### Resolution Summary

First audit run for this project; no prior report. All findings above are NEW.

### Spec amendments

`spec_writes` is OFF, so I changed no spec. Proposed audit rules for the operator:

1. **Tester spec, Fixtures:** "Order-preservation fixtures must use an API order that differs from every natural sort key the UI exposes (priority, id, title, date). Otherwise an order pin cannot detect a reintroduced sort."
2. **Tester spec, Coverage Gate, static analysis:** "Under TypeScript 6+ and Angular 22+, `strict` and `strictTemplates` default on when absent; plain `ng build` is the strict build unless `tsconfig*.json` sets either to `false`. The auditor confirms by checking for explicit `false`, not for presence."
3. **Coder / tester specs:** fix the drift listed in S5.

### Learnings

Persisted via `append_learnings` to `/tmp/kitt-rec-m_cey5za/mission-log/LEARNINGS.md`: LRN-2026-10-28-a (TS 6 / Angular 22 strict defaults) and LRN-2026-10-28-b (order pins whose fixture order matches a natural sort key).
