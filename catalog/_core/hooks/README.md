# kitt-core hooks

Hooks that run on lifecycle events during an AI CLI session. This
infrastructure ships in the `kitt-core` plugin, alongside the MCP server,
rather than in `meta-authoring`: `configure_hook.py` needs the bundled
`kitt` package to render registrations, and `kitt-core` is the one plugin
guaranteed to carry a server bundle for it to run inside via `uv run
--project`. `meta-authoring` keeps the authoring-side `kitt-create-hook`
command and `kitt-create-hooks` skill; this directory is the machinery
those author *for*.

**Scope:** `[CLAUDE]` only. Copilot CLI and Gemini CLI both have real hook systems, and a Copilot port of the capture-skill trigger existed here until P2; it was removed with the rest of KITT's Copilot surface and remains in the quarry if Copilot support returns.

Porting a Claude hook to another CLI is not a config change: the event name, config file, input field casing, output schema, and (for anything that reads the transcript) the transcript format all differ, and none of them are things another CLI's own comments should be trusted to describe accurately. Budget a port as a second program, not a rename.

## Available hooks

| Hook | CLI | Event | Purpose |
|---|---|---|---|
| [`prompt-log-hook.py`](#prompt-log-hookpy) | Claude | Stop | Append a one-line per-turn summary to the project's `PROMPT_LOG.md` |
| [`git-branch-guard.sh`](#git-branch-guardsh) | Claude | PreToolUse | Block `git commit` and `git push` when the current branch does not match an allowed pattern |
| [`capture-skill-trigger-hook.py`](#capture-skill-trigger-hookpy) | Claude | Stop | Nudge the agent to consider running `kitt-capture-skill` once a session crosses a tool-call threshold |
| [`skill-usage-hook.py`](#skill-usage-hookpy) | Claude | Stop | Count native `Skill` tool invocations into KITT's usage sidecar (names and counts only) |
| [`token-usage-hook.py`](#token-usage-hookpy) | Claude | Stop | Recompute the session's per-tool token attribution into `~/.kitt/token-usage.json` (names, counts, token figures only) |

Each ships a parameterized standalone configure command that idempotently registers the hook:

- `/kitt-configure-prompt-log` (markdown source: `commands/kitt-configure-prompt-log.md`, registration script: `scripts/configure_prompt_log.py`) → `.claude/settings.json`
- `/kitt-configure-git-guard` (markdown source: `commands/kitt-configure-git-guard.md`, registration script: `scripts/configure_git_guard.py`) → `.claude/settings.json`
- `/kitt-configure-capture-skill-hook` (markdown source: `commands/kitt-configure-capture-skill-hook.md`) → `.claude/settings.json`
- `/kitt-configure-skill-usage-hook` (markdown source: `commands/kitt-configure-skill-usage-hook.md`) → `.claude/settings.json`
- `/kitt-configure-token-usage-hook` (markdown source: `commands/kitt-configure-token-usage-hook.md`) → `.claude/settings.json`

The capture-skill, skill-usage, and token-usage commands shell out to the **one** generic registration script, `scripts/configure_hook.py`, which reads the declarative manifest described below. `configure_prompt_log.py` and `configure_git_guard.py` remain bespoke because they do more than register a hook (rewriting `permissions` entries, seeding `PROMPT_LOG.md`); their wiring is still declared in a `HOOK.yaml` so the entry shape has a single definition.

## Declarative hook manifests (`*.HOOK.yaml`)

Each hook declares its wiring once, beside its handler:

```yaml
name: capture-skill-trigger
description: Nudge the agent to consider running kitt-capture-skill ...
handler: capture-skill-trigger-hook.py
targets:
  claude:
    event: Stop
    matcher: ""
```

`src/kitt/hook_manifest.py` renders each target into the exact entry its CLI expects (Claude's nested `{matcher, hooks: [{type, command}]}` in `.claude/settings.json`), the same author-once pattern `conversion_manifest.py` already applies to commands and agents. `scripts/configure_hook.py` imports it directly; the manual-fallback JSON below remains as a wire-it-up-by-hand option, not a workaround for a missing module.

Registration is an **upsert by identity**: an existing entry is located by the handler *filename* appearing in its command string, not by exact command text. A hook whose absolute path changed (pipx reinstall, editable → wheel, moved catalog) is reconciled in place rather than appended next to its own stale twin, so re-running `--init` can never duplicate a registration.

Use `python3 scripts/configure_hook.py --list` to see every declared hook and its targets.

The crew pack's `kitt-run-crew` skill optionally invokes both during project setup. See the crew pack's `kitt-run-crew` skill, `<project_setup>` section, for how the crew integrates them.

### `prompt-log-hook.py`

Appends one structured entry per turn to a prompt log file. Useful for long-running or unattended sessions where you want a skimmable record of what was asked and what the assistant did, separate from the full transcript.

Each entry looks like:

```
---

**[2026-04-09 | a1b2c3d4 | msg 47] <user message on one line>**
> <one-line summary extracted from the assistant's response>
```

The fields are: `YYYY-MM-DD | <8-char-session-id> | msg <message-index>`. The 8-character session ID is the leading prefix of the full Claude Code session ID. The message index is the position of the assistant turn in the JSONL transcript, suitable for a `jq` lookup.

The summary is extracted by preferring lines that start with common action verbs (Added, Built, Created, Fixed, Moved, Ran, Updated, etc.). If no action line is found, it falls back to the first non-trivial line.

Trivial user messages (`test`, `ping`, `ok`, `yes`, `no`, `go`, `continue`, empty) are skipped so the log stays signal-dense.

#### Looking up the full transcript for an entry

Each Claude Code session writes a JSONL transcript to `~/.claude/projects/<encoded-cwd>/<full-session-id>.jsonl`. To open the exact assistant turn a log entry summarizes:

1. Find the full session filename. The 8-character prefix in the log entry matches the start of the JSONL filename:
   ```bash
   ls ~/.claude/projects/<encoded-cwd>/ | grep ^a1b2c3d4
   ```
2. Jump to the recorded message index with `jq`:
   ```bash
   jq -s '.[47]' ~/.claude/projects/<encoded-cwd>/a1b2c3d4-....jsonl
   ```

This is what differentiates the prompt-log from a plain summary: every line is a navigable pointer back into the full conversation.

#### Install

**Recommended: slash command.** Run `/kitt-configure-prompt-log` (markdown source: `commands/kitt-configure-prompt-log.md`). The command shells out to `scripts/configure_prompt_log.py`, which creates `PROMPT_LOG.md`, registers the Stop hook in `.claude/settings.json`, and is idempotent on re-run. Restart Claude Code afterward for the hook to fire.

**Manual fallback.** If you need to wire it up without the slash command, add to `.claude/settings.json` (or `~/.claude/settings.json` for global):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/kitt-core/hooks/prompt-log-hook.py"
          }
        ]
      }
    ]
  }
}
```

#### Configuration (environment variables)

All optional.

| Variable | Default | Purpose |
|---|---|---|
| `PROMPT_LOG_PATH` | `$cwd/PROMPT_LOG.md` | Absolute or relative path to the log file. |
| `PROMPT_LOG_CREATE` | unset (off) | Set to `1` to create the log file if missing. With the default behavior, the hook is a silent no-op in directories that do not already have a `PROMPT_LOG.md`. |

#### Opt-in behavior

The hook is designed to be safe to install globally. If the target log file does not exist and `PROMPT_LOG_CREATE` is not set to `1`, the hook exits silently without doing anything. You opt in by either:

1. Creating a `PROMPT_LOG.md` file in a project directory, or
2. Setting `PROMPT_LOG_CREATE=1` in that project's settings env or in your shell.

This means you can have the hook wired up globally and it will only fire in projects that want it.

#### Output sink for the log

The log is append-only plaintext markdown. Review it with any markdown viewer, grep it for specific actions, or use it as input to a pattern-extraction pass over a long migration run. It is not a replacement for the full transcript; it's a skimmable index over it.

### `git-branch-guard.sh`

Blocks `git commit` and `git push` when the current branch does not match an allowed pattern. The default pattern is `feature/*`, so commit and push are allowed only on branches whose names start with `feature/`. All other Bash commands pass through unaffected.

The hook reads the `Bash` tool's intended command from the PreToolUse payload, parses it for `git commit` / `git push`, runs `git branch --show-current` (honoring `-C <dir>` if present), and returns a JSON decision document Claude Code uses to allow or block the call. A blocked call surfaces a clear reason back to the conversation:

```
git commit/push blocked: branch main does not match pattern feature/*
```

#### Install

**Recommended: slash command.** Run `/kitt-configure-git-guard` (markdown source: `commands/kitt-configure-git-guard.md`). The command shells out to `scripts/configure_git_guard.py`, which makes the guard executable, strips conflicting `Bash(git commit *)` / `Bash(git push *)` entries from `permissions.allow` and `permissions.deny` (the hook supersedes them with branch-conditional logic), and registers the PreToolUse hook in `.claude/settings.json`. Idempotent on re-run. Restart Claude Code afterward for the hook to fire.

**Manual fallback.** If you need to wire it up without the slash command, add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash /absolute/path/to/kitt-core/hooks/git-branch-guard.sh"
          }
        ]
      }
    ]
  }
}
```

When wiring manually, also remove any `Bash(git commit *)` and `Bash(git push *)` entries from `permissions.allow` and `permissions.deny`. The hook is the source of truth for that decision; static permission rules covering the same commands will fight it.

#### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `BRANCH_GUARD_PATTERN` | `feature/*` | Bash glob pattern. Branches matching this pattern are allowed; everything else is blocked. Examples: `feature/*`, `feature/*\|fix/*`, `release/*`, `*` (allow all, useful for temporary disable). |

Set in your shell or in the project's `.claude/settings.json` `env` block.

#### Why a hook instead of a static permission rule

The static permission entries `Bash(git commit *)` and `Bash(git push *)` are unconditional. They cannot say "allow this command only on certain branches." Moving the rule into a PreToolUse hook lets the harness check the branch at the moment of the call, which is the only point at which the answer is reliably correct. The configure script removes any prior static rules covering the same commands so the two layers do not fight.

#### Dependencies

The script uses `jq` to parse the hook payload. Install with `brew install jq` on macOS or your distribution's package manager on Linux.

### `capture-skill-trigger-hook.py`

Makes `kitt-capture-skill` fire automatically instead of depending on a trigger phrase or the agent happening to offer proactively. The hook itself does not decide what's worth capturing — that judgment stays in the skill, which is the only thing that can actually read the conversation and weigh it. What the hook adds is unconditional asking: once a session crosses a tool-call threshold since the last check (default 8), it injects a nudge for the agent to run the evaluation now, while the context is still fresh.

The nudge is delivered via `hookSpecificOutput.additionalContext`, not `decision: "block"`. A block would force the agent to resolve the hook's objection before the turn can end, which would immediately re-fire on the next Stop if the agent declined (the same tool calls are still in the transcript). `additionalContext` surfaces the same information without needing to be resolved, so the agent can act on it, defer it, or ignore it without the hook fighting the conversation.

State (how much of the transcript has already been counted toward the threshold) is tracked per session in `.claude/.capture-skill-hook-state.json` — add that path to `.gitignore`, it is ephemeral machine state, not durable content.

The hook is a silent no-op wherever no capture-skill is installed — checked at project-local and user-level `.claude/skills/`, under both the KITT-pack name (`kitt-capture-skill`) and the unprefixed `capture-skill` name a real install can carry (confirmed against a live machine still running an install old enough that the skill predates the `kitt-` rename — a name-only check would have made this hook a silent, permanent no-op there). Safe to register globally either way: it never spams a project that has neither name installed.

#### Install

**Recommended: slash command.** Run `/kitt-configure-capture-skill-hook` (markdown source: `commands/kitt-configure-capture-skill-hook.md`). The command shells out to `scripts/configure_hook.py --hook capture-skill-trigger --cli claude`, which registers the Stop hook in `.claude/settings.json` and is idempotent on re-run. Restart Claude Code afterward for the hook to fire.

**Manual fallback.** If you need to wire it up without the slash command, add to `.claude/settings.json` (or `~/.claude/settings.json` for global):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/kitt-core/hooks/capture-skill-trigger-hook.py"
          }
        ]
      }
    ]
  }
}
```

#### Configuration (environment variables)

All optional.

| Variable | Default | Purpose |
|---|---|---|
| `CAPTURE_SKILL_HOOK_THRESHOLD` | `8` | Tool calls since the last nudge required to fire again. |
| `CAPTURE_SKILL_HOOK_STATE_PATH` | `$cwd/.claude/.capture-skill-hook-state.json` | Where per-session nudge-checkpoint state is stored. |

#### Why not fully autonomous

This hook stops one step short of writing anything itself: the threshold decides *when to ask*, not *when to write*. That keeps the actual capture gated behind the same judgment `kitt-capture-skill` already applies (real effort, durable, likely to recur) rather than writing on every threshold crossing regardless of whether anything worth keeping happened. Whether a higher-trust project should let the threshold trigger the skill directly with no nudge step is an open design question, not a settled one — the hook is built so either direction is a small change (swap `additionalContext` for a direct invocation instruction, or leave it as-is).

### `skill-usage-hook.py`

Counts native Claude Code skill invocations into KITT's usage sidecar (`~/.kitt/skill-usage.json`, or `$KITT_HOME/skill-usage.json`). It exists because of a specific blind spot: KITT's MCP server only sees skills loaded through its own `run_skill` tool, while Claude Code invokes skills natively and never tells the server. Without this hook, a heavy Claude Code user's usage report is near-zero across the board — numbers that look authoritative and are wrong.

What it records: skill **names and counts**, nothing else. It reads past `input.args` and never touches prompt text or file paths. Recording goes through `kitt skill-usage record hook:claude <name>...` rather than writing the JSON directly, so the sidecar schema has exactly one implementation.

**Two transcript facts, verified on real sessions rather than assumed:**

1. A native skill invocation is an assistant `tool_use` block named `Skill` with the skill in `input.skill` (`{"skill": ...}` or `{"skill": ..., "args": ...}`). Plugin-namespaced names (`superpowers:brainstorming`) are skipped — they are not KITT skills.
2. **`role` and `content` are nested under `message`, not at the top level of a transcript line.** Across 40 recent transcripts on a live machine: 9931 lines carrying `message.role`, zero carrying a top-level `role`. A hook that reads `line["role"]` counts nothing forever and reports no error. `skill-usage-hook.py` accepts both shapes.

State (how far into the transcript has already been counted) lives per session in `.claude/.skill-usage-hook-state.json`; add it to `.gitignore`. The checkpoint advances even when nothing was recorded, so a Stop event never re-counts a span. Losing the state file causes a bounded **over**count of one session — the only error in this system that biases upward, which is why the checkpoint write is unconditional.

The hook is a silent no-op when `kitt` is not on PATH, so it is safe to register globally.

#### Coverage boundary

This hook covers **Claude Code only**, and only on projects where it is registered. Native skill invocations on Copilot CLI (`~/.copilot/skills/`) and Gemini CLI (`~/.gemini/skills/`) are not counted by anything: both CLIs load skills entirely in-process. Copilot's `agentStop` hook plus its `events.jsonl` transcript make an equivalent counter *buildable*, but what a native skill invocation looks like in that transcript has not been verified on a real session, and an unverified counter that silently returns zero is worse than a documented gap. See the skill-usage telemetry doc (docs/skill-usage-telemetry.md in a repo checkout).

#### Install

**Recommended: slash command.** Run `/kitt-configure-skill-usage-hook` (markdown source: `commands/kitt-configure-skill-usage-hook.md`). The command shells out to `scripts/configure_hook.py --hook skill-usage --cli claude`, which registers the Stop hook in `.claude/settings.json` and is idempotent on re-run. Restart Claude Code afterward.

`skill-usage.HOOK.yaml` declares a `claude` target only. That is a deliberate assertion, not a to-do: see the coverage boundary above. Declaring a `copilot` target would make `configure_hook.py --cli copilot` succeed and register a counter nobody has watched fire, which is how a report full of zeros starts looking authoritative.

**Manual fallback.** Add to `.claude/settings.json` (or `~/.claude/settings.json` for global):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/skill-usage-hook.py"
          }
        ]
      }
    ]
  }
}
```

#### Configuration (environment variables)

All optional.

| Variable | Default | Purpose |
|---|---|---|
| `SKILL_USAGE_HOOK_STATE_PATH` | `$cwd/.claude/.skill-usage-hook-state.json` | Where per-session counting checkpoints are stored. |
| `SKILL_USAGE_HOOK_KITT_BIN` | `kitt` | The executable used to record counts. |

#### Reading the data

`kitt skill-usage report` from a terminal, or the `skill_usage_report` MCP tool in a session. `kitt skill-usage pin <name>` (or the `pin_skill` tool) marks a deliberately-rare skill so it is never labelled stale.

### `token-usage-hook.py`

**Claude Code, `Stop` event.** On every turn boundary it re-reads the session transcript and recomputes the whole session's per-tool token attribution into `~/.kitt/token-usage.json` (override with `TOKEN_USAGE_SIDECAR`). Overwrite-on-Stop, so repeated Stop events and resumed sessions never double-count.

What the numbers mean (the handler's docstring is the authority): per-turn `usage` totals are exact; per-tool figures are an attribution — `calls` and `result_chars` are exact, `gen_output_tokens` splits a turn's output across the tools it called, `result_tokens_est` estimates injected context at chars/4. Turns without tool calls land in the `(assistant text)` bucket so per-tool numbers reconcile against the session total.

It stores tool names, counts, and token figures only — never prompt text, tool inputs, file paths, or result bodies. Silent no-op on unparseable payloads, missing transcripts, or unwritable sidecars; safe to register globally.

#### Reading the data

`python3 hooks/token-usage-report.py` (the companion reader in this directory) renders the sidecar per session and per tool.

## Provenance

`prompt-log-hook.py` was adapted from a project-specific version authored by a colleague for an internal migration proof of value. The original hardcoded the log file location and included action-verb preferences biased toward that project's agent names. This version is parameterized and stack-agnostic.

`git-branch-guard.sh` was adapted from an internal project scaffolding's `git-branch-guard.sh`. The scaffolding version hardcoded the `feature/*` pattern; this version reads it from `BRANCH_GUARD_PATTERN`.

`capture-skill-trigger-hook.py` is original KITT code, not ported from anywhere and not based on a verified Hermes design precedent — an earlier draft of this doc claimed Hermes triggers autonomous skill-writing on "any run with 5+ tool calls" and that number could not be located in the cloned Hermes source (`hermes-agent/agent/curator.py`, `learn_prompt.py`, or elsewhere) when checked directly. See the perpetual-learning doc (docs/perpetual-learning.md in a repo checkout) and `src/kitt/tools/_curator.py` for KITT's other Hermes ports, which credit specific files rather than a paraphrased number.

`skill-usage-hook.py` is original KITT code. The sidecar it feeds is a port of hermes-agent's `tools/skill_usage.py` semantics (see `src/kitt/tools/_skill_usage.py` for what was and was not carried over); the hook itself has no upstream — Hermes bumps its counters from its own in-process skill tools and never needed to read a CLI's transcript.
