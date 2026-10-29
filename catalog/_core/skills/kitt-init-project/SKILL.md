---
name: kitt-init-project
description: One-shot umbrella skill that takes a project from "no KITT setup" to "AI-ready" in a single operator session. Detects the stack, recommends and surfaces missing packs/MCPs, writes kitt.yml, writes stack-pre-filled spec stubs, writes AGENTS.md plus per-CLI pointer files (CLAUDE.md, GEMINI.md, .github/copilot-instructions.md), and creates an empty LEARNINGS.md. Every write step previews the file content for operator confirmation before landing. Companion to `/kitt-doctor` (read-only) and the individual `/kitt-create-*` skills. Use when taking a project from zero to AI-ready, running the whole KITT onboarding, or setting up kitt end to end. Use when onboarding a parent folder of sibling repos.
---

<objective>
Make a fresh project AI-ready in one operator command. After this skill runs to completion, the project has:

- `kitt.yml` at the target with real fields filled in, TODO markers only on fields requiring human judgment.
- `specs/coder-spec.md` and `specs/tester-spec.md` with stack-appropriate content (Angular, Spring Boot, FastAPI, or generic fallback).
- `AGENTS.md` at the target with build/test commands, framework patterns, and "read these first" instructions for the AI. This is the canonical multi-CLI source.
- Per-CLI pointer files so teammates on different CLIs (Claude Code, Gemini CLI, GitHub Copilot) all pick up the same context:
  - `CLAUDE.md` at the target (one-line `@AGENTS.md` import)
  - `GEMINI.md` at the target (one-line `@AGENTS.md` import)
  - `.github/copilot-instructions.md` at workspace root (short self-contained reference; Copilot only reads this file from workspace root, and `@`-import support is version-dependent, CLI v1.0.66+ only, so the plain reference works everywhere)
- `LEARNINGS.md` created (empty) so the CRAG read path has a target file when the auditor first writes a lesson.
- A `/kitt-doctor` re-run that returns "ready" or specifically names the remaining human-required edits.

**Workspace root variant.** When the target is the parent directory of several sibling projects (detection says `container`, or a `workspace` `kitt.yml` already exists), the root gets a different set: a `workspace` `kitt.yml` naming the members, a root `AGENTS.md` in the workspace shape below, `CLAUDE.md` and `GEMINI.md` pointers, `.github/copilot-instructions.md`, and a root `LEARNINGS.md` seeded with the union of every member's stack tags. No spec stubs, tracking document, or handoff contract at the root; those are per-member, and each member lacking setup is offered its own init in turn. The workspace `AGENTS.md` outline:
- What this workspace is, in one line, then a members table: path, role, slug, one-line purpose, how to build and test that member.
- How the members relate: who owns the API contract (backend), who consumes the generated client (frontend), what `tests/` exercises.
- Rules for the AI: read a member's own `AGENTS.md` before editing anything inside it; every member is its own git repository, so commit inside the member; the crew writes to one home member per REQ, named by the REQ's `project:` field.
- Where the root `kitt.yml`, root `LEARNINGS.md`, and each member's `kitt.yml` live.

Without this skill, the operator has to chain `/kitt-doctor` -> `/kitt-create-yml` -> `/kitt-create-agent-instructions` -> manual `/plugin install` of missing packs -> manual `LEARNINGS.md` touch by hand. The empty-shell state that bit dogfooding came from operators stopping partway through that chain.
</objective>

<when_to_run>
- The operator wants to bring a project into the KITT crew for the first time.
- A project's KITT setup has drifted (missing specs, missing agent-instructions, etc.) and the operator wants a single command to bring it back to ready.
- After a major stack change.

Do NOT run during a crew run. This is setup, not runtime.
</when_to_run>

<procedure>
1. **Resolve the workspace and target from the OPERATOR's current context.** Same rule as the other create skills: the operator's current Claude Code working directory is the only legitimate source. Do NOT use env vars or pinned workspace state. If the operator did not name a target inside the workspace, ask which one; do not infer. A target of `.` at a directory that holds several child projects and no `project` `kitt.yml` (or that already holds a `workspace` `kitt.yml`) is a workspace root (the workspace-mode rule under "Path conventions" in `kitt-yml-schema.md`); use the workspace-root plan and write sequence below.

2. **Print the resolved workspace and target BEFORE doing anything.** One line up front: `Initializing KITT setup for <absolute target path>.` Stop and ask if the resolution is wrong. This step is non-negotiable.

3. **Call `mcp__kitt__detect_stack`** with the resolved absolute workspace path. `project_type: "container"` (children recognized, no root file yet) or `"workspace"` (root file present; `workspace.members`, `undeclared_children`, `missing_children` filled in) selects the workspace-root variant.

4. **Build the recommendation by hand**, the same way `/kitt-doctor` step 4 does: read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory) and cross-reference it against the detection JSON, `.ai-cli/kitt.lock.yaml`, and the three CLI MCP configs to get the list of missing packs and missing MCPs. There is no recommendation tool.

5. **Show the operator a one-block initialization plan** before any write happens. Render:
   - Resolved target path.
   - Detected stack (framework, language, package manager, test runner).
   - Files to be created: list each path (e.g. `apps/example-app/kitt.yml`, `apps/example-app/specs/coder-spec.md`, `apps/example-app/specs/tester-spec.md`, `apps/example-app/AGENTS.md`, `apps/example-app/CLAUDE.md`, `apps/example-app/GEMINI.md`, `<workspace>/.github/copilot-instructions.md`, `apps/example-app/LEARNINGS.md`).
   - Packs to install: list missing packs and the exact `/plugin install <pack>@kitt-marketplace` commands the operator will run after the skill finishes.
   - MCPs to install: list missing MCPs and their install commands.
   - "Confirm with `yes` to proceed."

   **Workspace-root plan** (when detection says `container` or `workspace`) renders instead:
   - Resolved workspace root and the members detection found (path, role guess, stack), plus any undeclared or missing children.
   - Files to be created at `<workspace_root>`: `kitt.yml` (workspace kind, from `propose_kitt_yml(detection, ".")`), `AGENTS.md` (workspace shape), `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `LEARNINGS.md` (seeded with the union of every member's stack tags). No spec stubs, tracking document, or handoff contract at the root.
   - Members lacking setup (no `kitt.yml`, missing specs, or missing agent-instructions), each with what is missing.
   - "Confirm with `yes` to write the root files. After they land, each member above is offered its own init in turn."

6. **Wait for operator confirmation.** Default is no; only an explicit yes proceeds.

7. **On confirm: run the writes in sequence**, surfacing each tool's output as it returns. Order matters because each step's success is a precondition for the next:

   a. `mcp__kitt__propose_kitt_yml` -> `mcp__kitt__write_kitt_yml`. The proposed YAML lands first because everything else references it.

   b. `mcp__kitt__write_spec_stubs` with three arguments: `target_dir` (the absolute target directory), `detection_json` (the `detect_stack` output verbatim), and `target_path` (the target's path relative to the workspace exactly as it appears in the detection's `targets` list, `.` for the workspace root). All three are required; the tool picks the per-stack template from the profile that `target_path` names. Stack-appropriate specs land in `<target>/specs/`.

   c. `mcp__kitt__write_tracking_doc_stub` with the absolute target dir. Drops the crew pack's `implementation-tracking.template.md` to the project at either the operator-declared `legacy-migration.tracking_doc` path (when set in kitt.yml) or the default `implementation-tracking.md`. Refuses to overwrite by default.

   d. `mcp__kitt__write_handoff_contract_stub` with the absolute target dir. Drops the crew pack's `frontend-handoff-contract.template.md` at the operator-declared `legacy-migration.handoff_contract` path (or the default `frontend-handoff-contract.md`). Only meaningful for backend-producer projects; pure-frontend targets receive the contract from their backend side, so the operator may delete the file on those projects. Refuses to overwrite by default.

   e. **Draft and write the agent-instructions files yourself**, the same way `/kitt-create-agent-instructions` does: there is no proposal or writer tool for these. Compose `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `copilot-instructions.md` directly from the detection JSON and the `kitt.yml`/specs just written, then write each with the Write tool at its documented destination (the Copilot file lands at workspace root, not target dir). Check each destination first; do not silently overwrite an existing file. These files tie the previous writes together by pointing the AI at `kitt.yml` and the specs.

   f. Call `mcp__kitt__seed_learnings` with the absolute target path and the detected stack tags (`angular`, `fastapi`; pass each that applies). The tool appends curated foundational lessons for the stack to `<target>/LEARNINGS.md` (creating the file if needed) AND registers the workspace in `~/.kitt/workspaces.txt` so cross-workspace reads can aggregate it. Seed entries are marked `seed: true` and bypass the recency cutoff in the CRAG prefilter, so they remain retrievable forever. This is what makes the RAG retrieval path produce useful output on day one of a new project; without seeded entries, the corpus would be empty until the first auditor distillation. Unknown stacks (e.g. Rust, Go) are skipped with no error. If `seed_learnings` returns an error (e.g. no seed files for the detected stack), surface it and continue without seeding rather than abort the whole init.

   If any write returns an `Error:` string, surface it, stop the sequence, and tell the operator which step failed. Do not silently continue.

   **7-W (workspace root).** On confirm of the workspace-root plan: (a) `mcp__kitt__propose_kitt_yml` with target `.` -> `mcp__kitt__write_kitt_yml` at `<workspace_root>`; the proposal is a `workspace` file, show it verbatim and keep its TODO comments. (b) Skip the spec, tracking-doc, and handoff-contract stubs; the tools refuse at a workspace root by design. (c) Draft and write the root `AGENTS.md` in the workspace shape, the two one-line pointer files, and `.github/copilot-instructions.md`, checking each destination first. (d) `mcp__kitt__seed_learnings` with `<workspace_root>` and the union of the members' stack tags (`angular`, `fastapi`; whichever apply). (e) **Member loop:** for each member lacking setup, print `Initializing KITT setup for <workspace_root>/<path>.` and run steps 3 to 7 with that member as the target and the member itself as the workspace (it is its own repository, so its Copilot file lands at `<member>/.github/copilot-instructions.md`, not at the container root), each with its own confirm. The operator may skip a member; record the skip in the final report.

8. **On non-confirm: do nothing.** Report no files written.

9. **After all writes succeed, re-run `mcp__kitt__detect_stack` and rebuild the recommendation by hand** (step 4's method) and print a final report so the operator can see what (if anything) is still pending. This is the same shape as `/kitt-doctor`'s closing report.

10. **Print the operator-action followups** that the skill itself cannot run (those would change ~/.claude.json or install global packages):
    - The exact `/plugin install <pack>@kitt-marketplace` invocations to install missing KITT packs.
    - The exact MCP install commands for any missing external MCPs.
    - The reminder to restart Claude Code so the new agents / skills / MCP tools register.
</procedure>

<output_format>
The skill produces two operator-facing artifacts:

1. A plan block (before any write happens) listing all files that will land plus the post-write commands the operator still has to run.
2. A confirmation block after writes complete, listing each file written and any residual setup steps.

Use plain markdown sections. Render proposed file contents inside fenced code blocks so whitespace and TODO markers are visible.
</output_format>

<role_boundaries>
You MAY:
- Call `mcp__kitt__detect_stack`.
- Read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory), `.ai-cli/kitt.lock.yaml`, and the three CLI MCP configs to build recommendations by hand.
- Call `mcp__kitt__propose_kitt_yml`, `mcp__kitt__write_kitt_yml`.
- Call `mcp__kitt__write_spec_stubs`.
- Call `mcp__kitt__write_tracking_doc_stub` and `mcp__kitt__write_handoff_contract_stub` to drop the pack-shipped templates so role agents never have to filesystem-search for them at run time.
- Draft the agent-instructions files' content directly and write them with the Write tool at their documented destinations, after checking for and refusing to silently overwrite existing files.
- Call `mcp__kitt__seed_learnings` to seed the project's `LEARNINGS.md` with curated starter lessons for the detected stack.
- Read existing project files for context.

You MAY NOT:
- Skip the operator confirmation step. The full plan must be shown and approved before any write.
- Silently overwrite ANY existing file. If a file is present, surface the error from the tool (or, for the agent-instructions files you write directly, your own existence check) and ask the operator whether to proceed with an explicit overwrite.
- Install KITT packs (`/plugin install ...`) or external MCPs on the operator's behalf. Those commands change `~/.claude.json` and must remain operator-driven.
- Create parent directories beyond `<target>/specs/`. The target itself must already exist.
- Write spec stubs, a tracking document, or a handoff contract at a workspace root. Those are per-member documents; the stub tools refuse the root and so do you.
- Modify proposed file contents between propose and write. The operator confirms specific strings; those exact strings are what land.
</role_boundaries>
