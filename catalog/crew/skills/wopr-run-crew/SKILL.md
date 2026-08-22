---
name: wopr-run-crew
description: "Orchestrate the four-role agent crew (scout, coder, tester, auditor) end to end against a single REQ. Use for disciplined dev work on any project with a wopr.yml: net-new feature implementation, ongoing iteration on an existing project, addressing auditor blockers, handing off a backend change to a frontend track, or running a legacy migration."
---

<essential_principles>
## Principles

```
scout  ->  coder  ->  tester  ->  auditor
```

- **Four roles, never merged.** Scout reads, coder writes production code, tester writes tests, auditor gates. An agent that writes code and its own tests approves its own output; the boundaries are what makes the crew trustworthy.
- **One REQ per crew run.** The caller picks the sequence; the crew executes one at a time.
- **Models per role** (keep in sync with the `model:` frontmatter in `agents/`): scout **haiku**; coder, tester, auditor **sonnet**. The auditor is a gate, not a per-change reviewer; do not invoke it during coder iteration.
- **Every agent runs via the Task tool** (`subagent_type=<agent-name>`, fresh isolated context). Never role-play an agent in the parent conversation. Orchestrator work stays in the parent: pre-steps, gates, tracking-doc status updates.
- **Spec files are the authority.** Agents follow the project's coder and tester specs resolved from `wopr.yml`. With `spec_writes` ON (default), the owning agent amends its spec when a new pattern emerges; OFF, agents flag proposals and the operator decides.
- **Stop on failure.** Missing required input: stop and report, do not guess paths. Auditor BLOCKED: stop; the next step is a human decision, not a re-run.
- **OpenAPI is mandatory.** The backend emits a spec; the frontend consumes a generated client; agents reference target-side contracts by JSON Pointer. No spec, no crew run: stop at setup.
</essential_principles>

<project_setup>
## Setup (once per project)

`wopr.yml` must exist at project root and parse cleanly. Schema: `docs/wopr-yml-schema.md` (this repo); worked example: `catalog/crew/templates/wopr.example.yml`. Coder and tester specs are instantiated from `catalog/crew/templates/` and operator-approved before the first run; agents maintain them thereafter.

Two opt-in project hooks exist: `/wopr-configure-prompt-log` (per-turn log to PROMPT_LOG.md) and `/wopr-configure-git-guard` (blocks commits off `feature/*`). Offer them once on a new project, record the operator's answer in the tracking doc, honor it thereafter.
</project_setup>

<session_intake>
## Session intake (once per session, not per REQ)

1. **Run type.** Ask the operator: (1) crew run, (2) blocker fix after a BLOCKED audit, (3) frontend handoff track, (4) any of these unattended via `scripts/autorun.sh`. Route to the matching sequence below.
2. **Scope.** From the tracking document's baseline, confirm which REQ(s) this session targets. The orchestrator never invents a REQ-ID.
3. **Structural context.** Ask for session-level decisions not in the REQs (module consolidation, endpoint renames, excluded scope, data-migration decisions, version pins, known-wrong legacy behaviors to drop, reference docs). Record the answers, or an explicit "none", in the tracking document; every agent reads them from there. Mid-session changes are edits to the document, not a re-interview.

Greenfield project with no requirements source: skip 2 and 3; the first crew run captures REQs as they are introduced. Non-migration project with an empty tracking baseline: the operator populates it from the requirements source before the first run.
</session_intake>

<req_resolution>
## REQ resolution (re-fetch fresh before every agent dispatch)

`wopr.yml` `requirements:` declares the source; re-read it per dispatch so operator edits land mid-run.

- `source: local` (default): REQ body is `<wopr.yml dir>/<requirements.local.path>/<REQ-ID>.md` (default path `requirements/`). Pre-flight once at start: the file exists and is non-empty, else stop.
- `source: jira`: REQ body is the Jira issue description, fetched with `getJiraIssue` from the Atlassian MCP. Pre-flight once at start: (1) the Atlassian MCP tools are callable, else stop with a pointer to register the MCP or switch to `local`; (2) resolve the site via `getAccessibleAtlassianResources`: exactly one site, cache its id as cloud_id; zero or multiple sites, stop and say so; (3) smoke-test the configured REQ-ID fetch, surfacing the underlying error on failure; (4) if `requirements.jira.project_key` is set, soft-warn on prefix mismatch.
</req_resolution>

<crag_pre_step>
## CRAG pre-step (once per crew run, before Step 1)

1. Call `learnings_search`: `req_id` = target REQ, `stack_tags` derived from `wopr.yml` (dominant stack first: build file and package layout imply spring-boot, angular, fastapi, etc.; add `openapi-generator` when a generator version is pinned; add `legacy-migration` when `legacy-migration.legacy_source_root` is set), `req_summary` = the REQ description from the tracking document, defaults for age and limit.
2. **Empty result: pass an empty `relevant_learnings` block to every agent.** No evaluator.
3. **Five or fewer candidates: inject them all, marked advisory, to every agent.** No evaluator; at this corpus size every agent sees everything anyway and selection adds nothing.
4. **More than five: dispatch `crew-evaluator`** (Task tool) with the `wopr.yml` path, the REQ context block, the candidate block verbatim, and this combined hint: `discovery and file-layout gotchas; implementation patterns and anti-patterns; flaky-test and coverage-gap shapes; checklist gaps and cross-stack lockstep concerns`. Parse anchored on the literal `## Evaluator Verdict` header (discard anything before it; if absent, log the raw response and fall back to an empty block). Take `### HIGH` and `### MEDIUM` entries verbatim as the `relevant_learnings` block; drop LOW. If the header counts disagree with the actual entries, warn once and trust the entries.

The same `relevant_learnings` block goes to all four agents. Specs win over learnings on any conflict. The evaluator exists as an independent circuit-breaker against the corpus feeding its own biases back; below the threshold there is no selection pressure for it to break.
</crag_pre_step>

<crew_sequence>
## Crew run: one REQ, four roles

Preconditions: setup complete (`wopr.yml`, specs, reachable OpenAPI spec per `openapi.spec_url`), session intake done, REQ resolution pre-flight passed.

**Step 1: Scout** (Task `subagent_type=crew-scout`). One dispatch does discovery and alignment: verify the tracking document's baseline against reality (record ALIGNED / DRIFTED / STALE in the Gap Analysis table; on STALE, stop and let the operator decide), then produce the five-section report and write the scout contract to `<target_dir>/crew-contracts/<REQ-ID>/scout.md`. Inputs: `wopr.yml` path, target REQ ID, fresh REQ body, session structural context (from the tracking doc), `relevant_learnings`.

**Gate: contract validation.** Call `validate_scout_contract` with the contract's absolute path. `ok: false`: stop and surface the errors verbatim; a malformed contract is a scout failure to fix, not something to work around. Warnings are advisory. This gate exists because un-contracted discovery gets re-done downstream at higher model prices.

**Step 2: Coder** (Task `subagent_type=crew-coder`). Inputs: `wopr.yml` path, scout contract (validated), target REQ ID, fresh REQ body, `spec_writes`, `relevant_learnings`. Marks the REQ In Progress, implements production code only, keeps OpenAPI annotations or generated-client consumption current, updates the frontend handoff contract when the REQ touches the API surface, records `spec_version` on the log entry. Does not mark Implemented.

**Step 3: Tester** (Task `subagent_type=crew-tester`). Inputs: as coder, plus the coder's changed-file list. Tests only, fixtures and mocks from generated types, full suite run, line and branch coverage measured, `coverage_status` recorded.

**Gate: coverage (five conditions).** (1) Build passes. (2) Full suite passes, zero new failures. (3) Coverage meets the tester-spec floors. (4) If the REQ touched the API surface, the handoff contract covers the change with a JSON Pointer into the spec. (5) Static analysis reports clean for this REQ's changes. Any failure: route to the blocker-fix sequence; do not dispatch the auditor to rediscover a known-failing gate. All pass: **the orchestrator** marks the REQ Implemented in the tracking document and closes out its Gap Analysis row in the same edit, updating every cell of the row including its narrative notes (a stale "pending" note beside an Implemented status, in either table or within one row, is a contradiction the next reader trips over).

**Step 4: Auditor** (Task `subagent_type=crew-auditor`). Inputs: `wopr.yml` path, scout contract, fresh REQ body, prior audit report path (empty on first run), `spec_writes`, `relevant_learnings`. Runs its checklist, independently re-verifying rather than trusting recorded values; writes the audit report; distills 0 to 3 learnings entries (the auditor is the only learnings writer); returns BLOCKED or UNBLOCKED.

**Gate: verdict.** BLOCKED: route to the blocker-fix sequence. UNBLOCKED: the REQ is done. Repeat for the next REQ.
</crew_sequence>

<blocker_fix_sequence>
## Blocker fix: auditor returned BLOCKED

Do not re-run the full crew. Route each BLOCKER to its owner: production code findings to the coder; test findings to the tester; handoff-contract findings to the coder; tracking-document drift to the scout; spec findings to the owning agent when `spec_writes` is ON, escalating to the operator when the spec itself looks wrong.

1. Operator classifies each BLOCKER by owner.
2. Dispatch the owning agent (Task tool) with the target REQ, the specific findings, `wopr.yml` path, and the audit report path.
3. Re-dispatch downstream agents only if the fix touched their output (an API-surface change re-runs the tester; a test-only change does not re-run the coder).
4. Re-dispatch the auditor with the prior report path; it writes a new report with each prior finding RESOLVED, STILL OPEN, or NEW.
5. UNBLOCKED: done. BLOCKED: loop.

**Stop condition:** the same finding surviving two fix cycles means the spec is missing guidance, the audit rule is wrong, or a WARNING is misclassified. Escalate to the operator; do not grind.
</blocker_fix_sequence>

<frontend_handoff_sequence>
## Frontend handoff: backend crew finished, frontend crew consumes

The frontend run is its own crew run with its own `wopr.yml`; the two runs share exactly two artifacts: the handoff contract (the frontend's `legacy-migration.handoff_contract` points at the backend's contract by absolute path) and the pinned OpenAPI spec (frontend `generator_version` must match backend `spec_version`).

Run the standard sequence against the frontend project with two differences: the scout additionally resolves every contract entry's JSON Pointer against the spec (unresolvable pointers are BLOCKER-class) and maps entries to consuming frontend REQs; and the auditor's handoff rule inverts, verifying the frontend CONSUMES every contract entry (URL, method, status, UI action, pointer) with unconsumed, non-deferred entries as BLOCKERs, plus generator/spec version lockstep. The coder imports from the generated client and never hand-edits generated files (generator output problems are fixed via custom templates per the coder spec).
</frontend_handoff_sequence>

<verification_checklist>
## Before declaring a crew run complete

- Exactly one REQ went through all four roles, and the tracking document matches reality (status, `coverage_status`, `spec_version`, no stale Gap Analysis row).
- The coverage gate passed before the auditor ran, and the full suite passed, not just the new tests.
- The audit report file exists for this run and the verdict is UNBLOCKED. Declaring a BLOCKED run complete is declaring a broken crew complete.
- API-surface REQs: the handoff contract has a current JSON Pointer entry, and `generator_version` / `spec_version` are in lockstep.
</verification_checklist>

<reference_index>
## References

- Config: `docs/wopr-yml-schema.md` (this repo), `catalog/crew/templates/wopr.example.yml`
- Agents: `catalog/crew/agents/wopr-crew-{scout,coder,tester,auditor,evaluator}.md`
- Templates: `catalog/crew/templates/{coder-spec,tester-spec,implementation-tracking,frontend-handoff-contract}.template.md`
- Scripts and hooks: `catalog/crew/scripts/autorun.sh`, `catalog/meta-authoring/hooks/` (prompt-log, git-branch-guard)
- Pack overview: `catalog/crew/README.md`
</reference_index>
