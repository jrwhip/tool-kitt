"""MCP tool surface for the structural routing-eval harness.

See :mod:`_routing_eval` for the scoring logic and — importantly — the
honesty disclaimer about what a "pass" here does and doesn't prove (no
model is in the loop; this is lexical/structural analysis only).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..catalog import get_catalog_path
from ._routing_eval import (
    build_trigger_index,
    find_duplicate_descriptions,
    format_routing_report,
    load_routing_fixtures,
    run_routing_eval,
    scan_catalog_skills,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def check_routing_evals(catalog_path: str = "") -> str:
    """Run the structural (no-model) routing-eval harness over the catalog.

    Loads every ``skills/**/SKILL.md`` in the catalog, extracts trigger
    phrases from each description, loads every sibling
    ``routing-eval.jsonl`` fixture file, and reports: duplicate
    descriptions (a routing-breaker no model can work around), fixture
    lint issues (tautological or malformed fixtures), and the pass/miss/
    ambiguous/false-positive tally from Layer A structural matching.

    This does NOT verify that Claude Code, Copilot CLI, or Gemini CLI
    would actually invoke the right skill for a given message — that
    decision is made by each CLI's own model at runtime and can't be
    reproduced offline. See ``_routing_eval`` module docstring for the
    full scope disclaimer.

    Args:
        catalog_path: Optional explicit catalog directory. Defaults to
            the bundled or repo-root catalog (same resolution as other
            catalog-aware tools).

    Returns:
        A human-readable report. Returns an ``Error:`` string if no
        catalog directory can be resolved.
    """
    root = Path(catalog_path).expanduser() if catalog_path else get_catalog_path()
    if root is None or not root.exists():
        return f"Error: no catalog directory found (looked at: {root or 'bundled/repo default'})"

    skills = scan_catalog_skills(root)
    if not skills:
        return f"Error: no SKILL.md files found under {root}"

    lines: list[str] = [f"Scanned {len(skills)} skill(s) under {root}"]

    dupes = find_duplicate_descriptions(skills)
    if dupes:
        lines.append(f"\n{len(dupes)} duplicate description(s) (routing cannot disambiguate):")
        for a, b, _normalized in dupes:
            lines.append(f"  - {a!r} and {b!r} share an identical description")
    else:
        lines.append("\nNo duplicate descriptions.")

    index = build_trigger_index(skills)
    load_result = load_routing_fixtures(root)
    if load_result.malformed:
        lines.append(f"\n{len(load_result.malformed)} malformed fixture line(s):")
        for m in load_result.malformed:
            lines.append(f"  - {m.file}:{m.line}: {m.error}")

    from ._routing_eval import lint_routing_fixtures

    lint_issues = lint_routing_fixtures(load_result.fixtures, index)
    if lint_issues:
        lines.append(f"\n{len(lint_issues)} fixture lint issue(s):")
        for issue in lint_issues:
            lines.append(
                f"  - [{issue.reason}] {issue.fixture.source}: "
                f"{issue.fixture.intent!r} — {issue.detail}"
            )
    else:
        lines.append("\nNo fixture lint issues.")

    report = run_routing_eval(index, load_result.fixtures)
    lines.append("\n" + format_routing_report(report))

    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register routing-eval tools with the MCP server."""
    mcp.tool()(check_routing_evals)
