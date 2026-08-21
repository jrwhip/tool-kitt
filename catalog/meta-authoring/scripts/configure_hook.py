#!/usr/bin/env python3
"""
configure_hook.py

Register any WOPR hook declared by a ``<name>.HOOK.yaml`` manifest into a
project, for any CLI that hook declares a target for. Idempotent: re-running
reconciles the existing entry in place instead of appending a duplicate,
including after the handler's absolute path has changed.

Replaces the former per-hook, per-CLI scripts
(``configure_capture_skill_hook.py`` and
``configure_capture_skill_hook_copilot.py``), which were near-identical apart
from the event name, the config file, and the entry shape -- all three of
which are now declared in the manifest and rendered by
``ai_cli_mcp.hook_manifest``.

Usage:
  python3 configure_hook.py --hook NAME --cli claude|copilot \
      [--project-root PATH] [--dry-run]
  python3 configure_hook.py --list

Default project root is the current working directory. Hook manifests are
read from the ``hooks/`` directory beside this script's pack.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_cli_mcp.hook_manifest import (
    HookManifestError,
    discover_hook_manifests,
    find_hook_manifest,
    register_hook,
)

SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent / "hooks"

_OUTCOME = {
    "registered": "registered",
    "updated": "reconciled (path or fields changed)",
    "unchanged": "already current -- nothing to do",
}


def _list_hooks() -> int:
    specs = discover_hook_manifests(HOOKS_DIR)
    if not specs:
        print(f"No hook manifests found in {HOOKS_DIR}")
        return 1
    print(f"Hooks declared in {HOOKS_DIR}:\n")
    for spec in specs:
        clis = ", ".join(
            f"{cli} ({t.event})" for cli, t in sorted(spec.targets.items())
        )
        print(f"  {spec.name}")
        print(f"    {spec.description}")
        print(f"    targets: {clis}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--hook", help="Hook name as declared in its HOOK.yaml.")
    parser.add_argument(
        "--cli",
        choices=("claude", "copilot"),
        help="Which CLI to register the hook for.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current working directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available hooks and their declared targets, then exit.",
    )
    args = parser.parse_args()

    if args.list:
        return _list_hooks()
    if not args.hook or not args.cli:
        parser.error("--hook and --cli are required (or use --list)")

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        sys.exit(f"ERROR: project root '{project_root}' is not a directory.")

    try:
        spec = find_hook_manifest(HOOKS_DIR, args.hook)
        target = spec.target(args.cli)
    except HookManifestError as e:
        sys.exit(f"ERROR: {e}")

    print("=" * 60)
    print(f"  Configure hook: {spec.name} ({args.cli})")
    print("=" * 60)
    print(f"  Project root : {project_root}")
    print(f"  Event        : {target.event}")
    print(f"  Handler      : {target.handler}")
    if args.dry_run:
        print("  Dry-run      : ON; no changes will be made")
    print()

    try:
        result, config_path = register_hook(
            spec, args.cli, project_root, dry_run=args.dry_run
        )
    except HookManifestError as e:
        sys.exit(f"ERROR: {e}")

    prefix = "[dry-run] would be " if args.dry_run else ""
    print(f"  {prefix}{_OUTCOME[result]} in {config_path}")
    print()
    if not args.dry_run and args.cli == "claude":
        print("  Restart Claude Code for the hook to take effect.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
