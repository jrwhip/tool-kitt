---
name: wopr-whats-next
description: Produce a grounded, reference-based handoff (and durable learnings) so this work resumes in a fresh context with zero loss, on any CLI (Claude Code, GitHub Copilot, Gemini CLI). Persists state through WOPR's cross-CLI MCP tools, not any CLI's private memory. Use when wrapping up a work session, switching CLIs, or before a context runs out.
---

<agent_identification>
**Identify which agent you are. The PROCEDURE is identical on all; only the tool NAMES for gathering evidence differ:**
- **I am Claude Code** → file reads = `Read`, shell = `Bash`, search = `Grep`
- **I am GitHub Copilot** → file reads = `read`, shell = `shell`, search = `search`
- **I am Gemini CLI** → use your equivalent read / shell / search tools

The handoff itself is persisted through WOPR's MCP tools (`get_handoff`, `create_handoff`, `append_learnings`), which are identical on every CLI. Each accepts a `target_workspace_path` (the absolute repo root of the project you are handing off). On Claude Code you may omit it and it defaults to the session's project (via `CLAUDE_PROJECT_DIR`); on GitHub Copilot and Gemini CLI you must pass it. WOPR never guesses from where the server happens to be running. That is the whole point: state survives a switch between CLIs and sessions because it never lives in any CLI's private memory.
</agent_identification>

<objective>
Produce a handoff that lets a fresh context resume this work with zero loss.

Two non-negotiable principles:

- **Ground every claim in evidence you gather now.** Do not narrate status from your recollection of the conversation. Before you write that something is done, in progress, or not started, confirm it against the repository (git, files, tickets). The classic failure of a handoff is asserting work is "not started" when it was actually finished and committed, which happens when status is narrated instead of verified.
- **Reference, don't repeat.** Point at the durable sources of truth (commit SHAs, ticket IDs, log/doc paths, `file:line`) instead of re-describing them. Prose drifts; a commit SHA and a ticket ID do not. Narrate only what is NOT already captured somewhere verifiable: the reasoning, the gotchas, and the exact next action.
</objective>

<procedure>
1. **Resolve the target workspace, then read the prior handoff.** The handoff belongs to the project you are working in: resolve its absolute repo root (`git rev-parse --show-toplevel`, or `$CLAUDE_PROJECT_DIR` on Claude Code) and pass it as `target_workspace_path` to every WOPR state tool below. Call `get_handoff(target_workspace_path)`. If one exists, you are superseding it: build on what is still true and capture anything from the old one that still matters, because step 4 replaces it.

2. **Gather hard evidence before writing anything.** Recent commits (`git log --oneline -20`) and what the active branch contains; uncommitted state (`git status -s`, `git diff --stat`). These are the authoritative record. Verify any "done" claim: does the commit/file/output actually exist? Run the check. If you cannot verify a claim, mark it `unverified` rather than asserting it. Identify the durable artifacts this work writes to (running logs, design docs, trackers) and reference their paths instead of copying their contents.

3. **Find the single next action.** The most valuable line in any handoff is the one concrete thing to do next, and exactly how to do it: the command to run, the `file:line` to edit, the verification that proves it worked. Lead with this.

4. **Persist the handoff via `create_handoff(target_workspace_path, ...)` (do NOT hand-write the file).** It refuses to overwrite an existing handoff unless you pass `overwrite=True`; since step 1 already read the prior one, pass `overwrite=True` to supersede it. Three tight fields:
   - **summary**: what was actually accomplished, grounded in references (commit SHAs, ticket IDs, doc paths). One line per real deliverable. No re-narration of what the commits already say.
   - **next_steps**: action-first bullets. The first bullet is the single next concrete action with its exact how-to. Subsequent bullets are ordered, each with precise targets.
   - **context**: only what is NOT recoverable from git/tickets/logs: key decisions and why, gotchas and dead ends to avoid, environment quirks, assumptions to validate, and pointers to the durable artifacts.

5. **Extract durable learnings with `append_learnings(target_workspace_path, ...)` (distinct from the handoff).** A handoff is session-continuation state; it expires the moment the next session supersedes it. A learning is a durable, cross-session pattern. For anything reusable you discovered (an anti-pattern, a non-obvious behavior, a gotcha that will bite again, a confirmed operator preference, a constraint worth encoding), append a `## LRN-YYYY-MM-DD-<letter>: <title>` entry (what happened / why it matters / the pattern to recognize or avoid). Put durable patterns in learnings, session state in the handoff.
</procedure>

<discipline>
- **Brevity is signal.** Include the next action, the grounded references, and the non-obvious context. Cut any re-narration of what a commit/ticket/log already states, generic boilerplate, and exhaustive blow-by-blow.
- **No CLI-private memory.** State lives in the handoff and learnings (shared MCP tools available on Claude Code, Copilot, and Gemini). Do not assume conversation history carries over, and do not rely on any single CLI's memory.
- **Verify, then write.** If a status line is not backed by a check you ran this session, either run the check or label it `unverified`.
</discipline>
