# P1 port notes

Mechanical clean-room port of the surviving subset of the prior private
toolset (`webteam-ai-tools`, v0.24.4) into this repository. The quarry
was read-only throughout and was not modified.

Every deviation from a straight file copy is recorded below. Behavior
of ported code is preserved: no reformatting, no logic changes. The
only edits are the package rename, import-path fixes, the deliberate
omissions listed here, and the specific dependency resolutions called
out in section 3.

## 1. Headline numbers

| Thing | Quarry | Here |
| --- | --- | --- |
| Registered MCP tools | 68 | **23** |
| Source modules (`.py` under `src/`) | 62 | 41 |
| Source lines (`src/`) | 18,622 | 10,105 |
| Test files | 51 | 31 |
| Test lines | 14,932 | 7,163 |
| Catalog packs | 13 (+1 roadmap) | 6 |
| Catalog lines (all file types) | 84,003 | 48,178 |

Test run: **548 passed, 1 skipped**. The single skip is pre-existing and
not introduced here: `tests/test_embeddings.py` skips at module import
when `numpy` is absent, which is the documented behavior of the optional
`[embeddings]` extra. `uv run ruff check src tests` and
`uv run mypy src/wopr` are both clean.

Catalog content was copied **verbatim**. The 48,178-line figure is the
six surviving packs unslimmed; content slimming is P2, so that number is
expected to drop a lot and is not a P1 result.

## 2. The 23 registered MCP tools

```
append_learnings                 learnings_search
check_mcp_servers_for_malware    list_pack_templates
check_routing_evals              pin_skill
create_handoff                   propose_wopr_yml
curate_learnings                 scan_skill_directory
detect_stack                     seed_learnings
get_handoff                      skill_usage_report
get_help                         validate_scout_contract
get_pack_template                write_handoff_contract_stub
get_workspace_info               write_spec_stubs
learnings_path                   write_tracking_doc_stub
                                 write_wopr_yml
```

`tests/test_server.py::TestCreateApp::test_registers_exactly_the_expected_tool_set`
pins this list by name, so a tool appearing or vanishing is a deliberate
diff rather than a silent change in `create_app`.

Two entries deviate from the plan's keep-list; both are explained in
section 3.

## 3. Dependency resolutions (kept module needed a dropped one)

### 3.1 `detect_stack` was ported, and registered as a tool

**Not in the plan's keep-list.** `wopr_yml.propose_wopr_yml` and
`write_wopr_yml` take a required `detection_json` argument whose
documented contract is "the output of `detect_stack`". `detect_stack`
lived in `tools/doctor.py`, which is dropped. Without it, two kept tools
have no legal input short of an agent hand-authoring the detection JSON,
and 25 assertions across `tests/test_wopr_yml.py` have no way to build a
fixture.

Resolution: extracted the detector (the dataclasses, all `_detect_*`
helpers, the `wopr.yml` inventory scan, the external-signal scan, and
`detect_stack` itself) into a new module `src/wopr/tools/stack_detect.py`
and registered `detect_stack` there. The extraction is verbatim except
for the module docstring, the removal of the `doctor_readiness` /
`doctor_recommendations` re-export blocks, and four comments that named
a client project (see 6.2). The recommendation-and-dismissal engine
(`recommend_wopr_setup`, `dismiss_wopr_recommendation`,
`list_dismissed_wopr_recommendations`,
`reset_wopr_recommendation_dismissals`) and both `doctor_*` support
modules did NOT cross over; that is the "doctor nag machinery" the plan
retires.

**If you disagree with registering it, deleting one line in
`stack_detect.register` and one entry in `EXPECTED_TOOLS` takes the
count to 22 and leaves the module importable for tests.**

### 3.2 `write_extracted_requirements_stub` was dropped

**In the plan's keep-list by implication** (`stub_writers.py` ports).
This writer's only job is to land
`catalog/legacy-migration/templates/extracted-requirements.template.md`.
The `legacy-migration` pack never crosses over, so the tool cannot
succeed here. Removed from `stub_writers.py` along with its re-export in
`wopr_yml.py`. Its two sibling writers (`write_tracking_doc_stub`,
`write_handoff_contract_stub`) land `crew` pack templates and are kept
unchanged, including their reading of `legacy-migration.*` keys out of a
project's `wopr.yml` (that is a yml key namespace, not a pack
dependency, and changing it would be a behavior change).

### 3.3 `is_safe_entry_name` inlined into `tools/_skill_usage.py`

`_skill_usage.py` imported it from `install_manifest.py` (dropped). The
function is 4 lines and self-contained. Copied verbatim into
`_skill_usage.py` with a docstring line naming its origin. It is the
load-bearing guard on sidecar key names, so it had to travel.

### 3.4 `_request_workspace` and `_all_available` inlined into `tools/skill_usage.py`

`skill_usage.py` imported both from `tools/resources.py`, the 10-tool
cross-CLI shim layer, which is dropped wholesale. `skill_usage.py` was
the only surviving consumer of either.

- `_request_workspace` copied verbatim into `skill_usage.py` as a
  private helper.
- `_all_available(ctx, category, ...)` was a three-branch generic; only
  the `"skills"` branch was ever reached from here. Inlined as
  `_installed_skill_names`, which is the same loop over
  `ServerContext.resource_dirs("skills", workspace)`. Same output for
  the same inputs; the `_collect_files` branch for non-skill categories
  did not travel because nothing calls it.

### 3.5 `manager.py` ported without `cmd_add` / `cmd_remove`

Both functions call `init.sync_packs` (dropped: it is the per-CLI
symlink installer). `cmd_list` and `cmd_catalog` are read-only, depend
only on `catalog.py`, and still work, so they ported unchanged and stay
wired to the CLI. Module docstring updated to say so.

### 3.6 `resolver.py` NOT ported (deviation from the plan's keep-list)

`resolver.py` is the skill-loading-tier resolver: it exists to classify
skills into `always` / `resolver` / `dormant` and render the generated
`wopr-skill-resolver` skill. Every symbol it imports comes from
`loading_manifest.py`, which the plan explicitly does not port ("the
skill-loading-tier mechanism is deliberately not ported"; "per-pack
plugin install IS the tiering now"). Its only consumer was `cli_setup`,
also dropped.

Porting it would have meant re-introducing the tier mechanism the plan
retires, as dead code with no caller and no test (`test_loading_tiers.py`
is on the do-not-port list). So it was dropped rather than stubbed.

One thing in it may be worth re-quarrying in P3: `read_frontmatter()`
(a bounded head-read + YAML parse of a `SKILL.md` frontmatter block)
and `summarize()` (compress a description to one line). The
`build-plugins` generator will need to read skill frontmatter. Both are
small and sit at
`webteam-ai-tools/src/ai_cli_mcp/resolver.py` lines 87-132.

## 4. Test adjustments

Every case below covered functionality that does not exist here. No
assertion was weakened to make a ported behavior pass.

1. **`tests/conftest.py`**: removed the autouse
   `_never_install_into_the_real_home` fixture. It guarded
   `cli_setup.setup_claude` / `setup_gemini` / `setup_copilot` against
   escaping a fake `$HOME`; none of those functions exist here, so the
   fixture could only raise `AttributeError` at import. The other
   autouse guard (`_wopr_home_never_points_at_the_real_home`, which is
   the one that matters for the surviving tools) is untouched, as is
   `_rebind_everywhere` which it uses. Two docstrings that named dropped
   modules were reworded.

2. **`tests/test_server.py`**: deleted `TestShouldRegisterExtras` (4
   cases). It tested `server._should_register_extras`, the gate that
   conditionally registered the `extras` pack's 15 utility tools. The
   `extras` pack does not cross over, so the gate was removed from
   `create_app` and the tools are gone. Replaced with
   `test_registers_exactly_the_expected_tool_set`, which pins the 23
   surviving tool names. Net: -4 cases, +1 case.

3. **`tests/test_skill_usage.py`**: deleted `TestRunSkillCounting` (4
   cases). All four drove the `run_skill` MCP tool, which is part of the
   dropped shim layer. One of the four asserted a property worth
   keeping ("telemetry must never be able to fail its call site"), so it
   was rewritten as `TestWriteFailureContainment`, asserting directly
   that `record_invocation` returns `False` on an unwritable sidecar
   instead of raising. Net: -4 cases, +1 case. Module docstring updated.

4. **`tests/test_multi_workspace_tools.py`**: reduced from 3 cases to
   1. Two cases drove `run_skill`, `add_note` / `list_notes`,
   `list_projects` and `time_tracking.log_time`, none of which cross
   over. The surviving case
   (`test_project_name_cannot_escape_selected_workspace`) tests
   `ServerContext.resolve_project_path` containment and is unchanged.
   Cross-workspace isolation for the tools that DID survive is still
   covered by `test_handoff_workspace.py` and `test_learnings*.py`.

5. **`tests/test_wopr_yml.py`**: deleted the three
   `write_extracted_requirements_stub` cases (see 3.2) and adjusted
   `test_stub_writers_register_registers_expected_tools` from a
   three-name list to a two-name list. Changed the import of
   `detect_stack` from `wopr.tools.doctor` to `wopr.tools.stack_detect`
   (see 3.1); all 25 call sites are otherwise untouched.

6. **`tests/test_pack_templates.py`**: deleted
   `test_returns_legacy_migration_extracted_requirements_template` and
   `test_lists_legacy_migration_templates`. Both fetch templates out of
   the dropped `legacy-migration` pack. The `crew` pack equivalents
   (which are the ones the tool is actually for) are unchanged and
   still passing.

7. **`tests/test_template_placeholders.py`**: `_PACKS` narrowed from
   `("crew", "legacy-migration")` to `("crew",)`. The placeholder-syntax
   sweep itself is unchanged; only its scope shrank with the catalog.

8. **`tests/test_llms_txt.py`**: not ported. See 5.3.

9. **Converters**: `converters.py`, `conversion_manifest.py` and their
   tests (`test_converters.py`, `test_conversion_manifest.py`) ported
   unchanged, including the Gemini TOML and Copilot emission paths and
   their assertions. Per the plan those are quarried later, not deleted
   in P1. All pass as-is; no fixture depended on a dropped pack.

## 5. Deliberate omissions

### 5.1 Root modules not ported

`cli_setup.py` (84 KB, the per-CLI symlink installer), `init.py`,
`install_manifest.py`, `uninstall.py`, `fingerprint.py`,
`hook_manifest.py`, `loading_manifest.py`, `resolver.py` (see 3.6).

### 5.2 Tool modules not ported

`agent_instructions.py`, `dev.py`, `dice.py`, `doctor.py` (except the
detector, see 3.1), `doctor_readiness.py`, `doctor_recommendations.py`,
`fleet.py`, `git.py`, `notes.py`, `projects.py`, `resources.py`,
`time_tracking.py`, `todos.py`, `weather.py`.

### 5.3 Root files not ported

`llms.txt` and `tests/test_llms_txt.py` were **dropped, not
regenerated**. `llms.txt` is an index of a `docs/` tree, a
`CONTRIBUTING.md`, a `RESEARCH-CLI-COMPATIBILITY.md`, a `docker/`
sandbox, a `whats-next.md`, and four pack READMEs, of which exactly one
(`catalog/crew/README.md`) exists here. Its test asserts that every
indexed path exists AND that nothing outside the indexed set is present,
so it can only be honestly restored once this repo has its own docs
tree. Regenerate both in a later phase when there is something to index.

Also not ported: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
`CONTRIBUTING.md`, `README.md` (the quarry's 40 KB one; a new short one
was authored), `RESEARCH-CLI-COMPATIBILITY.md`, `docs/`, `docker/`,
`specs/`, `.planning/`, `playground/`, `research/`,
`frontend-handoff-contract.md`, `implementation-tracking.md`,
`tools-manifest.json`, `wopr.yml`, `whats-next.md`, `LEARNINGS.md`,
`LEARNINGS.embeddings.npz`, `.ai-cli/`, `.github/`.

### 5.4 Catalog

Ported verbatim: `_core`, `crew`, `angular`, `python`, `auditors`,
`meta-authoring`.

Not ported: `java`, `vanilla-web`, `ios`, `accessibility`, `security`,
`legacy-migration`, `extras`.

`catalog/crew/data/learnings-seed/` kept all three seed files
(`angular.md`, `fastapi.md`, `spring-boot.md`) verbatim. Nothing in
`catalog.yaml` or in the tests references seeds per-pack, so the plan's
condition for dropping `spring-boot.md` was not met; that call belongs
to P2's content pass. Wheel build verified all three ride along.

`catalog.yaml` is the one catalog file that was EDITED rather than
copied. Changes: the seven dropped packs removed; the `extras` block
and its 15-entry `mcp_tools` list removed; the `wasm` roadmap entry
removed; the `.NET` explanatory comment removed (it explained a removal
that predates this repo); the `crew` description's trailing sentence
about the `legacy-migration` pack removed; and the profile set rebuilt
so no profile names a dropped pack. Profiles now: `angular-team`,
`python-ai`, `fullstack`, `everything`. `java-team` and
`legacy-migration-team` are gone.

## 6. Known-stale content carried over on purpose

These are content problems, not port errors. They belong to P2's
slimming pass, and fixing them now would have meant editing ported
prose, which P1 is not supposed to do.

### 6.1 Stale prose in ported code

- `help.py` (23 KB) still documents `wopr --init`, `wopr add`,
  `wopr remove`, `wopr --uninstall`, the skill resolver, Gemini and
  Copilot install paths, and packs that no longer exist. `wopr help`
  therefore prints instructions for a surface this repo does not have.
  It is the single biggest piece of stale text in `src/`.
- `server.py`'s `get_workspace_info` still counts
  `~/.gemini/{skills,commands}` and `~/.copilot/{skills,agents}` and
  still reports on `time-tracking.json` / `notes.json`. The code is
  correct as written and harmless (it reports zeroes), but it describes
  a world with three CLIs and tools that are gone. Structure kept per
  the port brief.
- `catalog/` markdown still contains `import ai_cli_mcp` shims (two
  `meta-authoring` commands, one line in `wopr-run-crew/SKILL.md`) and
  a reference to `src/ai_cli_mcp/tools/crew_contracts.py` in
  `catalog/crew/README.md`. Those are real breakages once this package
  is what gets installed. They were left alone because the catalog is
  specified as a verbatim copy in P1; they must be fixed in P2.

### 6.2 Placeholder markers from the quarry's own privacy scrub

The quarry had already been scrubbed of client and personal
identifiers, leaving bracketed placeholders behind. Roughly 20 of these
came across in comments and docstrings: `[TICKET-ID]` (an issue key)
and `[client-project-cac]` / `[client-project-b]` (project names). They
are in `src/wopr/{catalog,help}.py`,
`src/wopr/tools/{_data_paths,_embeddings,_errors,_target_paths,_version_check,wopr_yml}.py`,
and six test modules. They leak nothing, and rewriting comments is
outside a mechanical port, so they stay for now. Four occurrences WERE
rewritten in `stack_detect.py` only because that module's comments were
already being edited during the extraction.

`pyproject.toml`'s `[project.urls]` table (which pointed at a private
client org) was removed outright rather than placeheld, per the port
brief. No URLs are declared until this repo has a public home.

### 6.3 `LICENSE`

`pyproject.toml` declares `license = "MIT"` and lists `LICENSE` in the
sdist include list, but no `LICENSE` file exists. That was already true
in the quarry. Hatchling tolerates the missing include; the build is
clean. Add the file before any public push.

## 7. Verification performed

- `uv sync --extra dev` from a clean tree; `uv.lock` regenerated here,
  not copied from the quarry.
- `uv run pytest` -> 548 passed, 1 skipped.
- `uv run ruff check src tests` -> clean.
- `uv run mypy src/wopr` -> clean, 41 source files.
- `uv run wopr --help`, `--version`, `catalog`, `list`, `skill-usage
  report` all behave.
- `uv run python -c "from wopr.server import create_app; create_app()"`
  imports and builds the app.
- `uv build` -> wheel contains all six packs under `wopr/resources/`
  plus `wopr/catalog.yaml`, confirming the ported `hatch_build.py` hook
  maps to the new package name correctly. Build artifacts removed
  afterwards.

## 8. Small behavior fixes made (user-facing strings only)

Two log lines told the operator to run a command that no longer exists.
Left as-is they would be actively wrong output, so they were reworded.
No logic changed.

- `manager.py` `cmd_list`: `"No packs installed. Run 'wopr --init'
  first."` -> `"No packs installed for this workspace."`, and
  `"No global packs installed. Use 'wopr add -g <pack>' to install."` ->
  `"No global packs installed."`
- `skill_usage_cli.py`: `"No skills found. Run \`wopr --init\` first."`
  -> `"No skills found in this workspace's shared dirs."`
