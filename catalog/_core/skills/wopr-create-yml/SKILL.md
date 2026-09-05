---
name: wopr-create-yml
description: Scaffold a `wopr.yml` at a specified path inside the workspace, with detected fields pre-filled and TODO comments next to anything that needs operator review. Previews the YAML for operator confirmation before any file lands on disk. Companion to `/wopr-doctor`; the doctor surfaces missing wopr.yml placements, this skill creates them. Use when scaffolding a wopr.yml, creating a wopr config file, or previewing workspace config.
---

<objective>
Operator-facing scaffolding for `wopr.yml`. Detects the stack of a target inside the workspace, generates a proposed YAML with sensible defaults filled in (slug, name, source roots, build file, base package for Java, API contract hints), shows the operator the proposed content, and writes the file on confirmation. Never writes without confirmation. Never overwrites an existing file unless explicitly told to.
</objective>

<when_to_run>
- After `/wopr-doctor` reports a missing `wopr.yml` placement and the operator wants the boilerplate scaffolded rather than hand-authored.
- When standing up a new project that has no `wopr.yml` yet.
- When migrating an existing project to WOPR for the first time.

Do NOT run this skill during a crew run. The crew expects `wopr.yml` to exist before any agent step starts; scaffolding mid-crew is out of scope.
</when_to_run>

<procedure>
1. **Resolve the workspace and target from the OPERATOR's current context.** The skill is running in Claude Code; the operator's current working directory is the only legitimate source for the workspace. Do NOT rely on any WOPR install state, env var, or pinned workspace. The operator passes a target path relative to that workspace (e.g. `apps/example-app` for an Nx app, `.` for a single-app workspace root). When the operator does not pass a target, ask; do not infer.

2. **Print the resolved workspace and target BEFORE doing anything.** Print one line: `Scanning <absolute workspace path> for target <target_path>.` If the resolution is wrong (the operator wanted a specific sibling project but you resolved to an unrelated path), stop and ask. The propose-then-confirm loop is worthless if the underlying workspace is wrong. This step is non-negotiable.

3. **Call `mcp__wopr__detect_stack`** with the resolved absolute path as `workspace_path`. The tool requires this argument; it does not infer a workspace from environment state. If the result contains an `error`, surface it and stop.

4. **Call `mcp__wopr__propose_wopr_yml`** with the detection JSON and the target path (relative to the workspace, as it appears in the detection's `targets` list). The tool returns the proposed YAML as a string with TODO comments where operator review is needed.

5. **Show the operator the proposed YAML verbatim** in your response. Do not rephrase, summarize, or strip TODO comments. The operator must see exactly what would land on disk.

6. **Ask the operator to confirm.** Default answer is no; the operator must explicitly approve before any write happens. Common confirmation phrasings: "yes", "write it", "go", "ship it". Anything ambiguous means stop and re-ask.

7. **On confirm: call `mcp__wopr__write_wopr_yml`** with `target_dir` set to the ABSOLUTE path of the target directory (join the workspace path with the target path) and the YAML content verbatim from step 4. The tool requires `target_dir` to be absolute; it does not join onto any pinned workspace. It refuses by default to overwrite an existing file; surface that error cleanly if it fires and ask the operator whether to pass `overwrite=True`.

8. **On non-confirm: do nothing.** Report that no file was written, point at `/wopr-doctor` to re-run when ready.

9. **After the write succeeds**, remind the operator of the remaining setup steps:
   - The new `wopr.yml` points at spec paths that do not exist yet. This skill does not write them; run `/wopr-init-project` (the umbrella skill) to generate stack-appropriate `coder-spec.md` and `tester-spec.md` stubs alongside the rest of the onboarding.
   - Run `/wopr-create-agent-instructions` to scaffold `AGENTS.md` plus per-CLI pointer files (CLAUDE.md, GEMINI.md, `.github/copilot-instructions.md`) so a fresh AI session on any supported CLI has working context.
   - Review the new `requirements:` block in the proposed `wopr.yml`. Default is `source: local` with `path: requirements`; either create the local `requirements/` directory and drop `<REQ-ID>.md` files in it, OR swap the `local:` sub-block for `jira:` (with an optional `project_key` for REQ-ID prefix sanity checks) when the project tracks REQs in Jira. The Atlassian cloud_id is resolved at runtime by the orchestrator via the MCP; do not store it in `wopr.yml`. The crew orchestrator pulls the active REQ body from whichever source the yml declares.
   - Install any packs the doctor flagged as missing (each pack ships as a Claude Code plugin from the WOPR marketplace, e.g. `/plugin install wopr-crew@wopr-marketplace`).
   - Re-run `/wopr-doctor` to confirm gaps closed.
</procedure>

<output_format>
The propose step's output is the YAML the operator will see. Render it inside a fenced code block so the operator can spot whitespace and TODO comments clearly. Do not embellish; the YAML is the deliverable.

Example skill turn after a successful propose:

> Proposed `wopr.yml` for `apps/example-app`:
>
> ```yaml
> # wopr.yml generated by /wopr-create-yml for example-app.
> # Schema: wopr-yml-schema.md (WOPR crew pack; mcp get_pack_template)
> # Review every TODO comment before the first crew run; the generator
> # fills in defaults that may not match this project.
>
> project:
>   slug: example-app
>   name: Example App  # TODO: confirm the human-readable name.
>   target_source_root: src/app
>   test_root: src
>   build_file: project.json
>
> specs:
>   coder_spec: specs/coder-spec.md  # TODO: copy from catalog/crew/templates/coder-spec.template.md
>   tester_spec: specs/tester-spec.md  # TODO: copy from catalog/crew/templates/tester-spec.template.md
>   audit_report: AUDIT_REPORT.md
>
> api_contract:
>   kind: openapi
>   spec_url: null
>   pinned_generator_version: openapi-generator-cli 7.21.0
>   # TODO: Point `spec_url` at the backend's published spec. Pin must match the backend's `spec_version`.
>
> # legacy-migration block intentionally omitted. Add it by hand when migrating from a legacy stack; see wopr.example.yml.
> ```
>
> Write this to `apps/example-app/wopr.yml`? (yes / no)

After confirmation and a successful write, report the resolved absolute path and the next-step reminders from the procedure.
</output_format>

<role_boundaries>
This skill writes ONE file (the `wopr.yml`) and only on explicit operator confirmation.

You MAY:
- Call `mcp__wopr__detect_stack`, `mcp__wopr__propose_wopr_yml`, and `mcp__wopr__write_wopr_yml`.
- Read project files to add operator-facing color when the proposed YAML has a TODO that warrants explanation.
- Echo the proposed YAML verbatim in your response.

You MAY NOT:
- Write any file other than the target `wopr.yml`.
- Skip the confirmation step. Even when the operator passed a target explicitly, the propose-then-confirm step still runs so they see the YAML before it lands.
- Overwrite an existing `wopr.yml` silently. The tool refuses; surface that and ask the operator whether to pass `overwrite=True`.
- Create parent directories. The tool refuses when the target dir is missing; surface that and stop.
- Copy spec templates, install packs, or register MCPs. Those are the operator's follow-up steps; this skill only writes `wopr.yml`.
- Modify the proposed YAML between propose and write. The operator confirms a specific string; the write step writes that exact string.
</role_boundaries>
