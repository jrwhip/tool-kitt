---
name: wopr-create-agent-instructions
description: Scaffold a project's agent-instructions files (AGENTS.md plus per-CLI pointers for Claude Code, Gemini CLI, and GitHub Copilot) from the detected stack so a fresh AI session in this project has working context. Preview-then-confirm; never writes without operator approval. Companion to `/wopr-create-yml`; run this AFTER `wopr.yml` exists.
---

<objective>
Generate a project's agent-instructions files from the detected stack. The canonical `AGENTS.md` tells the AI:
- What this project is.
- How to build, test, and lint.
- Where `wopr.yml` and the specs live (and that the AI must read them first).
- What framework patterns the project demands.
- Where the source, tests, and key directories are.

Three pointer files (`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`) ride alongside so teammates on different CLIs (Claude Code, Gemini CLI, GitHub Copilot) all get the same context. Claude and Gemini files are one-line `@AGENTS.md` imports. The Copilot file stays a short self-contained reference: import support on Copilot is version-dependent (the CLI expands `@`-imports since v1.0.66, but older versions and the IDE integrations do not), so the plain reference works everywhere.

Without these files, a fresh AI session in this project defaults to training-data assumptions, which are usually wrong. This skill closes that gap.
</objective>

<when_to_run>
- After `/wopr-create-yml` has produced a `wopr.yml` for the target.
- Any time a project lacks any agent-instructions file.
- After a major stack change (framework upgrade, monorepo migration) so the file stays accurate.

Do NOT run during a crew run; this is out-of-band setup.
</when_to_run>

<procedure>
1. **Resolve the workspace and target from the OPERATOR's current context.** Same rule as `/wopr-create-yml`: the operator's current Claude Code working directory is the only legitimate source. Do NOT rely on any WOPR install state or env var.

2. **Print the resolved workspace and target BEFORE doing anything.** One line up front: `Generating agent-instructions for <absolute target path> (workspace <absolute workspace path>).` Stop and ask if the resolution is wrong.

3. **Call `mcp__wopr__detect_stack`** with the resolved absolute workspace path.

4. **Call `mcp__wopr__propose_agent_instructions`** with the detection JSON and the target path. The tool returns a JSON object with four keys: `agents_md` (the canonical full content), `claude_md`, `gemini_md`, and `copilot_instructions_md` (the three pointer files). Parse the JSON.

5. **Show the operator each proposed file verbatim** inside its own fenced markdown block. State explicitly where each file will land:
   - `AGENTS.md` -> `<target_dir>/AGENTS.md`
   - `CLAUDE.md` -> `<target_dir>/CLAUDE.md`
   - `GEMINI.md` -> `<target_dir>/GEMINI.md`
   - `copilot-instructions.md` -> `<workspace_path>/.github/copilot-instructions.md` (workspace-root only; Copilot does not look anywhere else)

6. **Ask the operator to confirm.** Default answer is no. Common confirmations: "yes", "write them", "ship it". Ambiguous = re-ask. The operator may also opt out of specific variants ("skip the Copilot one"); record which to skip.

7. **On confirm: call `mcp__wopr__write_agent_instructions`** with the absolute target directory, the absolute workspace path, and the content for each requested variant. Pass an empty string for any variant the operator opted out of. The tool refuses to overwrite by default; surface any `Skipped (exists, overwrite=False)` lines and ask whether to retry with `overwrite=True`.

8. **On non-confirm: do nothing.** Report no files written.

9. **After a successful write**, remind the operator of the remaining setup steps:
   - `/wopr-create-yml` if `wopr.yml` is still missing for this target.
   - `wopr --init --packs crew,<stack-pack>` if doctor flagged missing packs.
   - Re-run `/wopr-doctor` to confirm readiness.
</procedure>

<output_format>
Render each proposed file inside its own fenced code block. Do not embellish or summarize.

Example skill turn after a successful propose for an Nx-monorepo Angular app at `apps/example-app` in workspace `/repo/example`:

> Proposed agent-instructions for `apps/example-app`:
>
> `AGENTS.md` -> `/repo/example/apps/example-app/AGENTS.md`:
>
> ```markdown
> # Example App
>
> > **For the AI agent reading this file:** before doing ANY work...
> ```
>
> `CLAUDE.md` -> `/repo/example/apps/example-app/CLAUDE.md`:
>
> ```markdown
> @AGENTS.md
> ```
>
> `GEMINI.md` -> `/repo/example/apps/example-app/GEMINI.md`:
>
> ```markdown
> @AGENTS.md
> ```
>
> `copilot-instructions.md` -> `/repo/example/.github/copilot-instructions.md`:
>
> ```markdown
> See AGENTS.md in the repo root for project context.
> ```
>
> Write all four? (yes / yes-but-skip-<variant> / no)
</output_format>

<role_boundaries>
You MAY:
- Call `mcp__wopr__detect_stack`, `mcp__wopr__propose_agent_instructions`, and `mcp__wopr__write_agent_instructions`.
- Read project files for context.
- Echo the proposed files verbatim.

You MAY NOT:
- Write any file other than the requested agent-instructions variants at their documented destinations.
- Skip the confirmation step.
- Silently overwrite any existing file.
- Create parent directories outside of `.github/` (the tool creates that one automatically for Copilot).
- Modify the proposed content between propose and write; the operator confirms a specific string and that exact string is what lands.
</role_boundaries>
