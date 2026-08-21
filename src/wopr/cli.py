#!/usr/bin/env python3
"""CLI entry point for WOPR.

Usage:
    wopr                             # Run MCP server (stdio)
    wopr list                        # Show installed packs
    wopr catalog                     # Show all available packs
    wopr help                        # Show help topics
    wopr help packs                  # Help on a specific topic
    wopr skill-usage report          # Observed skill usage (a lower bound)
    wopr skill-usage pin NAME        # Never mark a rare skill stale
    wopr --version                   # Show version

Pack installation is not part of this surface. The prior toolset
deployed catalog content by symlinking it into each CLI's own
directories (``wopr --init``); that machinery is being replaced by
per-pack Claude Code plugins, so it is deliberately absent here.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__

logger = logging.getLogger("wopr")


def _configure_logging() -> None:
    """Configure logging so user-facing output matches previous print() style."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Prevent duplicate output from root logger
    logger.propagate = False


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="wopr",
        description=(
            "WOPR: a right-sized agent harness for Claude Code. "
            "Runs as an MCP server when given no subcommand."
        ),
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"wopr {__version__}",
    )
    parser.add_argument(
        "--workspace", "-w",
        metavar="PATH",
        help="Workspace path (for a subcommand, or for the MCP server)",
    )
    parser.add_argument(
        "--catalog",
        metavar="PATH",
        help="Path to external catalog directory",
    )
    parser.add_argument(
        "--global", "-g",
        dest="is_global",
        action="store_true",
        help="Inspect the global install (~/.wopr) instead of the workspace",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        choices=["list", "catalog", "help", "skill-usage"],
        help="Pack inspection or telemetry subcommand",
    )
    parser.add_argument(
        "subcommand_args",
        nargs="*",
        help=(
            "Arguments for the subcommand (a help topic, or a skill-usage "
            "action: report | record <source> <name>... | pin | unpin)"
        ),
    )

    args = parser.parse_args()

    # CLI paths need user-facing logging; server configures its own
    if args.subcommand:
        _configure_logging()

    if args.subcommand:
        workspace = Path(args.workspace or ".").expanduser().resolve()

        if args.subcommand == "list":
            from .manager import cmd_list
            return cmd_list(workspace, is_global=args.is_global)

        elif args.subcommand == "catalog":
            from .manager import cmd_catalog
            return cmd_catalog(args.catalog)

        elif args.subcommand == "skill-usage":
            from .skill_usage_cli import cmd_skill_usage
            return cmd_skill_usage(args.subcommand_args, workspace)

        elif args.subcommand == "help":
            from .help import get_help
            topic = args.subcommand_args[0] if args.subcommand_args else None
            print(get_help(topic, workspace))
            return 0

    # Run MCP server
    from .server import run_server
    workspace_arg = args.workspace
    return run_server(workspace_arg)


if __name__ == "__main__":
    raise SystemExit(main())
