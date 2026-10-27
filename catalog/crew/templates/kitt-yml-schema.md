# `kitt.yml` schema

> **Status:** ported 2026-08-21 into the kitt clean-room repo from the original toolset; field semantics unchanged.

## Purpose

`kitt.yml` is the per-project configuration file that KITT packs read at the start of every agent invocation. It lives at the project root. It carries:

- Project-level facts every KITT workflow pack needs (slug, source roots, build file, base package).
- Cross-pack concerns (spec file paths, API contract location and pinned generator version, requirements source).
- Pack-specific sections that only the relevant pack reads.

Putting all of these in one file at project root means a project can be served by multiple KITT packs (legacy-migration, java, angular, future workflow packs) without accumulating `.legacy-migration.yml`, `.java.yml`, `.angular.yml`, etc. side by side. Each pack reads the shared sections it needs plus its own pack-specific section.

## File location

- Default: `kitt.yml` at the project root (the directory where the operator opens their Claude Code session).
- Override: callers may pass an absolute path to a config file in a side directory. Useful when a project's root is not the operator's working directory.

## Behavior when absent

If `kitt.yml` is missing at the resolved path, the tool stops and reports an error pointing the operator at `/kitt-create-yml`. It does not fall back to interactive prompts or per-call parameter passing. Operator must produce a config file before dependent tools run.

## Top-level structure

```yaml
project:        # required, pack-agnostic
specs:          # required, pack-agnostic
api_contract:   # required by the crew pack: the machine-readable API contract (OpenAPI or GraphQL)
requirements:   # optional, pack-agnostic; defaults to source: local when absent
learnings:      # optional, pack-agnostic; semantic-search (CRAG) configuration
legacy-migration:   # required only when the legacy-migration pack is in use
# future packs add their own sections without disturbing existing ones
```

## Section: `project`

Pack-agnostic. Identifies the project and its top-level directory layout. Read by `stack_detect.py`'s `_summarize_kitt_yml` and by the `propose_kitt_yml` generator.

| Field | Required | Type | Notes |
|---|---|---|---|
| `slug` | yes | string | Kebab-case identifier. Used in agent names, file paths, audit reports. Example: `demo-api`. |
| `name` | yes | string | Human-readable project name. Used in audit-report titles and agent introductions. |
| `target_source_root` | yes | string | Path relative to project root. Where production code lives. Example: `src/main/java/com/example/app`. |
| `test_root` | yes | string | Path relative to project root. Where tests live. Example: `src/test/java`. |
| `build_file` | yes | string | Path relative to project root. The primary build config. Example: `pom.xml`, `package.json`, `project.json`. |
| `base_package` | optional | string | Language-dependent. Example: `com.example.app` for Java. Blank or omitted for stacks where the concept does not apply. |

## Section: `specs`

Pack-agnostic. The authoritative documents the agents read on every invocation. Read by `stack_detect.py`'s `_summarize_kitt_yml`.

| Field | Required | Type | Notes |
|---|---|---|---|
| `coder_spec` | yes | string | Path relative to project root. Coding standards document. |
| `tester_spec` | yes | string | Path relative to project root. Testing standards document. |
| `audit_report` | yes | string | Path relative to project root. Where the auditor writes the audit report. |
| `design_spec` | optional | string | Path relative to project root. The project's visual/design spec document. **Presence of this field is what dispatches the `crew-designer` role**; omit it and no crew run pays any appearance cost. Maintained by the designer, approved by the operator. |
| `visual_check` | optional | string | The command that runs the visual-regression suite (e.g. `npx playwright test --grep @visual`). Required when `design_spec` is set; the auditor runs it at the gate and a failing comparison is a BLOCKER. Baselines are committed to the repo and only ever approved by the operator. |
| `spec_writes` | optional | boolean | Default **`false`**. Governs whether crew agents may amend the spec sections they own (coder: pattern rules; tester: coverage shapes; auditor: audit rules). `false`: agents *propose* rules in their reports and the operator decides what lands. `true`: the owning agent amends its spec directly as patterns emerge. Read by the crew orchestrator at run start and passed to every crew agent; not parsed by `stack_detect.py`. Certain invariant sections are never amendable regardless of this flag (see the coder-spec template). |

## Section: `api_contract`

The machine-readable API contract that crew agents cite instead of hand-copying shapes. Required by the crew pack (no contract, no crew run). Read by `stack_detect.py`'s `_summarize_kitt_yml`.

| Field | Required | Type | Notes |
|---|---|---|---|
| `kind` | no | `openapi` \| `graphql` | Default `openapi`. Decides how agents address contract items: JSON Pointer into the OpenAPI document, or operation / type name in the GraphQL schema. |
| `spec_url` | yes | string | URL or path to the contract. OpenAPI: `/v3/api-docs`, `https://api.example.com/v3/api-docs`, `specs/openapi.json`. GraphQL: the schema source, e.g. `amplify/data/resource.ts` (Amplify Gen 2) or `schema.graphql`. |
| `pinned_generator_version` | yes | string | Format: `<tool> <semver>`. The tool that produces (backend) or consumes (frontend) the contract; used by the auditor for lockstep verification. OpenAPI: `openapi-generator-cli 7.21.0`, `springdoc-openapi 2.7.0`. GraphQL: `aws-amplify 6.20.0`, `graphql-codegen 5.0.0`. |

**Legacy alias.** Before GraphQL projects existed this section was named `openapi:` (same fields, no `kind`). The parser still reads `openapi:` as `api_contract` with `kind: openapi` and flags it (`legacy_section: openapi` in the summary); `api_contract` wins when both are present. New files use `api_contract`.

## Section: `requirements`

Pack-agnostic. Tells the orchestrator where the active REQ body comes from at crew dispatch. Absent section defaults to `source: local` with `local.path: requirements`, so existing projects predating this field keep working unchanged. Read by `stack_detect.py`'s `_summarize_kitt_yml`; generated (with the same default) by `propose_kitt_yml`.

| Field | Required | Type | Notes |
|---|---|---|---|
| `source` | optional | string | `local` or `jira`. Defaults to `local` when the whole `requirements` section, or this field, is absent. |
| `local.path` | optional | string | Directory of `<REQ-ID>.md` files, relative to this `kitt.yml`. Defaults to `requirements` when `source: local` and the field is omitted. Read only when `source: local`. |
| `jira.project_key` | optional | string | Optional sanity check against the configured Jira project. Read only when `source: jira`. |
| `jira.cloud_id` | not read | string | If present under `jira`, it is silently ignored. The Atlassian site is resolved at runtime via the Atlassian MCP's `getAccessibleAtlassianResources` call, not stored here; it is machine-level state, not project-level. **(not read by current tooling)** |

## Section: `learnings`

Pack-agnostic, optional. Configures the semantic half of the LEARNINGS retrieval path (`learnings_search`). Read by the MCP server's embedding-provider resolution (`src/kitt/tools/_embedding_providers.py`) from the `kitt.yml` in the workspace root that owns the `LEARNINGS.md` corpus. Absent section means the default: `embeddings.provider: local`.

| Field | Required | Type | Notes |
|---|---|---|---|
| `embeddings.provider` | optional | string | Which engine produces entry/query embeddings for semantic search. One of `local` (default; the bundled fastembed + BAAI/bge-small-en-v1.5 model, ~130MB downloaded lazily to `~/.cache/fastembed/` on first use), `bedrock` (Amazon Titan Text Embeddings V2 via AWS Bedrock; requires `pip install 'kitt[bedrock]'` plus AWS credentials and a region — without them, search degrades to the deterministic prefilter, no crash, no AWS call), or `none` (opt-out: semantic search off, the deterministic prefilter is the whole retrieval path). The env var `KITT_EMBEDDING_PROVIDER` overrides this field on any machine where it is set. Switching providers transparently rebuilds the `.npz` sidecars from the markdown corpus on next search. An unrecognized value is logged and treated as unset. |

## Section: `legacy-migration`

Read only by the `legacy-migration` pack namespace. Other packs ignore this section except for a presence check (`stack_detect.py` sets `has_legacy_migration_block: true` when the key exists, without inspecting its contents).

The legacy-migration pack itself (its scout, its `extract_legacy_context.py` pre-flight, its schema-extractor scripts) is not part of this repo. Of the fields below, only `tracking_doc` and `handoff_contract` are actively read by surviving tooling in this repo, via `write_tracking_doc_stub` and `write_handoff_contract_stub` in `src/kitt/tools/stub_writers.py` (each falls back to a default filename when the field is absent). The remaining fields are documented here because the `legacy-migration` section is still read as a yml namespace by surviving tools and a project may carry them for a pack run elsewhere; nothing in this repo currently parses them beyond the presence check above.

| Field | Required | Type | Notes |
|---|---|---|---|
| `legacy_source_root` | yes | string | Absolute path. Points at the legacy backend codebase the scout reads. Example: `/path/to/legacy/api/repo`. **(not read by current tooling)** |
| `legacy_ui_source_root` | optional | string | Absolute path. Points at the legacy frontend codebase. Set when the project has both a legacy backend and a legacy frontend, and the scout's `extract_legacy_context.py` pre-flight should also produce a `ui_api_map.md` summary. Example: `/path/to/legacy/ui/repo`. **(not read by current tooling)** |
| `extracted_requirements` | yes | string | Path relative to project root. Where REQ blocks and the Migration Context section live. Example: `LEGACY_REQUIREMENTS.md`. **(not read by current tooling)** |
| `tracking_doc` | yes | string | Path relative to project root. Implementation-tracking document. Example: `CURRENT_REQUIREMENTS.md`. Read by `write_tracking_doc_stub`; falls back to `implementation-tracking.md` when absent. |
| `legacy_analysis_root` | optional | string | Path relative to project root. Directory where the `extract_legacy_context.py` pre-flight writes its summary files (`endpoint_inventory.md`, `model_catalog.md`, `dao_signatures.md`, `ui_api_map.md`). Default: `legacy-analysis/`. Override only when the project's docs layout requires it. **(not read by current tooling)** |
| `schema_path` | optional | string | Path relative to project root. Legacy schema reference (DDL, ORM mappings). Set only when migrating from a legacy backend with a schema. **(not read by current tooling)** |
| `schema_env_prefix` | optional | string | Project-specific prefix for the schema-extractor scripts' database env vars. Scripts read `${PREFIX}_ORA_DB_PROXY` and `${PREFIX}_ORA_DB_PASSWORD` (Oracle) or `${PREFIX}_PG_DB_USER` and `${PREFIX}_PG_DB_PASSWORD` (PostgreSQL). Example: `DEMO`. Required only if the operator runs the schema extractor scripts directly; not read by the crew agents. **(not read by current tooling)** |
| `handoff_contract` | optional | string | Path relative to project root. Frontend handoff contract. Set only when this project has a frontend track in scope. Read by `write_handoff_contract_stub`; falls back to `frontend-handoff-contract.md` when absent. |
| `parity` | optional | mapping | Parity-harness config, present only when the project runs the parity harness. The pack runbook resolves each field into the `PARITY_*` env var the harness reads. **(not read by current tooling)** |

### `legacy-migration.parity` fields

Each maps 1:1 onto a harness env var:

| Field | Env var | Notes |
|---|---|---|
| `legacy_url` | `PARITY_LEGACY_URL` | Base URL of the legacy app. |
| `angular_url` | `PARITY_ANGULAR_URL` | The modern app under test. The name says "angular" (the reference stack); it is just the modern side. |
| `auth_adapter` | `PARITY_AUTH_ADAPTER` | A shipped reference adapter (`client-openam-oidc` \| `noop`) or your own module. |
| `catalog` | `PARITY_CATALOG` | Route catalog JSON, relative to project root. |
| `legacy_storage` | `PARITY_LEGACY_STORAGE` | Storage-state file for the legacy side. |
| `angular_storage` | `PARITY_ANGULAR_STORAGE` | Storage-state file for the modern side. |
| `test_user_id` | `PARITY_TEST_USER_ID` | Required for parameterized routes; a real id in YOUR data, no default. |
| `test_prog_type` | `PARITY_TEST_PROG_TYPE` | Same. |
| `api_scope_regex` | `PARITY_API_SCOPE_REGEX` | Optional scope of the API surface. |

## Path conventions

- **`<target_dir>`**, wherever it appears in pack documentation (crew agents, orchestrator skill, contracts), means **the directory containing the project's `kitt.yml`** — the project root by default, or the override directory when the operator passes an explicit config path. It is a documentation term resolved from the `kitt.yml` location, not a `kitt.yml` field. Example: the scout contract lands at `<target_dir>/crew-contracts/<REQ-ID>/scout.md`.
- All paths in shared sections (`project`, `specs`) are **relative to project root** unless the field documentation explicitly says otherwise.
- `api_contract.spec_url` accepts a URL OR a relative path; agents detect the form.
- `requirements.local.path` is relative to this `kitt.yml`.
- `legacy-migration.legacy_source_root` and `legacy-migration.legacy_ui_source_root` are **absolute**. The legacy source typically lives outside the project repo (a sibling directory or a separate clone).
- `legacy-migration.extracted_requirements`, `tracking_doc`, `legacy_analysis_root`, `schema_path`, and `handoff_contract` are **relative to project root**.
- `legacy-migration.schema_env_prefix` is a string identifier, not a path. It is appended to canonical env-var suffixes the schema-extractor scripts expect.

## Future packs

A new KITT workflow pack adds its own section to `kitt.yml`. It reads the shared sections (`project`, `specs`, `api_contract` if applicable, `requirements`) plus its own section. It does not modify or read other packs' sections. Adding a new section does not break existing packs.

If a new pack needs a field that already exists in a shared section, it reads from there. If it needs a new shared concern (e.g., a `lint` section that multiple packs would benefit from), the schema gets a new top-level section and this doc updates.

## Example: backend project (`demo-api-poc`)

See `kitt.example.yml` (this directory).

## Example: frontend project (`apps/demo-admin`)

Same example file covers both shapes. Backend uses the `legacy-migration.schema_path` and `legacy-migration.schema_env_prefix` fields; frontend omits them and sets `handoff_contract` to the same path the backend's audit emits.
