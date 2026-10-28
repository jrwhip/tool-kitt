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
> **Session structural context (2026-10-28 session, REQ-ML-1):** none.
> **Optional hooks (prompt-log, git-guard):** declined by operator; not registered.

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
| REQ-ML-1 | Filter the mission list by status (All / Open / Done) with a "Showing N of M missions" count | ✅ Implemented | Coverage gate passed 2026-10-28 (orchestrator re-verified). REQ review: approved 2026-10-28, 1 round. models: coder/auditor opus (high, scout contract: 4 files); scout haiku, tester sonnet |


---

## Gap Analysis (Latest Session)

Populated at the start of every new crew session by the scout agent. The scout compares the Requirements Baseline above against the current implementation state and fills this table. Overwritten on each gap-analysis pass; not appended.

**Last run:** 2026-10-27 (scout, `gap_analysis`, target REQ-ML-1). Verdict: `ALIGNED`. Row since updated by the orchestrator: coverage gate 2026-10-28, audit BLOCKED 2026-10-28.

| REQ ID | Baseline status | Current state | Gap | Next action | Owner agent |
|---|---|---|---|---|---|
| REQ-ML-1 | ✅ Implemented | Implemented 2026-10-28. `src/app/missions/mission-list.{ts,html,css}` add the All/Open/Done filter, the "Showing N of M missions" count line, and the no-match text. The status values `open` / `done` are hard-coded in `mission-list.ts` and match the contract's `/components/schemas/MissionStatus/enum`. `mission-list.spec.ts` covers criteria 1–7 (15/15 suite tests pass). Coverage gate passed 2026-10-28. Audit 2026-10-28: BLOCKED (B1, order fixture). | AC2/AC3 order tests cannot detect a priority sort (audit B1) | Blocker fix: change the fixture order (awaiting operator classification) | tester |

**Gap summary:**

- **In sync:** 1 REQ matches the baseline status (REQ-ML-1).
- **Behind baseline:** 0 REQs have regressed or have discovered gaps since the baseline was set.
- **Ahead of baseline:** 0 REQs are further along than the baseline records.
- **Drift:** 0 REQs where implementation diverges from the spec or the requirements source.
- **New findings:** 0 REQs the scout discovered that were not in the baseline.

The gap-analysis table drives the next crew run's work selection. A `🔄 In Progress` row with a concrete coverage gap becomes a tester-agent work item. A `Drift` becomes a coder-agent work item. `New findings` become scout work items to formalize into REQs before anyone writes code.

---

## Current Implementation Log

Append-only log of significant implementation events. Each entry is dated and points at the REQs it covers, the files changed, and any open follow-ups.

### 2026-10-27 - REQ-ML-1 (status filter for the mission list)

- **REQs covered:** REQ-ML-1
- **Files:** `src/app/missions/mission-list.ts` (added `StatusFilter` type, `filterOptions`, `filter` signal defaulting to `'all'`, `visible` computed over the single `toSignal(listMissions())` result, `onFilterChange` handler), `src/app/missions/mission-list.html` (native `<select class="status-filter">` with All/Open/Done options, `p.count` "Showing N of M missions", `p.no-match` "No missions match this filter."; all inside the non-empty branch only), `src/app/missions/mission-list.css` (toolbar, filter, count, no-match styles)
- **Tests:** none by coder (tester owns `src/app/missions/mission-list.spec.ts`). Tester (2026-10-27): extended `mission-list.spec.ts` with 9 filter tests in `describe('status filter (REQ-ML-1)')` plus 1 fetch-count test in `describe('MissionList fetch count (REQ-ML-1)')`; fixtures typed from `Mission` in `src/api`.
- **Coverage status:** coverage_status: coverage: n/a (no provider) / static_analysis: ng build strict / gate: PASS (ng test: 2 files, 15 tests passed; ng build exit 0)
- **Static-analysis note (2026-10-28, corrected after audit W1):** at the gate the orchestrator flagged the tester's `ng build strict` record as unsupported, because `tsconfig.json` does not set `strict` or `strictTemplates`. That flag was wrong. TypeScript 6 and Angular 22 enable both unless they are set to `false`, and the auditor confirmed a plain `ng build` rejects strict violations (LRN-2026-10-28-a). The tester's record stands. The orchestrator's extra `ngc` strict check (`/tmp/ml-strict-check/tsconfig.strict.json`, outside the repo) also ran clean. No follow-up needed.
- **Audit (2026-10-28):** BLOCKED. One open blocker, B1 (tester): the order fixture can't detect a priority sort. See `AUDIT_REPORT.md`.
- **Criterion to test map:** AC1 'renders one filter control with exactly All, Open, Done options, All selected first'; AC2 'lists every mission in API order with All selected' and 'returns to the full list when switching back to All'; AC3 'lists only open missions...', 'lists only done missions...'; AC4 'shows "Showing N of M missions" for each filter'; AC5 'shows the no-match text and a zero count...'; AC6 'shows the empty-state text and no filter control for an empty array'; AC7 'sends no new HTTP request when the filter changes' and 'calls MissionsService.listMissions exactly once across filter changes'; AC8 full `ng test` run green; AC9 the tests above; AC10 `git status` shows no change under `src/api/` or to `api/openapi.json`.
- **Spec version at this commit:** `api/openapi.json @ 1.2.0`
- **Notes:** Coder build `ng build` exit 0; pre-existing suite `ng test` 2 files / 5 tests passed. No change to `src/api/` or `api/openapi.json`; API surface not touched, so no handoff contract entry. Filter control and count line render only in the loaded, non-empty branch (orchestrator decision). Filtering preserves API order; no re-fetch on filter change. Hooks for tests: `select.status-filter` (option values `all`/`open`/`done`), `p.count`, `p.no-match`, `p.empty`, `li.mission`.

---

## Key Files

Files the scout and auditor should always be aware of when assessing state:

- [STACK: path to requirements source — extracted-requirements document for migrations, or project-defined location otherwise]
- [STACK: path to coder spec]
- [STACK: path to tester spec]
- [STACK: path to schema or DDL file]
- [STACK: path to frontend handoff contract; in a KITT workspace the backend member's, e.g. <workspace_root>/<backend.path>/frontend-handoff-contract.md]
- [STACK: path to the audit report]
