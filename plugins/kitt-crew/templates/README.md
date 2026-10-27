# crew templates

Two kinds of templates live here:

**Tracking-document templates** (the four `*.template.md` files): skeletons for the documents a crew run produces and consumes. The caller fills in `[STACK: ...]` markers with stack specifics before the crew starts.

**Project config example** (`kitt.example.yml`): a worked example of the KITT-shared project configuration file. Each project has its own `kitt.yml` at its project root. Schema reference: `kitt-yml-schema.md` (this directory; ships with the pack).

## Tracking-document templates

| Template | Purpose | Who reads it | Who writes it |
|---|---|---|---|
| `coder-spec.template.md` | Coding standards, architecture patterns, naming conventions, implementation rules | coder, auditor | human initially (team decides conventions); coder maintains it as patterns emerge when `spec_writes` is ON |
| `tester-spec.template.md` | Test framework setup, unit/component patterns, coverage standards, naming conventions | tester, auditor | human initially; tester maintains it as coverage shapes emerge when `spec_writes` is ON |
| `implementation-tracking.template.md` | Per-REQ status (pending, in-progress, implemented, out-of-scope) | all four agents | coder (⏳ → 🔄 and log entries), tester (coverage state), scout (drift corrections), **orchestrator (🔄 → ✅, only after the coverage gate passes)**, auditor (read-only) |
| `frontend-handoff-contract.template.md` | Every new or changed API surface item with REQ IDs and UI action items | coder, auditor, frontend team | coder (updates on every API change); auditor (BLOCKS merge if out of sync) |

For migration projects, an additional template (`extracted-requirements.template.md`) ships with the `legacy-migration` pack, which is not part of this distribution. The scout populates it in `deep_analysis` mode by reading the legacy codebase. Non-migration projects do not need this template; they populate the implementation-tracking document's Requirements Baseline directly from their own requirements source (feature backlog, written spec, ticket system).

## Project config (`kitt.yml`)

`kitt.yml` is the KITT-shared project configuration file, read by every agent on every invocation. It carries the project's slug, source roots, build file, API contract location (`api_contract`: OpenAPI or GraphQL) and pinned generator version, paths to the spec documents, and (for migration projects) the legacy source root, extracted requirements path, schema path, and handoff contract path.

See:

- `kitt.example.yml` (this directory): worked examples for both a backend and a frontend project.
- `kitt-yml-schema.md` (this directory): full schema with section-by-section field tables. Agents fetch it via `mcp__plugin_kitt-core_kitt__get_pack_template` (`pack="crew"`, `name="kitt-yml-schema.md"`).

The crew does not run without `kitt.yml`. If it is missing at the resolved path, every agent stops and reports.

## How to use a tracking-document template

The default path is to let the KITT setup tooling drop these templates for you. Operators should run `/kitt-init-project` (or the targeted stub-writer MCP tools below), not hand-copy from this directory.

**Recommended (one-shot):**

Run `/kitt-init-project` against the target project. The skill detects the stack, writes `kitt.yml`, writes stack-pre-filled spec stubs, and drops `implementation-tracking.template.md` and `frontend-handoff-contract.template.md` at the paths declared by `kitt.yml`. It refuses to overwrite existing files unless you opt in.

**Targeted (one template at a time):**

- `mcp__plugin_kitt-core_kitt__write_tracking_doc_stub` drops `implementation-tracking.template.md` at the operator-declared `legacy-migration.tracking_doc` path (default `implementation-tracking.md`).
- `mcp__plugin_kitt-core_kitt__write_handoff_contract_stub` drops `frontend-handoff-contract.template.md` at `legacy-migration.handoff_contract` (default `frontend-handoff-contract.md`). Only meaningful for backend-producer projects.

Both stub writers refuse to overwrite an existing file by default; pass `overwrite=True` to force.

**Read-only access to the raw template content** is available via `mcp__plugin_kitt-core_kitt__get_pack_template(pack=..., name=...)` and `mcp__plugin_kitt-core_kitt__list_pack_templates(pack=...)`. Agents inside the crew must use these tools instead of running `find` against the workspace; the MCP server already knows the install root.

**After the stub lands:**

1. Drop the `.template` infix from the filename if your `kitt.yml` path does not include it (e.g., `coder-spec.template.md` becomes `CODER_SPEC.md` or whatever your `specs.coder_spec` points at).
2. Walk through every `[STACK: ...]` marker and replace it with your stack's specifics. Delete sections that do not apply. Add sections for concerns the skeleton doesn't cover.
3. Point your `kitt.yml` at the filled-in document (`/kitt-init-project` handles this for the default paths).

**Manual fallback:** if for any reason you need to hand-copy, the templates live alongside this README in the crew pack. Treat this as the exception, not the default; it is what the stub-writer tools exist to eliminate.

## Stack-agnostic vs stack-specific content

Each template is structured in two layers:

- **Universal pattern.** A short description of the generic rule or behavior the section is about. These are stated at the top of each section and apply regardless of language or framework.
- **Stack-specific detail.** Everything in `[STACK: ...]` markers. The caller fills these in based on their specific target stack.

If you find yourself deleting a "universal pattern" line because it doesn't apply to your stack, stop and think. Usually the universal pattern still applies but the stack-specific implementation is unusual. Document WHY it's unusual in the section body instead of deleting the pattern.

## Naming of the filled-in documents

The templates use generic names (`CODER_SPEC`, `IMPLEMENTATION_TRACKING`, etc.). Your project can name the filled-in documents whatever it wants. The agents read paths from `kitt.yml`; they do not care what the file is called. What matters is that the paths in `kitt.yml` are correct.

## Where to keep the filled-in documents

The crew does not care where these documents live. Common patterns:

- **At the project root**: `CODER_SPEC.md`, `IMPLEMENTATION_TRACKING.md`, etc. Easy to find, easy to reference, visible in any file listing.
- **Under a `docs/` directory**: `docs/coder-spec.md`, `docs/implementation-tracking.md`, etc. Cleaner root, but adds a path prefix to every `kitt.yml` value.
- **Under a dedicated `.crew/` directory**: isolates crew state from general docs. Useful if the project's `docs/` is already busy.

Pick a pattern and update `kitt.yml` to match.
