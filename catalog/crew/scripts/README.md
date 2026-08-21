# crew scripts

Orchestration scripts for the crew pack. These are not agents or skills; they are deterministic infrastructure that does mechanical work the crew relies on. **Scripts cost zero tokens.** Whenever a step in `wopr-run-crew` is fully deterministic given known inputs and produces a known output shape, it belongs here rather than as an agent dispatch. See "Scripts vs agents" in `catalog/crew/README.md` for the heuristic.

## Inventory

| Script | Purpose | When to use |
|---|---|---|
| `autorun.sh` | Unattended-run loop for long AI CLI sessions. Detects rate-limit exits, waits for the reset window, and resumes automatically. CLI-agnostic via environment-variable overrides. | Multi-hour crew runs that outlast a single rate-limit window; overnight runs. |

`legacy-migration` pack ships additional scripts (`extract_legacy_context.py`, `run_schema_extractor.sh`, `extract_pg_schema.sh`) for migration projects. See `catalog/legacy-migration/scripts/README.md` for that inventory.

## `autorun.sh`

Unattended-run loop for long AI CLI sessions. Detects rate-limit exits, waits for the reset window, and resumes automatically. Stops and notifies when the CLI is asking for human input. Otherwise exits with an informative code for supervised review.

CLI-agnostic by design. Defaults target Claude Code (`claude --resume -y`, Claude Code's rate-limit and question phrasing), but every CLI-specific value is overridable via an environment variable. Point it at any CLI that supports resumable sessions and produces matchable rate-limit output.

### When to use it

- Multi-hour agent crews that outlast a single rate-limit window (scout to coder to tester to auditor loops)
- Overnight runs where you want the crew to progress while you sleep
- Any workflow where you know the work is long and the only expected blocker is rate limits

### When NOT to use it

- Short interactive work where you want to see every prompt before it runs
- Sessions where the CLI might legitimately need to ask questions about every step (the script stops on detected questions, but false negatives will cause unattended progress you didn't review)
- Work requiring tight supervision (reviews, architecture decisions, anything with irreversible consequences)

### Required environment variables

| Variable | Purpose |
|---|---|
| `WORK_DIR` | Absolute path to the project the agents are working on. The script `cd`s here before launching the CLI. |

### Optional environment variables (CLI invocation)

| Variable | Default | Purpose |
|---|---|---|
| `CLI_RESUME_CMD` | `claude --resume -y` | The command to run each iteration. The resume message is piped to this command on stdin. |
| `RESUME_MESSAGE` | `continue` | Text piped to `CLI_RESUME_CMD` on each iteration to kick the agent back into motion. |

### Optional environment variables (output matching)

| Variable | Default | Purpose |
|---|---|---|
| `RATE_LIMIT_PATTERN` | `You've hit your limit\|resets [0-9]+[ap]m` | Extended regex applied to the session output tail to detect rate-limit exits. |
| `RESET_TIME_PATTERN` | `[0-9]+[ap]m` | Extended regex matching the reset-time token itself. Used to compute an accurate wait window. |
| `NEEDS_INPUT_PATTERN` | see script | Extended regex matching phrases the CLI uses when it needs human direction. Rate-limit detection takes precedence. |

### Optional environment variables (paths)

| Variable | Default | Purpose |
|---|---|---|
| `SCRIPT_DIR` | `$WORK_DIR/.autorun` | Where run artifacts land (log file, last session output, etc). |
| `LOG_FILE` | `$SCRIPT_DIR/autorun_YYYYMMDD.log` | Combined stdout/stderr log for the autorun loop. |
| `SESSION_OUTPUT` | `$SCRIPT_DIR/.last_session_output.txt` | Captures the tail of the most recent session, used by rate-limit and user-input detection. |
| `PROMPT_LOG` | empty (disabled) | Optional path to a prompt log file. When set, lifecycle events (session resumed, rate limit hit, paused for input) get appended here. Works alongside `prompt-log-hook.py` in `meta-authoring/hooks/`. |

### Optional environment variables (timing)

| Variable | Default | Purpose |
|---|---|---|
| `WAIT_TIME` | `18000` | Fallback wait in seconds when the reset time could not be parsed. 5 hours. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Manual Ctrl+C during a session. Clean exit. |
| `1` | Session ended for an unknown reason (task complete, error, or something the heuristics didn't classify). Review the output. |
| `2` | CLI explicitly asked for human input. The script paused. Review the session output and respond manually. |
| `64` | Usage error. `WORK_DIR` was not set or does not point at a directory. |

### Usage

Minimal (defaults to Claude Code):

```sh
WORK_DIR=/Users/you/Projects/my-migration ./autorun.sh
```

Integrated with the meta-authoring prompt log hook:

```sh
WORK_DIR=/Users/you/Projects/my-migration \
PROMPT_LOG=/Users/you/Projects/my-migration/PROMPT_LOG.md \
./autorun.sh
```

Custom wait and resume message:

```sh
WORK_DIR=/Users/you/Projects/my-migration \
WAIT_TIME=3600 \
RESUME_MESSAGE="proceed with the next task" \
./autorun.sh
```

Pointed at a different CLI (hypothetical example; adjust to whatever your CLI actually uses for resume):

```sh
WORK_DIR=/Users/you/Projects/my-migration \
CLI_RESUME_CMD="some-other-cli --resume" \
RATE_LIMIT_PATTERN="rate limit hit|try again in" \
RESET_TIME_PATTERN="[0-9]+:[0-9]+" \
./autorun.sh
```

### Heuristics used for control flow

**Rate-limit detection:** greps the last 100 lines of session output against `RATE_LIMIT_PATTERN`. If it matches, the script extracts the reset time using `RESET_TIME_PATTERN`, computes a wait window from it (plus a 5-minute buffer), and sleeps before resuming. Defaults match Claude Code's output format (`You've hit your limit ... resets Xam|pm`).

**User-input detection:** greps the last 50 lines of session output against `NEEDS_INPUT_PATTERN`. Defaults match common question phrases used by Claude Code. Rate-limit detection takes precedence; a rate-limit exit is never treated as a question.

Both heuristics are intentionally narrow to avoid false positives. False negatives will happen. Use this script only on work where you are comfortable with the agent making progress between your checks.

### Platform notes

- Script targets zsh and uses `((...))` arithmetic. Test before running on other shells.
- macOS notifications via `osascript` are best-effort. On non-macOS platforms, the notification call is a silent no-op.
- The "next attempt at" timestamp tries the BSD `date -v` flavor first and falls back to the GNU `date -d` flavor, so it should print correctly on both macOS and Linux.

## Provenance

Adapted from a project-specific version authored by [colleague] for the `webteam-[client-project-b]-api` migration POV. The original hardcoded working directory paths, the prompt log file location, and the CLI invocation (`claude --resume -y`). This version accepts all three via environment variables, disables prompt-log integration by default (so callers opt in rather than opt out), and parameterizes the rate-limit and user-input detection regexes so the script works with any CLI that has resumable sessions. Original source: `research/seeds/client-project-b-api/scripts/claude-autorun.sh`.
