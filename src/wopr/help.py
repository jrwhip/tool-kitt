"""
Help system for WOPR.

Shared logic used by both the CLI (`wopr help`) and the MCP tool (`get_help`).

Audience: the agent, not a first-time human reader. Every topic states what
exists in THIS repository. Nothing here describes a planned surface, and
nothing re-explains a concept the model already knows.
"""

from __future__ import annotations

from pathlib import Path

from .catalog import (
    get_catalog_path,
    load_catalog,
    read_lock_file,
)

HELP_TOPICS = {
    "overview": "What WOPR is, and what it deliberately is not",
    "packs": "The six catalog packs and the profiles over them",
    "tools": "The 23 MCP tools, by group",
    "cli": "The wopr command line surface",
    "learnings": "The learnings corpus, retrieval, and curation",
}


def get_help(topic: str | None = None, workspace: Path | None = None) -> str:
    """Return help text for a topic, or the topic index if no topic given."""
    if topic is None:
        return _topic_index(workspace)

    topic = topic.lower().strip()
    handler = {
        "overview": _help_overview,
        "packs": _help_packs,
        "tools": _help_tools,
        "cli": _help_cli,
        "learnings": _help_learnings,
    }.get(topic)

    if handler:
        return handler(workspace)

    lines = [f"Unknown topic: '{topic}'", "", "Available topics:"]
    lines.extend(f"  {name:12s} {desc}" for name, desc in HELP_TOPICS.items())
    return "\n".join(lines)


def _topic_index(workspace: Path | None = None) -> str:
    lines = [
        "WOPR",
        "",
        "An MCP server plus a catalog of Claude Code commands, skills, and",
        "agents. Target: Claude Code only.",
        "",
        "HELP TOPICS",
        "",
    ]
    for name, desc in HELP_TOPICS.items():
        lines.append(f"  {name:12s} {desc}")

    lines.extend([
        "",
        "Usage:",
        "  CLI:  wopr help <topic>",
        "  MCP:  get_help(topic='<topic>')",
    ])

    if workspace:
        installed = _get_installed_packs(workspace)
        if installed:
            lines.append("")
            lines.append(f"Installed packs: {', '.join(installed)}")

    return "\n".join(lines)


def _help_overview(workspace: Path | None = None) -> str:
    lines = [
        "OVERVIEW",
        "",
        "Two halves:",
        "",
        "  MCP server   23 tools. Every one is deterministic work the model",
        "               cannot do from context alone: reading and writing a",
        "               shared corpus, validating a contract against a",
        "               schema, scanning files, scoring routing fixtures.",
        "",
        "  Catalog      Six packs of Claude Code commands, skills, and",
        "               agents under `catalog/`. Content, not code.",
        "",
        "WHAT WOPR DOES NOT DO",
        "",
        "  - No installer. There is no `wopr --init`, no `add`/`remove`, and",
        "    no `--uninstall`. Catalog content reaches a session as the",
        "    per-pack Claude Code plugins (plus a server bundle) that",
        "    `wopr build-plugins --out DIR` emits.",
        "  - No Gemini or Copilot support. Converters for both still exist",
        "    in `converters.py`, unused by any shipped command path.",
        "  - No skill-loading tiers and no skill resolver. Which pack you",
        "    install is the tiering.",
        "  - Nothing that restates general knowledge. If Claude already",
        "    knows it, it is not in the catalog.",
        "",
        "WORKSPACE RESOLUTION",
        "",
        "  Most tools take an optional `target_workspace_path`. Empty means",
        "  the workspace the server was started in. A path outside the",
        "  server's allowed roots is rejected, not silently redirected.",
    ]
    return "\n".join(lines)


def _help_packs(workspace: Path | None = None) -> str:
    catalog = load_catalog(get_catalog_path())
    packs = catalog.get("packs", {})
    profiles = catalog.get("profiles", {})
    installed = _get_installed_packs(workspace) if workspace else []

    lines = [
        "PACKS AND PROFILES",
        "",
        "PACKS",
        "",
    ]

    for name, info in sorted(packs.items()):
        desc = info.get("description", "")
        marker = ""
        if info.get("always_installed"):
            marker = " [always installed]"
        elif name in installed:
            marker = " [installed]"
        lines.append(f"  {name:16s} {desc}{marker}")

    if profiles:
        lines.extend(["", "PROFILES", ""])
        for name, info in sorted(profiles.items()):
            desc = info.get("description", "")
            pack_list = ", ".join(info.get("packs", []))
            lines.append(f"  {name:16s} {desc}")
            lines.append(f"  {'':16s} packs: {pack_list}")

    lines.extend([
        "",
        "LAYOUT",
        "",
        "  catalog/<pack>/commands/<name>.md        slash commands",
        "  catalog/<pack>/skills/<name>/SKILL.md    skills",
        "  catalog/<pack>/agents/<name>.md          subagents",
        "  catalog/<pack>/templates/                crew stub templates",
        "",
        "  Read a file directly. `wopr catalog` lists packs and profiles;",
        "  `wopr list` shows what a workspace's lock file records.",
    ])

    return "\n".join(lines)


def _help_tools(workspace: Path | None = None) -> str:
    lines = [
        "MCP TOOLS (23)",
        "",
        "LEARNINGS (5)",
        "",
        "  learnings_search        Retrieve entries for a query. Deterministic",
        "                          prefilter, optional fastembed reranking.",
        "  append_learnings        Add an entry. LRN- header format is",
        "                          validated; malformed entries are rejected.",
        "  learnings_path          Resolve the corpus path for a workspace.",
        "  seed_learnings          Copy stack-tagged seed entries into a new",
        "                          corpus (angular, fastapi).",
        "  curate_learnings        Deduplicate and compact an existing corpus.",
        "",
        "CREW SUBSTRATE (7)",
        "",
        "  detect_stack            Scan a workspace and return detection JSON.",
        "  propose_wopr_yml        Turn detection JSON into a proposed wopr.yml.",
        "  write_wopr_yml          Write it. Takes the same detection JSON.",
        "  write_spec_stubs        Create the spec files the crew treats as",
        "                          authority.",
        "  write_tracking_doc_stub      Implementation-tracking stub.",
        "  write_handoff_contract_stub  Frontend handoff-contract stub.",
        "  validate_scout_contract      Validate a scout contract file. This",
        "                          is the crew's gate: invalid means stop.",
        "",
        "  detect_stack feeds propose_wopr_yml and write_wopr_yml; both",
        "  require its output as `detection_json`.",
        "",
        "SKILL QA AND TELEMETRY (4)",
        "",
        "  check_routing_evals     Score every routing-eval.jsonl in the",
        "                          catalog. The merge gate for slimming work.",
        "  scan_skill_directory    Scan a skill directory for prompt-injection",
        "                          and exfiltration patterns before install.",
        "  skill_usage_report      Observed skill usage. A LOWER BOUND: only",
        "                          the optional Claude Code Stop hook feeds it.",
        "  pin_skill               Mark a deliberately rare skill so it is",
        "                          never reported stale.",
        "",
        "SUPPLY CHAIN (1)",
        "",
        "  check_mcp_servers_for_malware  Resolve configured MCP server",
        "                          packages against OSV and report advisories.",
        "",
        "HANDOFF (2)",
        "",
        "  create_handoff, get_handoff    Read and write whats-next.md.",
        "",
        "PACK TEMPLATES (2)",
        "",
        "  list_pack_templates, get_pack_template   Read templates shipped",
        "                          under a pack (crew is the only pack with",
        "                          templates today).",
        "",
        "SERVER (2)",
        "",
        "  get_workspace_info      Resolved workspace, local and global",
        "                          resource counts, which project files exist.",
        "  get_help                This.",
        "",
        "The set is pinned by name in",
        "tests/test_server.py::test_registers_exactly_the_expected_tool_set,",
        "so a tool appearing or vanishing is a deliberate diff.",
    ]
    return "\n".join(lines)


def _help_cli(workspace: Path | None = None) -> str:
    lines = [
        "CLI",
        "",
        "  wopr                             Run the MCP server on stdio.",
        "                                   No subcommand means server mode.",
        "  wopr list                        Packs recorded in a workspace's",
        "                                   .ai-cli lock file.",
        "  wopr catalog                     All packs and profiles in the",
        "                                   catalog.",
        "  wopr help [topic]                This help.",
        "  wopr skill-usage report          Observed skill usage.",
        "  wopr skill-usage pin <name>      Never report a rare skill stale.",
        "  wopr skill-usage unpin <name>    Undo a pin.",
        "  wopr skill-usage record <source> <name>...",
        "                                   Record invocations. What the",
        "                                   Claude Code Stop hook calls.",
        "",
        "FLAGS",
        "",
        "  --workspace PATH, -w    Workspace for a subcommand or the server.",
        "  --catalog PATH          External catalog directory.",
        "  --global, -g            Inspect ~/.wopr instead of the workspace.",
        "  --version, -v           Version.",
        "",
        "There is no install, add, remove, or uninstall subcommand. Pack",
        "deployment happens through the per-pack Claude Code plugins",
        "`wopr build-plugins` emits.",
    ]
    return "\n".join(lines)


def _help_learnings(workspace: Path | None = None) -> str:
    lines = [
        "LEARNINGS",
        "",
        "A per-workspace LEARNINGS.md of `LRN-` entries: things discovered by",
        "working in THIS codebase that no model knows from training. Failures",
        "with a fix, local conventions, non-obvious constraints. Not tutorials.",
        "",
        "FORMAT",
        "",
        "  Each entry opens with an `LRN-` header line. append_learnings",
        "  validates it and rejects anything malformed rather than writing a",
        "  corpus that later retrieval cannot parse.",
        "",
        "RETRIEVAL",
        "",
        "  learnings_search runs a deterministic prefilter over the corpus.",
        "  With the optional `[embeddings]` extra installed, a fastembed",
        "  sidecar reranks the prefiltered set. Without it, search still",
        "  works; results are prefilter order.",
        "",
        "  Retrieval is local. There is no hosted corpus and no promotion of",
        "  project entries into a shared one.",
        "",
        "CREW INTEGRATION",
        "",
        "  The crew's CRAG pre-step runs learnings_search once per crew",
        "  run, before Step 1. Five or fewer candidates are injected",
        "  directly, marked advisory; only when the prefilter returns more",
        "  than five does the crew-evaluator grade them. The resulting",
        "  `relevant_learnings` block goes to all four working agents.",
        "  See <crag_pre_step> in",
        "  catalog/crew/skills/wopr-run-crew/SKILL.md.",
        "",
        "SEEDS",
        "",
        "  seed_learnings copies stack-tagged starter entries from",
        "  catalog/crew/data/learnings-seed/ (angular, fastapi)",
        "  into a new workspace corpus.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_installed_packs(workspace: Path | None) -> list[str]:
    if not workspace:
        return []
    lock = read_lock_file(workspace / ".ai-cli")
    if not lock:
        return []
    return lock.get("installed_packs", [])
