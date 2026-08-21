#!/bin/zsh
# autorun.sh
#
# Unattended-run loop for long AI CLI sessions. Detects rate-limit exits,
# waits for the reset window, and resumes automatically. Stops and notifies
# when the CLI is asking for human input. Otherwise exits with an informative
# code for supervised review.
#
# Primary use case: long-running migration crews (legacy-migration pack's
# scout to coder to tester to auditor loop, or any other multi-hour agent
# workflow) that outlast a single rate-limit window.
#
# CLI-agnostic by design. Default values target Claude Code (`claude --resume
# -y`, Claude Code's rate-limit and question phrasing), but every CLI-specific
# value is overridable via an environment variable. Point it at any CLI that
# supports resumable sessions and produces matchable rate-limit output.
#
# ------------------------------------------------------------------------------
# Required environment variables
# ------------------------------------------------------------------------------
#   WORK_DIR        Absolute path to the project the agents are working on.
#                   The script will cd into this directory before launching
#                   the CLI.
#
# ------------------------------------------------------------------------------
# Optional environment variables (CLI invocation)
# ------------------------------------------------------------------------------
#   CLI_RESUME_CMD  The command to run each iteration. The resume message is
#                   piped to this command on stdin.
#                   Default: "claude --resume -y"
#                   Example for another CLI: CLI_RESUME_CMD="gemini --continue"
#
#   RESUME_MESSAGE  Text piped to CLI_RESUME_CMD on stdin at each iteration to
#                   kick the agent back into motion.
#                   Default: "continue"
#
# ------------------------------------------------------------------------------
# Optional environment variables (output matching)
# ------------------------------------------------------------------------------
#   RATE_LIMIT_PATTERN  Extended regex applied to the tail of SESSION_OUTPUT
#                       to detect rate-limit exits. Defaults match Claude
#                       Code's phrasing.
#                       Default: "You've hit your limit|resets [0-9]+[ap]m"
#
#   RESET_TIME_PATTERN  Extended regex matching the reset-time token itself.
#                       Used to compute an accurate wait window. The first
#                       "Nam" or "Npm" style match is used. Defaults match
#                       Claude Code's phrasing.
#                       Default: "[0-9]+[ap]m"
#
#   NEEDS_INPUT_PATTERN Extended regex matching phrases the CLI uses when it
#                       is asking for human direction. Rate-limit detection
#                       takes precedence.
#                       Default matches Claude Code's common question phrases.
#
# ------------------------------------------------------------------------------
# Optional environment variables (paths)
# ------------------------------------------------------------------------------
#   SCRIPT_DIR      Directory for run artifacts (log file, last-session-output,
#                   etc). Default: $WORK_DIR/.autorun
#
#   LOG_FILE        Combined stdout/stderr log for the autorun loop.
#                   Default: $SCRIPT_DIR/autorun_YYYYMMDD.log
#
#   SESSION_OUTPUT  File that captures the tail of the most recent session,
#                   used by rate-limit and user-input detection.
#                   Default: $SCRIPT_DIR/.last_session_output.txt
#
#   PROMPT_LOG      Optional prompt log file to append lifecycle entries to
#                   (session resume, rate-limit, paused-for-input, etc).
#                   When unset or empty, lifecycle logging is skipped.
#                   Default: empty (disabled). Set to
#                   "$WORK_DIR/PROMPT_LOG.md" to integrate with the
#                   prompt-log-hook.py hook in meta-authoring.
#
# ------------------------------------------------------------------------------
# Optional environment variables (timing)
# ------------------------------------------------------------------------------
#   WAIT_TIME       Fallback wait in seconds when a reset time could not be
#                   parsed from the session output. Default: 18000 (5 hours).
#
# ------------------------------------------------------------------------------
# Exit codes
# ------------------------------------------------------------------------------
#   0   Manual Ctrl+C during a session
#   1   Session ended for an unknown reason (task complete, error, or
#       something the heuristics didn't classify)
#   2   CLI explicitly asked for human input; autorun paused, review
#       the session output and respond manually
#   64  Usage error (WORK_DIR missing or not a directory)
#
# ------------------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------------------
#   WORK_DIR=/path/to/project ./autorun.sh
#
# With prompt-log integration:
#   WORK_DIR=/path/to/project \
#   PROMPT_LOG=/path/to/project/PROMPT_LOG.md \
#   ./autorun.sh
#
# Pointed at a different CLI:
#   WORK_DIR=/path/to/project \
#   CLI_RESUME_CMD="some-other-cli --resume" \
#   RATE_LIMIT_PATTERN="rate limit hit|try again in" \
#   ./autorun.sh
#
# ------------------------------------------------------------------------------

set -u

# ---- Required variable check -------------------------------------------------

if [ -z "${WORK_DIR:-}" ]; then
    echo "autorun.sh: WORK_DIR is required." >&2
    echo "  Set WORK_DIR to the absolute path of the project the agents will work on." >&2
    echo "  Example: WORK_DIR=/Users/you/Projects/my-migration ./autorun.sh" >&2
    exit 64
fi

if [ ! -d "$WORK_DIR" ]; then
    echo "autorun.sh: WORK_DIR does not exist or is not a directory: $WORK_DIR" >&2
    exit 64
fi

# ---- Defaults for optional variables -----------------------------------------

SCRIPT_DIR="${SCRIPT_DIR:-$WORK_DIR/.autorun}"
mkdir -p "$SCRIPT_DIR"

LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/autorun_$(date +%Y%m%d).log}"
SESSION_OUTPUT="${SESSION_OUTPUT:-$SCRIPT_DIR/.last_session_output.txt}"
PROMPT_LOG="${PROMPT_LOG:-}"
WAIT_TIME="${WAIT_TIME:-18000}"
RESUME_MESSAGE="${RESUME_MESSAGE:-continue}"

CLI_RESUME_CMD="${CLI_RESUME_CMD:-claude --resume -y}"
RATE_LIMIT_PATTERN="${RATE_LIMIT_PATTERN:-You've hit your limit|resets [0-9]+[ap]m}"
RESET_TIME_PATTERN="${RESET_TIME_PATTERN:-[0-9]+[ap]m}"
NEEDS_INPUT_PATTERN="${NEEDS_INPUT_PATTERN:-(what would you like|do you want me to|should I |how would you like|want me to proceed|shall I |please (clarify|provide|confirm|let me know)|which option|waiting for your|need your input)}"

cd "$WORK_DIR" || { echo "Failed to cd to $WORK_DIR" >&2; exit 1; }

# ---- Helpers -----------------------------------------------------------------

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" | tee -a "$LOG_FILE"
}

log "======================================"
log "autorun.sh started"
log "Working Directory: $WORK_DIR"
log "Script Directory:  $SCRIPT_DIR"
log "Log File:          $LOG_FILE"
log "Prompt Log:        ${PROMPT_LOG:-(disabled)}"
log "CLI Resume Cmd:    $CLI_RESUME_CMD"
log "Resume Message:    \"$RESUME_MESSAGE\""
log "Fallback Wait:     ${WAIT_TIME}s"
log "======================================"

# Detect rate limit from the last session's output
check_rate_limited() {
    local last_lines=$(tail -100 "$SESSION_OUTPUT" 2>/dev/null)
    if echo "$last_lines" | grep -qiE "$RATE_LIMIT_PATTERN"; then
        return 0
    fi
    return 1
}

# Calculate seconds to wait until the reset time plus a 5-minute buffer
calculate_wait_time() {
    local last_lines=$(tail -100 "$SESSION_OUTPUT" 2>/dev/null)
    local reset_time=$(echo "$last_lines" | grep -oE "$RESET_TIME_PATTERN" | tail -1)

    if [ -n "$reset_time" ]; then
        local hour=$(echo "$reset_time" | grep -oE "[0-9]+")
        local ampm=$(echo "$reset_time" | grep -oE "[ap]m")

        if [ "$ampm" = "pm" ] && [ "$hour" -ne 12 ]; then
            hour=$((hour + 12))
        elif [ "$ampm" = "am" ] && [ "$hour" -eq 12 ]; then
            hour=0
        fi

        local current_hour=$(date +%H)
        local current_min=$(date +%M)

        local target_seconds=$((hour * 3600 + 300))   # reset hour + 5 min buffer
        local current_seconds=$((current_hour * 3600 + current_min * 60))
        local wait=$((target_seconds - current_seconds))

        if [ $wait -lt 0 ]; then
            wait=$((wait + 86400))  # reset is tomorrow
        fi

        # Clamp: minimum 5 minutes, maximum 6 hours
        if [ $wait -lt 300 ]; then
            wait=300
        elif [ $wait -gt 21600 ]; then
            wait=21600
        fi

        echo $wait
        return
    fi

    echo $WAIT_TIME  # fallback
}

# Detect explicit requests for human input. Rate-limit exits are excluded
# first so they take precedence over the question heuristic.
check_needs_user_input() {
    local last_lines=$(tail -50 "$SESSION_OUTPUT" 2>/dev/null)

    if check_rate_limited; then
        return 1  # rate limit takes precedence, not a question
    fi

    if echo "$last_lines" | grep -qiE "$NEEDS_INPUT_PATTERN"; then
        return 0  # CLI is asking for human direction
    fi
    return 1
}

# Append a structured entry to the optional prompt log
update_prompt_log() {
    local event="$1"
    local session_num=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M')

    if [ -z "$PROMPT_LOG" ]; then
        return
    fi

    cat >> "$PROMPT_LOG" << EOF

---

**[AUTO-SESSION $session_num - $event] $timestamp**
> $event via autorun.sh.

EOF
    log "Updated prompt log: $event (session $session_num)"
}

# macOS notification (silent no-op on other platforms)
notify() {
    osascript -e "display notification \"$1\" with title \"autorun.sh\" sound name \"Ping\"" 2>/dev/null
}

# ---- Main loop ---------------------------------------------------------------

SESSION_COUNT=0

while true; do
    ((SESSION_COUNT++))
    log ""
    log "-------- Session $SESSION_COUNT Start --------"

    # Log resume to the prompt log at the start of every resumed session
    if [ $SESSION_COUNT -gt 1 ]; then
        update_prompt_log "Session resumed after rate limit reset" $SESSION_COUNT
    fi

    # Clear previous session output
    > "$SESSION_OUTPUT"

    # Pipe the resume message on stdin so the CLI continues working
    # autonomously after resume. The default CLI_RESUME_CMD uses -y to
    # auto-accept permission prompts; other CLIs will need an equivalent.
    echo "$RESUME_MESSAGE" | eval "$CLI_RESUME_CMD" 2>&1 | tee -a "$LOG_FILE" | tee "$SESSION_OUTPUT"

    EXIT_CODE=$?
    log "Session ended with exit code: $EXIT_CODE"

    # Ctrl+C means clean exit
    if [ $EXIT_CODE -eq 130 ]; then
        log "Manually interrupted. Exiting."
        exit 0
    fi

    # Rate limit means wait and loop
    if check_rate_limited; then
        DYNAMIC_WAIT=$(calculate_wait_time)
        WAIT_HOURS=$(echo "scale=1; $DYNAMIC_WAIT / 3600" | bc)

        log "Rate limit detected. Waiting ~${WAIT_HOURS}h for reset."
        update_prompt_log "Rate limit hit, waiting ${WAIT_HOURS}h for reset" $SESSION_COUNT
        log "Next attempt at: $(date -v+${DYNAMIC_WAIT}S '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d "+${DYNAMIC_WAIT} seconds" '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
        notify "Rate limited. Resuming in ${WAIT_HOURS}h"
        sleep $DYNAMIC_WAIT
        continue
    fi

    # CLI is asking for human direction; stop and notify
    if check_needs_user_input; then
        log "PAUSED: CLI is waiting for user input or clarification."
        log "Review the output and respond manually."
        update_prompt_log "PAUSED, CLI needs user input, manual response required" $SESSION_COUNT
        notify "CLI needs your input!"
        exit 2
    fi

    # Session ended for an unknown reason (task complete, error, etc.)
    log "Session ended, reason unclear (possibly completed or error)."
    log "Review output and decide whether to resume manually."
    update_prompt_log "Session ended, reason unclear, review needed" $SESSION_COUNT
    notify "Session ended, review needed"
    exit 1
done
