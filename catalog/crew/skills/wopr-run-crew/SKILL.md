---
name: wopr-run-crew
description: "Orchestrate the four-role agent crew (scout, coder, tester, auditor) end to end against a single REQ. Use for any disciplined dev work on a project configured with `wopr.yml`: net-new feature implementation, ongoing iteration on an existing project, addressing auditor blockers, handing off a backend change to a frontend track, or running a legacy migration. Covers initial setup, ongoing iteration, and the backend-to-frontend contract bridge."
---

<essential_principles>
## The crew has four roles. Never merge them.

```
scout  ->  coder  ->  tester  ->  auditor
```

Scout reads. Coder writes production code. Tester writes tests. Auditor gates. Each agent has a single job. Merging roles (for example: an agent that writes code AND its tests) produces agents that approve their own output. The role boundaries are what makes the crew trustworthy.

## Each run handles exactly one requirement.

Per crew invocation, one REQ flows through all four roles. Do not chain multiple REQs into a single run. One REQ per run keeps the audit report reviewable and keeps blame location clear when something breaks. The caller picks the REQ sequence; the crew executes one at a time.

## Model alignment is load-bearing.

Each role uses the model that matches its work (these must stay in sync with the `model:` frontmatter of the agent files in `agents/`):

- Scout: **haiku**. Discovery is structured read/grep/summarize work against a fixed contract format; the small tier handles it reliably and keeps per-run cost down.
- Coder, tester: **sonnet**. Implementation and test generation require judgment that the mid-tier handles reliably.
- Auditor: **sonnet**. Gating judgment across spec integrity, pattern compliance, coverage, handoff contract accuracy, and Migration Context application; the audit is checklist-driven against explicit specs, which the mid-tier gates reliably.

Invoking the auditor during coder iteration is how crew runs blow the budget. The auditor is a gate, not a reviewer that runs after every file change. The model assignments above only take effect when agents are delegated via the Task tool; role-playing an agent in the parent conversation runs everything at the parent model's tier and defeats this discipline.

## Spec files are the authority.

The agents follow the project's coder spec and tester spec, resolved from `wopr.yml`. Those specs are the project's architecture and testing rules. Agents do not improvise when the specs are silent.

When `spec_writes` is ON (default), the coder, tester, and auditor amend their respective specs as new patterns emerge during the work. The spec and the code are the same artifact, maintained together. When `spec_writes` is OFF, agents flag new patterns in tracking-doc Handoff Notes (or, for the auditor, in a "Proposed audit rules" section of the audit report) and the operator decides whether to update the specs.

For an initial migration on a brand-new project, the operator writes the first version of each spec before the first crew run. From then on, the agents keep the specs current as long as `spec_writes` stays ON.

## Stop on failure. Do not retry blindly.

If an agent reports that a required input is missing, stop and report. Do not guess paths. If the auditor returns BLOCKED, stop. The next step is a human decision about how to address the blockers, not an automatic re-run.

## OpenAPI is mandatory.

The target backend emits an OpenAPI spec. The frontend consumes the spec through a generated client. Projects without an OpenAPI spec are out of scope for this pack. The scout reads the spec. The coder consumes the generated client and produces annotations. The tester asserts against generated types. The auditor verifies generator version lockstep and JSON Pointer integrity. If the project has no spec, stop at Phase 0 and address that first.

## Every agent runs via the Task tool. Never role-play.

Every agent invocation in this skill is a Claude Code subagent delegation. The parent Claude session calls the Task tool with `subagent_type=<agent-name>` (for example, `subagent_type=crew-scout`) and passes inputs. A fresh isolated context window spawns, runs the declared model, uses the declared tool set, and returns a summary to the parent.

**Never read the agent's `.md` file and act out the agent's part in the parent conversation.** That collapses the four roles into one model, one context, and zero isolation. Role-play breaks the role-separation principle above, defeats the cost-discipline model assignments below, and makes it impossible for the auditor to detect cross-contamination. If the parent session finds itself writing code that "the coder would write" without a Task tool call, the crew has gone wrong. Stop and delegate.

**The word "invoke" in this skill always means "call the Task tool with `subagent_type=<agent-name>`".** When this skill says "Invoke X", "Delegate to X", or "Call the X agent", it means the same thing: Task tool, subagent_type, fresh context.
</essential_principles>

<project_setup>
## Project setup: confirm config and offer hook wiring (run once per project)

Before Phase 0 starts on a brand-new project, confirm two things:

**1. `wopr.yml` exists at the project root and parses cleanly.**

If it does not, stop and point the operator at:

- The schema doc: `webteam-ai-tools/docs/wopr-yml-schema.md`
- The example file: `webteam-ai-tools/catalog/crew/templates/wopr.example.yml`

The operator copies the example, fills in their project's values, and re-runs. Do not proceed without `wopr.yml`.

**2. Optional bootstrap hooks.**

Offer the operator the two project-bootstrap hooks the meta-authoring pack ships. Both are opt-in. Both are idempotent (already-registered hooks are skipped, not duplicated). Skip this section entirely on subsequent runs of the same project; the hooks stay registered until the operator removes them.

**Ask the operator:**

> "This project does not appear to have the WOPR crew hooks installed. Want me to register them now?
> 1. **prompt-log Stop hook** appends a one-line summary of every assistant turn to `PROMPT_LOG.md` at the project root. Useful for long unattended runs and audit trails.
> 2. **git-branch-guard PreToolUse hook** blocks `git commit` and `git push` on branches that do not match `feature/*`. Useful for keeping the agent off `main` and `develop`.
>
> Both are opt-in. Reply with any of: **prompt-log**, **branch-guard**, **both**, **neither**."

Skip the question if the operator's answer is already on file (a prior session captured it in the implementation-tracking document's Migration Context summary).

**Acting on the answer:**

- **prompt-log:** invoke the standalone `/wopr-configure-prompt-log` command. The command shells out to `meta-authoring/scripts/configure_prompt_log.py`, which creates `PROMPT_LOG.md` and registers the Stop hook in the project's `.claude/settings.json`. Restart Claude Code is required for the hook to fire on subsequent turns. The crew does not depend on the hook firing in the current session.
- **branch-guard:** invoke `/wopr-configure-git-guard`. Same shape. The hook fires on the next Claude Code restart. Until then, `git commit` and `git push` follow whatever permission rules already exist in `settings.json`.
- **both:** invoke both commands in sequence.
- **neither:** record the operator's choice in the Migration Context summary so the question is not asked again next session.

**Skip conditions (do not ask, do not invoke):**

- The project's `.claude/settings.json` already contains a Stop hook whose command path matches `meta-authoring/hooks/prompt-log-hook.py` AND a PreToolUse hook whose command path matches `meta-authoring/hooks/git-branch-guard.sh`. Both hooks are wired; nothing to do.
- The operator has previously declined both in this project's Migration Context summary. Honor the prior choice.
- The operator is running in an environment where `python3 -c "import wopr"` fails (WOPR not installed). Surface the install instructions instead of attempting registration.

**Why this is opt-in, not automatic:** the crew pack avoids touching project settings without explicit operator consent. The configure scripts modify `.claude/settings.json`, which is a project-scoped file the operator may have customized. Asking once per project, recording the choice, and respecting it on future runs is the conservative posture.
</project_setup>

<phase_0>
## Phase 0: check requirements state before routing

Before picking a crew run type, determine whether this project has a populated extracted-requirements document and a populated implementation-tracking document. The answer routes between two paths.

**Path A: shallow alignment check** (documents exist and have REQ blocks populated).

- Read the extracted-requirements document. Confirm it has real REQ blocks, not just the template skeleton.
- Read the implementation-tracking document. Confirm the Legacy Requirements Baseline table has rows with status values.
- Call the Task tool with `subagent_type=crew-scout` and pass `mode: gap_analysis` (see `agents/wopr-crew-scout.md`).
- Scout populates the Gap Analysis (Latest Session) table in the implementation-tracking document without re-extracting requirements from scratch.
- Scout verdict is one of: `ALIGNED` (baseline matches reality), `DRIFTED` (individual REQs have moved but baseline shape is correct), `STALE` (baseline is significantly out of date).
- If ALIGNED or DRIFTED, proceed to Migration Context Prompt.
- If STALE, operator decides: continue with the shallow check anyway, or switch to Path B.

**Path B: deep analysis (migration projects only)** — documents missing, empty, or only contain the template skeleton AND the project is migrating from a legacy codebase declared in `wopr.yml` (`legacy-migration.legacy_source_root` is set).

- Call the Task tool with `subagent_type=crew-scout` and pass `mode: deep_analysis`.
- Scout reads the legacy source end-to-end, produces the extracted-requirements document from scratch, and populates the implementation-tracking document's Requirements Baseline.
- Scout still produces a gap-analysis table in the same run, comparing its fresh baseline against whatever code exists in the target directory (empty on a true green-field migration, non-empty if partial work has already landed).
- After the scout completes Path B, proceed to Migration Context Prompt.

**Non-migration projects with empty tracking documents:** if the project is non-migration (no `legacy-migration.legacy_source_root` in `wopr.yml`) and the implementation-tracking document only contains the template skeleton, the operator populates the Requirements Baseline manually from the project's requirements source (feature backlog, written spec, ticket system) before the first crew run. The scout does not run in `deep_analysis` mode for non-migration projects. After the baseline is populated, Path A applies on subsequent runs.

**Greenfield note:** if the project is purely net-new (no prior implementation, no prior requirements source), skip Phase 0 entirely. Skip the Migration Context Prompt as well (no structural decisions to capture). Proceed directly to the intake question. The first crew run captures REQs as they are introduced.
</phase_0>

<migration_context_prompt>
## Migration Context Prompt: capture structural decisions once per session

After Phase 0 completes and before routing to a crew run type, ask the operator two questions. The answers are written verbatim into the extracted-requirements document's Migration Context section and summarized in the implementation-tracking document's Migration Context summary field.

**Question 1: which REQs are in scope for this session?**

Pull the list of REQs from the implementation-tracking document's gap-analysis table. Show the operator the list and ask which REQs they want to migrate in this crew run (or run series). Typical answers: "the next pending REQ", "all REQs in the REQ-CASE domain", "just REQ-CASE-3 and REQ-CASE-4", "everything marked `🔄 In Progress`".

**Question 2: any structural context the agents need that is not in the REQ list?**

Prompt the operator for each of these categories:

- **Module consolidation** (e.g., "merge `web` and `admin` modules into one API; role-based filtering replaces separate endpoints").
- **Endpoint renames** (e.g., "`/getCase` becomes `GET /api/v1/cases/{id}`; no alias preserved").
- **Excluded scope** (e.g., "email notifications deferred to a later phase; related REQs marked `❌ Out of Scope`").
- **Data migration decisions** (e.g., "`OLD_STATUS` column dropped; data migrated via Flyway `V2__consolidate_status.sql` before code deploys").
- **Spec and generator version pins** (e.g., "pinned to `openapi-generator-cli 7.21.0`; backend spec at `springdoc-openapi 2.7.0` on `/v3/api-docs`; lockstep upgrades only").
- **Known-wrong legacy behaviors the rewrite should NOT preserve** (e.g., "legacy sets `reportDate = now()` server-side; rewrite uses client-supplied `reportedAt`").
- **Reference documents or notes files the agents should consult.**

If the operator has no structural context to add, record that explicitly: "No structural changes this session; implement REQs as extracted."

**What happens with the answers:**

- Question 1 answers become the target REQ list for the crew run.
- Question 2 answers are written into the extracted-requirements document's Migration Context section. The scout performs this write after Phase 0 completes.
- The Migration Context summary field in the implementation-tracking document is updated with a one-line summary.
- Every downstream agent (coder, tester, auditor) reads these sources as part of its standard inputs.

**Rule:** the Migration Context Prompt runs once per crew session, not per REQ. If the operator changes scope mid-session (adds a new structural decision), they update the extracted-requirements document directly; the agents pick up the edit on their next read.
</migration_context_prompt>

<intake>
**Ask the operator:**

What kind of crew run is this?

1. **Crew run.** Any REQ on a project that has `wopr.yml` at its root. Used for both initial migrations (first REQ on a green-field target) and ongoing iteration (subsequent REQs on the same project). The four roles run end to end against one REQ.
2. **Blocker fix** cycle. The auditor returned BLOCKED on a prior run. Now the coder (and possibly the tester) addresses findings. Then re-audit.
3. **Frontend handoff track.** A backend migration finished and produced a frontend handoff contract. Run the crew again, this time targeting the frontend project, with the handoff contract as one of the scout's inputs.
4. **Unattended / overnight run.** Same as 1, 2, or 3 but driven by `autorun.sh` because the work outlasts a single token window.

Route from the operator's answer to the correct crew sequence below.
</intake>

<routing>
| Answer | Sequence |
|---|---|
| 1, "crew", "next REQ", "initial", "iterate", "ongoing" | `crew_sequence` |
| 2, "blocker", "fix findings", "unblock" | `blocker_fix_sequence` |
| 3, "frontend", "handoff", "SPA track", "consume contract" | `frontend_handoff_sequence` |
| 4, "overnight", "autorun", "unattended" | any of the above, wrapped in `autorun.sh` (see `scripts/README.md`) |
</routing>

<req_resolution>
## Pre-step: REQ resolution (runs before every working-agent Task call)

Every agent dispatch needs the active REQ's body (acceptance criteria, endpoint definitions, service-layer notes, links to legacy code). The orchestrator resolves the REQ body from one of two sources declared in `wopr.yml`'s `requirements:` section:

* `source: local` (default; backwards-compatible with `wopr.yml` files that predate this section): read `<wopr.yml dir>/<requirements.local.path>/<REQ-ID>.md` and pass its contents verbatim as the REQ body. The default `local.path` is `requirements/`.
* `source: jira`: call `mcp__plugin_atlassian_atlassian__getJiraIssue` with the operator's Atlassian cloud_id (resolved at runtime via the MCP; see pre-flight below) and the REQ-ID (the Jira issue key, e.g., `RISK25-067`). Use the issue description as the REQ body. The Atlassian MCP comes from either a self-hosted MCP server in `~/.claude.json` or the Claude.ai Atlassian plugin; either works. The `wopr.yml` does NOT carry the cloud_id; it is machine-level state, not project-level.

**Re-fetch fresh on every agent dispatch.** Both modes re-read the source per Task call (Step 1 scout, Step 2 coder, Step 3 tester, Step 4 auditor). The cost is negligible (one local file read or one Jira API call per phase) and the upside is that operator edits made mid-crew are picked up by the next agent.

### Jira-mode pre-flight (runs once at orchestrator start, before Step 1)

When `wopr.yml` declares `requirements.source: jira`, before dispatching the scout:

1. **Verify the Atlassian MCP tools are callable.** The required tools are `mcp__plugin_atlassian_atlassian__getAccessibleAtlassianResources` and `mcp__plugin_atlassian_atlassian__getJiraIssue`. If either is not registered in the current session, stop with the error: "requirements.source=jira is configured in wopr.yml but the Atlassian MCP tools are not available. Either (a) register a self-hosted Atlassian MCP server in your CLI's MCP config (`~/.claude.json` for Claude Code, `~/.gemini/settings.json` for Gemini CLI, `~/.copilot/mcp-config.json` for Copilot CLI), (b) enable the Claude.ai Atlassian plugin in Claude Code, or (c) switch `requirements.source` to `local`."

2. **Resolve the Atlassian site.** Call `getAccessibleAtlassianResources`. The response is a list of accessible Atlassian sites.
   * **Zero sites returned**: stop with "no Atlassian access available; enable the Claude.ai Atlassian plugin or register a self-hosted MCP server, or switch `requirements.source` to `local`."
   * **Exactly one site returned**: cache its `id` as the cloud_id for every `getJiraIssue` call in this crew run. No prompt, no further config.
   * **Multiple sites returned**: stop with "multiple Atlassian sites accessible (<list-them>); the default jira flow does not yet disambiguate. Either limit your Atlassian access to one site, or file a follow-up ticket so we add per-project site selection."

3. **Smoke-test the REQ-ID fetch.** Call `getJiraIssue` with the cached cloud_id and the configured REQ-ID. If the call fails (404, auth error, network), stop with the underlying error surfaced.

4. **(Optional sanity check)** If `wopr.yml` declares `requirements.jira.project_key`, verify the REQ-ID's prefix matches. Soft-warn (do not abort) on mismatch so the operator notices a likely typo.

The doctor surfaces a `requirements.jira_mode_advisory` warning at scan time but cannot reliably detect plugin-based access nor verify the cloud_id without invoking the MCP; the orchestrator's runtime pre-flight is the source of truth.

### Local-mode pre-flight (runs once at orchestrator start, before Step 1)

When `wopr.yml` declares `requirements.source: local` (or omits the `requirements:` section entirely):

1. Verify `<wopr.yml dir>/<requirements.local.path>/<REQ-ID>.md` exists and is non-empty. Stop with a clear error if missing.

The doctor surfaces a `requirements.local_path_missing` warning at scan time; the orchestrator's runtime check on the specific REQ-ID file is the source of truth.

### REQ-ID intake

The REQ-ID for a crew run comes from the operator at intake time (the Migration Context Prompt's Question 1, or a direct `/wopr-run-crew REQ-XXX` invocation). The orchestrator never invents a REQ-ID. One REQ per crew run; batch processing is the operator's loop, not this skill's.
</req_resolution>

<crag_pre_step>
## Pre-step: CRAG learnings retrieval (runs before every working-agent Task call)

Before each Task call to a working agent (scout, coder, tester, auditor), the orchestrator runs a Corrective RAG (CRAG) pre-step to retrieve the most relevant prior LEARNINGS entries and grade them via the `crew-evaluator` agent. The graded subset is handed into the working agent's Required Inputs as `relevant_learnings`.

This is a deterministic four-substep flow performed in the orchestrator's main turn (not delegated):

**Substep 1: candidate retrieval via MCP tool.**

Call the `learnings_search` MCP tool:

- `req_id` = the target REQ ID for this run (empty string for the scout pre-step when no REQ has been chosen yet).
- `stack_tags` = a list of stack identifiers derived from `wopr.yml`. Heuristic: `spring-boot` if `project.base_package` starts with `com.redacted.client` and `project.build_file` is `pom.xml` or similar Maven/Gradle file; `angular` if the build file is `project.json` or `angular.json`; `openapi-generator` if `openapi.pinned_generator_version` references `openapi-generator-cli`; `legacy-migration` if `legacy-migration.legacy_source_root` is set in `wopr.yml`. Always include the dominant stack first.
- `max_age_days` = 180 (default).
- `limit` = 20 (default).
- `req_summary` = a free-text summary of the current REQ from the tracking document (one or two paragraphs is fine). This drives the optional semantic-search candidate path when the `embeddings` extra is installed; without it, the deterministic prefilter is the only candidate source. Pass the REQ description verbatim from the tracking document where possible; the more concrete the language, the better the semantic matches.

The tool runs two candidate paths in parallel and returns their union (deduplicated by entry ID):

1. **Deterministic prefilter.** Required `stack_tags` intersection or `req_id` exact match, scored by REQ-match boost + stack overlap + recency. Always runs.
2. **Semantic top-N (optional).** Cosine similarity between an embedding of `req_summary` and per-entry vectors from each LEARNINGS.md's paired sidecar. Catches paraphrased queries and cross-stack transfer the deterministic prefilter would drop. Runs only when `req_summary` is non-empty and the `embeddings` extra is installed; gracefully no-ops otherwise.

The tool returns a markdown block of candidate entries verbatim (top-N from the unioned result), or the empty string when nothing matches.

**Substep 2: empty-path short-circuit.**

If `learnings_search` returned the empty string, skip the evaluator entirely. Pass an empty `relevant_learnings` block to the working agent. Log "no candidates" in your running narrative for traceability.

**Substep 3: evaluator Task call.**

Call the Task tool with `subagent_type=crew-evaluator` and these inputs:

- `wopr.yml` path.
- Current REQ context block (REQ ID, REQ summary from the tracking document, scout's relevant file paths if available, the current crew step name).
- The candidate learnings block from `learnings_search` verbatim.
- The step-relevance hint:
  - For Step 1 (Scout): `discovery patterns; file-layout gotchas; legacy-source navigation tips`.
  - For Step 2 (Coder): `implementation patterns + library/framework gotchas; anti-patterns to avoid`.
  - For Step 3 (Tester): `flaky-test patterns; coverage-gap shapes; fixture/mock conventions`.
  - For Step 4 (Auditor): `checklist gaps; recurring multi-REQ traps; cross-stack lockstep concerns`.

The evaluator returns a verdict block with `## Evaluator Verdict`, `### HIGH`, `### MEDIUM`, and `### LOW` sections (the full format is documented in `agents/wopr-crew-evaluator.md`).

**Substep 4: assemble `relevant_learnings`.**

Parse the evaluator's verdict block. **Anchor parsing on the literal `## Evaluator Verdict` header.** Locate the first occurrence of that header in the evaluator's response and discard everything that precedes it. The agent spec forbids preamble, but Sonnet's narrate-then-deliver default sometimes leaks setup commentary or per-candidate reasoning before the verdict block. The parser is the hard guarantee; the spec rule is a soft guardrail. If `## Evaluator Verdict` does not appear anywhere in the response, that is a hard failure: log the raw response and pass an empty `relevant_learnings` block (do not retry blindly).

From the verdict header forward, extract the `### HIGH` and `### MEDIUM` sections and concatenate their entries verbatim, in order, into a single markdown block. This becomes the `relevant_learnings` Required Input for the working agent in the next step. Drop the `### LOW` section entirely; it exists in the verdict for traceability only.

**Consistency check.** After extraction, verify three counts agree: the `relevant_count:` field in the verdict header, the number of `LRN-...` IDs listed under `ids:`, and the actual number of `## LRN-` entries inside the `### HIGH` and `### MEDIUM` sections combined. If any of the three disagree, log a one-line warning naming the mismatch (e.g., `relevant_count=5 but ids list has 4 entries and HIGH+MEDIUM contains 4 entries`) and trust the actual section contents, not the count field. Do not hard-fail; the entries themselves remain usable. Sonnet miscounts the metadata line in roughly 1 in N invocations, so the assertion-and-warn pattern keeps the crew moving while making the drift visible.

If the evaluator returns `relevant_count: 0` or no HIGH/MEDIUM sections, pass an empty block.

**The pre-step runs four times per crew run**, once before each of Steps 1, 2, 3, and 4. Including before the auditor. This prevents the auditor from re-distilling lessons that are already captured semantically. The auditor reads the same filtered subset as the working agents.
</crag_pre_step>

<crew_sequence>
## Crew run: one REQ, four roles

This is the single crew sequence for any REQ on any configured project. First-run vs ongoing-iteration is not a routing distinction; the same sequence runs in both cases. What differs is whether `wopr.yml` and the spec files already exist and have content (ongoing) or are being populated for the first time (initial).

**Preconditions:**

- Phase 0 has run and Migration Context has been captured (see `<phase_0>` and `<migration_context_prompt>` above).
- `wopr.yml` exists at project root and parses cleanly. Schema: `webteam-ai-tools/docs/wopr-yml-schema.md`. If missing, stop and point the operator at `catalog/crew/templates/wopr.example.yml`.
- Coder spec and tester spec have been filled in from the templates at `catalog/crew/templates/` with the target stack's specifics, including the Migration Context section on the coder spec and the `spec_version` / `generator_version` pins on the implementation-tracking document. Operator signs off before the first crew run on a new project; subsequent runs read whatever the agents have maintained since.
- For migration projects: legacy source is accessible and readable per `legacy-migration.legacy_source_root` in `wopr.yml`. For non-migration projects: the requirements source is identified in the implementation-tracking document's Key Files section.
- Target OpenAPI spec is reachable per `openapi.spec_url` in `wopr.yml`. The pack does not run without a spec.

**Pre-flight (runs once):** Run the REQ-resolution pre-flight (see `<req_resolution>` above) to verify the requirements source is usable. For `source: jira`, confirm the Atlassian MCP tool is callable and smoke-test the REQ-ID fetch. For `source: local`, confirm `<wopr.yml dir>/<requirements.local.path>/<REQ-ID>.md` exists. If pre-flight fails, stop with the surfaced error; do not dispatch the scout.

**Step 1: Scout.** Resolve the REQ body (see `<req_resolution>` above). Run the CRAG pre-step (see `<crag_pre_step>` above) with the step-relevance hint `discovery patterns; file-layout gotchas; legacy-source navigation tips`. Then call the Task tool with `subagent_type=crew-scout` and these inputs:

- `wopr.yml` path (default: `wopr.yml` at project root)
- Migration Context Prompt output (when the operator has new structural decisions for this session)
- Target REQ ID (from the Migration Context Prompt's Question 1 answer)
- Active REQ body (resolved by the REQ-resolution pre-step)
- `relevant_learnings` (the graded markdown block from the CRAG pre-step; pass an empty block when no candidates were retrieved)

Scout reads `wopr.yml` first, then the spec and tracking documents. Returns a five-section report: requirements status, relevant file paths, schema constraints (legacy schema AND target OpenAPI spec JSON Pointers), test coverage gaps, handoff notes. References the OpenAPI spec by JSON Pointer for every target-side contract claim; no hand-copied schemas. **Also writes the scout contract** to `<target_dir>/crew-contracts/<REQ-ID>/scout.md` (see scout agent spec for the schema).

**Gate (scout-contract validation):** before dispatching the coder, call `mcp__wopr__validate_scout_contract` with the absolute contract path. The tool returns JSON with an `ok` field plus `errors` and `warnings` lists. If `ok` is `false`, stop the crew and surface the validator's errors verbatim to the operator. The orchestrator does NOT silently retry; an under-populated or malformed contract is a scout failure to fix, not a hand-off to work around. Warnings (empty class inventory for a non-class REQ, very short body) are advisory and do not block dispatch. This gate exists because scout-first discovery was the single biggest token drain in early crew runs: without the gate, downstream agents re-grep the codebase at Opus prices, and inconsistent inference across agents produces drift (the same entity field gets three different names across coder, tester, and JPA layers).

**Gate (gap analysis):** operator reads the Gap Analysis (Latest Session) table in the implementation-tracking document. The scout populated it in Phase 0 and refined it in Step 1. Operator picks the target REQ for this crew run (if not already pinned by Migration Context Prompt Question 1). Does NOT proceed until the REQ is named and the Migration Context is confirmed relevant to this REQ.

**Step 2: Coder.** Resolve the REQ body again (re-fetch fresh per `<req_resolution>` above, so operator edits since the scout dispatch are picked up). Read the validated scout contract from disk so its content is available to inject. Run the CRAG pre-step with the step-relevance hint `implementation patterns + library/framework gotchas; anti-patterns to avoid`. Then call the Task tool with `subagent_type=crew-coder` and these inputs:

- `wopr.yml` path
- Scout contract content (frontmatter + body of `<target_dir>/crew-contracts/<REQ-ID>/scout.md`, injected verbatim)
- Target REQ ID
- Active REQ body (resolved by the REQ-resolution pre-step)
- `spec_writes` mode (default: `ON`)
- `relevant_learnings` (the graded markdown block from the CRAG pre-step; pass an empty block when no candidates were retrieved)

Coder reads `wopr.yml` first, then the coder spec, then the scout contract. Consults the contract's `files_touched` and `class_inventory` BEFORE doing any independent discovery. Marks the REQ `🔄 In Progress`, implements it, updates OpenAPI annotations (backend) or consumes the generated client (frontend), updates the frontend handoff contract if the REQ touched the API surface, records `spec_version` on the log entry. With `spec_writes` ON, amends the coder spec when a new pattern emerges. Coder does NOT mark `✅ Implemented` yet; that waits for the coverage gate.

**Step 3: Tester.** Resolve the REQ body again (re-fetch fresh). Read the scout contract. Run the CRAG pre-step with the step-relevance hint `flaky-test patterns; coverage-gap shapes; fixture/mock conventions`. Then call the Task tool with `subagent_type=crew-tester` and these inputs:

- `wopr.yml` path
- Scout contract content (injected verbatim)
- Target REQ ID
- Active REQ body (resolved by the REQ-resolution pre-step)
- Coder's most recent changes (file list)
- `spec_writes` mode (default: `ON`)
- `relevant_learnings` (the graded markdown block from the CRAG pre-step; pass an empty block when no candidates were retrieved)

Tester reads `wopr.yml` first, then the tester spec. Writes tests for the paths the tester spec requires, using generated types from the OpenAPI client for fixtures and mocks (no hand-written type copies). Runs the full suite. Measures line and branch coverage. Records `coverage_status` on the log entry. With `spec_writes` ON, amends the tester spec when a new coverage shape emerges.

**Gate (coverage):** before invoking the auditor, verify the five-condition coverage gate (defined in coder spec section 22, measured and recorded by the tester per tester spec sections 6 and 7):

1. Build passes.
2. Full test suite passes. Zero new failures.
3. Line and branch coverage meet the tester-spec floors.
4. If the REQ touched the API surface, the handoff contract has a line item covering the change with a JSON Pointer into the OpenAPI spec.
5. Static-analysis Quality Gate (Sonar or equivalent) reports `Passed` for the latest scan covering this REQ's commits. New BLOCKER, CRITICAL, or MAJOR findings introduced by this REQ count as failures.

If any condition fails, the coder and/or tester address the gap before the auditor runs. Route to `blocker_fix_sequence` for the fix cycle. Do not call the Task tool for the auditor on a failing gate; the auditor will report the same findings at higher cost.

If all five pass, the coder updates the REQ status to `✅ Implemented` and proceeds.

**Step 4: Auditor.** Resolve the REQ body again (re-fetch fresh). Read the scout contract. Run the CRAG pre-step with the step-relevance hint `checklist gaps; recurring multi-REQ traps; cross-stack lockstep concerns`. Running the pre-step before the auditor prevents re-distilling lessons that are already captured semantically in the corpus. Then call the Task tool with `subagent_type=crew-auditor` and these inputs:

- `wopr.yml` path
- Scout contract content (injected verbatim; the auditor uses it as a cross-check against the coder's and tester's output)
- Active REQ body (resolved by the REQ-resolution pre-step)
- Prior audit report path (empty on first run; resolved from `specs.audit_report` in `wopr.yml` thereafter)
- `spec_writes` mode (default: `ON`)
- `relevant_learnings` (the graded markdown block from the CRAG pre-step; pass an empty block when no candidates were retrieved)

Auditor reads `wopr.yml` first, then both specs and tracking documents. Runs the checklist, writes the audit report, returns BLOCKED or UNBLOCKED. Verifies generator-version lockstep, Mustache template presence, JSON Pointer resolution in the handoff contract, framework-version + CI workflow lockstep, and coverage-gate recording in the tracking document, on top of the existing pattern-compliance and REQ-traceability checks. With `spec_writes` ON, amends the audit-rule list section of the coder/tester spec when a new audit-rule gap is found.

**Gate:** operator reviews the verdict. If BLOCKED, route to `blocker_fix_sequence`. If UNBLOCKED, the REQ is done.

**Repeat** for the next REQ.
</crew_sequence>

<blocker_fix_sequence>
## Blocker fix: auditor returned BLOCKED

**Preconditions:** a prior audit returned `BLOCKED` with one or more BLOCKER findings.

**Do not re-run the full crew from the start.** The scout already did its discovery. The coder does not need re-onboarding. Go straight to the role that owns the finding.

**Routing by finding type:**

- Finding in production code (pattern compliance, layer separation, schema alignment, API surface): coder fixes.
- Finding in tests (coverage gap, naming, test-isolation violation): tester fixes.
- Finding in the handoff contract (missing entry, missing REQ ID, implicit delta): coder fixes (the coder owns the handoff contract during implementation).
- Finding in the tracking document (status drift): scout fixes.
- Finding in specs (coder spec, tester spec): when `spec_writes` is ON, the owning agent (coder for coder spec, tester for tester spec) amends the spec on its next invocation. A BLOCKER-level spec finding is usually a signal that the spec itself is wrong, which needs human review; escalate when in doubt.

**Sequence:**

1. Operator reads the audit report. Classifies each BLOCKER by owner.
2. Call the Task tool with `subagent_type=<owning-agent>` (one of `crew-{scout,coder,tester}`) and pass the target REQ and the specific findings to address. Include `wopr.yml` path and the audit report path as inputs so the agent sees what it's fixing.
3. After the owning agent finishes, call the Task tool for dependent downstream agents only if the fix touched their output. A fix in the coder that changes the API surface means re-delegating to the tester. A fix in the tester that only changes test code does not require re-delegating to the coder.
4. Call the Task tool with `subagent_type=crew-auditor` and pass `wopr.yml` path plus the prior audit report path.
5. Auditor writes a new audit report with a Resolution Summary listing each prior finding as RESOLVED, STILL OPEN, or NEW.
6. If UNBLOCKED, the REQ is done. If BLOCKED, loop.

**Stop condition:** if the same finding survives two fix cycles, stop. That is a signal the coder or tester spec is missing guidance, the audit rule is wrong, or the finding is actually a WARNING being misclassified. Escalate to the human operator. Do not grind.
</blocker_fix_sequence>

<frontend_handoff_sequence>
## Frontend handoff: backend-first migration now drives frontend

**Preconditions:**

- A backend migration has run. Its auditor produced a frontend handoff contract at the path configured in the backend's `wopr.yml` (`legacy-migration.handoff_contract`). The contract has JSON Pointer references into the OpenAPI spec for every endpoint entry.
- The frontend target app exists or has been scaffolded (see the operator's monorepo conventions).
- The frontend has its **own** `wopr.yml` at its project root. Its `legacy-migration.handoff_contract` field points at the BACKEND's contract by absolute path; this is how the bridge is wired.
- The frontend is wired to the generated client from the backend's OpenAPI spec, with pinned `generator_version` matching the backend's `spec_version` (see coder spec section 4b).
- Phase 0 runs against the frontend's own extracted-requirements and implementation-tracking documents. Migration Context is captured for the frontend session (usually a summary of the backend's context plus any frontend-specific structural decisions like route restructuring or state management migration).
- The frontend's coder spec and tester spec have been filled in for the frontend stack (Angular, React, Vue, whatever the monorepo uses). The agents read whatever the specs currently contain and amend them per `spec_writes`.

**Critical:** the frontend crew is its own crew run. It is not a direct continuation of the backend run. The two crews share one artifact (the handoff contract, referenced by both `wopr.yml` files) and the same pinned OpenAPI spec; they do not share execution.

**Step 1: Frontend scout.** Call the Task tool with `subagent_type=crew-scout` and these inputs:

- `wopr.yml` path (the **frontend's** config, not the backend's)
- Migration Context Prompt output (when applicable)
- Target REQ ID

Scout reads the frontend's `wopr.yml` first. Its `legacy-migration.handoff_contract` resolves to the backend's contract file. Scout reads that contract, resolves every JSON Pointer against the spec (treating unresolvable pointers as BLOCKER-class gaps), and matches each contract entry to a frontend REQ that consumes or displays that surface.

**Gate (gap analysis):** operator reviews the gap-analysis table. Picks the target REQ.

**Step 2: Frontend coder.** Call the Task tool with `subagent_type=crew-coder` and pass the frontend's `wopr.yml` path, target REQ ID, and `spec_writes` mode. Coder reads the handoff contract and the spec to match the API shape exactly. Imports from the generated client; does not hand-write HTTP services. If the generator default output is wrong for a specific case (for example, a `*/*` Accept header producing a blob response), fixes via custom Mustache template per coder spec section 4c; never hand-edits generated files.

**Step 3: Frontend tester.** Call the Task tool with `subagent_type=crew-tester` and pass the frontend's `wopr.yml` path, target REQ ID, and `spec_writes` mode. Tester writes component tests, service tests, whatever the frontend tester spec requires. Uses generated types for fixtures and mocks. Records `coverage_status`.

**Gate (coverage):** same five-condition gate.

**Step 4: Frontend auditor.** Call the Task tool with `subagent_type=crew-auditor` and pass the frontend's `wopr.yml` path. Auditor runs its checklist. The handoff-contract audit rule for frontend is inverted: it verifies the frontend CONSUMES every contract entry, matching URL, method, status, UI action item, and spec JSON Pointer. A frontend that does not consume a listed entry (and is not explicitly in the Deferred in scope section) is a BLOCKER (the frontend is out of sync with what the backend team declared). Auditor also verifies the pinned `generator_version` matches the backend's `spec_version`.

After the frontend gate, the REQ is complete across both halves.
</frontend_handoff_sequence>

<verification_checklist>
## Before declaring a crew run complete

- **Does `wopr.yml` exist at project root and parse cleanly?** Every agent reads it on every invocation. Missing or unparseable `wopr.yml` should have stopped Step 1; if it didn't, something is wrong upstream.
- **Did Phase 0 run at the start?** The scout should have produced (Path A) or refreshed (Path B) the Gap Analysis (Latest Session) table before any REQ was picked. If no gap analysis exists for this session, Phase 0 was skipped in error.
- **Was Migration Context captured?** The extracted-requirements document's Migration Context section should have current content for this session (or an explicit "No structural changes this session" note). If it still contains template placeholders, the Migration Context Prompt was skipped.
- **Did the run cover exactly one REQ?** Not zero, not more. If more than one REQ was implemented, the run was mis-scoped; split it retroactively in the tracking doc.
- **Does the tracking document match reality?** The REQ is marked `✅ Implemented` with pointers to actual files. `coverage_status` and `spec_version` fields are populated on the log entry. The scout or auditor should have caught drift; if they didn't, that's a gap in the checklists worth surfacing.
- **Did the coverage gate pass before the auditor ran?** Build, test suite, coverage thresholds, handoff-contract-current, and static-analysis Quality Gate are the five conditions. The tester's `coverage_status` entry should show `gate: PASS` and include the Sonar verdict.
- **Did the auditor actually write the audit report?** It is not optional. The file at the path resolved from `specs.audit_report` should be populated for this run.
- **Is the verdict UNBLOCKED?** If BLOCKED and you're declaring the run complete, you've declared a broken crew complete. Don't.
- **If the REQ touched the API surface, is the handoff contract updated with a JSON Pointer into the current spec?** The auditor's hard rule blocks this, but double-check.
- **Is the pinned `generator_version` in sync with the `spec_version`?** Lockstep is a BLOCKER-class auditor rule; verify `wopr.yml` and the tracking-document fields agree with what the generator config actually pins.
- **Did the full test suite pass?** Not just the new tests. Regression in old tests means the coder's change broke something that was working.
</verification_checklist>

<reference_index>
## Domain knowledge for the crew

**Configuration:**

- `webteam-ai-tools/docs/wopr-yml-schema.md` (project config schema, shared across WOPR packs)
- `catalog/crew/templates/wopr.example.yml` (worked examples for backend and frontend projects)

**Agents:**

- `catalog/crew/agents/wopr-crew-scout.md`
- `catalog/crew/agents/wopr-crew-coder.md`
- `catalog/crew/agents/wopr-crew-tester.md`
- `catalog/crew/agents/wopr-crew-auditor.md`

**Templates (tracking documents):**

- `catalog/crew/templates/coder-spec.template.md`
- `catalog/crew/templates/tester-spec.template.md`
- `catalog/crew/templates/implementation-tracking.template.md`
- `catalog/crew/templates/frontend-handoff-contract.template.md`
- `catalog/legacy-migration/templates/extracted-requirements.template.md` (migration projects only)

**Scripts:**

- `catalog/crew/scripts/autorun.sh` (unattended-run orchestration)
- `catalog/meta-authoring/hooks/prompt-log-hook.py` (Stop hook; appends per-turn summaries to `PROMPT_LOG.md`)
- `catalog/meta-authoring/hooks/git-branch-guard.sh` (PreToolUse hook; blocks `git commit` / `git push` on non-`feature/*` branches)
- `catalog/meta-authoring/scripts/configure_prompt_log.py` (registers the Stop hook idempotently; invoked by `/wopr-configure-prompt-log`)
- `catalog/meta-authoring/scripts/configure_git_guard.py` (registers the PreToolUse hook idempotently; invoked by `/wopr-configure-git-guard`)

**Grounding reference (not shipped with the pack):**

- `research/seeds/client-project-b-api/` (one complete reference implementation; the pack was extracted from this seed)

**Pack overview:**

- `catalog/crew/README.md` (this pack: pattern description, four-role crew, configuration, project setup)
- `catalog/legacy-migration/README.md` (migration-specific layer: deep analysis mode, legacy extraction tooling, translation tables; depends on `crew`)
</reference_index>
