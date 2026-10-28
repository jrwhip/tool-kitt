## Audit Report - REQ-ML-1 (Filter the mission list by status)

### Date / Auditor: 2026-10-27 / crew-auditor / Build: PASS (`npm run build`, strict TS) / Test Results: 17 passed, 0 failed (2 files; `npx ng test --no-watch`)

## PR Readiness Verdict: UNBLOCKED

Zero BLOCKERs. Warnings below need operator awareness; none gate the merge.

### BLOCKERS

None.

### WARNINGS

1. **Falsifiability (item 10) not executed.** The sandbox denied writes outside the project tree, so I could not build a throwaway copy and reintroduce a defect. Nothing was mutated in the working tree. Read-through assessment only:
   - Filter pins (`mission-list.spec.ts:99-117`, `:119-126`, `:128-138`) assert exact title lists and exact count strings. A `visible` that ignores the filter (`mission-list.ts:23-26`) would fail them.
   - The criterion 7 pin (`mission-list.spec.ts:158-164`) would fail if `setFilter` re-called `listMissions()`, because `expectNone` and `afterEach http.verify()` would see the request.
   - The criterion 1 default-selection pin (`mission-list.spec.ts:88-92`) is likely vacuous. jsdom selects the first option when none is marked selected, so `select().value === 'all'` and `selectedOptions[0] === 'All'` hold even without the `[selected]="filter() === 'all'"` bindings at `mission-list.html:10`. The operator or crew driver should run the throwaway reintroduction (remove the `[selected]` bindings and check that the test fails, or reorder the options) before relying on it.
2. **Coverage unmeasured (item 3).** No coverage provider is installed (`@vitest/coverage-v8` or `-istanbul`), so the coder-spec gate of line >= 80% / branch >= 70% cannot be evaluated. The tracking doc records "n/a" honestly (`implementation-tracking.md:39`, `:84`), so there is no inflated claim and no honesty BLOCKER. By the orchestrator's note the percentage is a diagnostic and traceability (item 8) gates. Still, a recorded `gate: PASS` rests on a gate that is only partly measurable. Propose installing a coverage provider and a `coverage.exclude` for `src/api/**` as a separate task.
3. **Static analysis is a substitute (item 3).** The coder-spec gate calls for a configured tool (`ng lint` or Sonar). None exists, and strict `ng build` stood in. I re-ran the build and it passes, so the record is not contradicted, but it is not a Quality Gate.
4. **Tracking-doc date inconsistencies.** The header says "Last updated 2026-10-28", REQ review "approved 2026-10-28", and the coverage gate "passed 2026-10-27" (`implementation-tracking.md:11`, `:17`, `:39`). The scout flagged the same header drift. The operator should reconcile it. This is cosmetic, but the tracking doc is the audit trail.
5. **Spec/repo naming drift (carried from the scout, not a REQ-ML-1 defect).** The tester spec names `IMPLEMENTATION_TRACKING.md` and `<name>.component.spec.ts`, and the coder spec says SCSS. The repo uses `implementation-tracking.md`, `mission-list.spec.ts`, and `.css`. The specs should be reconciled to the repo.

### SUGGESTIONS

- `mission-list.ts:30-36` `setFilter` falls back to `'all'` on any unknown value. This is fine, but an invalid-value test would pin it.
- The scout inventory lists `setFilter` without a visibility modifier. The code has it `protected`, which is reasonable and consistent with the other members.
- The unfilled template entry at `implementation-tracking.md:96-105` is pre-existing skeleton text and can be removed.
- Plural wording "Showing 1 of 1 missions" follows the REQ literally and is pinned by the tests (`mission-list.spec.ts:125`). Confirm that is intended.

### PASSED

- **1 Traceability (tracking doc):** REQ-ML-1 is Implemented, and the implementation and tests exist. The Gap Analysis row agrees with its status and verdict. The test counts reconcile: 4 pre-existing + 12 new + 1 app.spec = 17.
- **2 Pattern compliance:** standalone component, OnPush, `inject()`, `signal` / `computed` / `toSignal`, new control flow, no FormGroup, no manual `subscribe`, and no hand-written HTTP. `MissionStatus` and `MissionsService` come from the generated client (`mission-list.ts:3`). Fixtures use the generated `Mission` type.
- **4 Spec integrity:** the only endpoint consumed is `GET /api/missions` (`listMissions`), which exists in the contract and the client. There is no API-surface change.
- **5 Handoff contract:** no handoff contract in scope (frontend-only project, no API-surface change).
- **6 Migration Context:** "none", and no contradictions.
- **7 Build/CI lockstep:** the build passes and the test run executes 17 tests. No CI workflow was found to compare against.
- **8 Traceability (criteria to tests, spot-read):**
  - 1: `:81-92`. Option labels are asserted exactly, there is one `select`, and the default is `all` (but see warning 1).
  - 2: `:94-97`, `:112-117`. Titles are compared in API order.
  - 3: `:99-110`.
  - 4: `:119-126`. The count string is asserted for all three filters, including the REQ example, 2 of 3.
  - 5: `:128-144`. The no-match text, "Showing 0 of 2 missions", and zero rows are asserted.
  - 6: `:146-151`. The empty text is asserted and no `select` is rendered. The no-count behavior (`:153-156`) is correctly labelled an orchestrator decision, not a criterion.
  - 7: `:158-164`.
  - 8: the suite is green. 9: criteria 1-7 are covered. 10: see below.
  - Every criterion has at least one test that asserts the criterion's substance.
- **9 Maintainability:** the files are small and simple. The comment-policy grep over `src/app` (`LRN-\d{4}`, `ruling`, `gate-failure`, ISO dates) returned zero hits.
- **10 Criterion 10 via git:** `git status --porcelain src/api api` and `git diff HEAD --stat -- src/api api/openapi.json package.json package-lock.json` are empty. No generated file, contract file, or dependency changed. The generator pin (7.21.0) and spec version (1.2.0) match the tracking-doc header.
- **Scope drift:** the modified files (`mission-list.ts`, `.html`, `.css`, `.spec.ts`) match the scout's `files_touched` exactly. `implementation-tracking.md` is also modified, as expected. The untracked files are `crew-contracts/` and `LEARNINGS.embeddings.npz`.
- **Coverage honesty:** no numeric coverage is claimed, so there is no over-claim.
- **11 Appearance:** not in scope (no `design_spec`). **12 Write scope:** single-project run.

### Resolution Summary

First audit. No prior findings.

### Spec amendments

`spec_writes` is OFF, so nothing was amended. Proposed audit rules:
- Add a rule that default-selection tests for native `<select>` must not rely on first-option defaulting. Assert via a non-first default, or mutate-check the binding.
- Add `vitest.config.ts` coverage and a provider to the tester-spec prerequisites, so the coverage gate is measurable.
- Fix the tester-spec tracking filename and spec-file naming pattern to match the repo.

### Learnings (not persisted)

Not applicable. `append_learnings` was called; see the orchestrator response for the outcome.
