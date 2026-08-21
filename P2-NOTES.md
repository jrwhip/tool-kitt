# P2a notes

The mechanical batch of P2: fix references P1 knowingly left broken,
rewrite `help.py` to describe the surface that exists, consolidate
commands, and open `docs/slimming-ledger.md`.

Same discipline as P1-NOTES. Every judgment call is recorded, including
the ones that went against the brief and the two places where a P1
figure did not hold up.

Not touched, deliberately: `wopr-run-crew/SKILL.md` beyond one import
line (its current text is the golden-run baseline), any
`routing-eval.jsonl` (owned by a parallel workstream), and P1-NOTES.md
(historical record).

## 1. Headline numbers

| Thing | Before P2a | After P2a |
| --- | --- | --- |
| `_core` commands | 20 | 7 |
| `meta-authoring` commands | 11 | 10 |
| `auditors` commands | 4 | 4 |
| Catalog commands, total | 35 | 21 |
| `help.py` | 544 lines / 22,920 bytes | 315 lines / 12,345 bytes |
| `help.py` topics | 8 | 5 |
| Registered MCP tools | 23 | 23 |
| Test run | 548 passed, 1 skipped | 554 passed, 1 skipped |

Files changed: 34 (16 deleted, 3 added, 15 modified), 1,067 insertions
against 2,057 deletions.

`uv run ruff check src tests` and `uv run mypy src/wopr` clean.

## 2. Two P1 figures that did not survive checking

### 2.1 The tool count is 67 to 23, not 68 to 23

P1-NOTES section 1 reports 68 registered MCP tools in the quarry, which
makes the retirement figure 45. Writing the ledger required enumerating
the retired tools by name, so every `mcp.tool()(...)` call and every
`@mcp.tool()` decorated function in the quarry was extracted:

```
67 unique names across 23 modules
```

All 23 tools kept here appear in that 67, so the retirement is **44**,
not 45. The one hit that looks like a 68th is
`tools/dev.py:218`, which is the string `"""@mcp.tool()` inside the code
template that `create_mcp_tool` writes out. It is a literal in a
generated-source template, not a registration.

`docs/slimming-ledger.md` uses 67 / 23 / 44 and states the discrepancy
in a section of its own rather than quietly picking a number. P1-NOTES
is left alone: it is the record of what P1 believed.

### 2.2 The `ai_cli_mcp` site count was five commands, not two

P1-NOTES section 6.1 records the stale shims as "two `meta-authoring`
commands, one line in `wopr-run-crew/SKILL.md`" plus the `crew/README.md`
path. A repo-wide grep finds:

| File | Sites |
| --- | --- |
| `commands/wopr-configure-capture-skill-hook.md` | 4 |
| `commands/wopr-configure-capture-skill-hook-copilot.md` | 4 (file deleted) |
| `commands/wopr-configure-git-guard.md` | 4 |
| `commands/wopr-configure-prompt-log.md` | 4 |
| `commands/wopr-configure-skill-usage-hook.md` | 4 |
| `scripts/configure_hook.py` | 2 (one is a live import) |
| `hooks/README.md` | 4 |
| `crew/README.md` | 1 |
| `crew/skills/wopr-run-crew/SKILL.md` | 1 |

All fixed. The shim in the commands is
`python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')"`,
which is the same expression with the package renamed. The prose
"so the `ai_cli_mcp` package is importable" became "so the `wopr`
package is importable".

## 3. `hook_manifest.py`: a kept command with a dead dependency

`catalog/meta-authoring/scripts/configure_hook.py` imports
`ai_cli_mcp.hook_manifest`. P1 did not port `hook_manifest.py` (section
5.1: it was classified as installer machinery). Renaming the import to
`wopr.hook_manifest` therefore points at a module that does not exist,
and `/wopr-configure-capture-skill-hook` and
`/wopr-configure-skill-usage-hook` (both kept under task 4c, both
Claude-targeted) shell out to that script.

Three options were considered:

1. Rename the import and say nothing. Rejected: ships a command that
   raises `ModuleNotFoundError` with no warning anywhere.
2. Port `hook_manifest.py` from the quarry (456 lines; imports only
   `_atomic_write` and PyYAML, so the port is mechanical). Rejected as
   out of scope: it reverses a deliberate P1 decision, it was not in
   this batch's task list, and its tests were not ported either.
3. Rename the import and flag the gap loudly in all three places a
   reader could hit it.

Option 3 was taken. The gap is now stated in:

- `configure_hook.py`'s module docstring, as a `KNOWN GAP (P2)` block
  naming the quarry source and line count.
- `hooks/README.md`, in the manifest section, with a pointer to each
  hook's manual-fallback JSON, which still works.
- `docs/slimming-ledger.md`, under Pending.

The decision to port or rewrite belongs to whoever owns the next batch.
Both the two other configure commands (`git-guard`, `prompt-log`) use
bespoke scripts with no such dependency and are unaffected.

## 4. `help.py`: what was removed and why

The old file was written for a three-CLI product with a symlink
installer. Every section describing that product was wrong here, and
`wopr help install` in particular printed a `pipx install` line pointing
at a private client repository URL.

Topics went from 8 to 5:

| Old topic | Disposition |
| --- | --- |
| `overview` | Rewritten. Now leads with what WOPR does NOT do, because the surface an agent is most likely to guess wrong is the one that was removed. |
| `install` | Deleted outright. There is no installer, and the URL it printed was stale and private. |
| `packs` | Kept, reads `catalog.yaml` as before. The "MANAGING PACKS" block (`--init`, `add`, `remove`) is gone; a LAYOUT block naming the on-disk paths replaced it. |
| `commands` | Deleted. It listed commands by hand, half of which no longer exist, and it duplicated a directory listing. |
| `skills` | Deleted. Same problem, plus it documented the loading-tier system that was never ported. |
| `agents` | Deleted. Same problem. |
| `mcp` | Rewritten as `tools`. |
| `cli` | Rewritten. |
| (new) `learnings` | Added. The learnings system is the thing an agent most needs a local explanation of, and it had no topic of its own. |

Specific removals:

- `wopr --init`, `--init --packs`, `--init --profile`, `wopr add`,
  `wopr remove`, `wopr --uninstall` and its `--force` / `--global`
  variants. None exists.
- The pipx install and upgrade instructions, including the private URL.
- The Gemini CLI and Copilot CLI sections of `overview`, `install`,
  `commands`, `skills`, `agents` and `cli`.
- `~/.wopr/install-manifest.json`, written by the retired installer.
- The `wopr-loading:` tier table (`always` / `resolver` / `dormant`) and
  the generated `wopr-skill-resolver` skill.
- The `extras` tool block (dice, weather, notes, time tracking) and the
  `resources.py` shim block (`list/get_shared_*`, `run_skill`,
  `invoke_agent`) from the tools topic.
- Named skills and agents from packs that never crossed over
  (`wopr-build-spring-boot-apps`, `wopr-java-perfectionist-reviewer`,
  the `.NET` plugin pointer, `wopr-*-architect` for `ios` and `java`).
- `_get_shared_dir`, `_list_resources`, `_list_skill_dirs`. They
  enumerated `<workspace>/.ai-cli/shared/`, which only the retired
  installer populated, so their output was always empty.

Kept: `_get_installed_packs`. It reads the `.ai-cli` lock file, which
`manager.cmd_list` and `get_workspace_info` both still read.

Two accuracy corrections made during a read-back of the generated text:

- The `tools` topic first said `get_workspace_info` reports "catalog
  counts". It reports local and global resource counts. Fixed.
- The `learnings` topic first described the CRAG pre-step as running
  once per crew run with a threshold-gated evaluator. That is the
  planned P2 change, not current behavior. `<crag_pre_step>` in
  `wopr-run-crew/SKILL.md` runs before **each** working-agent Task call
  and short-circuits only on an empty candidate set. Rewritten to match
  the file.

Every command, flag and tool name the new file prints was executed or
grepped against this build. `wopr skill-usage unpin` and
`wopr skill-usage record` were confirmed in `skill_usage_cli.py` before
being documented.

Note on the brief: it asked for "serve/list/catalog/skill-usage". There
is no `serve` subcommand. `wopr` with no subcommand runs the MCP server
on stdio, and there is a fourth subcommand, `help`. The `cli` topic
documents what `argparse` actually accepts.

## 5. `get_workspace_info`

Removed the `~/.gemini/{skills,commands}` and `~/.copilot/{skills,agents}`
counters and the `time_tracking` / `notes` / `gemini_md` /
`copilot_instructions_md` file flags. Added a `learnings` flag for
`<workspace>/LEARNINGS.md`, which is the workspace file the surviving
tool set touches most and which was not reported at all.

The counters were correct code producing an honest zero. The problem is
what a zero communicates: beside a real Claude number it reads as
"installed but empty" rather than "not a thing here". `resources_note`
was rewritten for the same reason. It previously told the reader that
resources live globally per CLI; it now says both counters can be zero
on a healthy install because catalog content is moving to plugins.

`_count_in_dir` and `_count_skills_in` are unchanged and still used.

### Test additions

`test_server.py` had no coverage of `get_workspace_info` at all, so
there was nothing to update. Three cases were added under
`TestGetWorkspaceInfo`, pinning the slimming the same way
`EXPECTED_TOOLS` pins the tool set:

- `test_reports_claude_as_the_only_global_target` asserts the global
  block has exactly one key, `claude`, with exactly `skills`, `agents`,
  `commands` under it.
- `test_reports_only_files_a_surviving_tool_touches` asserts the exact
  six file flags.
- `test_still_reports_workspace_and_local_counters` asserts the fields
  that must NOT have regressed: workspace path, `workspace_source`,
  `cli_type`, the four local counters, and that the `learnings` flag
  actually flips when the file exists.

The third case exists because the first two are removal assertions, and
a removal assertion passes just as happily if the whole payload
collapses.

## 6. `/wopr-consider`: 12 files to 1

538 lines to 109 (80 percent). Read all 12 first; the shape was
consistent (`description` + `argument-hint` frontmatter, then
`<objective>` / `<process>` / `<output_format>` / `<success_criteria>`).

What each old file spent its length on:

- Explaining the framework (what 5 Whys is, what SWOT stands for). Cut
  entirely. This is training data.
- A `<process>` block restating the framework as numbered steps. Cut.
  Same content in imperative mood.
- An `<output_format>` block. **Kept**, distilled to one paragraph per
  framework. This is the only genuinely local content in the files: it
  is the output contract, and it is what makes twelve runs comparable.
- A `<success_criteria>` block. Mostly restatement, but the parts that
  were real constraints ("must fit ALL facts" for Occam, "compare to
  best alternative, not just any alternative" for opportunity cost,
  "stops when hitting actionable root, not infinite regress" for 5 Whys)
  were folded into the per-framework line.

Added per framework, which the old files did not have: a one-line "fits
when". Twelve files each described a framework in isolation; a router
needs to tell them apart. The no-argument path prints exactly those
lines, so the command is self-indexing.

Added a `<rules>` block, four lines, that did not exist in any old file:
use only the requested framework, apply it to real specifics, follow the
output structure, and state the framework's conclusion even when it is
inconvenient. The last one is the failure mode that makes a decision
framework worthless.

Frontmatter: `description` and `argument-hint` only, matching the 12
originals. Checked against the converters first. `parse_claude` reads
any YAML; `to_copilot_skill` uses `description` (required, non-empty)
and carries `argument-hint` when present and drops `allowed-tools`;
`to_gemini_command` uses `description` and ignores the rest. No
converter needs a field the new file lacks. `argument-hint` changed from
`[topic or leave blank for current context]` to
`[framework] [optional subject]` because the first argument now routes.

Aliases are declared per framework so `/wopr-consider 5why`,
`/wopr-consider razor` and `/wopr-consider 80-20` all land. Unmatched
first words print the list rather than guessing, which matters more now
that one wrong word selects a different framework instead of failing to
find a file.

## 7. `wopr-create-prompt` and `wopr-run-prompt`

Deleted, 634 lines. `wopr-create-prompt.md` alone was 468 lines, the
largest command in the catalog by a factor of three. Together they are a
markdown protocol for authoring a prompt file and then dispatching it to
fresh sub-contexts, sequentially or in parallel, with hand-specified
isolation semantics. The Task tool does the dispatch with real isolation
and plan mode does the authoring.

`wopr-create-meta-prompts` (the `_core` skill) and
`/wopr-create-meta-prompt` (the `meta-authoring` wrapper) were NOT
touched. They are a different artifact: staged research-plan-implement
prompt generation, not a dispatcher. Whether they survive is a per-skill
content-pass question with a routing-eval gate on it.

## 8. Which configure commands survived, and why

Five `wopr-configure-*` commands existed. Inspected all five for their
target, meaning the file the command writes into, not the CLI it can be
typed from.

| Command | Writes into | Verdict |
| --- | --- | --- |
| `wopr-configure-capture-skill-hook` | `.claude/settings.json` | KEPT |
| `wopr-configure-git-guard` | `.claude/settings.json` | KEPT |
| `wopr-configure-prompt-log` | `.claude/settings.json` | KEPT |
| `wopr-configure-skill-usage-hook` | `.claude/settings.json` | KEPT |
| `wopr-configure-capture-skill-hook-copilot` | `.github/hooks/hooks.json` | CUT |

Only one had a non-Claude target. Note that `conversion_manifest.py`
classified the Copilot one as **tier 2** and the four Claude ones as
**tier 3**, which is correct on its own terms (tier is about whether a
command's body converts for another CLI, not about what it configures)
and is exactly backwards from what this batch needed. The tier table was
not the right selector; the target was.

Its tier-2 entry and its three-sentence justification comment were
removed from the manifest along with the file.

### Hook manifests

The brief expected Copilot or Gemini-targeted `*.HOOK.yaml` files to
delete. There are none. All four manifests declare a `claude` target;
`capture-skill-trigger.HOOK.yaml` additionally declared a `copilot`
target pointing at a second handler.

| Manifest | Targets before | Targets after |
| --- | --- | --- |
| `capture-skill-trigger.HOOK.yaml` | claude, copilot | claude |
| `git-branch-guard.HOOK.yaml` | claude | claude |
| `prompt-log.HOOK.yaml` | claude | claude |
| `skill-usage.HOOK.yaml` | claude | claude |

So: no manifest deleted, one `copilot:` target block removed, and
`capture-skill-trigger-hook-copilot.py` (290 lines) deleted with it.

The other three were already Claude-only *on purpose*, each with its
reasoning in a header comment, and those comments are worth preserving
verbatim because they are the same argument this whole phase runs on:
`git-branch-guard` declares no Copilot target because "a guard that
fails OPEN is worse than no guard" and the schema was never verified
live; `skill-usage` because "a telemetry hook that silently counts zero
is worse than a documented gap, because the resulting report still looks
authoritative". The deleted Copilot handler documented itself as "Not
verified against live behavior", which is the same standard applied to
the artifact that failed it.

The `capture-skill-trigger.HOOK.yaml` header comment was rewritten to
record the removal and why (Copilot's transcript shape and the
`agentStop` schema difference), rather than deleting the explanation
along with the target.

### `hooks/README.md`

349 lines to 294. Removed: the `capture-skill-trigger-hook-copilot.py`
section, its table row, its configure-command bullet, its provenance
paragraph, the `copilot:` block in the manifest example, and the
paragraph explaining why the two capture-skill handlers stay unmerged
(there is one now). The scope paragraph was rewritten from "mostly
Claude, with one hook now also ported to Copilot" to Claude only, and it
keeps the operational fact that a hook port is a second program rather
than a config change.

Copilot and Gemini are still named twice, in the skill-usage coverage
boundary and in the note explaining why `skill-usage.HOOK.yaml` declares
no Copilot target. Both are statements about what the telemetry does not
see. Deleting them would make the report look more authoritative than it
is, which is the specific failure those paragraphs exist to prevent.

## 9. `catalog.yaml` and the conversion manifest

`catalog.yaml` needed no change. It declares packs, profiles and
descriptions; it does not enumerate commands, and no pack was added or
removed in this batch. Verified by reading it in full.

`conversion_manifest.py` needed four:

1. Tier 1: the 12 `wopr-consider-*` entries replaced by `wopr-consider`;
   `wopr-run-prompt` removed.
2. Tier 2: `wopr-create-prompt` and
   `wopr-configure-capture-skill-hook-copilot` removed. Tier 2 is now a
   single entry, `wopr-check-todos`.
3. `EXPLICIT_INVOCATION_ONLY_COMMANDS` was a comprehension over tier 1
   filtering on `name.startswith("wopr-consider-")`. After the collapse
   that prefix matches nothing, and the failure is silent: the set would
   have quietly dropped to `{wopr-realign}` plus the wrappers, and
   `/wopr-consider` would have become model-auto-selectable, which is
   the exact behavior the comment says must not happen. Replaced with a
   literal `{"wopr-consider", "wopr-realign"}` and a comment saying why
   it is literal.
4. The `EXPLICIT_INVOCATION_ONLY_COMMANDS` comment block was updated
   from "the 12 wopr-consider-* mental models" to the single command.

After the changes the three tiers hold 11 + 1 + 9 = 21 names, matching
the 21 command files on disk exactly.

## 10. Test adjustments

No assertion was weakened. Two changed, five were added.

1. **`test_converters.py::test_consider_command_gets_disable_model_invocation`**:
   the fixture name `"wopr-consider-pareto"` became `"wopr-consider"`.
   The assertion (`disable-model-invocation is True`) is unchanged. The
   old name would still have passed against a *stale* manifest and
   started failing against the corrected one, which is the correct
   direction: it caught item 3 in section 9.

2. **`test_conversion_manifest.py`**: added `TestManifestMatchesCatalog`
   with three cases and a `_catalog_command_names()` helper.
   `test_catalog_has_no_command_skill_name_collisions` was refactored to
   use the shared `CATALOG_DIR` constant; its assertion is unchanged.

   - `test_every_catalog_command_is_classified`: a file in no tier
     silently defaults to tier 3 and is skipped forever with no recorded
     reason.
   - `test_every_classified_command_exists_in_the_catalog`: a name left
     in a tier after its file is deleted makes
     `get_convertible_commands()` advertise a file that is not there.
   - `test_explicit_invocation_only_commands_exist`: pins the literal
     set against the catalog and against the two names by hand.

   Both drift directions actually occurred during this consolidation and
   were caught by reading, not by the suite. Now they fail the suite.

3. **`test_server.py`**: added `TestGetWorkspaceInfo` (3 cases, see
   section 5). `EXPECTED_TOOLS` is unchanged: this batch registered and
   retired no tools, and the list still reads 23.

`tests/test_catalog_frontmatter.py` needed no change. It sweeps
`catalog/**/SKILL.md`, not commands, and no skill was touched.

`tests/test_template_placeholders.py` needed no change. Its `_PACKS`
scope is `("crew",)` and it sweeps templates, not commands.

Net: 548 passed / 1 skipped, to 554 passed / 1 skipped. Plus 6, all
additions. The one skip is unchanged and pre-existing
(`test_embeddings.py` skips at import when `numpy` is absent, the
documented behavior of the optional `[embeddings]` extra).

## 11. `docs/slimming-ledger.md`

New file, and the first thing in `docs/`. Covers the 44 retired tools by
quarry module, the support modules, the 7 non-ported packs, the
resolver and loading-tier non-port, the P1 test adjustments, and every
item in this batch. Four verdicts: CUT, COLLAPSED, SLIMMED, KEPT. KEPT
rows are there on purpose: a ledger that only records deletions cannot
be checked, because a reader has no way to tell "considered and kept"
from "never looked at".

It ends with a Pending section listing what remains eval-gated (crew
`SKILL.md` rewrite, CRAG pre-step change, references pruning, per-skill
slimming) plus four items this batch found and did not fix:
`hook_manifest.py`, the leftover privacy placeholders, the unused
`converters.py` Gemini and Copilot paths, and two pieces of stale prose
(`wopr-doctor`'s skill text and the `run_skill` explanation in
`hooks/README.md`).

No marketing language, no em dashes, and every number in it is
reproducible from the repository or the quarry.

## 12. Verification performed

- `uv run pytest` -> 554 passed, 1 skipped.
- `uv run ruff check src tests` -> clean.
- `uv run mypy src/wopr` -> clean, 41 source files.
- `uv run wopr --help` -> lists the four real subcommands.
- `uv run wopr help` and all five topics printed and read back line by
  line against the code. Two errors found and fixed that way (section 4).
- `uv run python -c "from wopr.server import create_app; create_app()"`
  -> imports and builds.
- Repo-wide `grep -rn "ai_cli_mcp"` -> no live references remain. The
  four surviving hits are `P1-NOTES.md` (historical record, out of scope
  by instruction), this file, and two citations of the quarry path
  `ai_cli_mcp/hook_manifest.py` (in `configure_hook.py`'s gap note and
  in the ledger's Pending section), which name a file in the read-only
  quarry on purpose.
- Repo-wide grep for every deleted command name -> no dangling
  references outside comments that name them as deleted.
- No `git push`, no remote added, no write of any kind to
  `/home/jrwhip/Work/AI/WOPR/webteam-ai-tools`.
