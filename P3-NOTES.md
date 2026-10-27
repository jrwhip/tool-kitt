# P3 notes: `kitt build-plugins`

Phase P3 of the redesign plan: emit a Claude Code plugin marketplace
from the catalog, with the MCP server shipped inside `kitt-core`.
Distribution is marketplace-only. There is no `kitt install` of any
kind, no PyPI package to install first, and no `kitt --init`.

Everything below is a decision, a deviation, a documented fact I built
against, or an ambiguity the docs left open. Written for whoever picks
this up next, including me.

## What landed

| File | Lines | What |
|------|-------|------|
| `src/kitt/build_plugins.py` | 815 | The generator |
| `src/kitt/learnings_cli.py` | 99 | `kitt learnings append` / `search` |
| `src/kitt/cli.py` | 317 | Rewritten onto argparse subparsers |
| `tests/test_build_plugins.py` | 567 | 55 tests |
| `tests/test_cli.py` | 312 | 23 tests |

Touched for path resolution: `src/kitt/config.py`,
`src/kitt/tools/_data_paths.py`, `src/kitt/catalog.py`,
`pyproject.toml` (new `kitt-serve` console script).

Suite: 673 passed, 1 skipped. `ruff check .` clean.
`mypy src/kitt` clean (44 files). `mypy tests` is not part of the gate
and never has been; the existing test suite is untyped.

## Source of truth for the plugin format

Fetched on 2026-08-21 and built against, not against memory:

- `https://code.claude.com/docs/en/plugins-reference`
- `https://code.claude.com/docs/en/plugin-marketplaces`

Facts the generator depends on, quoted in substance:

1. **`plugin.json` lives in `.claude-plugin/`**, and that directory is
   optional. Only `name` is required. `description`, `version`,
   `author {name,email,url}`, `license`, `keywords` are all optional
   and all documented.
2. **Component directories must be at the plugin root, not inside
   `.claude-plugin/`.** Defaults: `commands/` (flat `.md` files),
   `agents/` (`.md` files), `skills/` (`<name>/SKILL.md`
   subdirectories), `hooks/hooks.json`, `.mcp.json` at plugin root.
   A test asserts `.claude-plugin/` contains nothing but
   `plugin.json`.
3. **`.mcp.json` at the plugin root is auto-detected.** Declaring
   `mcpServers` in `plugin.json` is an alternative, not a requirement,
   so `kitt-core/plugin.json` stays metadata-only.
4. **`${CLAUDE_PLUGIN_ROOT}` expands in `command`, `args` and `env`
   for stdio MCP servers.** Both the command path and the
   `KITT_PLUGIN_ROOT` env value rely on this.
5. **`marketplace.json` lives at `.claude-plugin/marketplace.json`**
   with required `name`, `owner` (object, `name` required) and
   `plugins` (array). Each entry requires `name` and `source`. A
   relative-path source "must start with `./`" and "resolved relative
   to the marketplace root, not the `.claude-plugin/` directory".
   Entries may carry any plugin-manifest field plus `source`,
   `category`, `tags`, `strict`, `relevance`.
6. **Marketplace names are namespaced per user and some are
   reserved.** `kitt-marketplace` is not on the reserved list
   (the list is all Anthropic-official names) and does not impersonate
   one.

Validated with the official validator, not by eyeball:

```
$ claude plugin validate .            # marketplace
✔ Validation passed
$ claude plugin validate kitt-core    # and each of the six plugins
✔ Validation passed
```

## Decisions

### 1. One plugin per pack, packs with nothing to ship are skipped

A pack ships a plugin when it has at least one command, agent or
skill. Nothing else qualifies: an empty plugin is noise in `/plugin`
and cannot do anything. All six current packs qualify.

Name mapping is a table, not a guess: `_core` to `kitt-core`,
`meta-authoring` to `kitt-meta`, everything else `kitt-<pack>`.
Two overrides, both from the plan.

### 2. Directory allowlist, not a blocklist

Copied when present: `commands/`, `agents/`, `skills/` (the Claude
Code components) plus `hooks/`, `scripts/`, `templates/`, `data/`
(pack-owned support files a skill or command references by relative
path). Everything else in a pack directory is left behind. An
allowlist means a new file type has to be considered before it can
ship, which is the safer default for a tree that becomes a public
marketplace.

Deliberate exclusions, each with a test:

- **`routing-eval.jsonl`** everywhere. Dev-time fixtures for the
  slimming gate (`check_routing_evals` reads them from the source
  catalog). They are evidence for the eval-gated slimming method, not
  runtime content.
- **Pack-root `README.md`.** `catalog/crew/README.md` opens with
  `kitt add crew` install instructions for machinery that no longer
  exists. Shipping it would ship a lie. The marketplace gets its own
  generated README instead.
- **`catalog/_core/context/`.** The `get_shared_context` shim that
  served those three documents retired with the rest of the cross-CLI
  shim layer in P1. Nothing reads them in a plugin-native world.
- **Dotfiles and dot-directories**, anywhere in a copy source. This
  covers `.git`, `.venv`, every future cache directory, and editor
  droppings without a maintenance list. `__pycache__` and
  `node_modules` are named explicitly since they are not dot-prefixed.

Known follow-up, not fixed here: `catalog/crew/templates/README.md`
and `catalog/crew/scripts/README.md` ride along inside their
directories and may contain the same stale `kitt add` phrasing as the
pack README. They are catalog content, and rewriting catalog prose is
not this generator's job.

### 3. Deterministic, total, marker-guarded

- **Deterministic.** Same catalog in, byte-identical tree out. Sorted
  traversal everywhere, no timestamps (the marker file deliberately
  carries none), no host paths in generated content. Verified by
  generating twice into different directories and comparing every
  file's bytes.
- **Total.** The output directory is wiped and rewritten. Nothing
  merges, so a file deleted from the catalog cannot survive in the
  emitted tree. A test plants a stale file and a stale directory and
  asserts both are gone after a regeneration.
- **Guarded.** A `.kitt-generated` marker at the marketplace root is
  the only thing that authorizes the wipe. An existing non-empty
  directory without it is refused with the path in the message and
  nothing touched. This is the difference between a mistyped `--out`
  and a bad afternoon.

### 4. The server ships inside `kitt-core`

```
kitt-core/
  .claude-plugin/plugin.json
  .mcp.json                      -> scripts/bootstrap-serve.sh
  commands/ agents/ skills/ data/
  scripts/bootstrap-serve.sh     (0755)
  server/
    pyproject.toml               (runtime deps only, kitt-serve entry)
    src/kitt/                    (the package, no tests, no evals)
    resources/
      catalog.yaml
      crew/templates/**
      crew/data/learnings-seed/**
```

`.mcp.json`:

```json
{
  "mcpServers": {
    "kitt": {
      "command": "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap-serve.sh",
      "env": { "KITT_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}" }
    }
  }
}
```

The shim resolves the plugin root from `KITT_PLUGIN_ROOT`, then
`CLAUDE_PLUGIN_ROOT`, then from its own location, then
`exec uv run --project "$plugin_root/server" kitt-serve`.

**Deviation from the plan text.** The plan wrote the shim as
`exec uv run --project "$CLAUDE_PLUGIN_ROOT/server" kitt-serve`.
`CLAUDE_PLUGIN_ROOT` is documented as a placeholder that Claude Code
expands inside `.mcp.json`, not as an environment variable guaranteed
to be exported into the launched process. Depending on it inside the
script would be depending on undocumented behavior. The fallback chain
covers all three cases and makes the shim runnable by hand from a
terminal, which is how both of its branches were tested.

Both branches were run for real:

```
$ printf '' | timeout 60 .../bootstrap-serve.sh   # server starts, exits 0 at EOF
$ env PATH=/usr/bin:/bin .../bootstrap-serve.sh   # exit 1 + per-OS guidance
kitt: uv was not found on PATH, and the bundled KITT MCP server needs it.
  Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
           or: winget install astral-sh.uv
  macOS:   brew install uv
  Linux:   curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 5. `kitt-serve` is a real entry point, not `kitt` with no args

`kitt` with no subcommand still runs the server, unchanged. The bundle
declares `kitt-serve = "kitt.cli:serve"` so the launch contract names
an action instead of relying on a bare invocation resolving to the
server. The same script is now declared in the repo's `pyproject.toml`
too, so a dev checkout exercises the identical entry point.

### 6. Runtime dependencies only in the bundled `pyproject.toml`

`mcp[cli]>=1.0.0,<2` and `pyyaml>=6.0`, copied verbatim from the source
project's `dependencies`. Not shipped: the `dev` extra (pytest, ruff,
mypy) and the optional `embeddings` extra (fastembed + numpy, roughly
100MB of onnxruntime plus a 130MB model download). A plugin install
must not pay for either. Without the extra, `learnings_search` falls
back to the deterministic prefilter, which is the documented behavior.

The bundled dependency list is a hand-maintained copy, so
`test_bundled_dependencies_match_the_source_project` parses
`pyproject.toml` and asserts equality. Drift fails the suite.

Python 3.10 is still supported, so the test parses the dependency
block with a regex rather than `tomllib` (3.11+).

### 7. Resource resolution: one env-var override, in `config.py`

The problem: the bundled package sits at
`<plugin>/server/src/kitt/`, and its resources sit at
`<plugin>/server/resources/`, which is outside the package. Neither of
the two existing candidates in `_data_paths.py` can reach that layout
(one walks up to a repo root looking for `catalog/`, the other looks
for `resources/` inside the package directory).

The fix is one override, not conditionals scattered through the tool
modules:

- `config.py` gains `ENV_KITT_PLUGIN_ROOT`, the layout constants
  `PLUGIN_SERVER_DIRNAME = "server"` and
  `PLUGIN_RESOURCES_DIRNAME = "resources"`, and
  `plugin_resources_root() -> Path | None`. Those two constants are
  the contract between the generator and the runtime; the generator
  imports them, so the two sides cannot drift.
- `_data_paths.candidate_data_paths` prepends the plugin candidate
  when the env var is set. Unset, the list is exactly the historical
  two, and the existing test that pins `len(result) == 2` still holds.
- `catalog.load_catalog` gains the same candidate for `catalog.yaml`
  (`get_help` loads the catalog).

Ordering: the plugin candidate goes first. An explicitly provided
environment variable beats path arithmetic derived from `__file__`.
Outside a plugin install it costs nothing.

`plugin_resources_root()` reads the environment directly rather than
going through `ServerConfig`, for the same reason
`catalog.get_global_home()` does: these resolvers are module-level
helpers that run on CLI paths where no `ServerContext` exists. The
value is process-level and immutable, so routing it through a config
object would buy nothing and cost an import cycle.

Verified from the bundle, with `KITT_PLUGIN_ROOT` set:

```
templates_dir: .../kitt-core/server/resources/crew/templates   (6 templates)
seed:          .../server/resources/crew/data/learnings-seed/fastapi.md
by-stack:      .../server/resources/crew/templates/by-stack/angular
catalog packs: ['_core', 'angular', 'auditors', 'crew', 'meta-authoring', 'python']
tools:         23
```

What is bundled and why: `crew/templates/**` (`get_pack_template`,
`list_pack_templates`, `write_spec_stubs`),
`crew/data/learnings-seed/**` (`seed_learnings`), `catalog.yaml`
(`get_help`). `catalog/_core/data/doctor-recommendations.yaml` is
**not** bundled: nothing in the surviving tool set reads it (the
doctor tool did not cross over in P1). It still ships as plugin
content inside `kitt-core/data/`, where a skill can read it.

### 8. Version: PEP 440 in, semver out

`__version__` is `1.0.0.dev0`, which is a legal PEP 440 version and an
illegal semver one. The manifests document `version` as a semantic
version, so `to_semver()` projects it: `1.0.0.dev0` becomes
`1.0.0-dev.0`, `1.2.0rc1` becomes `1.2.0-rc.1`, a plain `1.2.3` passes
through, anything unrecognized is emitted literally.

Honest note on necessity: `claude plugin validate` accepts
`"version": "1.0.0.dev0"` today, so this mapping is not required by
the validator. I kept it because the docs say semantic version and
because update detection compares version strings; a non-semver
pre-release is the kind of thing that compares wrong quietly. The
package keeps PEP 440 as its single source of truth and the projection
is one small tested function.

### 9. Cross-plugin collision checks

Planned fully before anything is written, so a collision fails the run
without leaving a half-generated tree:

- **Component names.** No command, agent or skill name may appear in
  two plugins. Claude Code namespaces components by plugin, so a
  collision is not fatal to the loader; it is fatal to routing, and it
  always means a catalog mistake. The message names the component, its
  kind, and both plugins.
- **Skill descriptions.** Reuses
  `_routing_eval.find_duplicate_descriptions` and
  `scan_catalog_skills`, scoped to skills that actually ship, so the
  generator and `check_routing_evals` cannot disagree about what a
  duplicate is. Two skills with byte-identical descriptions give the
  model nothing to route on.

The current catalog passes both. A test asserts that, so a future
catalog edit that breaks it fails the suite rather than the release.

The conversion manifest (`COMMAND_TIERS` / `AGENT_TIERS`) is
deliberately **not** consulted. Its tiers answer "can this convert to
Gemini or Copilot", and tier 3 exists mostly because a body calls
Claude's Skill tool or writes `.claude/settings.json`. Filtering the
Claude Code marketplace by it would drop exactly the commands that
work best on Claude Code. It stays where it belongs, in the (deferred)
Copilot converter.

### 10. CLI moved to subparsers

`build-plugins --out` and `learnings append|search` need real flags,
which the old flat positional parser could not express without
polluting the top level. All previous invocations still work and are
now pinned by tests: `kitt`, `kitt list`, `kitt catalog`,
`kitt help [topic]`, `kitt skill-usage record <source> <name>...`,
`--version`, and both option orders around the verb.

**Argparse trap worth remembering.** Since Python 3.9 a subparser
parses into a fresh namespace and copies every key back onto the
parent's, defaults included. A subcommand copy of `--workspace` on the
shared parent therefore overwrote the value the top level had already
parsed, and `kitt --workspace X list` silently resolved to the current
directory. Caught by a test, not by reading. Fix: the subcommand
parent uses `default=argparse.SUPPRESS` so unsupplied options never
enter the copy. Two parent parsers, one for the top level with real
defaults and one for subcommands with suppressed ones.

`main()` now takes an optional `argv`, so the tests drive the real
parser instead of a reimplementation of it.

### 11. `kitt learnings` is the MCP path, not a parallel one

`learnings_cli.py` calls `append_learnings` and `learnings_search`
directly (via `asyncio.run`) with `target_workspace_path` supplied
explicitly. Same LRN header validation, same origin-slug rules, same
leak vet, same sidecar behavior, because it is the same code. Tests
exercise the real coroutines: a stub would prove nothing about the
claim that a Bash-capable agent gets the same validation.

The one real difference: an MCP session can infer the workspace from
advertised roots or `CLAUDE_PROJECT_DIR`; a shell invocation cannot,
so the workspace defaults to the current directory and `--workspace`
overrides it.

Entry input is `--entry TEXT`, `--entry-file PATH`, or
`--entry-file -` for stdin (the heredoc case). Mutually exclusive and
required. The tools' `Error:` return-string convention maps to exit
code 1 with the message on stderr, so a shell caller can branch on it.

## Ambiguities and gaps in the plugin docs

1. **`marketplace.json` is not in the plugins reference.** The
   reference page documents `plugin.json` exhaustively and points at
   the marketplaces page for the catalog format. Both pages are
   needed; neither is sufficient.
2. **No stated version-string grammar.** Both pages say "semantic
   version" in prose. Nothing states whether the value is parsed,
   compared, or merely displayed, and the validator accepts a
   non-semver string. See decision 8.
3. **`hooks/` is a reserved-by-convention directory name.** The docs
   define `hooks/hooks.json` as the default hook config location.
   `kitt-meta` ships a `hooks/` directory of KITT's own
   `*.HOOK.yaml` manifests and handler scripts, which is a different
   thing that happens to share a name. It is inert: there is no
   `hooks.json`, and the docs describe only that filename as scanned.
   The `/kitt-configure-*` commands remain the way those hooks get
   registered. If a future Claude Code version scans `hooks/*.json`
   instead of `hooks/hooks.json`, this becomes a real collision and
   the directory should be renamed in the catalog.
4. **State inside `${CLAUDE_PLUGIN_ROOT}` is discouraged**, and the
   docs point at `${CLAUDE_PLUGIN_DATA}` for anything persistent, with
   the plugin root treated as ephemeral (the previous version's
   directory survives roughly 14 days after an update). `uv run
   --project <plugin>/server` writes `uv.lock` and `.venv/` into the
   plugin root on first launch. See "Known costs" below.
5. **Copied plugins cannot reference files outside their own
   directory.** The docs are explicit: `../shared-utils` does not
   work, because only the plugin directory is copied into the cache.
   This is the root of the open issue below.

## Open issue: `kitt-meta` hook configuration under a plugin install

Two independent breakages, both outside this generator and both worth
fixing before the marketplace is used for real.

**1. The script imports `kitt`.**
`catalog/meta-authoring/scripts/configure_hook.py` imports
`kitt.hook_manifest`. It ships in `kitt-meta`, which has no server
bundle, and it cannot reach `kitt-core`'s bundle: each plugin is
copied into its own cache directory and cross-plugin relative paths
are documented not to work.

**2. The commands still assume the pip-install layout.** Every
`/kitt-configure-*` command body runs:

```
! KITT_DIR=$(python3 -c "import kitt, pathlib; print(pathlib.Path(kitt.__file__).parent / 'resources')") \
  && python3 "$KITT_DIR/meta-authoring/scripts/configure_hook.py" ...
```

That is the wheel layout (`kitt/resources/<pack>/`, produced by
`hatch_build.py`) reached through an ambient `python3` that has `kitt`
importable. Marketplace-only distribution has neither: there is no pip
install, and the bundled `resources/` tree carries the crew subtrees
the MCP tools read, not pack scripts. Under a plugin install the
script is simply at `${CLAUDE_PLUGIN_ROOT}/scripts/configure_hook.py`
inside `kitt-meta`, so the lookup dance is both broken and
unnecessary.

`configure_git_guard.py` and `configure_prompt_log.py` are stdlib-only
and unaffected by (1), but their commands were not checked for (2) and
probably share the same invocation shape. All four hook handler
scripts under `hooks/` are stdlib-only and are invoked by Claude Code
directly, so they are fine.

That file and its module are owned by another workstream right now, so
this is a documented finding rather than a fix. Whatever option is
chosen for (1), the command bodies in
`catalog/meta-authoring/commands/kitt-configure-*.md` need the
`${CLAUDE_PLUGIN_ROOT}/scripts/...` path instead of the
`import kitt` lookup, which fixes (2) at the same time.

Options for (1), in my order of preference:

1. **Make the script self-contained** (PEP 723 inline metadata,
   stdlib only, manifest rendering inlined or vendored). Keeps the
   pack independent, which is what a per-pack plugin model wants.
2. **Move hook configuration into `kitt-core`** as a command next to
   the server it depends on. Correct dependency direction, but it
   moves an authoring concern out of the authoring pack.
3. **Emit the server bundle into any plugin that needs it.** About 64
   files and 1.4MB duplicated per plugin, plus two venvs to warm.
   Mechanically easy (the generator would take a per-pack
   `needs_server` flag), and the least appealing.

Explicitly rejected: locating `kitt-core` at runtime by guessing at
`~/.claude/plugins/cache/...`. That hard-codes an implementation
detail of the plugin cache, and the docs call the path ephemeral.

## Known costs, accepted

- **First MCP launch is slow.** uv resolves `mcp[cli]` and `pyyaml`
  and builds a venv. Roughly 40 packages. Later launches reuse it.
- **`uv.lock` and `.venv/` land inside the plugin root.** They are
  regenerated after a `/plugin update` (new root) and destroyed by a
  regeneration of the marketplace tree (the wipe is total, by design).
  Relocating them with `UV_PROJECT_ENVIRONMENT` pointed at
  `${CLAUDE_PLUGIN_DATA}` is the obvious refinement; I did not do it
  because the plan specifies exactly one env var in `.mcp.json` and I
  have no evidence yet that `${CLAUDE_PLUGIN_DATA}` expands in an MCP
  `env` block. Worth testing during the P3 install walkthrough.
- **The generator regenerates the whole tree.** If the marketplace
  becomes a git repo, every run rewrites all 294 files; git will still
  show only real content changes because generation is deterministic.

## Verification performed

Real run, `uv run kitt build-plugins --out /tmp/kitt-plugins-test`:

```
Wrote kitt-marketplace to /tmp/kitt-plugins-test
  version: 1.0.0-dev.0
  plugins: 6
    kitt-core: 7 commands, 5 agents, 14 skills + bundled MCP server
    kitt-angular: 2 agents, 2 skills
    kitt-auditors: 4 commands, 3 agents
    kitt-crew: 5 agents, 1 skill
    kitt-meta: 10 commands, 1 skill
    kitt-python: 2 agents, 1 skill
  files: 294
```

- Every emitted `.json` parses (8 files: 1 marketplace, 6 plugin
  manifests, 1 `.mcp.json`).
- `claude plugin validate .` passes for the marketplace and for each
  of the six plugin directories.
- `bash -n` passes on the shim; mode is `0755`.
- `uv run --project /tmp/kitt-plugins-test/kitt-core/server python -c
  "from kitt.server import create_app; create_app()"` succeeds, and
  the bundled server registers all 23 tools.
- With `KITT_PLUGIN_ROOT` set, pack templates, learnings seeds, the
  per-stack template dirs and `catalog.yaml` all resolve to the
  bundled `resources/` tree.
- Both shim branches exercised (server starts; missing uv exits 1 with
  per-OS guidance).
- Regenerating into a second directory produces byte-identical output.
- Pointing `--out` at a foreign non-empty directory refuses and leaves
  it untouched.

## Not done here (next session)

The plan's P3 verification list ends with an interactive step that
needs a live Claude Code session:
`/plugin marketplace add ./kitt-plugins`, install core plus crew plus a
stack pack, confirm skills, agents and commands resolve natively,
check `/context` shows only the installed packs' footprint, and run a
crew end to end through the plugin install. The generated tree is
ready for it and validates against the official validator, but nothing
above proves the installed-session behavior.

Also deferred: emitting a marketplace README install matrix richer
than the current one, and the hosted-learnings MCP entry in
`.mcp.json` (post-talk, per the plan).
