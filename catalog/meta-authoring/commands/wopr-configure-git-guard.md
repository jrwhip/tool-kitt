---
description: Register the git-branch-guard PreToolUse hook in this project's .claude/settings.json
---

Register the WOPR git-branch-guard PreToolUse hook in this project. Idempotent; safe to re-run.

The hook intercepts every `Bash` tool call. If the command is `git commit` or `git push` and the current branch does not match the configured pattern (default: `feature/*`), it blocks the call with an error message that surfaces back to Claude. All other Bash commands pass through.

**Preview without making changes:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_git_guard.py" --dry-run
```

**Apply:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_git_guard.py"
```

**Target a project other than the current directory:**

```
! WOPR_DIR=$(python3 -c "import wopr, pathlib; print(pathlib.Path(wopr.__file__).parent / 'resources')") && python3 "$WOPR_DIR/meta-authoring/scripts/configure_git_guard.py" --project-root /path/to/project
```

**After running:** Restart Claude Code for the PreToolUse hook to take effect.

**What it does:**

1. Makes the guard script (`meta-authoring/hooks/git-branch-guard.sh`) executable.
2. Reads `.claude/settings.json` (creates it if missing), removes any conflicting `Bash(git commit *)` or `Bash(git push *)` entries from `permissions.allow` / `permissions.deny` (the hook supersedes them with branch-conditional logic), then appends the PreToolUse hook entry. All other settings and hooks are preserved.

**Branch rule (default):**

| Branch | `git commit` | `git push` |
|---|---|---|
| `feature/*` | allowed | allowed |
| anything else | blocked | blocked |

**Customizing the pattern:** the hook honors the `BRANCH_GUARD_PATTERN` environment variable. Set it in your shell profile or in the `env` block of the project's `.claude/settings.json` to allow additional branches. Examples: `feature/*`, `feature/*|fix/*`, `release/*`.

**Idempotent.** Re-running is safe. Already-completed steps are skipped and reported as `ok`.

**Required:** WOPR must be installed (`pipx install wopr` or equivalent) so the `wopr` package is importable. The `python3 -c` shim resolves the meta-authoring scripts directory regardless of where WOPR was installed. The guard script itself uses `jq`; install it with `brew install jq` on macOS or your distribution's package manager on Linux.
