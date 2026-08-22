---
name: wopr-doctor
description: Scan the current workspace, identify the stack, and report what WOPR setup is missing (wopr.yml placement, WOPR packs, external MCPs, specs). Read-only diagnostic. Use before the first crew run on a project, after dependency upgrades that may have changed the stack, or any time the agent wants to confirm a project is correctly wired for WOPR.
---

<objective>
Operator-facing diagnostic for WOPR setup. Detects the stack via well-known marker files, cross-references against a recommendation table, and prints a structured report listing missing `wopr.yml` placements, missing WOPR packs, missing external MCPs, and missing specs. Does not write files. Operator runs the suggested commands themselves.
</objective>

<when_to_run>
- Before the first crew run on a new project. Confirms the project is wired up before the operator burns Sonnet/Opus tokens discovering setup gaps inside an agent run.
- After major dependency upgrades that may have changed the stack signature (added a framework, removed a backend, switched monorepo flavors).
- After installing a new WOPR pack, to confirm the new pack is correctly registered.
- Any time an operator suspects a missing MCP or misplaced `wopr.yml` is causing crew agents to behave unexpectedly.

Do NOT run this skill as part of a crew run. It is an out-of-band setup tool, not a runtime check.
</when_to_run>

<procedure>
1. **Resolve the target workspace from the OPERATOR's current context.** The operator's current working directory is the only legitimate source for this. Do NOT rely on any WOPR install state, env var, or pinned workspace. If the operator explicitly named a project path (e.g. `apps/example-app`), resolve it against the cwd into an absolute path. If the operator did not name one, ask them which project to scan; do not infer.

2. **Print the resolved workspace BEFORE doing anything.** Print one line up front to the operator: `Scanning <absolute workspace path>.` If the resolution is wrong (e.g. the operator wanted `apps/example-app` but you resolved to the monorepo root, or to an unrelated project), stop and ask for the right path. Doctor's value collapses to zero when it scans the wrong directory silently. This step is non-negotiable.

3. **Call `mcp__wopr__detect_stack`** with the resolved absolute path as `workspace_path`. The tool requires this argument; it does not infer a workspace from environment state. The result's top-level `workspace_path` field echoes the directory it scanned. If the result is an `error`, surface it cleanly and stop.

4. **Build the recommendation by hand.** There is no recommendation tool; `detect_stack` only detects. Read `catalog/_core/data/doctor-recommendations.yaml` (the framework-to-pack, signal-to-MCP, and language-to-plugin mapping tables) and cross-reference it against: the stack detected in step 3, the packs installed per `.ai-cli/wopr.lock.yaml`, and the MCP registrations in all three CLI configs (`~/.claude.json`, `~/.gemini/settings.json`, and `~/.copilot/mcp-config.json`). From this, derive missing `wopr.yml` paths, missing WOPR packs, missing external MCPs, and copy-paste install commands.

5. **Print a structured report** to the operator. Format the report sections in this order:
   - **Workspace path**: the scanned directory (same line you already showed in step 2).
   - **Stack detected**: language(s), framework(s), versions, package manager, monorepo type if any, test runner.
   - **wopr.yml status**: existing files with their content summary (slug, build_file, base_package, declared spec paths, openapi pin) AND missing files with proposed locations and reasons. Render the summary so the operator sees what each wopr.yml actually declares, not just that it exists.
   - **Readiness per project**: for each existing wopr.yml, render `ready: True/False` and the list of blockers (missing specs, unresolved TODO markers in specs, missing agent-instructions file, etc.). Any one of `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` at the target, or `.github/copilot-instructions.md` at workspace root, satisfies the agent-instructions requirement. A project is "ready" only when zero blockers remain. This is the source of truth for whether the project can run a crew; "wopr.yml exists" is no longer enough.
   - **CRAG status per project (warnings)**: for each existing wopr.yml, render the `warnings` list separately from blockers. The two common warnings are:
     - **CRAG corpus is empty**: `LEARNINGS.md` is missing or has no parseable `## LRN-` entries. The crew runs; the RAG just returns nothing on the first gate until the auditor distills the first entry. Suggest `mcp__wopr__seed_learnings` with the detected stack tags to bootstrap.
     - **Workspace not registered**: the project's absolute path is absent from `~/.wopr/workspaces.txt`. Outside-workspace sessions and sibling-workspace aggregation cannot see this project's lessons. The first call to `seed_learnings`, `append_learnings`, or `learnings_search` from inside the workspace registers it automatically.
     Warnings do NOT flip `ready` to False. Render them so the operator sees the gap and can choose to address it.
   - **WOPR packs**: installed (from `wopr.lock.yaml`) and recommended additions for the detected stack.
   - **External MCPs**: detected signals matched against the MCP registrations across all three CLI configs (`~/.claude.json`, `~/.gemini/settings.json`, `~/.copilot/mcp-config.json`). For each missing MCP, include the install command and documentation URL.
   - **Suggested commands**: ordered list of operator-runnable commands. Doctor does NOT run these; the operator does.

6. **Tell the operator what to do next.** Close with a one-liner: "Doctor is read-only. Run the commands above. Re-run doctor to confirm gaps closed."
   - When wopr.yml is missing OR readiness blockers exist (missing specs, missing agent-instructions, etc.), suggest **`/wopr-init-project`** as the single-command fix. It detects, writes wopr.yml + spec stubs + AGENTS.md + per-CLI pointer files + an empty LEARNINGS.md, all preview-then-confirm.
   - When ONLY wopr.yml is missing (specs and agent-instructions would also be missing under it but the operator wants finer control), suggest `/wopr-create-yml` for just the yml or `/wopr-create-agent-instructions` for the multi-CLI scaffolding.
   - Doctor's read-only contract is preserved because the writers are their own skills.

If detection returns any other `error` field, surface it cleanly and stop. Do not attempt to recommend setup against a broken scan.
</procedure>

<output_format>
Render the report as plain markdown sections. Avoid burying the operator in JSON; the underlying tools return structured JSON for programmatic consumption, but the operator reads natural-language summary blocks.

Example output shape:

```
# WOPR Doctor

**Workspace:** `/Users/dev/Projects/example-org/example-monorepo/example-monorepo-frontend`

## Stack detected

- Monorepo (14 apps under `apps/`)
- Angular 21 (apps/example-app, apps/example-app-2, ...)
- AG-Grid community
- Vitest test runner
- npm package manager

## wopr.yml status

No `wopr.yml` files found.

- Recommend creating `apps/example-app/wopr.yml` (per-app placement for monorepos).
- Recommend creating `apps/example-app-2/wopr.yml` (same).

## WOPR packs

Installed: `_core`
Recommended for this stack: `crew`, `angular`

Install:

    wopr --init --packs crew,angular

## External MCPs

- AG-Grid usage detected. `mcp__ag-mcp__*` is NOT registered.
  Install: `claude mcp add ag-mcp -- npx @ag-grid/ag-grid-mcp@latest`
- Atlassian references in `tickets/` detected. `mcp__plugin_atlassian_atlassian__*` IS registered. OK.

## Suggested commands

1. `wopr --init --packs crew,angular`
2. `claude mcp add ag-mcp -- npx @ag-grid/ag-grid-mcp@latest`
3. Create `apps/example-app/wopr.yml` from `catalog/crew/templates/wopr.example.yml`

Doctor is read-only. Run the commands above. Re-run doctor to confirm gaps closed.
```

Adjust section content based on what is and is not present. Skip sections that have nothing to report (do not print "wopr.yml status: nothing to report" when the file inventory is healthy).
</output_format>

<role_boundaries>
This skill is read-only.

You MAY:
- Call `mcp__wopr__detect_stack`.
- Read `catalog/_core/data/doctor-recommendations.yaml`, `.ai-cli/wopr.lock.yaml`, and the three CLI MCP configs to build recommendations by hand.
- Read project files to add operator-facing color to the report when a recommendation is non-obvious.

You MAY NOT:
- Write `wopr.yml`, `.ai-cli/wopr.lock.yaml`, or any other file.
- Run `wopr --init --packs ...`, `wopr add`, MCP install commands, or any setup command on the operator's behalf.
- Modify `~/.claude.json`, `~/.gemini/settings.json`, or `~/.copilot/mcp-config.json` to register new MCPs.
- Install Python packages.
- Edit project source code.

The operator runs the recommended commands themselves. Doctor's job is to surface gaps, not close them.
</role_boundaries>
