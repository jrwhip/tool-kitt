---
name: wopr-init-project
description: One-shot umbrella skill that takes a project from "no WOPR setup" to "AI-ready" in a single operator session. Detects the stack, recommends and surfaces missing packs/MCPs, writes wopr.yml, writes stack-pre-filled spec stubs, writes AGENTS.md plus per-CLI pointer files (CLAUDE.md, GEMINI.md, .github/copilot-instructions.md), and creates an empty LEARNINGS.md. Every write step previews the file content for operator confirmation before landing. Companion to `/wopr-doctor` (read-only) and the individual `/wopr-create-*` skills. Use when taking a project from zero to AI-ready, running the whole WOPR onboarding, or setting up wopr end to end.
---

<objective>
Make a fresh project AI-ready in one operator command. After this skill runs to completion, the project has:

- `wopr.yml` at the target with real fields filled in, TODO markers only on fields requiring human judgment.
- `specs/coder-spec.md` and `specs/tester-spec.md` with stack-appropriate content (Angular, Spring Boot, FastAPI, or generic fallback).
- `AGENTS.md` at the target with build/test commands, framework patterns, and "read these first" instructions for the AI. This is the canonical multi-CLI source.
- Per-CLI pointer files so teammates on different CLIs (Claude Code, Gemini CLI, GitHub Copilot) all pick up the same context:
  - `CLAUDE.md` at the target (one-line `@AGENTS.md` import)
  - `GEMINI.md` at the target (one-line `@AGENTS.md` import)
  - `.github/copilot-instructions.md` at workspace root (short self-contained reference; Copilot only reads this file from workspace root, and `@`-import support is version-dependent, CLI v1.0.66+ only, so the plain reference works everywhere)
- `LEARNINGS.md` created (empty) so the CRAG read path has a target file when the auditor first writes a lesson.
- A `/wopr-doctor` re-run that returns "ready" or specifically names the remaining human-required edits.

Without this skill, the operator has to chain `/wopr-doctor` -> `/wopr-create-yml` -> `/wopr-create-agent-instructions` -> manual `/plugin install` of missing packs -> manual `LEARNINGS.md` touch by hand. The empty-shell state that bit dogfooding came from operators stopping partway through that chain.
</objective>

<when_to_run>
- The operator wants to bring a project into the WOPR crew for the first time.
- A project's WOPR setup has drifted (missing specs, missing agent-instructions, etc.) and the operator wants a single command to bring it back to ready.
- After a major stack change.

Do NOT run during a crew run. This is setup, not runtime.
</when_to_run>

<procedure>
1. **Resolve the workspace and target from the OPERATOR's current context.** Same rule as the other create skills: the operator's current Claude Code working directory is the only legitimate source. Do NOT use env vars or pinned workspace state. If the operator did not name a target inside the workspace, ask which one; do not infer.

2. **Print the resolved workspace and target BEFORE doing anything.** One line up front: `Initializing WOPR setup for <absolute target path>.` Stop and ask if the resolution is wrong. This step is non-negotiable.

3. **Call `mcp__plugin_wopr-core_wopr__detect_stack`** with the resolved absolute workspace path.

4. **Build the recommendation by hand**, the same way `/wopr-doctor` step 4 does: read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory) and cross-reference it against the detection JSON, `.ai-cli/wopr.lock.yaml`, and the three CLI MCP configs to get the list of missing packs and missing MCPs. There is no recommendation tool.

5. **Show the operator a one-block initialization plan** before any write happens. Render:
   - Resolved target path.
   - Detected stack (framework, language, package manager, test runner).
   - Files to be created: list each path (e.g. `apps/example-app/wopr.yml`, `apps/example-app/specs/coder-spec.md`, `apps/example-app/specs/tester-spec.md`, `apps/example-app/AGENTS.md`, `apps/example-app/CLAUDE.md`, `apps/example-app/GEMINI.md`, `<workspace>/.github/copilot-instructions.md`, `apps/example-app/LEARNINGS.md`).
   - Packs to install: list missing packs and the exact `/plugin install <pack>@wopr-marketplace` commands the operator will run after the skill finishes.
   - MCPs to install: list missing MCPs and their install commands.
   - "Confirm with `yes` to proceed."

6. **Wait for operator confirmation.** Default is no; only an explicit yes proceeds.

7. **On confirm: run the writes in sequence**, surfacing each tool's output as it returns. Order matters because each step's success is a precondition for the next:

   a. `mcp__plugin_wopr-core_wopr__propose_wopr_yml` -> `mcp__plugin_wopr-core_wopr__write_wopr_yml`. The proposed YAML lands first because everything else references it.

   b. `mcp__plugin_wopr-core_wopr__write_spec_stubs` with the absolute target dir and detection JSON. Stack-appropriate specs land in `<target>/specs/`.

   c. `mcp__plugin_wopr-core_wopr__write_tracking_doc_stub` with the absolute target dir. Drops the crew pack's `implementation-tracking.template.md` to the project at either the operator-declared `legacy-migration.tracking_doc` path (when set in wopr.yml) or the default `implementation-tracking.md`. Refuses to overwrite by default.

   d. `mcp__plugin_wopr-core_wopr__write_handoff_contract_stub` with the absolute target dir. Drops the crew pack's `frontend-handoff-contract.template.md` at the operator-declared `legacy-migration.handoff_contract` path (or the default `frontend-handoff-contract.md`). Only meaningful for backend-producer projects; pure-frontend targets receive the contract from their backend side, so the operator may delete the file on those projects. Refuses to overwrite by default.

   e. **Draft and write the agent-instructions files yourself**, the same way `/wopr-create-agent-instructions` does: there is no proposal or writer tool for these. Compose `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `copilot-instructions.md` directly from the detection JSON and the `wopr.yml`/specs just written, then write each with the Write tool at its documented destination (the Copilot file lands at workspace root, not target dir). Check each destination first; do not silently overwrite an existing file. These files tie the previous writes together by pointing the AI at `wopr.yml` and the specs.

   f. Call `mcp__plugin_wopr-core_wopr__seed_learnings` with the absolute target path and the detected stack tags (`angular`, `fastapi`; pass each that applies). The tool appends curated foundational lessons for the stack to `<target>/LEARNINGS.md` (creating the file if needed) AND registers the workspace in `~/.wopr/workspaces.txt` so cross-workspace reads can aggregate it. Seed entries are marked `seed: true` and bypass the recency cutoff in the CRAG prefilter, so they remain retrievable forever. This is what makes the RAG retrieval path produce useful output on day one of a new project; without seeded entries, the corpus would be empty until the first auditor distillation. Unknown stacks (e.g. Rust, Go) are skipped with no error. If `seed_learnings` returns an error (e.g. no seed files for the detected stack), surface it and continue without seeding rather than abort the whole init.

   If any write returns an `Error:` string, surface it, stop the sequence, and tell the operator which step failed. Do not silently continue.

8. **On non-confirm: do nothing.** Report no files written.

9. **After all writes succeed, re-run `mcp__plugin_wopr-core_wopr__detect_stack` and rebuild the recommendation by hand** (step 4's method) and print a final report so the operator can see what (if anything) is still pending. This is the same shape as `/wopr-doctor`'s closing report.

10. **Print the operator-action followups** that the skill itself cannot run (those would change ~/.claude.json or install global packages):
    - The exact `/plugin install <pack>@wopr-marketplace` invocations to install missing WOPR packs.
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
- Call `mcp__plugin_wopr-core_wopr__detect_stack`.
- Read `../../data/doctor-recommendations.yaml` (relative to this skill's base directory), `.ai-cli/wopr.lock.yaml`, and the three CLI MCP configs to build recommendations by hand.
- Call `mcp__plugin_wopr-core_wopr__propose_wopr_yml`, `mcp__plugin_wopr-core_wopr__write_wopr_yml`.
- Call `mcp__plugin_wopr-core_wopr__write_spec_stubs`.
- Call `mcp__plugin_wopr-core_wopr__write_tracking_doc_stub` and `mcp__plugin_wopr-core_wopr__write_handoff_contract_stub` to drop the pack-shipped templates so role agents never have to filesystem-search for them at run time.
- Draft the agent-instructions files' content directly and write them with the Write tool at their documented destinations, after checking for and refusing to silently overwrite existing files.
- Call `mcp__plugin_wopr-core_wopr__seed_learnings` to seed the project's `LEARNINGS.md` with curated starter lessons for the detected stack.
- Read existing project files for context.

You MAY NOT:
- Skip the operator confirmation step. The full plan must be shown and approved before any write.
- Silently overwrite ANY existing file. If a file is present, surface the error from the tool (or, for the agent-instructions files you write directly, your own existence check) and ask the operator whether to proceed with an explicit overwrite.
- Install WOPR packs (`/plugin install ...`) or external MCPs on the operator's behalf. Those commands change `~/.claude.json` and must remain operator-driven.
- Create parent directories beyond `<target>/specs/`. The target itself must already exist.
- Modify proposed file contents between propose and write. The operator confirms specific strings; those exact strings are what land.
</role_boundaries>
