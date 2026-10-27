---
name: kitt-create-agent-instructions
description: Scaffold a project's agent-instructions files (AGENTS.md plus per-CLI pointers for Claude Code, Gemini CLI, and GitHub Copilot) from the detected stack so a fresh AI session in this project has working context. Preview-then-confirm; never writes without operator approval. Companion to `/kitt-create-yml`; run this AFTER `kitt.yml` exists. Use when scaffolding AGENTS.md, writing per-CLI pointer files, or generating agent instructions from the detected stack.
---

<objective>
Generate a project's agent-instructions files from the detected stack. The canonical `AGENTS.md` tells the AI:
- What this project is.
- How to build, test, and lint.
- Where `kitt.yml` and the specs live (and that the AI must read them first).
- What framework patterns the project demands.
- Where the source, tests, and key directories are.

Three pointer files (`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`) ride alongside so teammates on different CLIs (Claude Code, Gemini CLI, GitHub Copilot) all get the same context. Claude and Gemini files are one-line `@AGENTS.md` imports. The Copilot file stays a short self-contained reference: import support on Copilot is version-dependent (the CLI expands `@`-imports since v1.0.66, but older versions and the IDE integrations do not), so the plain reference works everywhere.

Without these files, a fresh AI session in this project defaults to training-data assumptions, which are usually wrong. This skill closes that gap.
</objective>

<when_to_run>
- After `/kitt-create-yml` has produced a `kitt.yml` for the target.
- Any time a project lacks any agent-instructions file.
- After a major stack change (framework upgrade, monorepo migration) so the file stays accurate.

Do NOT run during a crew run; this is out-of-band setup.
</when_to_run>

<procedure>
1. **Resolve the workspace and target from the OPERATOR's current context.** Same rule as `/kitt-create-yml`: the operator's current Claude Code working directory is the only legitimate source. Do NOT rely on any KITT install state or env var.

2. **Print the resolved workspace and target BEFORE doing anything.** One line up front: `Generating agent-instructions for <absolute target path> (workspace <absolute workspace path>).` Stop and ask if the resolution is wrong.

3. **Call `mcp__plugin_kitt-core_kitt__detect_stack`** with the resolved absolute workspace path.

4. **Draft the four files yourself.** There is no proposal tool; compose the content directly from the detection JSON and, when present, the target's `kitt.yml` and specs. `AGENTS.md` follows the outline in `<objective>` above (project identity, build/test/lint commands, the `kitt.yml`-and-specs pointer, framework patterns, key directories). `CLAUDE.md` and `GEMINI.md` are each a one-line `@AGENTS.md` import. `copilot-instructions.md` is a short self-contained reference (not an `@`-import) pointing at `AGENTS.md`.

5. **Show the operator each proposed file verbatim** inside its own fenced markdown block. State explicitly where each file will land:
   - `AGENTS.md` -> `<target_dir>/AGENTS.md`
   - `CLAUDE.md` -> `<target_dir>/CLAUDE.md`
   - `GEMINI.md` -> `<target_dir>/GEMINI.md`
   - `copilot-instructions.md` -> `<workspace_path>/.github/copilot-instructions.md` (workspace-root only; Copilot does not look anywhere else)

6. **Ask the operator to confirm.** Default answer is no. Common confirmations: "yes", "write them", "ship it". Ambiguous = re-ask. The operator may also opt out of specific variants ("skip the Copilot one"); record which to skip.

7. **On confirm: write each requested file yourself** at its documented destination. There is no writer tool for this; check each destination path first, and if a file already exists there, do not overwrite it silently. Report `Skipped (exists)` for that file and ask the operator whether to proceed with an explicit overwrite. Skip any variant the operator opted out of.

8. **On non-confirm: do nothing.** Report no files written.

9. **After a successful write**, remind the operator of the remaining setup steps:
   - `/kitt-create-yml` if `kitt.yml` is still missing for this target.
   - `/plugin install kitt-crew@kitt-marketplace` (plus the stack pack's plugin) if doctor flagged missing packs.
   - Re-run `/kitt-doctor` to confirm readiness.
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
- Call `mcp__plugin_kitt-core_kitt__detect_stack`.
- Read project files for context.
- Draft the four files' content directly and write them with the Write tool at their documented destinations, after checking for and refusing to silently overwrite existing files.
- Echo the proposed files verbatim.

You MAY NOT:
- Write any file other than the requested agent-instructions variants at their documented destinations.
- Skip the confirmation step.
- Silently overwrite any existing file.
- Create parent directories outside of `.github/` (the tool creates that one automatically for Copilot).
- Modify the proposed content between propose and write; the operator confirms a specific string and that exact string is what lands.
</role_boundaries>
