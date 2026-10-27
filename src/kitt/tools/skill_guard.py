"""MCP tool surface for the skill/plugin threat scanner.

See :mod:`_skill_guard` for the scan logic and the design rationale
(ported from a subset of Hermes Agent's ``tools/skills_guard.py``,
addressing the "no review, no signing" gap in both Claude Code's and
GitHub Copilot CLI's plugin marketplace mechanisms).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._skill_guard import format_scan_report, scan_skill

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def scan_skill_directory(skill_path: str) -> str:
    """Scan a skill file or directory for known threat patterns before trusting it.

    Best-effort static analysis, not a security boundary — a determined
    author could still evade regex matching. Useful specifically for
    skills pulled from outside the org's own catalog (a third-party
    marketplace entry, a skill shared informally), where nothing else in
    the marketplace/plugin install path reviews content before it
    installs.

    Args:
        skill_path: Absolute path to a skill directory or a single file
            (e.g. a downloaded/cloned skill before you `mv` it into a
            trusted location).

    Returns:
        A human-readable report: verdict (SAFE / CAUTION / DANGEROUS) and
        every finding with its severity, category, and location. Returns
        an ``Error:`` string if the path does not exist.
    """
    path = Path(skill_path).expanduser()
    if not path.exists():
        return f"Error: path does not exist: {path}"
    result = scan_skill(path)
    return format_scan_report(result)


def register(mcp: FastMCP) -> None:
    """Register skill-guard tools with the MCP server."""
    mcp.tool()(scan_skill_directory)
