# [PROJECT NAME] - Implementation Tracking

> **For pack users:** this is a skeleton for the implementation-tracking document. The scout agent reads it to know current state. The coder agent updates it when a REQ transitions from `⏳` to `🔄` to `✅`. The tester agent updates it (if the tester spec requires) to reflect test coverage state. The auditor agent blocks merge if this document drifts from reality.
>
> Every REQ ID from the project's requirements source appears here with a status. For legacy migrations, the requirements source is the extracted-requirements document populated by the scout in `deep_analysis` mode. For non-migration projects, the source is whatever the project uses to define REQs (feature backlog, ticket system, written spec). No REQ is silently omitted. Out-of-scope items appear with `❌` and a reason.

---

# [PROJECT NAME] - Implementation Tracking

> **Last updated:** [YYYY-MM-DD] ([one-line note on what changed])
> **Scope:** [STACK: e.g. API + DB layers only. Auth, email, documents, PDF export deferred.]
> **Status legend:** `⏳ Pending`, `🔄 In Progress`, `✅ Implemented`, `❌ Out of Scope`
> **Spec version pinned:** `[STACK: e.g. backend openapi.json @ 4.2.1, fetched 2026-04-15]`
> **Generator version pinned:** `[STACK: e.g. openapi-generator-cli 7.21.0]`
> **Migration Context summary:** [STACK: one-line summary; full content lives in the requirements source's Migration Context section (extracted-requirements document for migrations; project-defined location otherwise) and the coder spec's Migration Context section. Agents read those files; this field is a pointer, not a source of truth. The label is "Migration Context" for historical reasons; for non-migration projects, treat this as the session's structural context (e.g., "introducing OpenAPI client generation; replacing handwritten HTTP services").]

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | [STACK: e.g. Spring Boot 4.x / Java 21] |
| Database | [STACK: e.g. Oracle (ojdbc11 23.2.0.0)] |
| ORM | [STACK: e.g. Spring Data JPA / Hibernate] |
| Build | [STACK: e.g. Maven] |
| API Docs | [STACK: e.g. springdoc-openapi] |
| Logging | [STACK: e.g. slf4j + custom aspect] |
| Mapping | [STACK: e.g. ModelMapper 3.2.4 (strict, explicit type maps)] |
| Security | [STACK: e.g. Spring Security OAuth2 resource server] |
| Testing | [STACK: e.g. JUnit 5 / Mockito / MockMvc / JaCoCo] |
| Config | [STACK: e.g. AWS Parameter Store + application-local.properties fallback] |

---

## Requirements Baseline

Every REQ ID from the project's requirements source. For legacy migrations, this is populated from the extracted-requirements document. For non-migration projects, populate from whatever source the project uses (feature backlog, written spec, ticket system). Every row has a status. Out-of-scope items get a reason in Notes.

| REQ ID | Description | Status | Notes |
|---|---|---|---|
| REQ-[DOMAIN]-1 | [one-line description] | ⏳ Pending | |
| REQ-[DOMAIN]-2 | [one-line description] | 🔄 In Progress | [who, since when] |
| REQ-[DOMAIN]-3 | [one-line description] | ✅ Implemented | [file references] |
| REQ-[DOMAIN]-4 | [one-line description] | ❌ Out of Scope | [reason and pointer to where it will be addressed] |

[STACK: repeat the table per domain group if the REQ list is large enough that one flat table becomes unwieldy]

---

## Gap Analysis (Latest Session)

Populated at the start of every new crew session by the scout agent. The scout compares the Requirements Baseline above against the current implementation state and fills this table. Overwritten on each gap-analysis pass; not appended.

**Last run:** [YYYY-MM-DD] by scout agent session `[session id or label]`

| REQ ID | Baseline status | Current state | Gap | Next action | Owner agent |
|---|---|---|---|---|---|
| [STACK] | [e.g. ✅ Implemented] | [e.g. Implemented, tests green, coverage 84%] | None | N/A | - |
| [STACK] | [e.g. 🔄 In Progress] | [e.g. Happy path done; error paths missing] | 404 path, 406 business-rule-reject path | Add coverage for error paths | tester |
| [STACK] | [e.g. ⏳ Pending] | [e.g. Not started] | Full implementation | Implement REQ | coder |
| [STACK] | [e.g. ✅ Implemented] | [e.g. Drift: endpoint returns 200 but spec says 201] | Contract vs implementation mismatch | Fix response status, update handoff contract | coder |
| [STACK] | (not in baseline) | [e.g. Discovered endpoint `/api/v1/foo` has no REQ] | New requirement discovered | Add REQ to Requirements Baseline, then triage | scout |

**Gap summary:**

- **In sync:** [count] REQs match the baseline status.
- **Behind baseline:** [count] REQs have regressed or have discovered gaps since the baseline was set.
- **Ahead of baseline:** [count] REQs are further along than the baseline records. Baseline needs refresh.
- **Drift:** [count] REQs where implementation diverges from the spec or the requirements source.
- **New findings:** [count] REQs the scout discovered that were not in the baseline.

The gap-analysis table drives the next crew run's work selection. A `🔄 Partial` with a concrete gap becomes a tester-agent work item. A `Drift` becomes a coder-agent work item. `New findings` become scout work items to formalize into REQs before anyone writes code.

---

## Current Implementation Log

Append-only log of significant implementation events. Each entry is dated and points at the REQs it covers, the files changed, and any open follow-ups.

### [YYYY-MM-DD] - [REQ-ID or feature name]

- **REQs covered:** REQ-[DOMAIN]-N[, ...]
- **Files:** [list of new or modified production files]
- **Tests:** [list of new or modified test files]
- **Coverage status:** [STACK: e.g. `line 83% / branch 72% / gate: PASS`, or `line 67% / branch 50% / gate: FAIL (missing error path coverage for REQ-X-2)`]
- **Spec version at this commit:** [STACK: e.g. `openapi.json @ 4.2.1`]
- **Notes:** [anything the next agent or reviewer needs to know, e.g. "role checks deferred until auth is live", "virus scan deferred"]

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
- [STACK: path to frontend handoff contract]
- [STACK: path to the audit report]
