#!/usr/bin/env python3
"""Record one Claude Code session against a scratch copy of the fixture app.

The deck replays the recording as a terminal timeline. Output shape:

    {"version": 2, "harness": "claude-code", "model": "...", "label": "...",
     "prompt": "...", "plugins": [...], "recordedAt": "...",
     "events": [{"t": ms, "kind": "tool"|"text"|"output"|"agent"|"result", ...}],
     "after": {"changed": [...], "diffstat": "...", "tests": {...}},
     "usage": {...}}

Usage:
    python3 record.py "/kitt-doctor ." replays/doctor.json --label doctor
    python3 record.py @prompts/naked.txt replays/naked.json --label naked --no-plugins
    python3 record.py @prompts/crew.txt replays/crew.json --label crew --fixture fixture-configured

Stdlib only. Run it from this directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent.parent / "plugins"
DEFAULT_PLUGINS = ("kitt-core", "kitt-crew", "kitt-angular")
FIXTURE_IGNORE = ("node_modules", "dist", ".angular", ".git", "coverage", "*.log")
# Everything the session may do inside the scratch copy, spelled out. No blanket permission flag.
ALLOWED_TOOLS = ",".join([
    "Read", "Glob", "Grep", "Edit", "Write", "MultiEdit", "Skill", "Task", "TodoWrite", "AskUserQuestion",
    "Bash(npm:*)", "Bash(npx:*)", "Bash(ng:*)", "Bash(node:*)", "Bash(git:*)", "Bash(ls:*)", "Bash(cat:*)",
    "Bash(find:*)", "Bash(mkdir:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(sed:*)", "Bash(wc:*)", "Bash(grep:*)",
    "Bash(tree:*)", "Bash(uv:*)", "Bash(python3:*)", "Bash(pwd:*)", "Bash(echo:*)", "Bash(test:*)", "Bash(cp:*)",
    "Bash(mv:*)", "Bash(touch:*)", "Bash(diff:*)", "Bash(jq:*)", "Bash(true:*)",
    "mcp__plugin_kitt-core_kitt", "mcp__kitt",
])
AFTER_EXCLUDE = ("node_modules", "dist", ".angular", "coverage")


def summarize_tool(name: str, inp: dict) -> str:
    """One line per tool call, the way a human would narrate it."""
    match name:
        case "Read":
            return inp.get("file_path", "")
        case "Glob":
            return inp.get("pattern", "")
        case "Grep":
            return f"/{inp.get('pattern', '')}/ in {inp.get('path') or '.'}"
        case "Edit" | "Write" | "MultiEdit":
            return inp.get("file_path", "")
        case "Bash":
            return inp.get("command", "")
        case "Task" | "Agent":
            return f"{inp.get('subagent_type', 'agent')}: {inp.get('description', '')}"
        case "Skill":
            return inp.get("skill", "") + (" " + inp["args"] if inp.get("args") else "")
        case "AskUserQuestion":
            qs = inp.get("questions") or []
            return "; ".join(q.get("question", "") for q in qs)[:200]
        case "TodoWrite":
            return f"{len(inp.get('todos') or [])} todos"
        case _:
            if name.startswith("mcp__"):
                return json.dumps(inp)[:160]
            return json.dumps(inp)[:120]


def short_tool_name(name: str) -> str:
    """mcp__plugin_kitt-core_kitt__detect_stack -> kitt:detect_stack"""
    if name.startswith("mcp__"):
        parts = name.split("__")
        return f"kitt:{parts[-1]}" if "kitt" in name else ":".join(parts[1:])
    return name


def relativize(text: str, root: str) -> str:
    return text.replace(root + "/", "").replace(root, ".").replace(str(Path.home()), "~")


def result_text(content) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    else:
        return ""
    # MCP tools answer as {"result": "..."}; keep the inner text so the replay reads like a terminal.
    if text.startswith("{") and '"result"' in text[:12]:
        try:
            inner = json.loads(text).get("result")
            if isinstance(inner, str):
                return inner
        except json.JSONDecodeError:
            pass
    return text


def write_js(out: Path, rec: dict) -> None:
    """A .js twin of the recording, so the deck opens from file:// with no server."""
    key = rec.get("label") or out.stem
    js = out.with_suffix(".js")
    js.write_text("window.KITT_REPLAYS = window.KITT_REPLAYS || {};\n"
                  f"window.KITT_REPLAYS[{json.dumps(key)}] = {json.dumps(rec)};\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="prompt text, or @path/to/file")
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--fixture", default="fixture", help="directory (relative to this script) to copy")
    ap.add_argument("--no-plugins", action="store_true", help="record plain Claude Code, no KITT plugins")
    ap.add_argument("--plugin", action="append", default=None, help="plugin dir name under plugins/ (repeatable)")
    ap.add_argument("--keep", action="store_true", help="print the scratch path and keep it (default: keep anyway)")
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--output-chars", type=int, default=400, help="chars of Bash output to keep per event")
    args = ap.parse_args()
    if args.prompt.startswith("@"):
        args.prompt = (HERE / args.prompt[1:]).read_text().strip()

    fixture = HERE / args.fixture
    if not fixture.is_dir():
        print(f"error: fixture dir {fixture} not found", file=sys.stderr)
        return 2

    scratch = Path(tempfile.mkdtemp(prefix="kitt-rec-")) / "mission-log"
    shutil.copytree(fixture, scratch, ignore=shutil.ignore_patterns(*FIXTURE_IGNORE))
    node_modules = HERE / "fixture" / "node_modules"
    if node_modules.is_dir():
        os.symlink(node_modules, scratch / "node_modules")
    (scratch / ".gitignore").write_text("node_modules\ndist\n.angular\ncoverage\n")
    git = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.com"]
    subprocess.run([*git, "init", "-q", "-b", "main"], cwd=scratch, check=True)
    subprocess.run([*git, "add", "-A"], cwd=scratch, check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], cwd=scratch, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=scratch, capture_output=True, text=True, check=True).stdout.strip()

    plugins: list[str] = []
    if not args.no_plugins:
        for name in args.plugin or DEFAULT_PLUGINS:
            p = PLUGIN_ROOT / name
            if not p.is_dir():
                print(f"error: plugin {p} not found", file=sys.stderr)
                return 2
            plugins.append(str(p))

    cmd = ["claude", "-p", args.prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
           "--setting-sources", "project,local"]
    for p in plugins:
        cmd += ["--plugin-dir", p]
    if args.model:
        cmd += ["--model", args.model]
    if args.max_turns:
        cmd += ["--max-turns", str(args.max_turns)]

    # Isolation: `--setting-sources project,local` drops the operator's user-level settings, hooks,
    # CLAUDE.md, and user-installed plugins, so the session sees only the fixture plus the plugins
    # passed on the command line. Login state is shared, so no credential copying is needed.
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    print(f"recording in {scratch}", file=sys.stderr)
    print("$ " + " ".join(c if len(c) < 80 else c[:77] + "..." for c in cmd), file=sys.stderr)

    t0 = time.monotonic()
    events: list[dict] = []
    root = str(scratch)
    model = args.model or ""
    agents: dict[str, str] = {}  # tool_use_id of a Task call -> agent label
    tool_names: dict[str, str] = {}  # tool_use_id -> tool name, for output events
    usage: dict = {}
    final_text = ""

    def emit(ev: dict) -> None:
        ev["t"] = int((time.monotonic() - t0) * 1000)
        events.append(ev)
        kind = ev["kind"]
        line = ev.get("detail") or ev.get("text") or ev.get("output") or ""
        who = f"[{ev['agent']}] " if ev.get("agent") else ""
        print(f"{ev['t']/1000:7.1f}s {who}{kind:6} {ev.get('tool', '')} {line[:110]!s}".rstrip(), file=sys.stderr)

    # Keep the raw stream so a recording can be re-parsed without re-running the session.
    raw_path = args.out.with_suffix(".raw.ndjson")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw = raw_path.open("w")
    with tempfile.NamedTemporaryFile("w+", prefix="kitt-rec-stderr-", suffix=".log", delete=False) as errf:
        proc = subprocess.Popen(cmd, cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=errf, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            parent = msg.get("parent_tool_use_id")
            agent = agents.get(parent) if parent else None
            if mtype == "system" and msg.get("subtype") == "init":
                model = msg.get("model", model)
                continue
            if mtype == "assistant":
                for block in msg.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        ev = {"kind": "text", "text": relativize(block["text"].strip(), root)}
                        if agent:
                            ev["agent"] = agent
                        emit(ev)
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {}) or {}
                        tool_names[block.get("id", "")] = name
                        if name in ("Task", "Agent"):  # the subagent tool; "Agent" since Claude Code 2.1
                            label = inp.get("subagent_type") or inp.get("description") or "agent"
                            label = label.split(":")[-1]
                            agents[block.get("id", "")] = label
                            ev = {"kind": "agent", "tool": name, "agent_name": label,
                                  "detail": relativize(inp.get("description", ""), root),
                                  "model": inp.get("model")}  # the per-role model the orchestrator chose
                        else:
                            ev = {"kind": "tool", "tool": short_tool_name(name),
                                  "detail": relativize(summarize_tool(name, inp), root)}
                        if agent:
                            ev["agent"] = agent
                        emit(ev)
            elif mtype == "user":
                for block in msg.get("message", {}).get("content", []) or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    name = tool_names.get(block.get("tool_use_id", ""), "")
                    if name not in ("Bash",) and not name.startswith("mcp__"):
                        continue
                    text = relativize(result_text(block.get("content")), root).strip()
                    if not text:
                        continue
                    ev = {"kind": "output", "tool": short_tool_name(name), "output": text[: args.output_chars],
                          "truncated": len(text) > args.output_chars, "error": bool(block.get("is_error"))}
                    if agent:
                        ev["agent"] = agent
                    emit(ev)
            elif mtype == "result":
                usage = {
                    "subtype": msg.get("subtype"),
                    "is_error": msg.get("is_error"),
                    "duration_ms": msg.get("duration_ms"),
                    "duration_api_ms": msg.get("duration_api_ms"),
                    "num_turns": msg.get("num_turns"),
                    "total_cost_usd": msg.get("total_cost_usd"),
                    "usage": msg.get("usage"),
                    "modelUsage": msg.get("modelUsage"),
                }
                final_text = relativize(msg.get("result") or "", root)
                emit({"kind": "result", "text": final_text[:2000], "subtype": msg.get("subtype", ""),
                      "cost": msg.get("total_cost_usd")})
        proc.wait()
        raw.close()
        errf.seek(0)
        stderr_tail = errf.read()[-4000:]

    # What changed, and does the suite still pass?
    diffstat = subprocess.run(["git", "diff", "--stat", base], cwd=scratch, capture_output=True, text=True).stdout
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=scratch, capture_output=True, text=True).stdout
    changed_files = [l[3:] for l in changed.splitlines() if l.strip() and not l[3:].startswith(AFTER_EXCLUDE)]
    tests = {"ran": False}
    if (scratch / "package.json").exists() and (scratch / "node_modules").exists():
        tr = subprocess.run(["npx", "ng", "test"], cwd=scratch, capture_output=True, text=True, env=env)
        out = tr.stdout + tr.stderr
        tests = {"ran": True, "exit": tr.returncode, "tail": out[-1500:]}
        for ln in out.splitlines():
            if "Tests" in ln and ("passed" in ln or "failed" in ln):
                tests["summary"] = ln.strip()
    patch = subprocess.run(["git", "diff", base, "--", ".", ":!package-lock.json"], cwd=scratch,
                           capture_output=True, text=True).stdout

    rec = {
        "version": 2,
        "harness": "claude-code",
        "model": model,
        "label": args.label,
        "prompt": args.prompt,
        "plugins": [Path(p).name for p in plugins],
        "scratch": str(scratch),
        "recordedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "exitCode": proc.returncode,
        "events": events,
        "after": {"changed": changed_files, "diffstat": diffstat, "tests": tests, "patch": patch[:60000]},
        "usage": usage,
        "finalText": final_text,
        "stderrTail": stderr_tail,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rec, indent=1))
    write_js(args.out, rec)
    print(f"\nwrote {args.out} ({len(events)} events, exit {proc.returncode}, cost {usage.get('total_cost_usd')})",
          file=sys.stderr)
    print(f"scratch kept at {scratch}", file=sys.stderr)
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
