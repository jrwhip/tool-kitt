"""MCP tools over the skill usage telemetry sidecar.

Thin surface on :mod:`._skill_usage`: one report, one pin toggle. The
store module owns the schema, the atomic write, the lifecycle rules,
and -- importantly -- the coverage boundary that ships inside every
report payload. Read its module docstring before drawing a conclusion
from any number these tools return.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..context import ServerContext, ToolContext
from . import _skill_usage
from ._workspace_target import (
    InvalidTargetWorkspaceError,
    resolve_request_workspace,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


async def _request_workspace(
    target_workspace_path: str, request_ctx: ToolContext | None
) -> tuple[Path | None, str | None]:
    """Resolve a request's workspace, tolerating the ambient-signal case.

    An explicitly supplied path that fails validation is an error the
    caller must see. No path at all is not an error here: both tools in
    this module degrade to a global-only view when the workspace cannot
    be determined.

    Lived in the resource-shim tool module in the prior toolset, which
    does not cross over; this module is now its only consumer.
    """
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, request_ctx, allow_legacy_config=True
        )
        return workspace, None
    except InvalidTargetWorkspaceError as e:
        if target_workspace_path:
            return None, str(e)
        return None, None


def _installed_skill_names(workspace: Path | None) -> list[str]:
    """Enumerate every skill directory under the shared resource dirs.

    A skill that appears in the report is one this server can actually
    see on disk. Lived in the resource-shim tool module in the prior
    toolset (as ``_all_available(ctx, "skills", ...)``); inlined here
    for the one category that survived.
    """
    names: set[str] = set()
    for skills_dir in ServerContext.get().resource_dirs("skills", workspace):
        for entry in skills_dir.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                names.add(entry.name)
    return sorted(names)


async def skill_usage_report(
    target_workspace_path: str = "",
    stale_after_days: int = _skill_usage.DEFAULT_STALE_AFTER_DAYS,
    archive_after_days: int = _skill_usage.DEFAULT_ARCHIVE_AFTER_DAYS,
    ctx: ToolContext | None = None,
) -> str:
    """Report how often each installed skill has been observed being used.

    Answers "which of the installed skills does anyone actually use",
    which drives pack slimming and skill loading tiers.

    IMPORTANT: the counts are a LOWER BOUND, not a census. Only two
    sources are observed -- the ``run_skill`` MCP tool, and (when the
    operator has registered it) the Claude Code ``skill-usage-hook.py``
    Stop hook. Native skill invocations on Copilot CLI and Gemini CLI
    are NOT counted at all: those CLIs load skills themselves and never
    reach this server. A zero count therefore means UNOBSERVED, never
    "unused". The returned ``coverage`` block spells this out; report it
    alongside any recommendation you make from these numbers.

    Args:
        stale_after_days: Idle days before a skill is labelled ``stale``.
        archive_after_days: Idle days before a skill is labelled
            ``archived``. The label is advice only -- nothing is moved or
            deleted, ever.

    Returns:
        JSON with ``coverage``, ``totals``, ``thresholds``, and one row
        per skill (``count``, ``sources``, ``state``, ``pinned``,
        ``first_seen_at``, ``last_used_at``, ``installed``).
    """
    workspace, error = await _request_workspace(target_workspace_path, ctx)
    if error:
        return error
    installed = _installed_skill_names(workspace)
    payload = _skill_usage.report(
        installed,
        stale_after_days=max(1, stale_after_days),
        archive_after_days=max(1, archive_after_days),
    )
    return json.dumps(payload, indent=2)


async def pin_skill(
    skill_name: str,
    pinned: bool = True,
    target_workspace_path: str = "",
    ctx: ToolContext | None = None,
) -> str:
    """Exempt a skill from automatic stale/archived labelling (or undo it).

    The opt-out for deliberately-rare skills. A release-checklist skill
    that fires twice a year is not stale, it is seasonal; pinning says
    so once instead of re-litigating it on every report.

    Args:
        skill_name: Skill directory name (e.g. ``kitt-create-plans``).
        pinned: True to pin, False to release back to automatic
            lifecycle labelling.

    Returns:
        JSON with the resulting record, or an error message.
    """
    workspace, error = await _request_workspace(target_workspace_path, ctx)
    if error:
        return error
    if not _skill_usage.is_valid_skill_name(skill_name):
        return f"Error: '{skill_name}' is not a valid skill name."
    if not _skill_usage.set_pinned(skill_name, pinned):
        return (
            f"Error: could not update the pin for '{skill_name}'. The sidecar "
            f"at {_skill_usage.usage_path()} may not be writable."
        )
    installed = _installed_skill_names(workspace)
    record = _skill_usage.load_usage().get(skill_name, {})
    return json.dumps(
        {
            "name": skill_name,
            "pinned": record.get("pinned") is True,
            "state": record.get("state"),
            "count": record.get("count", 0),
            "installed": skill_name in installed,
            "note": (
                "Pinned skills are never labelled stale or archived. Nothing "
                "is ever moved or deleted by this label either way."
                if pinned
                else "Skill is back under automatic lifecycle labelling."
            ),
        },
        indent=2,
    )


def register(mcp: FastMCP) -> None:
    """Register the skill usage telemetry tools."""
    mcp.tool()(skill_usage_report)
    mcp.tool()(pin_skill)
