# Skill usage telemetry

What gets counted, where the numbers live, and (most load-bearing) what a zero means.

## What it is

A sidecar JSON file, keyed by skill name, holding invocation counts and lifecycle labels (`active` / `stale` / `archived`) with a `pinned` opt-out. Writes are atomic and best-effort: a telemetry failure must never fail the call site that triggered it. The design is ported from hermes-agent's `tools/skill_usage.py`; the divergences and their reasons are documented in the module docstring of `src/kitt/tools/_skill_usage.py`, which is the authoritative reference.

## Who writes it

Exactly one writer exists on the current surface: the **Claude Code skill-usage hook** (`catalog/_core/hooks/skill-usage-hook.py`, registered per project via `/kitt-configure-skill-usage-hook`). It observes native `Skill` invocations in sessions where it is registered and bumps the sidecar. The historical second writer, the `run_skill` MCP tool, was retired with the cross-CLI shim layer; nothing else counts anything.

## Who reads it

- `skill_usage_report` (MCP tool) and `kitt skill-usage report` (CLI): counts and lifecycle labels per skill.
- `pin_skill` (MCP tool): marks a skill exempt from staleness labeling.
- The slimming ledger process: usage numbers are retirement evidence where they exist (`docs/slimming-ledger.md`).

## The coverage boundary, honestly

**Zero means unobserved, not unused.** Counting happens only on Claude Code, only in projects where the hook is registered, and only for invocations the hook can see. Sessions without the hook, other CLIs, and skills read as plain files by an agent all register nothing. Any decision made on these numbers (retiring a skill, dropping a pack) must treat absence of data as absence of data. Lifecycle labels are labels: `archived` never moves or deletes a file; the operator acts on it, the module does not.
