# KITT

KITT is an agent harness for Claude Code: a stdio MCP server plus a
catalog of skills, agents, and commands, shipped as one Claude Code
plugin per pack. The MCP server ships the deterministic things a model
cannot do for itself (a learnings corpus with retrieval and a curation
gate, the four-role crew's contract and spec-scaffolding substrate,
routing evals, skill telemetry, skill and dependency scanning,
handoffs). The catalog ships the orchestration contracts and local
opinions that go with them.

The design rule is deltas, not curricula: an artifact earns its place
only if it is post-cutoff knowledge, a genuine local opinion, a
deterministic tool, or an orchestration contract. Anything that
re-teaches the model what it already knows is cut.

## Install

This repository is a Claude Code plugin marketplace. Add it once, then
install the packs you want. Install `kitt-core` first: it carries the
MCP server that every other pack's skills call.

```
/plugin marketplace add jrwhip/tool-kitt
/plugin install kitt-core@kitt-marketplace
/plugin install kitt-crew@kitt-marketplace
```

Plugins can be enabled per project, so a project carries only the packs
its stack needs. `claude plugin details kitt-core@kitt-marketplace`
shows what each pack adds to a session's context.

| Plugin | What it ships |
|--------|---------------|
| `kitt-core` | Foundation tools: mental models, debugging, todo management, planning, handoffs, learnings, and the MCP server |
| `kitt-crew` | The four-role agent crew (scout, coder, tester, auditor): one REQ per run, API-contract-first, spec-files-as-authority |
| `kitt-angular` | Angular development: component patterns, testing, code review |
| `kitt-python` | Python development: FastAPI, AI integrations, testing, packaging |
| `kitt-auditors` | Skill, command, and subagent quality auditors |
| `kitt-meta` | Tools for creating new commands, skills, agents, and hooks |

### Prerequisite: uv

`kitt-core` runs its MCP server through [uv](https://docs.astral.sh/uv/).
uv is a static binary, installs into your user profile, needs no admin
rights, and provisions its own Python. The server ships a `uv.lock`, so
the first launch installs exactly the pinned versions.

- Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`,
  or `winget install astral-sh.uv`
- macOS: `brew install uv`
- Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Developing

```
uv sync --all-extras
uv run pytest
uv run kitt build-plugins --out plugins --marketplace-root .
```

`catalog/` and `catalog.yaml` are the source. `plugins/` and
`.claude-plugin/marketplace.json` are generated from them and committed,
so the marketplace can be served straight from git. A test fails when
the committed tree lags the catalog; rerun the build and commit.

## Lineage

KITT began life as `tool-kitt` in 2025, grew into a larger private
toolset, and was then rebuilt clean-room as the plugins-only harness in
this repository. The 2025 tree is preserved under the
`archive/2025-tool-kitt` tag. Nothing client-specific is in this
repository; see `NOTICE.md` for material adapted from other projects.

## License

MIT. See `LICENSE` and `NOTICE.md`.
