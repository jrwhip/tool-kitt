# KITT

KITT is an agent harness for Claude Code: a stdio MCP server plus a
catalog of skills, agents, and commands. The MCP server ships the
deterministic things a model cannot do for itself (a learnings corpus
with retrieval and a curation gate, the four-role crew's contract and
spec-scaffolding substrate, routing evals, skill telemetry, skill and
dependency scanning, handoffs). The catalog ships the orchestration
contracts and local opinions that go with them.

The design rule is deltas, not curricula: an artifact earns its place
only if it is post-cutoff knowledge, a genuine local opinion, a
deterministic tool, or an orchestration contract. Anything that
re-teaches the model what it already knows is cut.

## Lineage

This repository is a clean-room rebuild. It is not a fork. An earlier,
private toolset (68 MCP tools, 13 catalog packs, roughly 75k lines of
catalog markdown) was designed against pre-4.5 models and is now
over-instructed for the current ones. That toolset stays private and
stays put; KITT ports the surviving subset, re-authored as it crosses
over, and drops the rest. Nothing client-entangled comes across.

## Install

Not published yet. From a checkout:

```
uv sync
uv run kitt --help
```

Register the MCP server with Claude Code by pointing it at `kitt` (no
subcommand) over stdio.

## Status

Early. See `P1-NOTES.md` for what ported, what did not, and why.
