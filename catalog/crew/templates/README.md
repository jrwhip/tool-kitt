# crew templates

Two kinds of templates live here:

**Tracking-document templates** (the four `*.template.md` files): skeletons for the documents a crew run produces and consumes. The caller fills in `[STACK: ...]` markers with stack specifics before the crew starts.

**Project config example** (`wopr.example.yml`): a worked example of the WOPR-shared project configuration file. Each project has its own `wopr.yml` at its project root. Schema reference: `webteam-ai-tools/docs/wopr-yml-schema.md`.

## Tracking-document templates

| Template | Purpose | Who reads it | Who writes it |
|---|---|---|---|
| `coder-spec.template.md` | Coding standards, architecture patterns, naming conventions, implementation rules | coder, auditor | human initially (team decides conventions); coder maintains it as patterns emerge when `spec_writes` is ON |
| `tester-spec.template.md` | Test framework setup, unit/component patterns, coverage standards, naming conventions | tester, auditor | human initially; tester maintains it as coverage shapes emerge when `spec_writes` is ON |
| `implementation-tracking.template.md` | Per-REQ status (pending, in-progress, implemented, out-of-scope) | all four agents | coder (status transitions), tester (coverage state), scout (drift corrections), auditor (read-only) |
| `frontend-handoff-contract.template.md` | Every new or changed API surface item with REQ IDs and UI action items | coder, auditor, frontend team | coder (updates on every API change); auditor (BLOCKS merge if out of sync) |

For migration projects, an additional template lives in the `legacy-migration` pack: `extracted-requirements.template.md`. The scout populates it in `deep_analysis` mode by reading the legacy codebase. Non-migration projects do not need this template; they populate the implementation-tracking document's Requirements Baseline directly from their own requirements source (feature backlog, written spec, ticket system).

## Project config (`wopr.yml`)

`wopr.yml` is the WOPR-shared project configuration file, read by every agent on every invocation. It carries the project's slug, source roots, build file, OpenAPI spec URL and pinned generator version, paths to the spec documents, and (for migration projects) the legacy source root, extracted requirements path, schema path, and handoff contract path.

See:

- `wopr.example.yml` (this directory): worked examples for both a backend and a frontend project.
- `webteam-ai-tools/docs/wopr-yml-schema.md`: full schema with section-by-section field tables.

The crew does not run without `wopr.yml`. If it is missing at the resolved path, every agent stops and reports.

## How to use a tracking-document template

The default path is to let the WOPR setup tooling drop these templates for you. Operators should run `/wopr-init-project` (or the targeted stub-writer MCP tools below), not hand-copy from `catalog/crew/templates/`.

**Recommended (one-shot):**

Run `/wopr-init-project` against the target project. The skill detects the stack, writes `wopr.yml`, writes stack-pre-filled spec stubs, and drops `implementation-tracking.template.md`, `frontend-handoff-contract.template.md`, and (for migration projects) `extracted-requirements.template.md` at the paths declared by `wopr.yml`. It refuses to overwrite existing files unless you opt in.

**Targeted (one template at a time):**

- `mcp__wopr__write_tracking_doc_stub` drops `implementation-tracking.template.md` at the operator-declared `legacy-migration.tracking_doc` path (default `implementation-tracking.md`).
- `mcp__wopr__write_handoff_contract_stub` drops `frontend-handoff-contract.template.md` at `legacy-migration.handoff_contract` (default `frontend-handoff-contract.md`). Only meaningful for backend-producer projects.
- `mcp__wopr__write_extracted_requirements_stub` drops `extracted-requirements.template.md` at `legacy-migration.extracted_requirements`. Only fires when `wopr.yml` declares `legacy-migration.legacy_source_root` (i.e., the project is a migration target); returns a `Skipped:` line otherwise.

All three stub writers refuse to overwrite an existing file by default; pass `overwrite=True` to force.

**Read-only access to the raw template content** is available via `mcp__wopr__get_pack_template(pack=..., name=...)` and `mcp__wopr__list_pack_templates(pack=...)`. Agents inside the crew must use these tools instead of running `find` against the workspace; the MCP server already knows the install root.

**After the stub lands:**

1. Drop the `.template` infix from the filename if your `wopr.yml` path does not include it (e.g., `coder-spec.template.md` becomes `CODER_SPEC.md` or whatever your `specs.coder_spec` points at).
2. Walk through every `[STACK: ...]` marker and replace it with your stack's specifics. Delete sections that do not apply. Add sections for concerns the skeleton doesn't cover.
3. Point your `wopr.yml` at the filled-in document (`/wopr-init-project` handles this for the default paths).

**Manual fallback:** if for any reason you need to hand-copy, the templates live in `catalog/crew/templates/` (or `catalog/legacy-migration/templates/` for `extracted-requirements.template.md`). Treat this as the exception, not the default; it is what the stub-writer tools exist to eliminate.

## Stack-agnostic vs stack-specific content

Each template is structured in two layers:

- **Universal pattern.** A short description of the generic rule or behavior the section is about. These are stated at the top of each section and apply regardless of language or framework.
- **Stack-specific detail.** Everything in `[STACK: ...]` markers. The caller fills these in based on their specific target stack.

If you find yourself deleting a "universal pattern" line because it doesn't apply to your stack, stop and think. Usually the universal pattern still applies but the stack-specific implementation is unusual. Document WHY it's unusual in the section body instead of deleting the pattern.

## Naming of the filled-in documents

The templates use generic names (`CODER_SPEC`, `IMPLEMENTATION_TRACKING`, etc.). Your project can name the filled-in documents whatever it wants. The agents read paths from `wopr.yml`; they do not care what the file is called. What matters is that the paths in `wopr.yml` are correct.

## Where to keep the filled-in documents

The crew does not care where these documents live. Common patterns:

- **At the project root**: `CODER_SPEC.md`, `IMPLEMENTATION_TRACKING.md`, etc. Easy to find, easy to reference, visible in any file listing.
- **Under a `docs/` directory**: `docs/coder-spec.md`, `docs/implementation-tracking.md`, etc. Cleaner root, but adds a path prefix to every `wopr.yml` value.
- **Under a dedicated `.crew/` directory**: isolates crew state from general docs. Useful if the project's `docs/` is already busy.

Pick a pattern and update `wopr.yml` to match.
