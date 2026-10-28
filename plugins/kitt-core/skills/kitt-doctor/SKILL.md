---
name: kitt-doctor
description: Scan the current workspace, identify the stack, and report what KITT setup is missing (kitt.yml placement, KITT packs, external MCPs, specs). Read-only diagnostic. Use before the first crew run on a project, after dependency upgrades that may have changed the stack, or any time the agent wants to confirm a project is correctly wired for KITT. Use when checking a multi-project workspace root.
---

<objective>
Operator-facing diagnostic for KITT setup. Detects the stack via well-known marker files, cross-references against a recommendation table, and prints a structured report listing missing `kitt.yml` placements, missing KITT packs, missing external MCPs, and missing specs. Does not write files. Operator runs the suggested commands themselves.
</objective>

<when_to_run>
- Before the first crew run on a new project. Confirms the project is wired up before the operator burns Sonnet/Opus tokens discovering setup gaps inside an agent run.
- After major dependency upgrades that may have changed the stack signature (added a framework, removed a backend, switched monorepo flavors).
- After turning a single repo into a workspace of sibling repos, or when scanning the parent directory of several projects, to see every member's readiness in one report.
- After installing a new KITT pack, to confirm the new pack is correctly registered.
- Any time an operator suspects a missing MCP or misplaced `kitt.yml` is causing crew agents to behave unexpectedly.

Do NOT run this skill as part of a crew run. It is an out-of-band setup tool, not a runtime check.
</when_to_run>

<procedure>
1. **Resolve the target workspace from the OPERATOR's current context.** The operator's current working directory is the only legitimate source for this. Do NOT rely on any KITT install state, env var, or pinned workspace. If the operator explicitly named a project path (e.g. `apps/example-app`), resolve it against the cwd into an absolute path. If the operator did not name one, ask them which project to scan; do not infer. A directory holding a `kitt.yml` whose top-level key is `workspace` is a workspace root (the workspace-mode rule under "Path conventions" in `kitt-yml-schema.md`); scanning it reports every declared member.

2. **Print the resolved workspace BEFORE doing anything.** Print one line up front to the operator: `Scanning <absolute workspace path>.` (at a workspace root: `Scanning <absolute workspace path> (workspace root, N members).`) If the resolution is wrong (e.g. the operator wanted `apps/example-app` but you resolved to the monorepo root, or to an unrelated project), stop and ask for the right path. Doctor's value collapses to zero when it scans the wrong directory silently. This step is non-negotiable.

3. **Call `mcp__plugin_kitt-core_kitt__detect_stack`** with the resolved absolute path as `workspace_path`. The tool requires this argument; it does not infer a workspace from environment state. The result's top-level `workspace_path` field echoes the directory it scanned. If the result is an `error`, surface it cleanly and stop.

3a. **Workspace root?** When `detect_stack` returns `project_type: "workspace"`, its `workspace` block lists the declared members (`path`, `slug`, `role`, `exists`, `has_kitt_yml`, `kitt_yml_kind`, `has_learnings`, `detected`) plus `undeclared_children` and `missing_children`. Call `mcp__plugin_kitt-core_kitt__detect_stack` once more per existing member (`<workspace_root>/<path>`) so each member gets the same readiness inputs a single-project scan would, then build per-member readiness and CRAG warnings exactly as steps 4 and 5 do for one project. Every entry in `kitt_yml_inventory` carries `summary.kind`; the root entry is `workspace` and is never a project with missing specs. Do not recommend a `project`-style `kitt.yml` for the root.

4. **Build the recommendation by hand.** There is no recommendation tool; `detect_stack` only detects. Read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory) (the framework-to-pack, signal-to-MCP, and language-to-plugin mapping tables) and cross-reference it against: the stack detected in step 3, the packs installed per `.ai-cli/kitt.lock.yaml`, and the MCP registrations in all three CLI configs (`~/.claude.json`, `~/.gemini/settings.json`, and `~/.copilot/mcp-config.json`). From this, derive missing `kitt.yml` paths, missing KITT packs, missing external MCPs, and copy-paste install commands.

5. **Print a structured report** to the operator. Format the report sections in this order:
   - **Workspace path**: the scanned directory (same line you already showed in step 2).
   - **Stack detected**: language(s), framework(s), versions, package manager, monorepo type if any, test runner.
   - **Workspace** (workspace mode only): the root `kitt.yml` summary (slug, name, member count), then a members table with columns `path | role | slug | kitt.yml | ready | blockers | LEARNINGS`, then **Undeclared children** (directories the scan recognized that `workspace.projects` omits) and **Missing children** (declared paths absent on disk). Root readiness has three checks only: the root `kitt.yml` parses, root `AGENTS.md` present, root `LEARNINGS.md` present. There are no specs at the root, so no spec blockers.
   - **kitt.yml status**: existing files with their content summary (slug, build_file, base_package, declared spec paths, API contract kind and pin) AND missing files with proposed locations and reasons. Render the summary so the operator sees what each kitt.yml actually declares, not just that it exists.
   - **Readiness per project**: for each existing kitt.yml, render `ready: True/False` and the list of blockers (missing specs, unresolved TODO markers in specs, missing agent-instructions file, etc.). Any one of `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` at the target, or `.github/copilot-instructions.md` at workspace root, satisfies the agent-instructions requirement. A project is "ready" only when zero blockers remain. This is the source of truth for whether the project can run a crew; "kitt.yml exists" is no longer enough.
   - **CRAG status per project (warnings)**: for each existing kitt.yml, render the `warnings` list separately from blockers. The two common warnings are:
     - **CRAG corpus is empty**: `LEARNINGS.md` is missing or has no parseable `## LRN-` entries. The crew runs; the RAG just returns nothing on the first gate until the auditor distills the first entry. Suggest `mcp__plugin_kitt-core_kitt__seed_learnings` with the detected stack tags to bootstrap.
     - **Workspace not registered**: the project's absolute path is absent from `~/.kitt/workspaces.txt`. Outside-workspace sessions and sibling-workspace aggregation cannot see this project's lessons. The first call to `seed_learnings`, `append_learnings`, or `learnings_search` from inside the workspace registers it automatically.
     - **Embeddings status**: call `mcp__plugin_kitt-core_kitt__learnings_path` with the project's absolute path and report its `embeddings:` block — the active provider (`local` / `bedrock` / `none`, resolved from the `KITT_EMBEDDING_PROVIDER` env var, then `kitt.yml` `learnings.embeddings.provider`, then the `local` default), whether the provider is available, and the sidecar state (missing, or present with entry count and dimensions). An unavailable provider or a `none` opt-out means `learnings_search` runs deterministic-prefilter-only; say so explicitly so the operator knows the semantic half is off and why.
     Warnings do NOT flip `ready` to False. Render them so the operator sees the gap and can choose to address it.
   - **KITT packs**: installed (from `kitt.lock.yaml`) and recommended additions for the detected stack.
   - **External MCPs**: detected signals matched against the MCP registrations across all three CLI configs (`~/.claude.json`, `~/.gemini/settings.json`, `~/.copilot/mcp-config.json`). For each missing MCP, include the install command and documentation URL.
   - **Suggested commands**: ordered list of operator-runnable commands. Doctor does NOT run these; the operator does.

6. **Tell the operator what to do next.** Close with a one-liner: "Doctor is read-only. Run the commands above. Re-run doctor to confirm gaps closed."
   - When kitt.yml is missing OR readiness blockers exist (missing specs, missing agent-instructions, etc.), suggest **`/kitt-init-project`** as the single-command fix. It detects, writes kitt.yml + spec stubs + AGENTS.md + per-CLI pointer files + an empty LEARNINGS.md, all preview-then-confirm.
   - When ONLY kitt.yml is missing (specs and agent-instructions would also be missing under it but the operator wants finer control), suggest `/kitt-create-yml` for just the yml or `/kitt-create-agent-instructions` for the multi-CLI scaffolding.
   - In workspace mode, when the root file is missing or any member is not ready, suggest **`/kitt-init-project`** from the root: it writes the root files and then offers each member's init in turn.
   - Doctor's read-only contract is preserved because the writers are their own skills.

If detection returns any other `error` field, surface it cleanly and stop. Do not attempt to recommend setup against a broken scan.
</procedure>

<output_format>
Render the report as plain markdown sections. Avoid burying the operator in JSON; the underlying tools return structured JSON for programmatic consumption, but the operator reads natural-language summary blocks.

Example output shape:

```
# KITT Doctor

**Workspace:** `/Users/dev/Projects/example-org/example-monorepo/example-monorepo-frontend`

## Stack detected

- Monorepo (14 apps under `apps/`)
- Angular 21 (apps/example-app, apps/example-app-2, ...)
- AG-Grid community
- Vitest test runner
- npm package manager

## kitt.yml status

No `kitt.yml` files found.

- Recommend creating `apps/example-app/kitt.yml` (per-app placement for monorepos).
- Recommend creating `apps/example-app-2/kitt.yml` (same).

## KITT packs

Installed: `_core`
Recommended for this stack: `crew`, `angular`

Install (each pack ships as a Claude Code plugin from the KITT marketplace):

    /plugin install kitt-crew@kitt-marketplace
    /plugin install kitt-angular@kitt-marketplace

## External MCPs

- AG-Grid usage detected. `mcp__ag-mcp__*` is NOT registered.
  Install: `claude mcp add ag-mcp -- npx @ag-grid/ag-grid-mcp@latest`
- Atlassian references in `tickets/` detected. `mcp__plugin_atlassian_atlassian__*` IS registered. OK.

## Suggested commands

1. `/plugin install kitt-crew@kitt-marketplace` and `/plugin install kitt-angular@kitt-marketplace`
2. `claude mcp add ag-mcp -- npx @ag-grid/ag-grid-mcp@latest`
3. Create `apps/example-app/kitt.yml` from the crew pack's `kitt.example.yml` (fetch via `get_pack_template`, `pack="crew"`)

Doctor is read-only. Run the commands above. Re-run doctor to confirm gaps closed.
```

Workspace-mode example (the Workspace section sits between "Stack detected" and "kitt.yml status"):

```
## Workspace

**Root:** `/home/dev/myproduct/kitt.yml` (slug `myproduct`, 3 members). Root AGENTS.md: present. Root LEARNINGS.md: present.

| path      | role     | slug          | kitt.yml | ready | blockers                       | LEARNINGS |
|-----------|----------|---------------|----------|-------|--------------------------------|-----------|
| backend/  | backend  | myproduct-api | yes      | yes   |                                | yes       |
| frontend/ | frontend | myproduct-ui  | yes      | no    | specs/tester-spec.md has TODOs | yes       |
| tests/    | tests    | myproduct-e2e | no       | no    | no kitt.yml                    | no        |

Undeclared children: `docs/` has a package.json but is not in workspace.projects.
Missing children: none.
```

Adjust section content based on what is and is not present. Skip sections that have nothing to report (do not print "kitt.yml status: nothing to report" when the file inventory is healthy).
</output_format>

<role_boundaries>
This skill is read-only.

You MAY:
- Call `mcp__plugin_kitt-core_kitt__detect_stack`.
- Call `mcp__plugin_kitt-core_kitt__learnings_path` (read-only diagnostic) for the embeddings-status warning line.
- Call `mcp__plugin_kitt-core_kitt__get_workspace_info` (read-only) to confirm `kitt_yml_kind` and the member list at a workspace root.
- Read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory), `.ai-cli/kitt.lock.yaml`, and the three CLI MCP configs to build recommendations by hand.
- Read project files to add operator-facing color to the report when a recommendation is non-obvious.

You MAY NOT:
- Write `kitt.yml`, `.ai-cli/kitt.lock.yaml`, or any other file.
- Run `/plugin install ...`, MCP install commands, or any setup command on the operator's behalf.
- Modify `~/.claude.json`, `~/.gemini/settings.json`, or `~/.copilot/mcp-config.json` to register new MCPs.
- Install Python packages.
- Edit project source code.

The operator runs the recommended commands themselves. Doctor's job is to surface gaps, not close them.
</role_boundaries>
