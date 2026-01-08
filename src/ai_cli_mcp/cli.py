#!/usr/bin/env python3
"""
CLI entry point for Tool-KITT.

Usage:
    tool-kitt              # Run MCP server
    tool-kitt --init       # Initialize in current directory
    tool-kitt --init PATH  # Initialize in specified directory
    tool-kitt --version    # Show version
"""

import argparse
import sys
from pathlib import Path

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tool-kitt",
        description="Your AI coding assistant's Swiss Army knife - MCP server for Claude, Gemini, and Copilot CLIs",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"tool-kitt {__version__}",
    )
    parser.add_argument(
        "--init",
        nargs="?",
        const=".",
        metavar="PATH",
        help="Initialize workspace at PATH (default: current directory)",
    )
    parser.add_argument(
        "--workspace", "-w",
        metavar="PATH",
        help="Workspace path for MCP server (overrides AI_CLI_WORKSPACE env var)",
    )

    args = parser.parse_args()

    if args.init is not None:
        from .init import initialize_workspace
        workspace_path = Path(args.init).expanduser().resolve()
        return initialize_workspace(workspace_path)

    # Run MCP server
    from .server import run_server
    workspace = args.workspace
    return run_server(workspace)


if __name__ == "__main__":
    sys.exit(main())
