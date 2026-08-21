"""``wopr skill-usage`` subcommand: record, report, pin, unpin.

Two audiences, one store (:mod:`tools._skill_usage`):

* **Hooks.** The Claude Code ``skill-usage-hook.py`` Stop hook runs as a
  standalone stdlib script in its own process and cannot import WOPR.
  Rather than reimplement the sidecar schema there (which guarantees the
  two copies drift), the hook shells out to ``wopr skill-usage record``.
  ``wopr`` being on PATH is already a hard requirement of every install
  -- the MCP registrations write ``"command": "wopr"`` with no path.
* **Operators.** ``wopr skill-usage report`` answers "which skills does
  anyone actually use" from a terminal, and ``pin``/``unpin`` set the
  never-mark-stale opt-out without needing an agent session.

Flag-free by design: ``cli.py``'s top-level parser owns all option
parsing, and subcommand arguments arrive as a bare list of positionals.
Hence ``record <source> <name>...`` rather than ``record --source=...``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import ServerConfig
from .context import ServerContext
from .tools import _skill_usage

logger = logging.getLogger("wopr")

USAGE = (
    "Usage:\n"
    "  wopr skill-usage report                  # observed usage per skill\n"
    "  wopr skill-usage record <source> <name>... # count invocations\n"
    "  wopr skill-usage pin <name>              # never mark stale\n"
    "  wopr skill-usage unpin <name>\n"
    f"\nValid sources: {', '.join(sorted(_skill_usage.KNOWN_SOURCES))}"
)


def installed_skill_names(workspace: Path | None) -> list[str]:
    """Skill directory names reachable from the shared resource dirs.

    Goes through :class:`ServerContext` rather than globbing paths
    directly so the CLI and the MCP tool agree on what "installed"
    means. Initializing the context here is process-local state on a
    short-lived CLI invocation; it writes nothing.
    """
    try:
        ctx = ServerContext.get()
    except RuntimeError:
        ctx = ServerContext.init(ServerConfig.from_env())
    names: set[str] = set()
    for skills_dir in ctx.resource_dirs("skills", workspace):
        try:
            entries = list(skills_dir.iterdir())
        except OSError:
            continue
        names.update(
            d.name for d in entries if d.is_dir() and (d / "SKILL.md").exists()
        )
    return sorted(names)


def _cmd_record(args: list[str]) -> int:
    if len(args) < 2:
        logger.error("Error: 'record' needs a source and at least one skill name.")
        logger.error("%s", USAGE)
        return 1
    source, names = args[0], args[1:]
    if source not in _skill_usage.KNOWN_SOURCES:
        logger.error(
            "Error: unknown source '%s'. Valid sources: %s",
            source,
            ", ".join(sorted(_skill_usage.KNOWN_SOURCES)),
        )
        return 1
    # Repeated names mean repeated invocations; collapse to one write per
    # name so a busy transcript costs one read-modify-write per skill
    # instead of one per occurrence.
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    recorded = 0
    for name, count in sorted(counts.items()):
        if _skill_usage.record_invocation(name, source, count=count):
            recorded += count
        else:
            logger.warning("  Skipped '%s' (invalid name or unwritable sidecar)", name)
    logger.info(
        "Recorded %d invocation(s) across %d skill(s) from %s",
        recorded,
        len(counts),
        source,
    )
    return 0


def _cmd_report(workspace: Path | None) -> int:
    payload = _skill_usage.report(installed_skill_names(workspace))
    rows = payload["skills"]
    logger.info("Skill usage (%s)", payload["sidecar"])
    logger.info(
        "  %d skills tracked, %d observed at least once, %d pinned",
        payload["totals"]["skills"],
        payload["totals"]["observed"],
        payload["totals"]["pinned"],
    )
    if not rows:
        logger.info("  No skills found in this workspace's shared dirs.")
        return 0
    logger.info("")
    logger.info("  %-40s %6s  %-9s %s", "SKILL", "COUNT", "STATE", "SOURCES")
    for row in sorted(rows, key=lambda r: (-int(r["count"]), str(r["name"]))):
        sources = ", ".join(f"{k}={v}" for k, v in sorted(row["sources"].items()))
        flags = " [pinned]" if row["pinned"] else ""
        flags += "" if row["installed"] else " [not installed]"
        logger.info(
            "  %-40s %6d  %-9s %s%s",
            row["name"][:40],
            row["count"],
            row["state"],
            sources or "-",
            flags,
        )
    logger.info("")
    logger.info("Counts are a LOWER BOUND. %s", payload["coverage"]["reading_zero"])
    for gap in payload["coverage"]["uncovered"]:
        logger.info("  Not counted: %s", gap)
    return 0


def _cmd_pin(args: list[str], pinned: bool) -> int:
    if not args:
        logger.error("Error: '%s' needs a skill name.", "pin" if pinned else "unpin")
        logger.error("%s", USAGE)
        return 1
    failed = False
    for name in args:
        if _skill_usage.set_pinned(name, pinned):
            logger.info("  %s %s", "Pinned" if pinned else "Unpinned", name)
        else:
            logger.error("  Could not update '%s'", name)
            failed = True
    return 1 if failed else 0


def cmd_skill_usage(args: list[str], workspace: Path | None = None) -> int:
    """Dispatch ``wopr skill-usage <action> [args...]``."""
    if not args:
        logger.error("%s", USAGE)
        return 1
    action, rest = args[0], args[1:]
    if action == "record":
        return _cmd_record(rest)
    if action == "report":
        return _cmd_report(workspace)
    if action in ("pin", "unpin"):
        return _cmd_pin(rest, action == "pin")
    logger.error("Error: unknown skill-usage action '%s'.", action)
    logger.error("%s", USAGE)
    return 1
