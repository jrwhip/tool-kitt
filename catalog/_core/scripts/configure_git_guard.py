#!/usr/bin/env python3
"""
configure_git_guard.py

Registers the git-branch-guard.sh PreToolUse hook in
<project-root>/.claude/settings.json. Removes any conflicting
`Bash(git commit *)` and `Bash(git push *)` entries from the project's
permissions.allow / permissions.deny lists, since the hook now provides
the branch-conditional logic those static rules used to approximate.

Idempotent: re-running skips work that is already done.

Usage:
  python3 configure_git_guard.py [--project-root PATH] [--dry-run]

Default project root is the current working directory. Guard script path
is resolved relative to this script's location in the kitt-core plugin's
scripts/ directory (a sibling of hooks/).

Only Python stdlib is used.
"""

import argparse
import json
import shlex
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GUARD_PATH = (SCRIPT_DIR.parent / "hooks" / "git-branch-guard.sh").resolve()

REPLACED_RULES = {"Bash(git commit *)", "Bash(git push *)"}


def configure_git_guard(settings_path: Path, hook_command: str, dry_run: bool) -> None:
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ERROR: {settings_path} contains invalid JSON: {e}")
            print("  Fix the JSON manually before re-running this script.")
            sys.exit(1)
    else:
        settings = {}
        print(f"  note     {settings_path} does not exist; will create it")

    pre_hooks = settings.get("hooks", {}).get("PreToolUse", [])
    for entry in pre_hooks:
        for h in entry.get("hooks", []):
            if h.get("command", "") == hook_command:
                print(f"  ok       PreToolUse hook already registered in {settings_path}")
                return

    permissions = settings.setdefault("permissions", {})
    removed_allow: list[str] = []
    removed_deny: list[str] = []

    for key in ("allow", "deny"):
        original = permissions.get(key, [])
        filtered = [r for r in original if r not in REPLACED_RULES]
        removed = [r for r in original if r in REPLACED_RULES]
        if removed:
            permissions[key] = filtered
            if key == "allow":
                removed_allow = removed
            else:
                removed_deny = removed

    hooks = settings.setdefault("hooks", {})
    hooks.setdefault("PreToolUse", []).append({
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": hook_command}],
    })

    new_text = json.dumps(settings, indent=2) + "\n"

    if dry_run:
        print(f"  [dry-run] would register PreToolUse hook in {settings_path}")
        print(f"  [dry-run] command: {hook_command}")
        if removed_allow:
            print(f"  [dry-run] would remove from allow: {removed_allow}")
        if removed_deny:
            print(f"  [dry-run] would remove from deny: {removed_deny}")
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(new_text, encoding="utf-8")
    print(f"  registered PreToolUse hook in {settings_path}")
    print(f"  command: {hook_command}")
    if removed_allow:
        print(f"  removed from allow: {removed_allow}")
    if removed_deny:
        print(f"  removed from deny: {removed_deny}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        sys.exit(f"ERROR: project root '{project_root}' is not a directory.")

    if not GUARD_PATH.exists():
        sys.exit(
            f"ERROR: guard script not found at {GUARD_PATH}.\n"
            "Verify the kitt-core plugin is installed correctly."
        )

    hook_command = f"bash {shlex.quote(str(GUARD_PATH))}"
    settings_path = project_root / ".claude" / "settings.json"

    print("=" * 60)
    print("  Configure Git Branch Guard")
    print("=" * 60)
    print(f"  Project root : {project_root}")
    print(f"  Guard script : {GUARD_PATH}")
    if args.dry_run:
        print("  Dry-run      : ON; no changes will be made")
    print()

    if args.dry_run:
        print(f"  [dry-run] would chmod +x {GUARD_PATH}")
    else:
        current_mode = GUARD_PATH.stat().st_mode
        GUARD_PATH.chmod(current_mode | 0o111)
        print(f"  chmod +x     {GUARD_PATH}")

    configure_git_guard(settings_path, hook_command, args.dry_run)

    print()
    if not args.dry_run:
        print("  Done. Restart Claude Code for the PreToolUse hook to take effect.")
    print("=" * 60)


if __name__ == "__main__":
    main()
