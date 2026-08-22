# WOPR footprint audit

Measured 2026-08-21. All token counts produced with `tiktoken` `o200k_base` (see "Method and its limits" at the end). Every number below names the command or file it came from.

Three artifacts are in play and they are three different things:

| Artifact | Path | Version | Where the version came from |
|---|---|---|---|
| Installed binary (live) | `/home/jrwhip/.local/share/uv/tools/wopr/bin/wopr` via `/home/jrwhip/.local/bin/wopr` | `wopr 0.2.0` | `wopr --version`; `.../site-packages/wopr-0.2.0.dist-info/METADATA` |
| Old repo ("before") | `/home/jrwhip/Work/AI/WOPR/webteam-ai-tools` | `0.24.4` | `src/ai_cli_mcp/__init__.py:__version__` |
| New repo ("after") | `/home/jrwhip/Work/AI/WOPR/wopr` | `1.0.0.dev0` | `src/wopr/__init__.py:8` |

A fourth copy exists: `/home/jrwhip/Work/AI/webteam-ai-tools` at `0.24.3` (`src/ai_cli_mcp/__init__.py:__version__`). It is not code that runs; it is the directory the live server is pointed at as its workspace.

---

## 1. Which wopr MCP server is actually wired in right now

**It is the stale installed binary, not either checkout.**

The only `wopr` MCP registration is at the user level in `~/.claude.json` under the top-level `mcpServers` key. Exact entry, from `python3 -c "import json; print(json.dumps(json.load(open('/home/jrwhip/.claude.json'))['mcpServers'], indent=2))"`:

```json
"wopr": {
  "command": "wopr",
  "args": [],
  "env": {
    "WOPR_WORKSPACE": "/home/jrwhip/Work/AI/webteam-ai-tools",
    "AI_CLI_TYPE": "claude"
  }
}
```

Resolution of `command: "wopr"`, from `readlink -f $(which wopr)`:

```
/home/jrwhip/.local/bin/wopr  ->  /home/jrwhip/.local/share/uv/tools/wopr/bin/wopr
```

Shebang line of that script (`head -5`) is `#!/home/jrwhip/.local/share/uv/tools/wopr/bin/python`, and its body is `from ai_cli_mcp.cli import main`. `ai_cli_mcp` is the **old** package name. The new repo's package is `wopr` (`pyproject.toml` `[project.scripts] wopr = "wopr.cli:main"`).

Places checked and found to contain no competing `wopr` MCP entry:

| File | Result |
|---|---|
| `~/.claude/settings.json` | no `mcpServers` key at all; does declare `extraKnownMarketplaces.wopr-marketplace -> /home/jrwhip/Work/AI/WOPR/wopr-plugins` |
| `~/.claude/settings.local.json` | file does not exist |
| `~/.claude.json` `projects.*.mcpServers` | only `/home/jrwhip/Work/AI/sites` has one, and it is `stripe` |
| `/home/jrwhip/Work/AI/WOPR/.claude/settings.local.json` | `enabledPlugins: { "wopr-python@wopr-marketplace": true }` only; no MCP entry |
| `/home/jrwhip/Work/AI/.claude/settings.local.json`, `/home/jrwhip/Work/AI/webteam-ai-tools/.claude/settings.local.json` | no `wopr` MCP entry |
| `/home/jrwhip/Work/AI/WOPR/wopr-plugins/wopr-core/.mcp.json` | declares `wopr -> ${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap-serve.sh`, but `wopr-core` is not in any active `enabledPlugins`, so it is not loaded |

**Tool count of the live server: 25.** Obtained by launching the exact configured command over stdio and issuing `tools/list`:

```
/home/jrwhip/Work/AI/WOPR/wopr/.venv/bin/python /tmp/wopr-audit/dump_tools.py \
  /home/jrwhip/.local/bin/wopr '[]' \
  '{"WOPR_WORKSPACE":"/home/jrwhip/Work/AI/webteam-ai-tools","AI_CLI_TYPE":"claude"}' \
  /tmp/wopr-audit/old_live_tools.json
# -> 25 tools
```

The 25 names returned are exactly the 25 `mcp__wopr__*` tools present in the live session tool list: `add_todo, check_build, complete_todo, create_handoff, create_mcp_tool, get_handoff, get_help, get_project_context, get_shared_agent, get_shared_command, get_shared_context, get_shared_skill, get_workspace_info, git_diff, git_log, git_status, invoke_agent, list_projects, list_shared_agents, list_shared_commands, list_shared_context, list_shared_skills, list_todos, run_npm_script, run_skill`.

That surface matches neither the new repo (23 tools, different names) nor the v0.24.4 old repo (67 tools). It is the `0.2.0` build.

---

## 2. Tool-definition token cost

Method: launch each server over stdio, `tools/list`, then for each tool sum `tokens(name) + tokens(description) + tokens(json.dumps(inputSchema, separators=(",",":"), sort_keys=True))`.

Commands used:

```
# new (repo checkout, 1.0.0.dev0)
python dump_tools.py /home/jrwhip/Work/AI/WOPR/wopr/.venv/bin/wopr '[]' \
  '{"WOPR_WORKSPACE":"/home/jrwhip/Work/AI/WOPR/wopr"}' new_tools.json          # 23 tools

# old repo (0.24.4), run with PYTHONPATH=/home/jrwhip/Work/AI/WOPR/webteam-ai-tools/src
python dump_tools.py /tmp/wopr-audit/run_old.sh '[]' \
  '{"WOPR_WORKSPACE":"/home/jrwhip/Work/AI/WOPR/webteam-ai-tools","AI_CLI_TYPE":"claude"}' old_repo_tools.json   # 67 tools

# live installed (0.2.0)  -> old_live_tools.json                                # 25 tools

uv run --with tiktoken python count_tools.py new_tools.json old_live_tools.json old_repo_tools.json
```

### Totals

| Server | Tools | Name tokens | Description tokens | Schema tokens | Total |
|---|---:|---:|---:|---:|---:|
| NEW repo `wopr 1.0.0.dev0` | 23 | 84 | 4,642 | 1,243 | **5,969** |
| OLD repo `wopr 0.24.4` | 67 | 221 | 7,876 | 3,398 | **11,495** |
| LIVE installed `wopr 0.2.0` | 25 | 70 | 1,010 | 833 | **1,913** |

### Deltas

| Comparison | Tool delta | Token delta | Percent |
|---|---:|---:|---:|
| NEW vs OLD repo (0.24.4) | -44 (-65.7%) | **-5,526** | -48.1% |
| NEW vs LIVE installed (0.2.0) | -2 (-8.0%) | **+4,056** | +212.0% |

Two things the table says plainly:

- Against the stated "before" (0.24.4), cutting 67 tools to 23 cut tool-definition tokens roughly in half, not by two thirds. Descriptions did not shrink proportionally with tool count: mean tokens per tool went from 171.6 (11,495 / 67) to 259.5 (5,969 / 23).
- Against what is actually running in Jerry's sessions today (0.2.0), the new server is 3.1x more expensive in tool-definition tokens. The 0.2.0 tools have terse one-line descriptions (mean 40.4 description tokens per tool) versus the new server's 201.8.

### Prefix overhead

Claude Code presents MCP tools as `mcp__<server>__<name>`. Cost of the `mcp__wopr__` prefix, summed across the tool list:

| Server | Plain names | Prefixed names | Added |
|---|---:|---:|---:|
| NEW (23) | 84 | 222 | +138 |
| LIVE 0.2.0 (25) | 70 | 220 | +150 |
| OLD repo (67) | 221 | 623 | +402 |

So the honest in-context totals are 6,107 (new), 2,063 (live 0.2.0), 11,897 (old 0.24.4).

### Top ten by cost, NEW server

Source: `count_tools.py new_tools.json`.

| Tool | name | desc | schema | total |
|---|---:|---:|---:|---:|
| `learnings_search` | 3 | 441 | 128 | 572 |
| `append_learnings` | 3 | 414 | 65 | 482 |
| `check_mcp_servers_for_malware` | 8 | 344 | 53 | 405 |
| `write_wopr_yml` | 5 | 304 | 66 | 375 |
| `curate_learnings` | 4 | 294 | 70 | 368 |
| `skill_usage_report` | 3 | 281 | 71 | 355 |
| `seed_learnings` | 3 | 267 | 59 | 329 |
| `check_routing_evals` | 5 | 231 | 31 | 267 |
| `create_handoff` | 3 | 171 | 91 | 265 |
| `list_pack_templates` | 3 | 215 | 30 | 248 |

The five learnings-related tools alone (`learnings_search`, `append_learnings`, `curate_learnings`, `seed_learnings`, `learnings_path`) are 1,853 tokens, 31.0% of the new server's 5,969.

### What the 44 removed tools were

From `old_repo_tools.json` minus `new_tools.json`. The largest removed blocks: an "extras" pack the old server registered when present in the workspace (`get_weather`, `get_forecast`, `roll_dice`, `flip_coin`, `random_number`, `random_choice`, `add_note`, `list_notes`, `search_notes`, `delete_note`, `start_timer`, `stop_timer`, `log_time`, `list_time_entries`, `time_summary`), the shared-catalog accessors (`list_shared_*` / `get_shared_*`, 8 tools), the wopr-recommendation set (`recommend_wopr_setup`, `dismiss_wopr_recommendation`, `reset_wopr_recommendation_dismissals`, `list_dismissed_wopr_recommendations`), git/project/todo/npm passthroughs, and `write_agent_instructions` (555 tokens, the second most expensive tool in the old server). Log line from the old-repo run: `[wopr] INFO: Extras pack tools registered`. The live 0.2.0 run instead logged `[wopr] INFO: Extras pack not installed, skipping utility tools`.

---

## 3. Eager context footprint of the generated plugins

`/home/jrwhip/Work/AI/WOPR/wopr-plugins`, generated by `wopr build-plugins`.

Three tiers are measured:

- **T1 eager**: what a session pays before anything is invoked. One listing line per skill / command / agent, built as `- {name}: {description}` from YAML frontmatter (`description:` for commands, `name:` + `description:` for skills and agents; command name falls back to file stem).
- **T2 on-trigger**: the whole `SKILL.md` for a skill that fires, plus the whole `.md` for a command that is run or an agent that is spawned.
- **T3 deep**: T2 plus every other file inside each skill directory (`references/`, `templates/`, `workflows/`).

Command: `uv run --with tiktoken python /tmp/wopr-audit/count_catalog.py /tmp/wopr-audit/spec.json /tmp/wopr-audit/catalog_counts.json`.

### Per plugin

| Plugin | Skills | Commands | Agents | T1 eager | T1 skills | T1 cmds | T1 agents | T2 | T3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `wopr-core` | 14 | 11 | 5 | **1,330** | 994 | 245 | 91 | 42,198 | 205,901 |
| `wopr-crew` | 1 | 0 | 5 | **454** | 80 | 0 | 374 | 8,442 | 8,442 |
| `wopr-auditors` | 0 | 4 | 3 | **256** | 0 | 103 | 153 | 8,190 | 8,190 |
| `wopr-meta` | 1 | 6 | 0 | **211** | 84 | 127 | 0 | 2,951 | 3,318 |
| `wopr-angular` | 2 | 0 | 2 | **200** | 117 | 0 | 83 | 6,800 | 42,483 |
| `wopr-python` | 1 | 0 | 2 | **144** | 58 | 0 | 86 | 5,517 | 18,122 |
| **All six** | **19** | **21** | **17** | **2,595** | 1,333 | 475 | 787 | **74,098** | **286,456** |

Plus 155 tokens of plugin descriptions in `/home/jrwhip/Work/AI/WOPR/wopr-plugins/.claude-plugin/marketplace.json` (per plugin: core 16, angular 14, auditors 15, crew 60, meta 26, python 24). `wopr-crew`'s marketplace description is 60 tokens because it carries a full paragraph.

Eager is **0.91%** of the deep tier (2,595 / 286,456) and **3.50%** of the on-trigger tier.

### wopr-core skills, eager versus body versus deep

Source: `catalog_counts.json`, `plugin:wopr-core`.

| Skill | T1 eager | SKILL.md | deep (all files) | files |
|---|---:|---:|---:|---:|
| `wopr-create-plans` | 62 | 4,674 | 58,305 | 32 |
| `wopr-create-agent-skills` | 48 | 1,899 | 38,944 | 25 |
| `wopr-create-subagents` | 50 | 2,822 | 26,663 | 8 |
| `wopr-create-meta-prompts` | 51 | 4,653 | 20,157 | 11 |
| `wopr-create-hooks` | 43 | 2,517 | 17,364 | 7 |
| `wopr-debug-like-expert` | 47 | 2,654 | 14,932 | 6 |
| `wopr-create-slash-commands` | 36 | 4,009 | 10,566 | 4 |
| `wopr-init-project` | 161 | 2,347 | 2,347 | 1 |
| `wopr-doctor` | 83 | 2,070 | 2,070 | 1 |
| `wopr-create-yml` | 96 | 1,878 | 1,878 | 1 |
| `wopr-create-agent-instructions` | 107 | 1,360 | 1,360 | 1 |
| `wopr-whats-next` | 88 | 1,287 | 1,287 | 1 |
| `wopr-draft-req` | 60 | 698 | 698 | 1 |
| `wopr-wargame` | 62 | 665 | 665 | 1 |
| **Total** | **994** | **33,533** | **197,236** | **100** |

Eager per skill ranges 36 to 161 tokens; median 61. The seven skills with `references/` directories account for 186,931 of the 197,236 deep tokens (94.8%) while contributing 337 eager tokens (33.9% of the skill eager tier).

### wopr-core commands and agents, eager

| Command | eager | full |
|---|---:|---:|
| `wopr-configure-git-guard` | 30 | 535 |
| `wopr-configure-capture-skill-hook` | 28 | 565 |
| `wopr-configure-skill-usage-hook` | 28 | 618 |
| `wopr-create-plan` | 25 | 69 |
| `wopr-configure-prompt-log` | 24 | 372 |
| `wopr-add-to-todos` | 21 | 707 |
| `wopr-realign` | 21 | 710 |
| `wopr-consider` | 18 | 1,369 |
| `wopr-run-plan` | 18 | 1,056 |
| `wopr-check-todos` | 17 | 653 |
| `wopr-debug` | 15 | 139 |
| **Total** | **245** | **6,793** |

| Agent | eager | full |
|---|---:|---:|
| Code Reviewer | 21 | 233 |
| Refactor Agent | 20 | 257 |
| Code Auditor | 17 | 517 |
| Mentor | 17 | 454 |
| Architect | 16 | 411 |
| **Total** | **91** | **1,872** |

### Things that cost zero context tokens

- `wopr-core/server/` is 49 MB across 2,178 files (`du -sh`, `find ... | wc -l`). It is a bundled Python source tree launched as a subprocess by `scripts/bootstrap-serve.sh`; none of it enters the context window. Its context cost is the 23 tool definitions counted in section 2.
- `wopr-core/hooks/` contains 4 hooks (`capture-skill-trigger`, `git-branch-guard`, `prompt-log`, `skill-usage`) but there is **no `hooks/hooks.json`** (`ls wopr-core/hooks` confirms). Nothing is auto-registered on install; each is opt-in via a `/wopr-configure-*` command. Eager cost from hooks on a fresh install: 0.
- `wopr-crew/templates/` (14 files), `wopr-crew/data/` (3), `wopr-core/data/` (1), `wopr-*/scripts/`: read on demand by tools, not resident.

---

## 4. Before/after against the old webteam-ai-tools catalog

Source: `/home/jrwhip/Work/AI/WOPR/webteam-ai-tools/catalog`, 12 pack directories, same measurement script and same tier definitions.

| Old pack | Skills | Commands | Agents | T1 eager | T2 | T3 |
|---|---:|---:|---:|---:|---:|---:|
| `_core` | 12 | 20 | 5 | 1,279 | 46,342 | 210,672 |
| `crew` | 1 | 0 | 6 | 750 | 29,356 | 29,356 |
| `meta-authoring` | 1 | 11 | 0 | 357 | 6,095 | 6,544 |
| `accessibility` | 1 | 0 | 2 | 264 | 7,668 | 15,975 |
| `auditors` | 0 | 4 | 3 | 256 | 8,190 | 8,190 |
| `security` | 1 | 0 | 2 | 255 | 11,645 | 26,923 |
| `angular` | 2 | 0 | 2 | 200 | 6,797 | 42,480 |
| `vanilla-web` | 1 | 0 | 2 | 181 | 7,395 | 16,502 |
| `java` | 1 | 0 | 2 | 143 | 4,920 | 17,178 |
| `python` | 1 | 0 | 2 | 132 | 5,505 | 18,110 |
| `ios` | 0 | 0 | 1 | 43 | 1,742 | 1,742 |
| `legacy-migration` | 0 | 0 | 0 | 0 | 0 | 0 |
| **All twelve** | **21** | **35** | **27** | **3,860** | **135,655** | **393,672** |

`legacy-migration` scores zero because it ships no `skills/`, `commands/`, or `agents/` directory: it is `context/`, `parity/`, `reference/`, `scripts/`, `templates/` only (`find catalog/legacy-migration -maxdepth 2 -type d`).

### Before/after pair

Two comparisons, because the new build ships 6 packs and the old shipped 12.

**A. Everything installed, old versus new**

| | Old catalog (12 packs) | New plugins (6) | Delta |
|---|---:|---:|---:|
| Skills | 21 | 19 | -2 |
| Commands | 35 | 21 | -14 (-40.0%) |
| Agents | 27 | 17 | -10 (-37.0%) |
| **T1 eager** | **3,860** | **2,595** | **-1,265 (-32.8%)** |
| T2 on-trigger | 135,655 | 74,098 | -61,557 (-45.4%) |
| T3 deep | 393,672 | 286,456 | -107,216 (-27.2%) |

**B. Like for like, the same six pack names**

Old subset = `_core, angular, auditors, crew, meta-authoring, python`.

| | Old, 6 packs | New, 6 plugins | Delta |
|---|---:|---:|---:|
| Skills | 17 | 19 | +2 |
| Commands | 35 | 21 | -14 |
| Agents | 18 | 17 | -1 |
| **T1 eager** | **2,974** | **2,595** | **-379 (-12.7%)** |
| T2 on-trigger | 102,285 | 74,098 | -28,187 (-27.6%) |
| T3 deep | 315,352 | 286,456 | -28,896 (-9.2%) |

The 886-token eager gap between A and B is the six dropped packs (`accessibility` 264, `security` 255, `vanilla-web` 181, `java` 143, `ios` 43, `legacy-migration` 0). Dropping them removes 78,320 T3 tokens that were never eager in the first place.

Note that the eager tier moved less than the counts did. Core gained skills (12 to 14) while losing commands (20 to 11), and the new skill descriptions are longer, so `_core`'s eager tier went **up** slightly: 1,279 to 1,330 (+51, +4.0%). The eager savings in comparison B come almost entirely from `crew` (750 to 454, -296) and `meta-authoring` (357 to 211, -146).

Crew agent detail, old versus new (same script, `catalog_counts.json`):

| Agent | old eager | old full | new eager | new full |
|---|---:|---:|---:|---:|
| `crew-scout` | 161 | 3,222 | 105 | 996 |
| `crew-auditor` | 97 | 5,598 | 64 | 1,430 |
| `crew-coder` | 72 | 2,729 | 53 | 849 |
| `crew-tester` | 88 | 2,473 | 50 | 815 |
| `crew-evaluator` | 102 | 1,395 | 102 | 1,395 |
| `wopr-crew` (orchestrator) | 132 | 3,575 | removed | removed |

### Sanity check: the new repo's catalog matches the generated plugins

Running the same script over `/home/jrwhip/Work/AI/WOPR/wopr/catalog` gives identical counts (19 skills, 21 commands, 17 agents) and an identical T1 of 2,595. T3 differs slightly (291,741 source versus 286,456 generated, a 5,285-token gap) because `build-plugins` does not copy every source-side file into the plugin bundle. Per pack: `_core` 209,894 -> 205,901, `angular` 42,946 -> 42,483, `crew` 8,726 -> 8,442, `meta-authoring` 3,637 -> 3,318, `python` 18,348 -> 18,122, `auditors` 8,190 -> 8,190.

---

## 5. The always-on tier: what `wopr-core` alone costs

Scenario: a session with `wopr-core@wopr-marketplace` enabled and nothing else. `wopr-core/.mcp.json` registers the bundled MCP server, and that server exposes the whole 23-tool surface (there is no per-pack tool gating in `.mcp.json`; it is one `wopr` server entry pointing at `scripts/bootstrap-serve.sh` which runs `uv run --project "$plugin_root/server" wopr-serve`).

| Component | Tokens | Source |
|---|---:|---|
| 23 MCP tool definitions, `mcp__wopr__`-prefixed names + descriptions + schemas | 6,107 | `count_tools.py new_tools.json` (5,969) + prefix delta (138) |
| 14 skill listing lines | 994 | `catalog_counts.json`, `plugin:wopr-core.detail.skills[].eager` |
| 11 command listing lines | 245 | same, `.commands[].eager` |
| 5 agent listing lines | 91 | same, `.agents[].eager` |
| Plugin description in `marketplace.json` | 16 | `.claude-plugin/marketplace.json` |
| Hooks auto-registered on install | 0 | no `wopr-core/hooks/hooks.json` exists |
| Bundled server source (49 MB, 2,178 files) | 0 | subprocess, never in context |
| **Always-on total** | **7,453** | |

Composition: MCP tool definitions are **81.9%** of the always-on cost (6,107 / 7,453). The entire skill + command + agent catalog is 1,330 tokens, 17.8%.

For scale, the deep tier reachable from that same install is 205,901 catalog tokens plus whatever tool results return. The always-on tier is 3.6% of it.

Same figure for the old world, for the pair: a session with the old `_core` pack installed and the 0.24.4 server running would pay 11,897 (67 prefixed tool definitions) + 1,279 (core eager catalog) = **13,176**. New versus old always-on: **-5,723 tokens, -43.4%**.

And against what is actually running today (0.2.0 server, no plugin catalog eagerly loaded at all, since the live session has only `wopr-python@wopr-marketplace` enabled): 2,063 + 144 = **2,207**. Adopting `wopr-core` would raise the always-on floor of Jerry's sessions by 5,246 tokens.

---

## Method and its limits

**Tokenizer.** All counts come from `tiktoken`'s `o200k_base` encoding, invoked as `uv run --with tiktoken python ...`. That is a real tokenizer, not a heuristic, but it is **OpenAI's** tokenizer, not Anthropic's. No Anthropic tokenizer was available: `python3 -c "import anthropic"` fails with `ModuleNotFoundError`, and `env | grep -c ANTHROPIC_API_KEY` returns `0`, so `client.messages.count_tokens` could not be used. For English prose and JSON the two vocabularies are close, but the numbers here should be read as a consistent proxy, not as exact Claude billing counts. The direction and size of the error is not measured. Every comparison in this document uses the same encoder on both sides, so the deltas and percentages are more trustworthy than the absolute values.

**Tool definitions.** For each tool: `tokens(name) + tokens(description) + tokens(json.dumps(inputSchema, separators=(",",":"), sort_keys=True))`. This is the payload, not the wire format. It excludes the JSON envelope Claude Code wraps each tool in, any per-tool separator or field-name overhead, and the `annotations` / `outputSchema` fields when present. The `mcp__wopr__` prefix cost is reported separately rather than folded into the main totals; where a total is described as "in-context" it includes the prefix.

**Servers were launched, not parsed.** Tool lists came from an actual MCP `initialize` + `tools/list` handshake over stdio against each binary (`/tmp/wopr-audit/dump_tools.py`), not from source inspection or from `tools-manifest.json`. This matters because the old server registers a variable set: it logged `Extras pack tools registered` when pointed at `/home/jrwhip/Work/AI/WOPR/webteam-ai-tools` and `Extras pack not installed, skipping utility tools` when pointed at `/home/jrwhip/Work/AI/webteam-ai-tools`. The 67-tool figure is therefore workspace-dependent, and 15 of those 67 are the extras pack. Without extras the old repo would expose 52 tools.

**Eager tier model.** T1 is a reconstruction, not an observation. It assumes Claude Code lists each skill, command, and agent as one `- {name}: {description}` line, which matches the shape of the skill and agent listings visible in a live session. It does **not** include: the fixed prose that wraps those listings, the `(Tools: ...)` suffix on agent entries beyond a single "All tools" placeholder, `argument-hint` or `allowed-tools` frontmatter on commands, per-plugin section headers, or the marketplace scaffolding. Real eager cost is therefore somewhat higher than T1 across the board, by an amount that scales with item count and so slightly understates the savings from removing items.

**Frontmatter parsing** is a regex over the leading `---` block with naive folding of continuation lines, not a YAML parser. Multi-line block scalars (`description: >`) would be flattened with single spaces; no such usage was spotted, but it was not exhaustively verified.

**T3 counts every file** in a skill directory as text, including any non-prose assets. A file that would never be read into context still contributes to T3. T3 is a ceiling ("what exists behind this door"), not a prediction of spend.

**Not measured at all:** tool *results* (the largest real consumer of context in practice), `CLAUDE.md` / `AGENTS.md` files, `_core/context/` and `_core/data/` payloads, crew `templates/`, the `LEARNINGS.md` corpus and its embeddings, hook output injected at runtime, the system prompt, and conversation history. Nothing here estimates cost per session or per task; it is a static footprint of the harness definition surface only.

**Artifacts.** Raw JSON dumps live at `/tmp/wopr-audit/`: `new_tools.json`, `old_live_tools.json`, `old_repo_tools.json`, `catalog_counts.json`, `spec.json`, plus the scripts `dump_tools.py`, `count_tools.py`, `count_catalog.py`, `run_old.sh`. These are in `/tmp` and will not survive a reboot; regenerate with the commands quoted in each section.
