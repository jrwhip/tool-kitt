#!/bin/bash
# git-branch-guard.sh
# Claude Code PreToolUse hook. Blocks `git commit` and `git push` when the
# current branch does not match a configurable pattern (default: feature/*).
# Returns JSON to stdout; Claude Code reads it and allows or blocks the call.
#
# Configuration (env var):
#   BRANCH_GUARD_PATTERN  Glob pattern for allowed branches. Default: feature/*
#                         Examples: "feature/*", "feature/*|fix/*",
#                         "release/*", "*"
#
# Install: register as a PreToolUse hook in .claude/settings.json. The
# accompanying configure_git_guard.py script does this idempotently.

set -euo pipefail

PATTERN="${BRANCH_GUARD_PATTERN:-feature/*}"

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""')

# Only act on git commit or git push. Exit silently for everything else.
if ! printf '%s' "$CMD" | grep -qE '^git( -C [^ ]+)? (commit|push)'; then
  exit 0
fi

# Extract -C <dir> if the command targets a specific repo (macOS-compatible).
DIR=$(printf '%s' "$CMD" | sed -n 's/.*-C \([^ ]*\).*/\1/p' | head -1)

if [ -n "$DIR" ]; then
  BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null || echo "")
else
  BRANCH=$(git branch --show-current 2>/dev/null || echo "")
fi

# Bash glob match against the configured pattern.
# shellcheck disable=SC2053
if [[ "$BRANCH" == $PATTERN ]]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Branch %s matches pattern %s; commit/push allowed"}}\n' "$BRANCH" "$PATTERN"
else
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"block","permissionDecisionReason":"git commit/push blocked: branch %s does not match pattern %s"}}\n' "$BRANCH" "$PATTERN"
fi
