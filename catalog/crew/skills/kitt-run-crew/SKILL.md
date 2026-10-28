---
name: kitt-run-crew
description: "Orchestrate the four-role agent crew (scout, coder, tester, auditor) end to end against a single REQ. Use for disciplined dev work on any project with a kitt.yml: net-new feature implementation, ongoing iteration on an existing project, addressing auditor blockers, handing off a backend change to a frontend track, or running a legacy migration. Use when running the crew from a workspace root against one member."
---

<essential_principles>
## Principles

```
scout  ->  coder  ->  tester  ->  auditor
```

- **Four roles, never merged.** Scout reads, coder writes production code, tester writes tests, auditor gates. An agent that writes code and its own tests approves its own output; the boundaries are what makes the crew trustworthy.
- **One REQ per crew run.** The caller picks the sequence; the crew executes one at a time.
- **Models per role, resolved per REQ.** The defaults are in the `model:` frontmatter in `agents/` (scout **haiku**; coder, tester, auditor, evaluator, designer **sonnet**). The orchestrator never relies on them directly: it calls `mcp__kitt__resolve_crew_models` (see `<model_resolution>`) and passes the returned model for each role as the `model` argument of that role's dispatch. A requirement's complexity moves the roles listed in `kitt.yml` `crew.escalation.roles` up or down one tier; every other role stays put. No role ever inherits the orchestrator's model. The designer exists only on projects declaring `specs.design_spec`. The auditor is a gate, not a per-change reviewer; do not invoke it during coder iteration.
- **Every agent runs via the Task tool** (`subagent_type=<agent-name>`, fresh isolated context). Never role-play an agent in the parent conversation. Orchestrator work stays in the parent: pre-steps, gates, tracking-doc status updates.
- **Spec files are the authority.** Agents follow the project's coder and tester specs resolved from `kitt.yml`. With `specs.spec_writes: true` in `kitt.yml`, the owning agent amends its spec when a new pattern emerges; OFF (the default), agents flag proposals in their reports and the operator decides what lands. The orchestrator reads the field once at run start and passes it to every crew agent.
- **Stop on failure.** Missing required input: stop and report, do not guess paths. Auditor BLOCKED: stop; the next step is a human decision, not a re-run.
- **Two operator gates, and no sequence skips either.** The REQ review gate runs before the first dispatch and gates the requirement; the auditor's verdict runs after the code and gates the implementation. Neither one substitutes for the other: an approved REQ says nothing about the code, and an UNBLOCKED audit only certifies that the code matches whatever the REQ said.
- **A machine-readable API contract is mandatory** (`api_contract` in `kitt.yml`: an OpenAPI document or a GraphQL schema, per `kind`). The backend owns the contract; the frontend consumes a generated client; agents cite contract items by **contract reference**: a JSON Pointer into the OpenAPI document, or the operation / type name in the GraphQL schema. Never hand-copied shapes. No contract, no crew run: stop at setup.
</essential_principles>

<project_setup>
## Setup (once per project)

A `project` `kitt.yml` must exist at the project root and parse cleanly (in workspace mode: at the home member's root; see `<workspace_mode>`). Schema and worked example ship with the crew pack: fetch via `mcp__kitt__get_pack_template` (`pack="crew"`, `name="kitt-yml-schema.md"`) and `name="kitt.example.yml"`. Coder and tester specs are instantiated from the pack templates (landed by `/kitt-init-project` or the stub-writer tools) and operator-approved before the first run; agents maintain them thereafter.

Two opt-in project hooks exist: `/kitt-configure-prompt-log` (per-turn log to PROMPT_LOG.md) and `/kitt-configure-git-guard` (blocks commits off `feature/*`). Offer them once on a new project, record the operator's answer in the tracking doc, honor it thereafter.
</project_setup>

<workspace_mode>
## Workspace mode (launched from a container of sibling projects)

Definition: the workspace-mode rule under "Path conventions" in `kitt-yml-schema.md`. Detect once per session: call `mcp__kitt__get_workspace_info` for the launch directory; `kitt_yml_kind: workspace` means workspace mode, and `workspace_config.members` (path, slug, role, kitt.yml present) is the member list for the rest of the session. Any other kind, or no `kitt.yml`, means a plain single-project session and nothing in this section applies.

- **Home member.** The REQ's `project:` frontmatter names it by slug. Missing, or a slug that is not a member: ask the operator which member; never guess. `also_writes:` lists extra members the REQ may write to; default empty, and the usual answer to a two-member need is two REQs joined by `depends_on`.
- **Home `kitt.yml` path** = `<workspace_root>/<home.path>/kitt.yml`. This is the `kitt.yml` path every dispatch below passes; the crew agents read a project file, never the workspace file.
- **Workspace context block**, passed to every dispatch alongside the `kitt.yml` path: the workspace root; every member with its path, role, slug, and `kitt.yml` path; `read_allowed: all members`; `write_allowed: <home> + also_writes`. This is what lets a frontend REQ's scout read the backend's API contract and route handlers directly instead of guessing at them.
- **REQ lookup from the root.** Resolve the home member's `kitt.yml` `requirements:` block and read `<home>/<requirements.local.path>/<REQ-ID>.md` (or the Jira issue). When the operator gives only a REQ-ID and no member, search every member's requirements path; exactly one hit sets the home, anything else asks.
- **Artifacts stay in the home member.** Scout contract, tracking document, audit report, and `append_learnings` (`target_workspace_path` = the home member's directory) all land there, never at the workspace root. A member's history reads the same whether the REQ ran from the root or from inside the member; the member is the git unit the audit report and contract are committed with; and the contract validator resolves `files_touched` against the contract's own directory, so a home-member contract keeps its scope check meaningful.
- **Lessons are read from the root.** The CRAG pre-step passes `target_workspace_path` = `<workspace_root>` to `learnings_search`, which reads the root corpus plus every member's. Writes still go to the home member.
- A session launched inside a member is never in workspace mode; cross-member reads are then out of scope, as before.
</workspace_mode>

<session_intake>
## Session intake (once per session, not per REQ)

1. **Run type.** Ask the operator: (1) crew run, (2) blocker fix after a BLOCKED audit, (3) frontend handoff track, (4) light run for a small, well-scoped, test-neutral change. Route to the matching sequence below. (Unattended operation is not an intake option: the operator launches `scripts/autorun.sh` outside the session; it resumes attended sequences and exits on a BLOCKED verdict, because BLOCKER classification is an operator decision.)
2. **Scope.** From the tracking document's baseline, confirm which REQ(s) this session targets. The orchestrator never invents a REQ-ID.
3. **Structural context.** Ask for session-level decisions not in the REQs (module consolidation, endpoint renames, excluded scope, data-migration decisions, version pins, known-wrong legacy behaviors to drop, reference docs). Record the answers, or an explicit "none", in the tracking document; every agent reads them from there. Mid-session changes are edits to the document, not a re-interview.

Greenfield project with no requirements source: skip 2 and 3; the first crew run captures REQs as they are introduced. Non-migration project with an empty tracking baseline: the operator populates it from the requirements source before the first run.
</session_intake>

<req_resolution>
## REQ resolution (re-fetch fresh before every agent dispatch)

`kitt.yml` `requirements:` declares the source; re-read it per dispatch so operator edits land mid-run.

- `source: local` (default): REQ body is `<kitt.yml dir>/<requirements.local.path>/<REQ-ID>.md` (default path `requirements/`; in workspace mode the home member's `kitt.yml` dir). Pre-flight once at start: the file exists and is non-empty, else stop.
- `source: jira`: REQ body is the Jira issue description, fetched with `getJiraIssue` from the Atlassian MCP. Pre-flight once at start: (1) the Atlassian MCP tools are callable, else stop with a pointer to register the MCP or switch to `local`; (2) resolve the site via `getAccessibleAtlassianResources`: exactly one site, cache its id as cloud_id; zero or multiple sites, stop and say so; (3) smoke-test the configured REQ-ID fetch, surfacing the underlying error on failure; (4) if `requirements.jira.project_key` is set, soft-warn on prefix mismatch.
</req_resolution>

<req_review_gate>
## Gate: REQ review (operator, once per REQ per session)

Runs after REQ resolution pre-flight and before the CRAG pre-step, on every sequence that has a REQ in scope. The audit verdict at Step 4 gates the code; it cannot gate the requirement, because by the time it runs the scout contract, the tests, and the code were all derived from the REQ text. **A wrong REQ caught here costs one turn; caught at the audit it has already paid for a full crew.**

1. Show the operator the fresh REQ body verbatim — frontmatter and every section, not a summary — plus one line per entry in `depends_on` giving that REQ's current status, so an unmet prerequisite surfaces here instead of in the audit.
2. Ask for one of four answers and wait. **Silence is not approval: no agent dispatch, and no CRAG call, before the answer lands.**
   - **Approve** — proceed to the CRAG pre-step.
   - **Edit** — the operator dictates the correction; the orchestrator rewrites the REQ at its source, re-shows it, and asks again. No round limit.
   - **Rework** — the requirement is wrong in shape rather than in wording. Stop the run and hand the REQ back to the `kitt-draft-req` skill, which owns the format and the criteria quality bar; re-enter this gate on its output.
   - **Cancel** — the requirement is wrong at its root. Leave the REQ in place at `status: pending`, stop, and dispatch nothing. Do not delete it.
3. Record the outcome on the REQ's Requirements Baseline row in the tracking document: `REQ review: approved <date>, <n> round(s)`, or `REQ review: cancelled <date> — <reason>`.

**What one approval covers.** This REQ, at the text the operator just read, for the rest of the session. The blocker-fix sequence does not re-gate — the REQ did not change, the code did. An operator edit to the REQ body after approval voids it: re-enter this gate before the next dispatch.

**`source: jira`:** on **Edit**, the orchestrator writes the issue only if the Atlassian MCP exposes a write tool in this session. When it does not, say so plainly, let the operator edit the issue, then re-fetch and re-show rather than editing a local copy that the next dispatch would not see.

**Skip only when no REQ is in scope** — a light run on a styling or copy change the operator described in session. There is no requirement document to review, and the change description is the operator's own words from one turn earlier.

**Unattended runs stop here, by design.** `scripts/autorun.sh` matches on the CLI asking for human direction and notifies instead of resuming, the same way it handles a BLOCKED verdict. An unattended loop therefore pauses once per REQ at this gate; that is the gate working, not the script failing.
</req_review_gate>

<model_resolution>
## Model resolution (per REQ, two calls)

Which model each role runs on is a deterministic lookup, not a judgment call, so a tool does it. Call `mcp__kitt__resolve_crew_models` with the absolute `kitt.yml` path (the home member's in workspace mode):

1. **Before Step 1**, with `req_path` set to the REQ file (local source) or `complexity` set to the level named in the Jira issue, if any. Use `models.scout` (and `models.designer`) from the result for those dispatches.
2. **After the contract gate passes**, again with `scout_contract_path` set to the validated contract. Use `models.coder`, `models.tester`, `models.auditor`, and `models.evaluator` from this result for every later dispatch in the run, including gate-failure fixes and blocker fixes.

`ok: false` stops the run with the errors shown verbatim; a misconfigured `crew` section is the operator's to fix, not something to work around. Record the resolved complexity, its source, and any adjusted roles on the REQ's tracking-document row (for example `models: coder/auditor opus (high, scout contract: 8 files)`), so the audit trail shows which tier did the work. An operator who states a level in session ("treat this one as high") passes it as `complexity`; it wins over the REQ file and the contract.
</model_resolution>

<crag_pre_step>
## CRAG pre-step (once per crew run, before Step 1)

1. Call `learnings_search` (in workspace mode with `target_workspace_path` = `<workspace_root>`, so the root corpus and every member's are read): `req_id` = target REQ, `stack_tags` derived from `kitt.yml` (dominant stack first: build file and package layout imply spring-boot, angular, fastapi, etc.; add `openapi-generator` when `api_contract.kind` is `openapi` and a generator version is pinned, `graphql` when it is `graphql`; add `legacy-migration` when `legacy-migration.legacy_source_root` is set), `req_summary` = the REQ description from the tracking document, defaults for age and limit.
2. **Empty result: pass an empty `relevant_learnings` block to every agent.** No evaluator.
3. **Five or fewer candidates: inject them all, marked advisory, to every agent.** No evaluator; at this corpus size every agent sees everything anyway and selection adds nothing.
4. **More than five: dispatch `crew-evaluator`** (Task tool, `model=<models.evaluator>`) with the `kitt.yml` path, the REQ context block, the candidate block verbatim, and this combined hint: `discovery and file-layout gotchas; implementation patterns and anti-patterns; flaky-test and coverage-gap shapes; checklist gaps and cross-stack lockstep concerns`. Parse anchored on the literal `## Evaluator Verdict` header (discard anything before it; if absent, log the raw response and fall back to an empty block). Take `### HIGH` and `### MEDIUM` entries verbatim as the `relevant_learnings` block; drop LOW. If the header counts disagree with the actual entries, warn once and trust the entries.

The same `relevant_learnings` block goes to all four agents. Specs win over learnings on any conflict. The evaluator exists as an independent circuit-breaker against the corpus feeding its own biases back; below the threshold there is no selection pressure for it to break.
</crag_pre_step>

<crew_sequence>
## Crew run: one REQ, four roles

Preconditions: setup complete (`kitt.yml`, specs, reachable API contract per `api_contract.spec_url`), session intake done, REQ resolution pre-flight passed, REQ review gate approved.

**Step 0: Resolve models** (`mcp__kitt__resolve_crew_models`, not optional, before any dispatch). Call it with the absolute `kitt.yml` path and `req_path` (or `complexity` for a Jira-sourced level). Stop on `ok: false`. Hold the returned `models` map; every dispatch below passes `model=<models.role>` from it. A dispatch without a `model` argument is a defect in the run, not a shortcut.

**Step 1: Scout** (Task `subagent_type=crew-scout`, `model=<models.scout>`). One dispatch does discovery and alignment: verify the tracking document's baseline against reality (record ALIGNED / DRIFTED / STALE in the Gap Analysis table; on STALE, stop and let the operator decide), then produce the five-section report and write the scout contract to `<target_dir>/crew-contracts/<REQ-ID>/scout.md`. Inputs: `kitt.yml` path (the home member's in workspace mode, plus the workspace context block), `mode` (pass explicitly: `gap_analysis` unless this is a migration project with an empty/skeleton tracking document AND `legacy-migration.legacy_source_root` is set, in which case `deep_analysis`), target REQ ID, fresh REQ body, session structural context (from the tracking doc), `relevant_learnings`.

**Gate: contract validation.** Call `validate_scout_contract` with the contract's absolute path. When it passes, call `mcp__kitt__resolve_crew_models` a second time with `scout_contract_path` set to that path; its `models` map replaces the Step 0 map for every later dispatch (coder, tester, auditor, evaluator, and any gate-failure or blocker fix). Record the resolved complexity, its source, and the adjusted roles on the REQ's tracking row. It checks shape AND consistency: workspace-escaping paths are errors; absent files, frontmatter/body path drift, and inventory entries outside `files_touched` are warnings. `ok: false`: stop and surface the errors verbatim; a malformed contract is a scout failure to fix, not something to work around. Warnings are advisory. When the orchestrator later overrides any contract content on evidence, it edits the contract to match the decision and notes the override inline, so downstream agents and the auditor cross-check against current truth rather than a stale plan. This gate exists because un-contracted discovery gets re-done downstream at higher model prices.

**Step 1.5: Designer** (Task `subagent_type=crew-designer`, `model=<models.designer>`) — **only when `kitt.yml` declares `specs.design_spec`**; skip otherwise, backend-only projects pay nothing. Inputs: `kitt.yml` path, scout contract, target REQ ID, fresh REQ body, `relevant_learnings`. Derives the REQ's appearance acceptance criteria from the design spec, writes/updates the `@visual` regression tests, and generates candidate baselines it never commits. **Baseline approval is operator-only:** the orchestrator surfaces the designer's candidate list and stops for the operator to review and commit before proceeding. The auditor runs `specs.visual_check` at the gate (checklist item 11).

**Step 2: Coder** (Task `subagent_type=crew-coder`, `model=<models.coder>` from the post-contract resolution). Inputs: `kitt.yml` path (plus the workspace context block in workspace mode), scout contract (validated), target REQ ID, fresh REQ body, `spec_writes`, `relevant_learnings`. Marks the REQ In Progress, implements production code only, keeps the API contract (OpenAPI annotations or GraphQL schema) or generated-client consumption current, updates the frontend handoff contract when the REQ touches the API surface, records `spec_version` on the log entry. Does not mark Implemented.

**Step 3: Tester** (Task `subagent_type=crew-tester`, `model=<models.tester>`). Inputs: as coder, plus the coder's changed-file list. Tests only, fixtures and mocks from generated types, full suite run, line and branch coverage measured, `coverage_status` recorded.

**Gate: coverage (five conditions).** This is the gate's single authoritative statement; the specs and agent files reference it and supply stack parameters, they do not redefine it. The orchestrator owns it. (1) Build passes. (2) Full suite passes, zero new failures (workspace mode: in the home member and in every `also_writes` member). (3) **Traceability:** every acceptance criterion of the REQ maps to at least one named test in the tester's criterion→test map; a zero-test criterion fails the gate. Line/branch coverage is measured and recorded alongside the map as a **diagnostic** — a number the auditor cross-checks for honesty, not a pass metric; percentage certified 902 assertions and a wireframe as done once, and will again. (4) If the REQ touched the API surface, the handoff contract covers the change with a contract reference that resolves against the API contract. (5) Static analysis reports clean for this REQ's changes (the tester triggers the scan and records the verdict in `coverage_status`). Any failure: run the **gate-failure fix** — route the failing condition to its owner (build or production-code failure → coder; test, coverage, or static-analysis failure → tester; handoff-contract gap → coder), dispatch that one agent with the failing condition, then re-check the gate. Loop until it passes; do not dispatch the auditor to rediscover a known-failing gate, and do not use the blocker-fix sequence (that sequence exists for audit verdicts and re-dispatches the auditor). All pass: **the orchestrator** marks the REQ Implemented in the tracking document and closes out its Gap Analysis row in the same edit, updating every cell of the row including its narrative notes (a stale "pending" note beside an Implemented status, in either table or within one row, is a contradiction the next reader trips over).

**Step 4: Auditor** (Task `subagent_type=crew-auditor`, `model=<models.auditor>`). Inputs: `kitt.yml` path (plus the workspace context block in workspace mode), scout contract, fresh REQ body, prior audit report path (empty on first run), `spec_writes`, `relevant_learnings`. Runs its checklist, independently re-verifying rather than trusting recorded values; writes the audit report; distills 0 to 3 learnings entries (the auditor is the sole distiller); returns BLOCKED or UNBLOCKED. **After the auditor returns, check its report for a `### Learnings (not persisted)` section** — it appears when `append_learnings` was unavailable in the auditor's session. If present, the orchestrator calls `append_learnings` itself with those entries verbatim (`target_workspace_path` = the kitt.yml directory, which in workspace mode is the home member's directory), so distilled learnings are never silently dropped.

**Gate: verdict.** BLOCKED: route to the blocker-fix sequence. UNBLOCKED: the REQ is done. Repeat for the next REQ.
</crew_sequence>

<blocker_fix_sequence>
## Blocker fix: auditor returned BLOCKED

Do not re-run the full crew. Route each BLOCKER to its owner: production code findings to the coder; test findings to the tester; handoff-contract findings to the coder; tracking-document drift to the scout; spec findings to the owning agent when `spec_writes` is ON, escalating to the operator when the spec itself looks wrong.

1. Operator classifies each BLOCKER by owner.
2. Dispatch the owning agent (Task tool) with the target REQ, the specific findings, `kitt.yml` path, and the audit report path.
3. Re-dispatch downstream agents only if the fix touched their output (an API-surface change re-runs the tester; a test-only change does not re-run the coder).
4. Re-dispatch the auditor with the prior report path; it writes a new report with each prior finding RESOLVED, STILL OPEN, or NEW.
5. UNBLOCKED: done. BLOCKED: loop.

**Stop condition:** the same finding surviving two fix cycles means the spec is missing guidance, the audit rule is wrong, or a WARNING is misclassified. Escalate to the operator; do not grind.
</blocker_fix_sequence>

<light_sequence>
## Light run: small change, full gate

For styling, copy, and other small well-scoped changes: **coder → auditor**. No scout, no separate tester dispatch. The ceremony is negotiable; the gate is not — **the auditor is never optional in any sequence**, and every severe incident in the Arcade build happened in un-gated direct work, not in a crew run.

**Qualification is mechanical, not judgment:** the change must need no new or modified tests (existing suite still passes untouched) and touch no API surface. If implementing reveals a test impact or an API change, stop and restart as a full crew run; do not stretch the light sequence.

**The REQ review gate still applies when a REQ is in scope**, and runs before step 1 below. It is skipped only for a change the operator described in session with no requirement document behind it.

1. Dispatch the coder (Task `subagent_type=crew-coder`, `model=<models.coder>` from a resolver call with no contract) with `kitt.yml` path, the change description, `spec_writes`, and an explicit note that this is a light run: no scout contract exists, so its own reading replaces the contract, and the no-tests boundary holds as usual.
2. Run the full suite and the static-analysis check; any failure routes back to the coder.
3. Dispatch the auditor as in Step 4 of the crew sequence (prior report path, `spec_writes`, `relevant_learnings` optional). It runs its checklist against the change; BLOCKED routes to the blocker-fix sequence.
4. UNBLOCKED: done. Log the change in the tracking document's implementation log (no REQ status transition unless a REQ was in scope).
</light_sequence>

<frontend_handoff_sequence>
## Frontend handoff: backend crew finished, frontend crew consumes

The frontend run is its own crew run with its own `kitt.yml`; the two runs share exactly two artifacts: the handoff contract (the frontend's `legacy-migration.handoff_contract` points at the backend's contract by absolute path) and the pinned API contract (frontend `generator_version` must match backend `spec_version`). When backend and frontend are both members of one workspace, the frontend's `handoff_contract` path is derivable, `<workspace_root>/<backend.path>/<the backend's legacy-migration.handoff_contract, default frontend-handoff-contract.md>`; offer that absolute path when the frontend `kitt.yml` lacks the field. The two runs remain two runs, each with its own home member.

Run the standard sequence against the frontend project with two differences: the scout additionally resolves every contract entry's contract reference against the API contract (unresolvable references are BLOCKER-class) and maps entries to consuming frontend REQs; and the auditor's handoff rule inverts, verifying the frontend CONSUMES every contract entry (operation, status or result, UI action, contract reference) with unconsumed, non-deferred entries as BLOCKERs, plus generator/spec version lockstep. The coder imports from the generated client and never hand-edits generated files (generator output problems are fixed via custom templates per the coder spec).
</frontend_handoff_sequence>

<verification_checklist>
## Before declaring a crew run complete

- Exactly one REQ went through all four roles, and the tracking document matches reality (status, `coverage_status`, `spec_version`, no stale Gap Analysis row).
- The REQ review gate was answered by the operator before the first dispatch, and its outcome is recorded on the REQ's Requirements Baseline row.
- The coverage gate passed before the auditor ran, and the full suite passed, not just the new tests.
- The audit report file exists for this run and the verdict is UNBLOCKED. Declaring a BLOCKED run complete is declaring a broken crew complete.
- API-surface REQs: the handoff contract has a current entry with a resolvable contract reference, and `generator_version` / `spec_version` are in lockstep.
- Workspace mode: `git status` is clean in every member outside `write_allowed`, and every artifact landed in the home member, not at the workspace root.
- Every agent dispatch in the run carried a `model` argument taken from `resolve_crew_models` (Step 0 for the scout and designer; the post-contract call for everything after), and the REQ's tracking row names the resolved complexity and its source. A run whose agents fell back to their file defaults skipped a step.
</verification_checklist>

<reference_index>
## References

- Config: schema `kitt-yml-schema.md` and worked example `kitt.example.yml`, both via `mcp__kitt__get_pack_template` (`pack="crew"`); the workspace-mode rule is under "Path conventions" in the schema
- Agents: dispatched by name — `crew-scout`, `crew-designer` (conditional), `crew-coder`, `crew-tester`, `crew-auditor`, `crew-evaluator` (definitions ship with this plugin); the `model` for each dispatch comes from `mcp__kitt__resolve_crew_models`, configured under `crew:` in `kitt.yml`
- Templates: enumerate via `mcp__kitt__list_pack_templates` (`pack="crew"`); fetch via `mcp__kitt__get_pack_template`
- Scripts and hooks: `scripts/autorun.sh` in this plugin's root; the prompt-log and git-branch-guard hooks ship with the kitt-core plugin and are registered via `/kitt-configure-prompt-log` and `/kitt-configure-git-guard`
- Pack overview: the crew pack README (repo checkout only; not shipped in the plugin)
</reference_index>
