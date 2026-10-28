# Mission Log - Implementation Tracking

> **For pack users:** this is a skeleton for the implementation-tracking document. The scout agent reads it to know current state. The coder agent marks a REQ `🔄 In Progress`; only the orchestrator flips it to `✅ Implemented`, after the coverage gate passes. The tester agent updates it (if the tester spec requires) to reflect test coverage state. The auditor agent blocks merge if this document drifts from reality.
>
> Every REQ ID from the project's requirements source appears here with a status. For legacy migrations, the requirements source is the extracted-requirements document populated by the scout in `deep_analysis` mode. For non-migration projects, the source is whatever the project uses to define REQs (feature backlog, ticket system, written spec). No REQ is silently omitted. Out-of-scope items appear with `❌` and a reason.

---

# Mission Log - Implementation Tracking

> **Last updated:** 2026-10-28 (baseline populated from requirements/)
> **Scope:** Frontend only. The Mission Log API is a separate service; this app consumes it through the generated client.
> **Status legend:** `⏳ Pending`, `🔄 In Progress`, `✅ Implemented`, `❌ Out of Scope`
> **Spec version pinned:** `api/openapi.json @ 1.2.0`
> **Generator version pinned:** `openapi-generator-cli 7.21.0`
> **Migration Context summary:** Net-new project; no structural changes this session.
> **Session structural context (2026-10-28 session, REQ-ML-1):** none. Optional hooks (prompt-log, git-guard): declined by operator, none registered. `spec_writes`: off.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Angular 22 (standalone components, signals, OnPush) / TypeScript 6 |
| Build | Angular CLI (`ng build`) / npm |
| API contract | OpenAPI 3.1 at `api/openapi.json`, consumed via generated client in `src/api/` |
| Testing | Vitest through `ng test` |
| Styling | Component-scoped CSS |

---

## Requirements Baseline

Every REQ ID from the project's requirements source. For legacy migrations, this is populated from the extracted-requirements document. For non-migration projects, populate from whatever source the project uses (feature backlog, written spec, ticket system). Every row has a status. Out-of-scope items get a reason in Notes.

| REQ ID | Description | Status | Notes |
|---|---|---|---|
| REQ-ML-1 | Filter the mission list by status (All / Open / Done) with a "Showing N of M missions" count | ✅ Implemented | REQ review: approved 2026-10-28, 1 round. Coverage gate passed 2026-10-27 (orchestrator-verified: build PASS, suite 17/17, criteria 1-7 traced; static analysis = strict `ng build`, no lint target configured; line/branch coverage not measurable, no coverage provider installed). |


---

## Gap Analysis (Latest Session)

Populated at the start of every new crew session by the scout agent. The scout compares the Requirements Baseline above against the current implementation state and fills this table. Overwritten on each gap-analysis pass; not appended.

**Last run:** 2026-10-27 (gap_analysis, REQ-ML-1). Verdict: `ALIGNED`.

| REQ ID | Baseline status | Current state | Gap | Next action | Owner agent |
|---|---|---|---|---|---|
| REQ-ML-1 | ✅ Implemented | Implemented. Status filter (native select, All/Open/Done, `filter` signal + `visible` computed), "Showing N of M missions" count line, and `.no-match` text in `src/app/missions/`. Empty API array renders only the existing `.empty` branch (no filter, no count line; orchestrator decision). Single fetch via `toSignal(listMissions())` preserved. 12 new tests in `mission-list.spec.ts` cover criteria 1-7; suite 17/17. | None for REQ-ML-1 criteria. Follow-ups (not gaps): REQ silent on count line for empty array; no coverage provider or lint target configured. | None. Audit UNBLOCKED 2026-10-27 (AUDIT_REPORT.md: 0 blockers, 5 warnings) | — |

**Gap summary:**

- **In sync:** 1 REQ matches the baseline status (REQ-ML-1, Implemented after the coverage gate on 2026-10-27; scout's pre-implementation verdict was ALIGNED at Pending).
- **Behind baseline:** 0 REQs have regressed or have discovered gaps since the baseline was set.
- **Ahead of baseline:** 0 REQs are further along than the baseline records.
- **Drift:** 0 REQs where implementation diverges from the spec or the requirements source.
- **New findings:** 0 REQs the scout discovered that were not in the baseline. Open questions on REQ-ML-1 (empty-state count line, plural wording) are recorded in the scout contract Handoff Notes, not as new REQs.

The gap-analysis table drives the next crew run's work selection. A `🔄 In Progress` row with a concrete coverage gap becomes a tester-agent work item. A `Drift` becomes a coder-agent work item. `New findings` become scout work items to formalize into REQs before anyone writes code.

---

## Current Implementation Log

Append-only log of significant implementation events. Each entry is dated and points at the REQs it covers, the files changed, and any open follow-ups.

### 2026-10-27 - REQ-ML-1 (coder)

- **REQs covered:** REQ-ML-1
- **Files:** src/app/missions/mission-list.ts, src/app/missions/mission-list.html, src/app/missions/mission-list.css
- **Tests:** none written by coder (tester owns mission-list.spec.ts)
- **Coverage status:** (empty; tester to fill)
- **Spec version at this commit:** `api/openapi.json @ 1.2.0`
- **Notes:** (Coverage status filled in the tester entry below.) `npm run build` passes; `npm test` passes (5 tests, 2 files, pre-existing). Single fetch preserved (filter is a signal; visible list is a computed). Empty API array renders only the `.empty` branch (no select, no count line), per orchestrator decision. No-match text uses new class `no-match`. Not marked Implemented; orchestrator does that after the gate.

### 2026-10-27 - REQ-ML-1 (tester)

- **REQs covered:** REQ-ML-1
- **Files:** src/app/missions/mission-list.spec.ts
- **Tests:** `ng test --no-watch`: 2 files, 17 tests passed, 0 failed (4 pre-existing + 12 new in `MissionList > status filter` + 1 app.spec).
- **Coverage status:** line n/a / branch n/a (not measurable: `ng test --coverage` requires `@vitest/coverage-v8` or `-istanbul`, not installed; no dependency added) / static_analysis: PASS (no `ng lint` target configured; `ng build` with strict TS passed) / gate: PASS (traceability: criteria 1-7 each map to named tests below; suite green)
- **Criterion map** (all in mission-list.spec.ts, describe `MissionList > status filter`):
  - 1: "renders exactly one filter control with options All, Open, Done (criterion 1)"; "selects All on first render (criterion 1)"
  - 2: "lists every mission in API order with All selected (criterion 2)"; "returns to the full list when All is re-selected (criterion 2)"
  - 3: "lists only open missions when Open is selected"; "lists only done missions when Done is selected"
  - 4: "shows the count line for each filter (criterion 4)"
  - 5: "shows the no-match text and a zero count when the filter matches nothing"; "does not show the no-match text when missions match"
  - 6: "shows the empty-state text and no filter control for an empty array (criterion 6)" (count-line absence pinned separately as an orchestrator decision, not a criterion)
  - 7: "sends no new request when the filter changes (criterion 7)" (expectNone plus afterEach http.verify)
  - 8: full suite green; 9: this map; 10: no changes under src/api or api/openapi.json (git status clean there).
- **Spec version at this commit:** `api/openapi.json @ 1.2.0`

### [YYYY-MM-DD] - [REQ-ID or feature name]

- **REQs covered:**
- **Files:**
- **Tests:**
- **Coverage status:**
- **Spec version at this commit:**
- **Notes:**

[STACK: add an entry per feature or per REQ, whichever granularity matches how the team works]

---

## Key Files

Files the scout and auditor should always be aware of when assessing state:

- [STACK: path to requirements source — extracted-requirements document for migrations, or project-defined location otherwise]
- [STACK: path to coder spec]
- [STACK: path to tester spec]
- [STACK: path to schema or DDL file]
- [STACK: path to frontend handoff contract; in a KITT workspace the backend member's, e.g. <workspace_root>/<backend.path>/frontend-handoff-contract.md]
- [STACK: path to the audit report]
