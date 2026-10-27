#!/usr/bin/env python3
"""
token-usage-report.py

Retrospective report over the token-usage sidecar written by
``token-usage-hook.py``. Answers "where did the tokens go, by tool?"
across one session or all of them.

Usage:
  token-usage-report.py                 # text report, all sessions
  token-usage-report.py --markdown      # markdown (for a doc/slide)
  token-usage-report.py --json          # raw aggregate as JSON
  token-usage-report.py --session <id>  # one session only
  token-usage-report.py --sidecar PATH  # override sidecar location

What is EXACT vs ESTIMATED (stated so the numbers are not oversold):
  * Session totals (input/output/cache/thinking) are EXACT -- summed from
    each turn's own ``usage`` object. These are what you actually paid for.
    Cache-read almost always dominates: every turn re-reads the whole
    conversation as cached input, so cost grows with turn count, not with
    any one tool.
  * Per-tool ``gen_output`` is the calling turn's output tokens attributed
    to the tool(s) it called (split evenly across a multi-tool turn).
  * Per-tool ``result_est`` is the tool's result size in characters / 4 --
    an ESTIMATE of the context each tool injected (re-read every later turn).
  * ``est_total`` = gen_output + result_est. A ranking aid, not a bill.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TOTAL_FIELDS = [
    ("turns", "turns"),
    ("input_tokens", "input"),
    ("output_tokens", "output"),
    ("cache_creation_input_tokens", "cache_creation"),
    ("cache_read_input_tokens", "cache_read"),
    ("thinking_tokens", "thinking"),
]
TOOL_FIELDS = ["calls", "gen_output_tokens", "result_chars", "result_tokens_est"]


def resolve_sidecar(override: str) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("TOKEN_USAGE_SIDECAR", "").strip()
    return Path(env) if env else Path.home() / ".wopr" / "token-usage.json"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        sys.exit(f"No token-usage sidecar at {path}. Has the hook run on any session yet?")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def aggregate(sidecar: dict[str, Any], only: str) -> dict[str, Any]:
    sessions = sidecar.get("sessions", {})
    if only:
        if only not in sessions:
            sys.exit(f"Session {only!r} not in sidecar ({len(sessions)} sessions present).")
        sessions = {only: sessions[only]}
    totals = {k: 0 for k, _ in TOTAL_FIELDS}
    tools: dict[str, dict[str, int]] = {}
    for s in sessions.values():
        for k, _ in TOTAL_FIELDS:
            totals[k] += int(s.get("totals", {}).get(k, 0))
        for name, t in s.get("tools", {}).items():
            agg = tools.setdefault(name, {f: 0 for f in TOOL_FIELDS})
            for f in TOOL_FIELDS:
                agg[f] += int(t.get(f, 0))
    ranked = sorted(
        tools.items(),
        key=lambda kv: kv[1]["gen_output_tokens"] + kv[1]["result_tokens_est"],
        reverse=True,
    )
    return {"session_count": len(sessions), "totals": totals, "tools": ranked}


def _n(x: int) -> str:
    return f"{x:,}"


def render_text(agg: dict[str, Any], md: bool) -> str:
    L: list[str] = []
    h1 = "# " if md else ""
    L.append(f"{h1}WOPR Token Usage Retrospective")
    L.append("")
    L.append(f"Sessions: {agg['session_count']}")
    L.append("")
    t = agg["totals"]
    L.append(("## " if md else "") + "Authoritative session totals (exact)")
    L.append("")
    if md:
        L.append("| metric | tokens |")
        L.append("|---|---:|")
        for k, label in TOTAL_FIELDS:
            L.append(f"| {label} | {_n(t[k])} |")
    else:
        for k, label in TOTAL_FIELDS:
            L.append(f"  {label:<16}{_n(t[k]):>18}")
    L.append("")
    L.append(("## " if md else "") + "Per-tool attribution (gen exact-split; result estimated)")
    L.append("")
    rows = agg["tools"]
    if md:
        L.append("| tool | calls | gen_output | result_est | est_total |")
        L.append("|---|---:|---:|---:|---:|")
        for name, d in rows:
            est = d["gen_output_tokens"] + d["result_tokens_est"]
            L.append(f"| {name} | {_n(d['calls'])} | {_n(d['gen_output_tokens'])} | {_n(d['result_tokens_est'])} | {_n(est)} |")
    else:
        L.append(f'  {"tool":<40}{"calls":>7}{"gen_out":>12}{"result_est":>13}{"est_total":>12}')
        for name, d in rows:
            est = d["gen_output_tokens"] + d["result_tokens_est"]
            L.append(f'  {name[:40]:<40}{d["calls"]:>7}{_n(d["gen_output_tokens"]):>12}{_n(d["result_tokens_est"]):>13}{_n(est):>12}')
    L.append("")
    note = (
        "Totals are exact (what you paid); cache_read dominates and grows with "
        "turn count, not any one tool. Per-tool gen_output is the calling turn's "
        "output split across its tool calls; result_est is result_chars/4. "
        "est_total ranks tools, it is not a bill."
    )
    L.append(("> " if md else "Note: ") + note)
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Retrospective token-usage report by tool.")
    ap.add_argument("--session", default="", help="Limit to one session id.")
    ap.add_argument("--sidecar", default="", help="Sidecar path override.")
    ap.add_argument("--json", action="store_true", help="Emit raw aggregate JSON.")
    ap.add_argument("--markdown", action="store_true", help="Markdown output.")
    args = ap.parse_args()

    sidecar = load(resolve_sidecar(args.sidecar))
    agg = aggregate(sidecar, args.session)
    if args.json:
        print(json.dumps({"session_count": agg["session_count"], "totals": agg["totals"],
                          "tools": {n: d for n, d in agg["tools"]}}, indent=2))
    else:
        print(render_text(agg, args.markdown))


if __name__ == "__main__":
    main()
