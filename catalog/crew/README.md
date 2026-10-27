# crew pack

Universal four-role agent crew for disciplined REQ-driven development. One scout, one coder, one tester, one auditor. One REQ per crew run. API-contract-first (OpenAPI or GraphQL). Spec-files-as-authority. Coverage-gated.

This pack is the load-bearing surface for any project that wants KITT-driven development discipline: net-new feature work, ongoing iteration on an existing modern project, blocker fixes, frontend handoffs, or legacy migration. The crew does not care where REQs come from; it cares about role separation, model alignment, and the audit gate.

A migration-specific layer (Phase 0 deep analysis, legacy extraction tooling, translation tables, schema extractor) is not part of KITT. The crew's `deep_analysis` scout mode and the `legacy-migration.*` `kitt.yml` fields are the integration points such a pack composes with.

## Install

```sh
claude plugin install kitt-crew@kitt-marketplace
```

Every profile in `catalog.yaml` (`angular-team`, `python-ai`, `fullstack`, `everything`) composes this pack.

## What this pack ships

```
catalog/crew/
├── README.md                                    (this file)
├── agents/
│   ├── kitt-crew-scout.md                   discovery, first in the crew
│   ├── kitt-crew-coder.md                   implements one REQ at a time
│   ├── kitt-crew-tester.md                  generates tests for implemented REQs
│   ├── kitt-crew-auditor.md                 final-gate auditor, writes audit report and distills lessons
│   ├── kitt-crew-evaluator.md               read-only CRAG relevance grader for the perpetual learning corpus
│   └── kitt-crew-designer.md                conditional design/UX role; visual spec + @visual regression tests
├── skills/
│   └── kitt-run-crew/
│       └── SKILL.md                             orchestrates the four agents end to end, including the CRAG pre-step
├── templates/
│   ├── README.md                                template usage guide
│   ├── coder-spec.template.md                   coding standards the coder reads
│   ├── tester-spec.template.md                  testing standards the tester reads
│   ├── implementation-tracking.template.md      per-REQ status, read/written by all four agents
│   ├── frontend-handoff-contract.template.md   API change breakdown for frontend handoff
│   └── kitt.example.yml                         worked examples of the project config file
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

A fifth, **conditionally dispatched** role exists for projects that declare `specs.design_spec` in `kitt.yml`: the **Designer** (`kitt-crew-designer.md`) maintains the visual spec, derives per-REQ appearance acceptance criteria, and writes the `@visual` regression tests the auditor runs at the gate. Baseline approval is operator-only. Backend-only projects never dispatch it.

The crew's principles, full step-by-step orchestration, intake routing (crew run, blocker fix, frontend handoff, unattended), and verification checklist live in two parallel forms:

* **`skills/kitt-run-crew/SKILL.md`**, the skill form, loaded via the Skill tool on Claude Code and Gemini CLI and available as a native skill on Copilot CLI.
* The crew's single orchestration source is `skills/kitt-run-crew/SKILL.md`. The former agent-mode duplicate (`agents/kitt-crew.md`, the Copilot entry) was removed when Copilot support was deferred; one procedure, one file.

How to invoke per CLI:

* **Claude Code**: `/kitt-run-crew DEMO-123` (the Skill tool handles the slash-prefix), or natural language ("run the kitt-run-crew skill against DEMO-123").
* **Gemini CLI**: same as Claude (slash-prefix or natural language); the skill is symlinked to `~/.gemini/skills/`.
* **Copilot CLI**: deferred. The former agent-mode entry (`agents/kitt-crew.md`) was removed with it; when Copilot support lands, it will dispatch the four role subagents via Copilot's documented `agent` tool.

## Perpetual learning: the CRAG read path

Every crew run carries forward distilled lessons from prior runs through a Corrective RAG (CRAG) read path. Once per crew run, before Step 1, the orchestrator runs a three-substep pre-step:

1. A deterministic pre-filter (the `learnings_search` MCP tool) narrows the corpus by REQ-ID match, stack-tag intersection, and recency.
2. Only when the pre-filter returns more than five candidates, an independent `crew-evaluator` agent grades them HIGH / MEDIUM / LOW against the current REQ context (five or fewer are injected whole, marked advisory — at that corpus size selection adds nothing). The evaluator is read-only and isolated from the auditor by design; it is the structural defense against self-improvement-loop bias.
3. HIGH and MEDIUM entries form the single `relevant_learnings` block that goes to all four working agents. LOW entries are kept out of the prompt but listed by ID for traceability.

After the gate, the auditor performs a **distillation step**: zero to three new entries get appended to `LEARNINGS.md` via the `append_learnings` MCP tool. The auditor is the only writer in the system. Distillation is append-only and end-of-run only.

Two file locations:

- `<workspace root>/LEARNINGS.md`: committable, per-project. Lives in the project repo, travels with the project.
- `~/.kitt/LEARNINGS.md`: per-machine, used only when a call names no target workspace at all and none is in scope. The registry at `~/.kitt/workspaces.txt` lets outside-workspace reads aggregate across every known workspace path.

The workspace root is resolved the same way by every learnings tool (seed, append, search, curate): starting at the target path and walking up, the nearest directory carrying `kitt.yml` **or** `LEARNINGS.md` wins, and the search stops at the git toplevel. A repo whose `kitt.yml` files live in subpackages declares where its corpus lives by seeding the directory that should own it; `seed_learnings` writes `LEARNINGS.md` there, and that file is itself the marker. A call that names a target which resolves to no workspace root gets an error listing the searched paths, not a silent write to `~/.kitt/LEARNINGS.md`. The algorithm and its edge cases are documented in `src/kitt/tools/_workspace_root.py`.

Three new MCP tools register with the KITT server: `mcp__kitt__append_learnings`, `mcp__kitt__learnings_search`, `mcp__kitt__learnings_path`. The auditor uses the first; the orchestrator uses the second during the pre-step; the third is diagnostic.

Full operator-facing reference (file format, MCP tool reference, operating procedure, failure modes, design decisions, research citations) is in `docs/perpetual-learning.md` (this repo). The orchestrator's procedural definition of the pre-step lives under `<crag_pre_step>` in `skills/kitt-run-crew/SKILL.md`. The evaluator's grading rubric and output contract live in `agents/kitt-crew-evaluator.md`. The auditor's distillation rules live under "Distillation step" in `agents/kitt-crew-auditor.md`.

## Scout-contract handoff

The scout writes a structured contract file to `<target_dir>/crew-contracts/<REQ-ID>/scout.md` on every crew run. The contract carries the load-bearing structured data the downstream agents need: `files_touched`, `class_inventory` (class names with file paths and key signatures), and `package_structure`. Each downstream agent (coder, tester, auditor) receives the contract content as a required input and consults it before doing any discovery of its own.

The orchestrator validates the contract via `mcp__kitt__validate_scout_contract` after the scout completes. A missing or under-populated contract aborts the crew before the coder dispatches; the validator's errors are surfaced verbatim to the operator. There is no silent retry. An empty `class_inventory` is permitted for non-class-shaped REQs (config edits, doc REQs) and surfaces as an advisory warning rather than a blocker.

The validator also checks the contract against itself, because a contract that passes a shape check while contradicting itself hands two agents two different instructions. A `files_touched` entry that is absolute, traverses out with `..`, or otherwise resolves outside the workspace is an error: the list is an edit allowlist. Three more conditions are warnings, since each has a legitimate reading the operator has to judge: entries with no file on disk (a scout naming files the coder will create, or a typo), a backticked path in the body that spells a `files_touched` basename differently (`tests/test_queue.py` against `tests/api/test_queue.py`), and a `class_inventory` entry naming a file `files_touched` never claims.

Why this exists: scout-first discovery was the single biggest token drain in early crew runs. Without an enforced handoff, downstream coder and tester agents independently re-grepped the codebase at Opus prices, producing hundreds of thousands of tokens of duplicate discovery per project. Worse, the lack of a shared contract let the same entity field name land in three different forms across three agents. The contract is the gate that fixes both.

The contract format and the validator's specific rules live in `src/kitt/tools/crew_contracts.py`. The scout's writing instructions live under "Scout contract format" in `agents/kitt-crew-scout.md`. The orchestrator's gate enforcement lives under "Gate (scout-contract validation)" in `skills/kitt-run-crew/SKILL.md`.

## Scripts vs agents

Agents are reasoning instruments: they synthesize novel code, design test scenarios, audit against a spec, judge whether a contract drift is significant. Anything that is fully deterministic given known inputs and produces a known output shape is NOT an agent task. It is a script.

**Heuristic for skill authors:**

> If the step requires interpreting natural-language context or making a judgment call, dispatch an agent. Otherwise, write a script (or call an existing MCP tool).

Cost matters here. An Opus agent invocation spends tens of thousands of tokens. A Python script that reads a CSV and returns an exit code spends none. A colleague's 7-REQ Spring Boot retrospective (`retrospective_summary_2026-05-18.md`, section 6, "what to script vs. what to agent") estimated ~100-350k tokens wasted across his project on tasks an agent did not need to think about. Examples flagged in that retrospective:

| Should NOT be an agent | Should be |
|---|---|
| Create feature branch from chain tip | `git checkout -b feature/...` (one-liner or hook) |
| Move draft to a `processed/` directory | `mv` command |
| Run a build command and parse its exit code | Bash + structured output file |
| JaCoCo / coverage threshold check (>= N%) | Python parsing the coverage CSV |
| Sonar scan invocation | `mvn sonar:sonar` with token wired in |
| Verify a generated artifact is non-empty | One-line bash check in pre-flight |

This pack already follows the heuristic in several places:

* **Scout-contract validation** at the scout -> coder gate is done by the `mcp__kitt__validate_scout_contract` MCP tool, not by dispatching an agent to "verify the contract is well-formed."
* **CRAG candidate retrieval** uses the `mcp__kitt__learnings_search` MCP tool to do the deterministic prefilter; only the grading step (which is judgment work) goes through the `crew-evaluator` agent.
* **Doctor readiness** walks specs for unresolved `TODO:` markers via Python file reads. Agent dispatch would be wasteful for character counting.
* **Legacy-migration pre-extraction** runs as a Python script (`extract_legacy_context.py`) the operator triggers once; the scout reads the script's structured output rather than re-grepping the legacy codebase on every crew run.
* **`autorun.sh`** handles the unattended rate-limit loop in shell, not via agent reasoning.

When proposing a new crew step in a skill, apply the heuristic before reaching for the Task tool. Skill authors creating subagents are pointed at this section from `kitt-create-subagents/SKILL.md`.

Existing scripts ship in `catalog/crew/scripts/`, which carries its own README inventory.

## Requirements source: local or Jira

The orchestrator pulls the active REQ body from one of two sources, declared in `kitt.yml`'s `requirements:` section:

- `source: local` (default): reads `<kitt.yml dir>/<requirements.local.path>/<REQ-ID>.md`. Default path is `requirements/`. Backwards-compatible: existing projects without a `requirements:` section behave as `source: local` with the default path.
- `source: jira`: calls `mcp__plugin_atlassian_atlassian__getJiraIssue` with the REQ-ID (the Jira issue key). The Atlassian MCP comes from either a self-hosted MCP server registered in `~/.claude.json` or the Claude.ai Atlassian plugin enabled in Claude Code; either works at runtime.

The Atlassian cloud_id is **not** stored in `kitt.yml`. It is machine-level state (the same Atlassian site for every project on a given operator's machine) and the MCP exposes it via `getAccessibleAtlassianResources`. The orchestrator resolves it at jira-mode pre-flight: zero sites → abort with fix-paths advice; one site → use it; multiple sites → abort because the default flow does not yet disambiguate. Single-site operators (the common case) have zero machine-level config to manage; multi-site operators file a follow-up so we add per-project site selection.

`kitt.yml`'s `requirements.jira` block carries only an optional `project_key` (REQ-ID prefix sanity check; e.g., `DEMO`). Both `cloud_id` and any other Jira fields are intentionally absent from the schema.

The orchestrator re-fetches the REQ body fresh on every agent dispatch (scout, coder, tester, auditor). Operator edits made mid-crew are picked up by the next agent.

Doctor surfaces `requirements.local_path_missing` (warning) when `source: local` and the path is absent, and `requirements.jira_mode_advisory` (informational notice) when `source: jira` so the operator sees that both install paths for Atlassian access are documented. The orchestrator's runtime pre-flight is the real check; the crew aborts before scout dispatch with an actionable error if no Atlassian site is accessible (or if too many are).

## Project configuration: `kitt.yml`

Every project using the crew has a `kitt.yml` at its project root. The schema is shared across KITT packs (any pack that needs project context reads `kitt.yml`). See:

- `templates/kitt.example.yml`: worked examples for backend and frontend projects
- `catalog/crew/templates/kitt-yml-schema.md`: full schema with field tables (ships with the pack; agents fetch it via `get_pack_template`)

The crew does not run without `kitt.yml`. If it is missing, every agent stops and reports.

## Pre-flight (run once per project)

The recommended path is `/kitt-init-project` (one operator command) followed by the optional hooks. The skill detects the stack, writes `kitt.yml`, writes the stack-pre-filled coder and tester specs, drops `implementation-tracking.template.md` and `frontend-handoff-contract.template.md`, writes `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md`, and seeds `LEARNINGS.md` with curated foundational lessons for the detected stack.

If you prefer the manual path:

1. Drop `kitt.yml` at the project root, populated from `templates/kitt.example.yml`.
2. Call `mcp__kitt__write_tracking_doc_stub` and (for backend-producer projects) `mcp__kitt__write_handoff_contract_stub` to land the tracking and handoff templates at the paths declared in `kitt.yml`. These tools resolve the install root server-side; hand-copying from `catalog/crew/templates/` is the fallback, not the default.
3. Walk every `[STACK: ...]` marker and replace it with your stack's specifics. Delete sections that do not apply. Add sections for concerns the skeleton doesn't cover.

Optional but recommended: register the KITT bootstrap hooks. `/kitt-configure-prompt-log` adds a Stop hook for the per-turn audit log; `/kitt-configure-git-guard` adds a PreToolUse hook that keeps agents off `main` and `develop`.

For migration projects, a migration-specific pack composes on top and populates the migration-specific `kitt.yml` fields.

**Important:** the crew role agents (`scout`, `coder`, `tester`, `auditor`, orchestrator) are forbidden from running `find` against the workspace or `/` to locate pack-shipped templates. The stub-writer tools above (and `mcp__kitt__get_pack_template` for direct read access) exist to make brute-force filesystem search unnecessary. Operator-driven `/kitt-init-project` is the canonical entry point.

## Status

**Pre-release.** The four-role crew shape and the agent set have been validated on one completed migration POC. The pack is dogfooded across multiple KITT-adjacent projects (example-crm, example-billing-system, demo-api) before a `1.0` cut.

Grounding material from the original extraction lives at `research/seeds/demo-api/` in this repo. Out of `catalog/` so it does not ship.

## Relationship to other packs

- A migration-specific pack can depend on this pack and compose on top for migration projects.
- **`angular`** ships Angular patterns and reviewers. Composed with the crew via the `angular-team`, `fullstack`, and `everything` profiles.
- **`python`** ships FastAPI/Python patterns and reviewers. Composed via `python-ai`, `fullstack`, and `everything`.
- **`_core`** ships the prompt-log Stop hook and git-branch-guard PreToolUse hook that the project setup section above references.
- **`auditors`** ships skill/command/subagent quality auditors. Useful when authoring new packs but not required for crew runs.
