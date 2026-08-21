# Slimming ledger

A receipt for every deletion. One row per artifact or per module group,
with the evidence or the reasoning that justified the verdict. Nothing
here is a plan: an entry appears only after the cut has landed.

Verdicts:

| Verdict | Meaning |
| --- | --- |
| CUT | Removed. Not present in this repository. |
| COLLAPSED | Several artifacts replaced by one that covers the same surface. |
| SLIMMED | Kept, with content removed. |
| KEPT | Considered for removal and deliberately retained. |

The quarry (`webteam-ai-tools` v0.24.4) is read-only and still holds
everything listed as CUT. Nothing is unrecoverable.

## A note on the tool count

P1-NOTES states the quarry registered 68 MCP tools. A name-level
enumeration of every `mcp.tool()(...)` call and every `@mcp.tool()`
decorated function in the quarry finds **67**, not 68, and all 23 kept
tools appear in that 67. The retirement figure in this ledger is
therefore **44 tools (67 to 23)**. The 45 in P1-NOTES is one higher than
any enumeration reproduces. Rows below name every retired tool, so the
count is checkable rather than asserted.

## MCP tools retired (44), by quarry module

| Artifact | Verdict | Evidence or rationale | Phase | Date |
| --- | --- | --- | --- | --- |
| `tools/resources.py` (10): `list_shared_commands`, `get_shared_command`, `list_shared_skills`, `get_shared_skill`, `list_shared_agents`, `get_shared_agent`, `list_shared_context`, `get_shared_context`, `run_skill`, `invoke_agent` | CUT | The cross-CLI shim layer. It existed so Gemini and Copilot could reach skills and agents they had no native loader for. Claude Code loads all three natively, so every tool here is a slower path to something the CLI already does. Largest single reduction. | P1 | 2026-08-21 |
| `tools/time_tracking.py` (5): `start_timer`, `stop_timer`, `log_time`, `list_time_entries`, `time_summary` | CUT | Time tracking is not agent-harness work. No catalog artifact called them. | P1 | 2026-08-21 |
| `tools/doctor.py` (4 of 5): `recommend_wopr_setup`, `dismiss_wopr_recommendation`, `list_dismissed_wopr_recommendations`, `reset_wopr_recommendation_dismissals` | CUT | The recommend-and-dismiss engine: three of the four tools exist only to manage the nagging produced by the first. `detect_stack` was extracted and kept (see KEPT rows). | P1 | 2026-08-21 |
| `tools/dice.py` (4): `roll_dice`, `flip_coin`, `random_choice`, `random_number` | CUT | Sampling toys. Not deterministic work an agent cannot do, and not orchestration. | P1 | 2026-08-21 |
| `tools/notes.py` (4): `add_note`, `list_notes`, `search_notes`, `delete_note` | CUT | A second note store next to `TO-DOS.md`, `whats-next.md` and `LEARNINGS.md`. Overlapping stores with no defined boundary between them. | P1 | 2026-08-21 |
| `tools/git.py` (3): `git_status`, `git_diff`, `git_log` | CUT | Claude Code runs `git` through Bash natively, with better output than a JSON wrapper. | P1 | 2026-08-21 |
| `tools/todos.py` (3): `add_todo`, `list_todos`, `complete_todo` | CUT | Native TodoWrite plus the file-based `/wopr-add-to-todos` and `/wopr-check-todos` commands cover this. | P1 | 2026-08-21 |
| `tools/dev.py` (3): `run_npm_script`, `check_build`, `create_mcp_tool` | CUT | The first two are Bash with extra steps. `create_mcp_tool` wrote a Python source file into a package it could not reload. | P1 | 2026-08-21 |
| `tools/agent_instructions.py` (2): `propose_agent_instructions`, `write_agent_instructions` | CUT | Generated `AGENTS.md` and per-CLI pointer files. Per-CLI pointers go with the per-CLI support; `AGENTS.md` is a file the agent can write directly. | P1 | 2026-08-21 |
| `tools/projects.py` (2): `list_projects`, `get_project_context` | CUT | Multi-project discovery from a single server. The plugin model gives one workspace per session. | P1 | 2026-08-21 |
| `tools/weather.py` (2): `get_weather`, `get_forecast` | CUT | Not development tooling. | P1 | 2026-08-21 |
| `tools/fleet.py` (1): `fleet_status` | CUT | Reported on a fleet of tracked repositories. No consumer ported. | P1 | 2026-08-21 |
| `tools/stub_writers.py` (1 of 3): `write_extracted_requirements_stub` | CUT | Its only output is `catalog/legacy-migration/templates/extracted-requirements.template.md`. That pack does not cross over, so the tool could not succeed here. Its two siblings write `crew` templates and are kept. | P1 | 2026-08-21 |
| `detect_stack` | KEPT | Removed from `doctor.py` with the rest of that module, then re-extracted into `tools/stack_detect.py`. `propose_wopr_yml` and `write_wopr_yml` take its output as a required `detection_json` argument; without it both kept tools have no legal input and 25 assertions in `test_wopr_yml.py` have no fixture. | P1 | 2026-08-21 |
| `check_mcp_servers_for_malware`, `scan_skill_directory` | KEPT | Deterministic scanning against OSV data and a threat-pattern table. Not reproducible from model context. | P1 | 2026-08-21 |
| `check_routing_evals` | KEPT | The merge gate for every later slimming step. Scores routing fixtures; a regression blocks the cut. | P1 | 2026-08-21 |

## Support modules retired

| Artifact | Verdict | Evidence or rationale | Phase | Date |
| --- | --- | --- | --- | --- |
| `cli_setup.py` (84 KB), `init.py`, `install_manifest.py`, `uninstall.py` | CUT | The per-CLI symlink installer behind `wopr --init` / `add` / `remove` / `--uninstall`. Per-pack Claude Code plugins replace the whole mechanism. | P1 | 2026-08-21 |
| `resolver.py` and `loading_manifest.py` | CUT | The skill-loading-tier mechanism: classify each skill `always` / `resolver` / `dormant` and render a generated `wopr-skill-resolver` skill. Every symbol `resolver.py` imports comes from `loading_manifest.py`, and its only caller was `cli_setup`. Which pack you install is the tiering now, so porting it would have re-introduced the retired mechanism as dead code with no caller and no test. | P1 | 2026-08-21 |
| `fingerprint.py`, `hook_manifest.py` | CUT | Both served the installer. `hook_manifest.py` has a surviving consumer and is listed under Pending below. | P1 | 2026-08-21 |
| `doctor_readiness.py`, `doctor_recommendations.py` | CUT | Support modules for the retired recommend-and-dismiss engine. | P1 | 2026-08-21 |
| `is_safe_entry_name`, `_request_workspace`, `_all_available` | KEPT | Small functions that lived in dropped modules and had surviving callers. Inlined verbatim into `tools/_skill_usage.py` and `tools/skill_usage.py`. `_all_available` was a three-branch generic; only the `skills` branch was reachable, so it was inlined as `_installed_skill_names`. | P1 | 2026-08-21 |
| `llms.txt` and `tests/test_llms_txt.py` | CUT | `llms.txt` indexes a `docs/` tree, `CONTRIBUTING.md`, a `docker/` sandbox and four pack READMEs, of which exactly one exists here. Its test asserts both that every indexed path exists and that nothing outside the index is present, so it can only be restored honestly once this repo has its own docs tree. Regenerate, do not port. | P1 | 2026-08-21 |

## Catalog packs

| Artifact | Verdict | Evidence or rationale | Phase | Date |
| --- | --- | --- | --- | --- |
| `extras` pack (15 utility MCP tools) | CUT | Dice, weather, notes, and time tracking. The `_should_register_extras` gate in `create_app` went with it; every tool module now registers unconditionally. | P1 | 2026-08-21 |
| `legacy-migration` pack | CUT | Client-specific migration workflow. Its templates and its stub writer had no general audience. | P1 | 2026-08-21 |
| `java`, `vanilla-web`, `ios` packs | CUT | Stacks not in play for the current work. They stay in the quarry and can be re-quarried per pack. | P1 | 2026-08-21 |
| `accessibility`, `security` packs | CUT | Both were reference-heavy curricula rather than local deltas. Intended to return as checklists, which is a different artifact, not a slimmed version of these. | P1 | 2026-08-21 |
| `_core`, `crew`, `angular`, `python`, `auditors`, `meta-authoring` | KEPT | Ported verbatim in P1. Content slimming is P2 and is tracked in the rows below and in Pending. | P1 | 2026-08-21 |
| `catalog.yaml` profiles `java-team`, `legacy-migration-team` | CUT | Both named packs that no longer exist. The four surviving profiles reference only surviving packs. | P1 | 2026-08-21 |
| `catalog/crew/data/learnings-seed/spring-boot.md` | KEPT | The plan allowed dropping it with the `java` pack, but nothing in `catalog.yaml` or the tests binds a seed file to a pack, so the condition for dropping was not met. Seeds are selected by stack tag at call time. | P1 | 2026-08-21 |

## Test adjustments (P1)

| Artifact | Verdict | Evidence or rationale | Phase | Date |
| --- | --- | --- | --- | --- |
| `conftest.py` autouse `_never_install_into_the_real_home` | CUT | Guarded `cli_setup.setup_claude` / `setup_gemini` / `setup_copilot`. None exists here, so the fixture could only raise `AttributeError` at import. The `$WOPR_HOME` guard that protects the surviving tools is untouched. | P1 | 2026-08-21 |
| `test_server.py::TestShouldRegisterExtras` (4 cases) | COLLAPSED | Tested the retired `extras` registration gate. Replaced by `test_registers_exactly_the_expected_tool_set`, which pins all 23 surviving tool names. Net minus 4 plus 1. | P1 | 2026-08-21 |
| `test_skill_usage.py::TestRunSkillCounting` (4 cases) | COLLAPSED | All four drove the retired `run_skill` tool. One asserted a property worth keeping ("telemetry must never be able to fail its call site"), rewritten as `TestWriteFailureContainment` against `record_invocation` directly. Net minus 4 plus 1. | P1 | 2026-08-21 |
| `test_multi_workspace_tools.py` (3 cases to 1) | SLIMMED | Two cases drove `run_skill`, notes, projects and time tracking. The surviving case tests `resolve_project_path` containment and is unchanged. Cross-workspace isolation for surviving tools is still covered by `test_handoff_workspace.py` and `test_learnings*.py`. | P1 | 2026-08-21 |
| `test_wopr_yml.py` (3 cases), `test_pack_templates.py` (2 cases) | CUT | Covered `write_extracted_requirements_stub` and `legacy-migration` templates. The `crew` template cases, which are what the tool is for, are unchanged. | P1 | 2026-08-21 |

## P2a: stale references, help, commands

| Artifact | Verdict | Evidence or rationale | Phase | Date |
| --- | --- | --- | --- | --- |
| `import ai_cli_mcp` in 5 meta-authoring commands, `wopr-run-crew/SKILL.md`, `configure_hook.py`, `crew/README.md`, `hooks/README.md` | SLIMMED | Renamed to `wopr` / `src/wopr`. These were live breakages, not cosmetics: the shim resolves the installed resources directory and fails outright against the renamed package. P1-NOTES 6.1 counted "two meta-authoring commands"; the actual site count is five commands plus four documentation and script references. | P2a | 2026-08-21 |
| `src/wopr/help.py` (544 lines, 22,920 bytes) | SLIMMED | Rewritten to 315 lines, 12,345 bytes (46 percent smaller). Removed: `wopr --init` / `add` / `remove` / `--uninstall`, pipx install instructions pointing at a private client URL, the Gemini and Copilot install and usage sections, the skill-loading-tier explanation, the `extras` tool list, and per-item listings of skills and agents in packs that were never ported. Topics went from 8 (overview, install, packs, commands, skills, agents, mcp, cli) to 5 (overview, packs, tools, cli, learnings). Every command, tool and flag it now names was executed against this build. | P2a | 2026-08-21 |
| `help.py` shared-directory listing helpers (`_get_shared_dir`, `_list_resources`, `_list_skill_dirs`) | CUT | They enumerated `<workspace>/.ai-cli/shared/{commands,skills,agents}`, which only the retired installer populated. They could report nothing but empty. | P2a | 2026-08-21 |
| `get_workspace_info`: `~/.gemini/{skills,commands}` and `~/.copilot/{skills,agents}` counters | CUT | Correct code that could only ever return zero. A zero beside a real number reads as "installed but empty" rather than "not supported". Pinned by `TestGetWorkspaceInfo::test_reports_claude_as_the_only_global_target`. | P2a | 2026-08-21 |
| `get_workspace_info`: `time_tracking`, `notes`, `gemini_md`, `copilot_instructions_md` file flags | CUT | Reported on `time-tracking.json` and `notes.json`, whose tools are gone, and on instruction files for CLIs that are not supported. `LEARNINGS.md` was added: it is the one workspace file the surviving tool set reads and writes most. Pinned by `test_reports_only_files_a_surviving_tool_touches`. | P2a | 2026-08-21 |
| 12 `wopr-consider-*` commands (538 lines) | COLLAPSED | One argument-routed `/wopr-consider <framework>` at 109 lines (80 percent reduction). Each of the 12 files spent most of its length explaining what its framework is, which Claude 5 knows. What is local and worth keeping is the expected output structure, so each framework keeps one "fits when" line and its output contract. With no argument the command lists the frameworks and stops rather than guessing. | P2a | 2026-08-21 |
| `wopr-create-prompt.md` (468 lines), `wopr-run-prompt.md` (166 lines) | CUT | A hand-rolled meta-prompt pipeline: author a prompt file, then dispatch it to fresh sub-contexts sequentially or in parallel. The native Task tool does the dispatch and plan mode does the authoring, both with better isolation than a markdown protocol can specify. 634 lines. | P2a | 2026-08-21 |
| `wopr-configure-capture-skill-hook-copilot.md` (37 lines) and `capture-skill-trigger-hook-copilot.py` (290 lines) | CUT | Copilot-targeted. The handler's own documentation records that it was never verified against a live `agentStop` firing. 327 lines. | P2a | 2026-08-21 |
| `capture-skill-trigger.HOOK.yaml` `copilot:` target | CUT | The only Copilot target in any hook manifest. The other three manifests (`git-branch-guard`, `prompt-log`, `skill-usage`) already declared `claude` only, each with a recorded reason, so no manifest file needed deleting. | P2a | 2026-08-21 |
| `wopr-configure-capture-skill-hook.md`, `wopr-configure-git-guard.md`, `wopr-configure-prompt-log.md`, `wopr-configure-skill-usage-hook.md` | KEPT | All four write into `.claude/settings.json` for Claude Code. Four of the five configure commands were Claude-targeted; only the `-copilot` one was not. | P2a | 2026-08-21 |
| `hooks/README.md` (349 lines to 294) | SLIMMED | Removed the `capture-skill-trigger-hook-copilot.py` section, its table row, its configure-command bullet, its provenance paragraph, the `copilot:` block in the manifest example, and the paragraph explaining why the two capture-skill handlers stay unmerged. The Copilot and Gemini mentions that remain are honest coverage-boundary statements about what telemetry does not see. | P2a | 2026-08-21 |
| `conversion_manifest.py` `EXPLICIT_INVOCATION_ONLY_COMMANDS` | SLIMMED | Was derived by a `wopr-consider-` prefix comprehension over tier 1. After the collapse that prefix matches nothing, so the rule would have silently stopped marking anything. Now a literal set, pinned against the catalog by `test_explicit_invocation_only_commands_exist`. | P2a | 2026-08-21 |
| `TestManifestMatchesCatalog` (3 new cases) | KEPT | Added, not removed. The tier tables are hand-maintained and the catalog is the truth; both drift directions (a classified command with no file, a file in no tier) occurred during this consolidation and were caught by hand. Now they fail the suite. | P2a | 2026-08-21 |

## Command counts

| Pack | Before P2a | After P2a |
| --- | --- | --- |
| `_core` | 20 | 7 |
| `meta-authoring` | 11 | 10 |
| `auditors` | 4 | 4 |
| Total | 35 | 21 |

## Pending

Not yet cut. Each of these is gated on evidence that does not exist yet,
and none should land before its gate is in place.

- **`wopr-run-crew/SKILL.md` rewrite.** 473 lines. Gate: a golden crew
  run on a small deterministic REQ, recorded 2 to 3 times against the
  current text, then re-run after the rewrite. Pass means the same gate
  outcome, no new blocker class, and lower token counts. The current
  text is the baseline, so it must not be edited beforehand: the only
  P2a change to that file was the one-line `import wopr` fix.
- **CRAG pre-step change.** Run once per crew run instead of once per
  working-agent Task call, and skip the evaluator when the prefilter
  returns few enough entries. Same golden-run gate. The evaluator is a
  circuit breaker against self-bias, not a verification step, so it is
  threshold-gated rather than deleted.
- **References pruning.** Roughly 50k catalog lines targeted at well
  under 10k. Gate: per-skill `routing-eval.jsonl` fixtures including
  negatives, scored by `check_routing_evals`.
- **Per-skill content slimming.** Same gate as references pruning, per
  surviving skill.
- **`hook_manifest.py`.** Retired in P1 as installer machinery, but
  `catalog/meta-authoring/scripts/configure_hook.py` imports it and two
  surviving configure commands shell out to that script. Those two
  commands are non-functional until the module is ported or the script
  is rewritten. Both the script docstring and `hooks/README.md` state
  this, and each hook's manual-fallback JSON still works. Quarry source:
  `ai_cli_mcp/hook_manifest.py`, 456 lines, depending only on
  `_atomic_write` and PyYAML.
- **Placeholder markers.** Roughly 20 `[TICKET-ID]`,
  `[client-project-cac]`, `[client-project-b]` and `[colleague]` markers
  remain in comments, docstrings and `hooks/README.md`, inherited from
  the quarry's own privacy scrub. They leak nothing.
- **`converters.py` Gemini and Copilot paths.** Retained with their
  tests. No shipped command path uses them. They stay until the
  `build-plugins` generator exists and proves the catalog layout no
  longer needs to be converter-friendly.
- **`catalog/_core/skills/wopr-doctor/`.** The skill describes the
  retired doctor tools. Belongs to the per-skill content pass.
- **Stale `run_skill` mentions in `hooks/README.md`.** The
  skill-usage-hook section still explains the blind spot in terms of
  `run_skill`, which no longer exists. The blind spot is real and the
  explanation is now wrong. Belongs to the references pass.
