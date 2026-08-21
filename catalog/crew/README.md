# crew pack

Universal four-role agent crew for disciplined REQ-driven development. One scout, one coder, one tester, one auditor. One REQ per crew run. OpenAPI-first. Spec-files-as-authority. Coverage-gated.

This pack is the load-bearing surface for any project that wants WOPR-driven development discipline: net-new feature work, ongoing iteration on an existing modern project, blocker fixes, frontend handoffs, or legacy migration. The crew does not care where REQs come from; it cares about role separation, model alignment, and the audit gate.

The migration-specific layer (Phase 0 deep analysis, legacy extraction tooling, translation tables, schema extractor) lives in the `legacy-migration` pack as an opt-in add-on for migration projects.

## Install

Standalone:

```sh
wopr add crew
```

With migration support:

```sh
wopr add crew legacy-migration
```

Profiles that compose this pack are listed in `catalog.yaml` (`legacy-migration-team`, `everything`, etc.).

## What this pack ships

```
catalog/crew/
├── README.md                                    (this file)
├── agents/
│   ├── wopr-crew-scout.md                   discovery, first in the crew
│   ├── wopr-crew-coder.md                   implements one REQ at a time
│   ├── wopr-crew-tester.md                  generates tests for implemented REQs
│   ├── wopr-crew-auditor.md                 final-gate auditor, writes audit report and distills lessons
│   └── wopr-crew-evaluator.md               read-only CRAG relevance grader for the perpetual learning corpus
├── skills/
│   └── wopr-run-crew/
│       └── SKILL.md                             orchestrates the four agents end to end, including the CRAG pre-step
├── templates/
│   ├── README.md                                template usage guide
│   ├── coder-spec.template.md                   coding standards the coder reads
│   ├── tester-spec.template.md                  testing standards the tester reads
│   ├── implementation-tracking.template.md      per-REQ status, read/written by all four agents
│   ├── frontend-handoff-contract.template.md   API change breakdown for frontend handoff
│   └── wopr.example.yml                         worked examples of the project config file
└── scripts/
    ├── README.md                                autorun.sh usage, env vars, exit codes
    └── autorun.sh                               unattended-run loop with rate-limit resume
```

## The crew shape

The crew decomposes work into four roles. Each role is a separate agent with a single job. Roles are never combined: an agent that writes code AND its tests produces self-approving output.

1. **Scout.** Reads the project's spec documents, the requirements source, and the codebase. Produces a structured discovery report. Read-only except for status updates to the tracking document.
2. **Coder.** Implements one REQ at a time against the coder spec. Updates tracking-doc status. Maintains the coder spec when `spec_writes` is ON. Does not write tests.
3. **Tester.** Generates tests for the just-implemented REQ against the tester spec. Maintains the tester spec when `spec_writes` is ON. Records coverage status. Does not modify production code.
4. **Auditor.** Reads everything (specs, tracking doc, handoff contract, audit report history) and decides UNBLOCKED or BLOCKED. Runs once per gate (a gate is not iterative; the merge decision is downstream of the audit report). Writes the audit report.

The crew's principles, full step-by-step orchestration, intake routing (crew run, blocker fix, frontend handoff, unattended), and verification checklist live in two parallel forms:

* **`skills/wopr-run-crew/SKILL.md`**, the skill form, loaded via the Skill tool on Claude Code and Gemini CLI and available as a native skill on Copilot CLI.
* **`agents/wopr-crew.md`**, the agent form: the recommended entry on Copilot CLI, and an alternative for Claude / Gemini operators who prefer agent dispatch over skill invocation. Same semantics, same procedure, same outputs; just loaded as a custom agent rather than a skill.

How to invoke per CLI:

* **Claude Code**: `/wopr-run-crew FOC26-XXXX` (the Skill tool handles the slash-prefix), or natural language ("run the wopr-run-crew skill against FOC26-XXXX").
* **Gemini CLI**: same as Claude (slash-prefix or natural language); the skill is symlinked to `~/.gemini/skills/`.
* **Copilot CLI**: `copilot --agent wopr-crew --prompt "FOC26-XXXX"`, or invoke the agent inside a session via `@wopr-crew FOC26-XXXX`, or natural language ("use the wopr-crew agent against FOC26-XXXX"). The agent dispatches the four role subagents (`@wopr-crew-scout`, `coder`, `tester`, `auditor`) via Copilot's documented `agent` tool (subagent dispatch).

## Perpetual learning: the CRAG read path

Every crew run carries forward distilled lessons from prior runs through a Corrective RAG (CRAG) read path. Before each of the four agent steps, the orchestrator runs a four-substep pre-step:

1. A deterministic pre-filter (the `learnings_search` MCP tool) narrows the corpus by REQ-ID match, stack-tag intersection, and recency.
2. If anything passes the filter, an independent `crew-evaluator` agent grades the candidates HIGH / MEDIUM / LOW against the current REQ context. The evaluator is read-only and isolated from the auditor by design; it is the structural defense against self-improvement-loop bias.
3. HIGH and MEDIUM entries are injected into the next working agent's `relevant_learnings` input. LOW entries are kept out of the prompt but listed by ID for traceability.

After the gate, the auditor performs a **distillation step**: zero to three new entries get appended to `LEARNINGS.md` via the `append_learnings` MCP tool. The auditor is the only writer in the system. Distillation is append-only and end-of-run only.

Two file locations:

- `<workspace>/LEARNINGS.md`: committable, per-project. Lives in the project repo, travels with the project.
- `~/.wopr/LEARNINGS.md`: per-machine, used when working outside any workspace (no `wopr.yml` in scope). The registry at `~/.wopr/workspaces.txt` lets outside-workspace reads aggregate across every known workspace path.

Three new MCP tools register with the WOPR server: `mcp__wopr__append_learnings`, `mcp__wopr__learnings_search`, `mcp__wopr__learnings_path`. The auditor uses the first; the orchestrator uses the second during the pre-step; the third is diagnostic.

Full operator-facing reference (file format, MCP tool reference, operating procedure, failure modes, design decisions, research citations) is in `webteam-ai-tools/docs/perpetual-learning.md`. The orchestrator's procedural definition of the pre-step lives under `<crag_pre_step>` in `skills/wopr-run-crew/SKILL.md`. The evaluator's grading rubric and output contract live in `agents/wopr-crew-evaluator.md`. The auditor's distillation rules live under "Distillation step" in `agents/wopr-crew-auditor.md`.

## Scout-contract handoff

The scout writes a structured contract file to `<target_dir>/crew-contracts/<REQ-ID>/scout.md` on every crew run. The contract carries the load-bearing structured data the downstream agents need: `files_touched`, `class_inventory` (class names with file paths and key signatures), and `package_structure`. Each downstream agent (coder, tester, auditor) receives the contract content as a required input and consults it before doing any discovery of its own.

The orchestrator validates the contract via `mcp__wopr__validate_scout_contract` after the scout completes. A missing or under-populated contract aborts the crew before the coder dispatches; the validator's errors are surfaced verbatim to the operator. There is no silent retry. An empty `class_inventory` is permitted for non-class-shaped REQs (config edits, doc REQs) and surfaces as an advisory warning rather than a blocker.

Why this exists: scout-first discovery was the single biggest token drain in early crew runs. Without an enforced handoff, downstream coder and tester agents independently re-grepped the codebase at Opus prices, producing hundreds of thousands of tokens of duplicate discovery per project. Worse, the lack of a shared contract let the same entity field name land in three different forms across three agents. The contract is the gate that fixes both.

The contract format and the validator's specific rules live in `src/wopr/tools/crew_contracts.py`. The scout's writing instructions live under "Scout contract format" in `agents/wopr-crew-scout.md`. The orchestrator's gate enforcement lives under "Gate (scout-contract validation)" in `skills/wopr-run-crew/SKILL.md`.

## Scripts vs agents

Agents are reasoning instruments: they synthesize novel code, design test scenarios, audit against a spec, judge whether a contract drift is significant. Anything that is fully deterministic given known inputs and produces a known output shape is NOT an agent task. It is a script.

**Heuristic for skill authors:**

> If the step requires interpreting natural-language context or making a judgment call, dispatch an agent. Otherwise, write a script (or call an existing MCP tool).

Cost matters here. An Opus agent invocation spends tens of thousands of tokens. A Python script that reads a CSV and returns an exit code spends none. [colleague]'s 7-REQ Spring Boot retrospective ([retrospective_summary_2026-05-18.md](https://github.com/[client-org]/webteam-[client-project-b]-ai-scaffolding/blob/feature/tbd-email-domain-api/ai/prompts/retrospective_summary_2026-05-18.md#6-what-to-script-vs-what-to-agent) section 6) estimated ~100-350k tokens wasted across his project on tasks an agent did not need to think about. Examples flagged in that retrospective:

| Should NOT be an agent | Should be |
|---|---|
| Create feature branch from chain tip | `git checkout -b feature/...` (one-liner or hook) |
| Move draft to a `processed/` directory | `mv` command |
| Run a build command and parse its exit code | Bash + structured output file |
| JaCoCo / coverage threshold check (>= N%) | Python parsing the coverage CSV |
| Sonar scan invocation | `mvn sonar:sonar` with token wired in |
| Verify a generated artifact is non-empty | One-line bash check in pre-flight |

This pack already follows the heuristic in several places:

* **Scout-contract validation** at the scout -> coder gate is done by the `mcp__wopr__validate_scout_contract` MCP tool, not by dispatching an agent to "verify the contract is well-formed."
* **CRAG candidate retrieval** uses the `mcp__wopr__learnings_search` MCP tool to do the deterministic prefilter; only the grading step (which is judgment work) goes through the `crew-evaluator` agent.
* **Doctor readiness** walks specs for unresolved `TODO:` markers via Python file reads. Agent dispatch would be wasteful for character counting.
* **Legacy-migration pre-extraction** runs as a Python script (`extract_legacy_context.py`) the operator triggers once; the scout reads the script's structured output rather than re-grepping the legacy codebase on every crew run.
* **`autorun.sh`** handles the unattended rate-limit loop in shell, not via agent reasoning.

When proposing a new crew step in a skill, apply the heuristic before reaching for the Task tool. Skill authors creating subagents are pointed at this section from `wopr-create-subagents/SKILL.md`.

Existing scripts ship in `catalog/crew/scripts/` and `catalog/legacy-migration/scripts/`. Both directories carry their own README inventories.

## Requirements source: local or Jira

The orchestrator pulls the active REQ body from one of two sources, declared in `wopr.yml`'s `requirements:` section:

- `source: local` (default): reads `<wopr.yml dir>/<requirements.local.path>/<REQ-ID>.md`. Default path is `requirements/`. Backwards-compatible: existing projects without a `requirements:` section behave as `source: local` with the default path.
- `source: jira`: calls `mcp__plugin_atlassian_atlassian__getJiraIssue` with the REQ-ID (the Jira issue key). The Atlassian MCP comes from either a self-hosted MCP server registered in `~/.claude.json` or the Claude.ai Atlassian plugin enabled in Claude Code; either works at runtime.

The Atlassian cloud_id is **not** stored in `wopr.yml`. It is machine-level state (the same Atlassian site for every project on a given operator's machine) and the MCP exposes it via `getAccessibleAtlassianResources`. The orchestrator resolves it at jira-mode pre-flight: zero sites → abort with fix-paths advice; one site → use it; multiple sites → abort because the default flow does not yet disambiguate. Single-site operators (the common case) have zero machine-level config to manage; multi-site operators file a follow-up so we add per-project site selection.

`wopr.yml`'s `requirements.jira` block carries only an optional `project_key` (REQ-ID prefix sanity check; e.g., `FOC26`). Both `cloud_id` and any other Jira fields are intentionally absent from the schema.

The orchestrator re-fetches the REQ body fresh on every agent dispatch (scout, coder, tester, auditor). Operator edits made mid-crew are picked up by the next agent.

Doctor surfaces `requirements.local_path_missing` (warning) when `source: local` and the path is absent, and `requirements.jira_mode_advisory` (informational notice) when `source: jira` so the operator sees that both install paths for Atlassian access are documented. The orchestrator's runtime pre-flight is the real check; the crew aborts before scout dispatch with an actionable error if no Atlassian site is accessible (or if too many are).

## Project configuration: `wopr.yml`

Every project using the crew has a `wopr.yml` at its project root. The schema is shared across WOPR packs (any pack that needs project context reads `wopr.yml`). See:

- `templates/wopr.example.yml`: worked examples for backend and frontend projects
- `webteam-ai-tools/docs/wopr-yml-schema.md`: full schema with field tables

The crew does not run without `wopr.yml`. If it is missing, every agent stops and reports.

## Pre-flight (run once per project)

The recommended path is `/wopr-init-project` (one operator command) followed by the optional hooks. The skill detects the stack, writes `wopr.yml`, writes the stack-pre-filled coder and tester specs, drops `implementation-tracking.template.md` and `frontend-handoff-contract.template.md` (and `extracted-requirements.template.md` on migration projects), writes `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md`, and seeds `LEARNINGS.md` with curated foundational lessons for the detected stack.

If you prefer the manual path:

1. Drop `wopr.yml` at the project root, populated from `templates/wopr.example.yml`.
2. Call `mcp__wopr__write_tracking_doc_stub` and (for backend-producer projects) `mcp__wopr__write_handoff_contract_stub` to land the tracking and handoff templates at the paths declared in `wopr.yml`. Migration projects also call `mcp__wopr__write_extracted_requirements_stub`. These tools resolve the install root server-side; hand-copying from `catalog/crew/templates/` is the fallback, not the default.
3. Walk every `[STACK: ...]` marker and replace it with your stack's specifics. Delete sections that do not apply. Add sections for concerns the skeleton doesn't cover.

Optional but recommended: register the WOPR bootstrap hooks. `/wopr-configure-prompt-log` adds a Stop hook for the per-turn audit log; `/wopr-configure-git-guard` adds a PreToolUse hook that keeps agents off `main` and `develop`.

For migration projects, also install the `legacy-migration` pack and populate the migration-specific `wopr.yml` fields. See `catalog/legacy-migration/README.md`.

**Important:** the crew role agents (`scout`, `coder`, `tester`, `auditor`, orchestrator) are forbidden from running `find` against the workspace or `/` to locate pack-shipped templates. The stub-writer tools above (and `mcp__wopr__get_pack_template` for direct read access) exist to make brute-force filesystem search unnecessary. Operator-driven `/wopr-init-project` is the canonical entry point.

## Status

**Pre-release.** The four-role crew shape and the agent set have been validated on one completed migration POC. The pack is dogfooded across multiple WOPR-adjacent projects ([client-project-cac], [client-system], [client-project-b]) before a `1.0` cut.

Grounding material from the original extraction lives at `research/seeds/client-project-b-api/` in this repo. Out of `catalog/` so it does not ship.

## Relationship to other packs

- **`legacy-migration`** depends on this pack. Composes on top for migration projects.
- **`java`** ships Spring Boot patterns and reviewers. Independent of this pack but commonly composed via the `legacy-migration-team` and `java-team` profiles.
- **`angular`** ships Angular patterns and reviewers. Same shape.
- **`meta-authoring`** ships the prompt-log Stop hook and git-branch-guard PreToolUse hook that the project setup section above references.
- **`auditors`** ships skill/command/subagent quality auditors. Useful when authoring new packs but not required for crew runs.
