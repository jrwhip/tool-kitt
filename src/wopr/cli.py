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
    wopr build-plugins --out DIR     # Emit the plugin marketplace
    wopr learnings append --entry-file -   # Append a LEARNINGS entry
    wopr learnings search --req-id REQ-1   # Retrieve relevant entries
    wopr --version                   # Show version

Pack installation is not part of this surface. The prior toolset
deployed catalog content by symlinking it into each CLI's own
directories (``wopr --init``); that machinery is replaced by the
per-pack Claude Code plugins ``wopr build-plugins`` emits.

Parser shape: one subparser per subcommand, with the three workspace
options on a shared parent so they are accepted on either side of the
subcommand (``wopr --workspace X list`` and ``wopr list --workspace X``
both work, as they did under the previous flat parser).
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


def _workspace_options(*, suppress_defaults: bool) -> argparse.ArgumentParser:
    """Parent parser holding the options accepted on either side of the verb.

    ``suppress_defaults`` is not a style choice. Since Python 3.9 a
    subparser parses into a fresh namespace and copies every key back
    onto the parent's, defaults included, so a subcommand copy of
    ``--workspace`` silently overwrites the value the top level already
    parsed: ``wopr --workspace X list`` would resolve to the current
    directory. ``SUPPRESS`` keeps unsupplied subcommand options out of
    that copy, so the top-level value survives and an explicit
    subcommand value still wins.
    """
    default = argparse.SUPPRESS if suppress_defaults else None
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--workspace", "-w",
        metavar="PATH",
        default=default,
        help="Workspace path (for a subcommand, or for the MCP server)",
    )
    parent.add_argument(
        "--catalog",
        metavar="PATH",
        default=default,
        help="Path to external catalog directory",
    )
    parent.add_argument(
        "--global", "-g",
        dest="is_global",
        action="store_true",
        default=argparse.SUPPRESS if suppress_defaults else False,
        help="Inspect the global install (~/.wopr) instead of the workspace",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    """Build the full argument parser."""
    top_level = _workspace_options(suppress_defaults=False)
    common = _workspace_options(suppress_defaults=True)
    parser = argparse.ArgumentParser(
        prog="wopr",
        parents=[top_level],
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

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    subparsers.add_parser(
        "list", parents=[common], help="Show installed packs",
    )
    subparsers.add_parser(
        "catalog", parents=[common], help="Show all available packs",
    )

    help_parser = subparsers.add_parser(
        "help", parents=[common], help="Show help on a topic",
    )
    help_parser.add_argument(
        "topic", nargs="?", help="Help topic (omit for the topic index)",
    )

    # Flag-free by design: the skill-usage hook shells out to
    # ``wopr skill-usage record <source> <name>...`` and
    # ``skill_usage_cli`` owns the positional grammar.
    usage_parser = subparsers.add_parser(
        "skill-usage", parents=[common], help="Skill telemetry: report, record, pin",
    )
    usage_parser.add_argument(
        "args",
        nargs="*",
        help="report | record <source> <name>... | pin <name> | unpin <name>",
    )

    build_parser_ = subparsers.add_parser(
        "build-plugins",
        parents=[common],
        help="Generate the Claude Code plugin marketplace from the catalog",
    )
    build_parser_.add_argument(
        "--out",
        metavar="DIR",
        required=True,
        help=(
            "Output directory for the marketplace. Wiped and rewritten on "
            "every run; refused if it is non-empty and was not generated "
            "by this command."
        ),
    )

    learnings_parser = subparsers.add_parser(
        "learnings",
        parents=[common],
        help="Append to or search the LEARNINGS corpus without the MCP server",
    )
    learnings_sub = learnings_parser.add_subparsers(
        dest="learnings_action", metavar="ACTION",
    )

    append_parser = learnings_sub.add_parser(
        "append", parents=[common], help="Append one LEARNINGS.md entry",
    )
    entry_source = append_parser.add_mutually_exclusive_group(required=True)
    entry_source.add_argument(
        "--entry", metavar="MARKDOWN", help="Entry markdown as a literal string",
    )
    entry_source.add_argument(
        "--entry-file",
        metavar="PATH",
        help="Read the entry from a file, or from stdin with -",
    )
    append_parser.add_argument(
        "--origin",
        default="",
        metavar="SLUG",
        help="Provenance slug recorded in the entry meta block (e.g. crew-auditor)",
    )

    search_parser = learnings_sub.add_parser(
        "search", parents=[common], help="Retrieve the most relevant entries",
    )
    search_parser.add_argument("--req-id", default="", help="Exact REQ id to match")
    search_parser.add_argument(
        "--stack-tags",
        default="",
        metavar="A,B",
        help="Comma-separated stack tags to prefilter on",
    )
    search_parser.add_argument(
        "--max-age-days", type=int, default=180, help="Drop entries older than this",
    )
    search_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum entries to return",
    )
    search_parser.add_argument(
        "--summary",
        default="",
        metavar="TEXT",
        help="REQ summary for the optional semantic pass",
    )

    return parser


def _resolve_workspace(args: argparse.Namespace) -> Path:
    return Path(args.workspace or ".").expanduser().resolve()


def _run_learnings(args: argparse.Namespace) -> int:
    from .learnings_cli import cmd_learnings_append, cmd_learnings_search, read_entry

    workspace = _resolve_workspace(args)

    if args.learnings_action == "append":
        return cmd_learnings_append(
            workspace,
            entry_markdown=read_entry(args.entry, args.entry_file),
            origin=args.origin,
        )
    if args.learnings_action == "search":
        tags = [t.strip() for t in args.stack_tags.split(",") if t.strip()]
        return cmd_learnings_search(
            workspace,
            req_id=args.req_id,
            stack_tags=tags,
            max_age_days=args.max_age_days,
            limit=args.limit,
            req_summary=args.summary,
        )

    print(
        "Error: `wopr learnings` needs an action: append or search. "
        "Run `wopr learnings --help`.",
        file=sys.stderr,
    )
    return 2


def _run_build_plugins(args: argparse.Namespace) -> int:
    from .build_plugins import (
        BuildPluginsError,
        build_plugins,
        find_repo_root,
        format_build_report,
    )

    try:
        result = build_plugins(
            Path(args.out).expanduser().resolve(), find_repo_root()
        )
    except BuildPluginsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    logger.info("%s", format_build_report(result))
    return 0


def serve() -> int:
    """Run the MCP server. Entry point of the bundled ``wopr-serve`` script.

    ``wopr`` with no subcommand does the same thing. The plugin bundle
    gets its own console script so the launch contract in the emitted
    ``.mcp.json`` names an action rather than relying on a bare
    ``wopr`` invocation resolving to the server.
    """
    from .server import run_server

    return run_server(None)


def main(argv: list[str] | None = None) -> int:
    """Dispatch one CLI invocation.

    ``argv`` defaults to ``sys.argv[1:]``; passing it explicitly is what
    lets the tests drive the real parser instead of a reimplementation
    of it.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # CLI paths need user-facing logging; server configures its own
    if args.subcommand:
        _configure_logging()

    if args.subcommand == "list":
        from .manager import cmd_list

        return cmd_list(_resolve_workspace(args), is_global=args.is_global)

    if args.subcommand == "catalog":
        from .manager import cmd_catalog

        return cmd_catalog(args.catalog)

    if args.subcommand == "skill-usage":
        from .skill_usage_cli import cmd_skill_usage

        return cmd_skill_usage(args.args, _resolve_workspace(args))

    if args.subcommand == "help":
        from .help import get_help

        print(get_help(args.topic, _resolve_workspace(args)))
        return 0

    if args.subcommand == "build-plugins":
        return _run_build_plugins(args)

    if args.subcommand == "learnings":
        return _run_learnings(args)

    # Run MCP server
    from .server import run_server

    return run_server(args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
