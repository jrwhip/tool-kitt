"""The catalog's prose is a contract, and nothing else was checking it.

Every other test in this suite checks code, or the shape of generated
files. None of them read what the catalog actually *says*. That gap is
not academic: a skill that instructs an agent to call a tool which does
not exist, or to dispatch a subagent type nothing defines, or to read a
file that was deleted two refactors ago, fails at run time in the worst
possible way -- silently, inside a subagent, in a way that reads as
"the model did not follow instructions."

Four things are checked, one class each:

a. **Tool references resolve.** Every ``mcp__wopr__<tool>`` token in the
   catalog must name a tool ``create_app()`` actually registers. The
   registered set is enumerated from the live server, not restated here;
   ``tests/test_server.py`` already owns the pinned list, and a second
   hand-maintained copy would just be one more thing to drift.
b. **Subagent dispatches resolve.** Every ``subagent_type=<name>``
   reference must name an agent the catalog defines.
c. **Repo paths resolve.** Backtick-quoted repo-relative paths must
   point at something that exists.
d. **No foreign tool namespace leaks in.** Specifically, the runtime
   plugin prefix must never appear in source. See the policy block in
   ``src/wopr/build_plugins.py``: source is install-agnostic and the
   generator owns the runtime name. A hand-written runtime name in the
   catalog would be correct for exactly one install shape and wrong
   after the next plugin rename.

Every check reports its full violation list in one assertion rather than
failing on the first one, because these run against ~90 markdown files
and a one-at-a-time failure mode makes cleanup an N-round loop.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from wopr.build_plugins import SOURCE_TOOL_PREFIX, runtime_tool_prefix
from wopr.config import ServerConfig
from wopr.context import ServerContext
from wopr.converters import parse_claude
from wopr.server import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "catalog"


def _catalog_markdown() -> list[Path]:
    """Every markdown file under ``catalog/``, sorted.

    Pack-root READMEs are included even though the generator does not
    ship them: a developer reading ``catalog/crew/README.md`` to learn
    the crew is misled by a stale path just as effectively as a model
    reading a skill.
    """
    return sorted(CATALOG_ROOT.rglob("*.md"))


CATALOG_MARKDOWN = _catalog_markdown()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _where(path: Path, lineno: int) -> str:
    return f"{path.relative_to(REPO_ROOT)}:{lineno}"


@pytest.fixture
def registered_tools(tmp_path: Path) -> frozenset[str]:
    """Tool names the real server registers.

    Function-scoped on purpose. ``create_app`` calls
    ``ServerContext.init()``, which clobbers a process-wide singleton,
    and conftest's ``WOPR_HOME`` guard is itself function-scoped -- a
    module-scoped fixture here would run before that guard and could
    touch the operator's real ``~/.wopr``.
    """
    ServerContext.reset()
    try:
        app = create_app(
            config=ServerConfig(cli_type="claude"), workspace=str(tmp_path)
        )
        return frozenset(tool.name for tool in app._tool_manager.list_tools())
    finally:
        ServerContext.reset()


def test_the_catalog_scan_is_not_vacuous():
    """Every check below iterates this list. An empty list passes them all."""
    assert len(CATALOG_MARKDOWN) > 50, len(CATALOG_MARKDOWN)


# ===========================================================================
# a. Tool references
# ===========================================================================

_TOOL_TOKEN_RE = re.compile(
    re.escape(SOURCE_TOOL_PREFIX) + r"(?P<tool>[a-z][a-z0-9_]*)"
)
"""Matches the same shape ``rewrite_tool_names`` rewrites.

Deliberately identical: a token this test blesses but the generator
does not rewrite would ship the dead source name, and a token the
generator rewrites but this test never inspects is unverified."""


class TestToolReferencesResolve:
    """A named tool the server does not register is a dead instruction.

    Claude Code does not error on a call to an unregistered MCP tool in
    prose -- the model simply cannot find it and improvises. Four
    phantom tools (``recommend_wopr_setup``, ``propose_agent_instructions``,
    ``write_agent_instructions``, ``write_extracted_requirements_stub``)
    lived in shipped skills long after the tools behind them were cut.
    """

    def test_every_tool_reference_names_a_registered_tool(
        self, registered_tools: frozenset[str]
    ):
        violations: list[str] = []
        for path in CATALOG_MARKDOWN:
            for lineno, line in enumerate(_lines(path), start=1):
                for match in _TOOL_TOKEN_RE.finditer(line):
                    name = match.group("tool")
                    if name not in registered_tools:
                        violations.append(
                            f"{_where(path, lineno)}: "
                            f"{SOURCE_TOOL_PREFIX}{name} is not registered"
                        )
        assert not violations, (
            f"{len(violations)} reference(s) to tools create_app() does not "
            "register:\n" + "\n".join(violations)
        )

    def test_the_scan_finds_real_tool_references(
        self, registered_tools: frozenset[str]
    ):
        """Guards the test above from passing on an empty match set."""
        found = {
            match.group("tool")
            for path in CATALOG_MARKDOWN
            for match in _TOOL_TOKEN_RE.finditer(
                path.read_text(encoding="utf-8")
            )
        }
        assert len(found) >= 10, sorted(found)
        assert found & registered_tools, sorted(found)


# ===========================================================================
# b. Subagent dispatches
# ===========================================================================

_SUBAGENT_RE = re.compile(
    r"subagent_type\s*=\s*(?P<name>\"[^\"\n]*\"|'[^'\n]*'|[^\s,)`\"']+)"
)

BUILTIN_AGENT_TYPES = frozenset(
    {
        # Claude Code's own always-available general agent. Not a catalog
        # agent and never will be, so it cannot be resolved from the
        # catalog and has to be named here.
        "general-purpose",
    }
)


def _catalog_agent_names() -> frozenset[str]:
    """Frontmatter ``name:`` of every agent the catalog defines.

    The dispatch name is the frontmatter ``name``, not the filename:
    ``catalog/crew/agents/wopr-crew-auditor.md`` is dispatched as
    ``crew-auditor``. Reading the filename instead would pass this test
    while every real dispatch failed.
    """
    names: set[str] = set()
    for agents_dir in sorted(CATALOG_ROOT.glob("*/agents")):
        for agent_md in sorted(agents_dir.glob("*.md")):
            front = parse_claude(
                agent_md.read_text(encoding="utf-8")
            ).frontmatter
            name = front.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    return frozenset(names)


CATALOG_AGENT_NAMES = _catalog_agent_names()


def _is_placeholder(token: str) -> bool:
    """True for tokens that are illustrative by shape, not by listing.

    ``<agent-name>``, ``{script-name}``, ``$VAR``, ``path/to/file`` and
    ``ALL_CAPS`` segments are all forms an author uses precisely because
    the real value varies. Exempting them by pattern keeps the explicit
    allowlists below short enough to stay honest.
    """
    if any(ch in token for ch in "<>{}$*"):
        return True
    if "path/to/" in token:
        return True
    return any(
        len(part) >= 3 and part.replace("_", "").isupper()
        for part in token.split("/")
        if part
    )


class TestSubagentDispatchesResolve:
    """``subagent_type`` naming nothing is a Task call that cannot run."""

    def test_the_catalog_defines_agents_to_resolve_against(self):
        assert len(CATALOG_AGENT_NAMES) >= 10, sorted(CATALOG_AGENT_NAMES)
        assert "crew-auditor" in CATALOG_AGENT_NAMES

    def test_every_subagent_reference_names_a_defined_agent(self):
        known = CATALOG_AGENT_NAMES | BUILTIN_AGENT_TYPES
        violations: list[str] = []
        found = 0
        for path in CATALOG_MARKDOWN:
            for lineno, line in enumerate(_lines(path), start=1):
                for match in _SUBAGENT_RE.finditer(line):
                    raw = match.group("name").strip("\"'")
                    if _is_placeholder(raw):
                        continue
                    found += 1
                    if raw not in known:
                        violations.append(
                            f"{_where(path, lineno)}: subagent_type={raw!r} "
                            "matches no catalog agent"
                        )
        assert found >= 5, f"only {found} concrete dispatches found; check the regex"
        assert not violations, (
            f"{len(violations)} unresolvable subagent dispatch(es):\n"
            + "\n".join(violations)
        )


# ===========================================================================
# c. Repo paths
# ===========================================================================

_BACKTICKED_RE = re.compile(r"`([^`\n]+)`")

_REPO_PATH_RE = re.compile(r"^(docs|catalog|scripts|templates)/")
"""The four roots worth checking.

Not every slash-bearing string is a repo path -- ``src/app/foo.ts``,
``~/.claude/skills/`` and ``.ai-cli/shared/`` all appear in the catalog
and describe a *user's* project or home directory, not this repo. These
four are the ones that can only mean this repo's own tree."""

ILLUSTRATIVE_PATHS: dict[str, str] = {
    # wopr-create-agent-skills teaches skill layout in the abstract; these
    # three name files in a hypothetical skill the reader is about to
    # write, not files in this repo.
    "scripts/deploy.sh": "example command in references/using-scripts.md",
    "scripts/helper.py": "example layout in references/skill-structure.md",
    "templates/plan-template.md": "example in references/using-templates.md",
    # crew/templates/README.md documents where crew stubs land in the
    # OPERATOR's project. `docs/` there is their repo's docs directory.
    "docs/coder-spec.md": "target path inside an operator's project",
    "docs/implementation-tracking.md": "target path inside an operator's project",
}


def _resolution_bases(path: Path) -> list[Path]:
    """Where a repo-relative path in ``path`` may legitimately resolve.

    Catalog prose writes paths relative to whichever root the reader is
    standing in, and all four readings are used today:

    * repo root -- ``docs/wopr-yml-schema.md``, ``catalog/crew/README.md``
    * the containing file's own directory
    * the containing skill -- ``templates/brief.md`` in
      ``wopr-create-plans/README.md`` means that skill's ``templates/``
    * the containing pack -- ``scripts/configure_hook.py`` in
      ``catalog/_core/hooks/README.md`` means ``catalog/_core/scripts/``

    Accepting any of them is deliberate. This check exists to catch
    references to things that do not exist AT ALL; policing which root
    an author wrote from would fail on correct prose.
    """
    bases = [REPO_ROOT, path.parent]
    for ancestor in path.parents:
        if (ancestor / "SKILL.md").is_file():
            bases.append(ancestor)
            break
        if ancestor == CATALOG_ROOT:
            break
    relative = path.relative_to(CATALOG_ROOT)
    bases.append(CATALOG_ROOT / relative.parts[0])
    bases.append(CATALOG_ROOT)
    return bases


class TestRepoPathsResolve:
    """A backticked path that does not exist sends the reader nowhere.

    Worse for an agent than for a human: an agent told to read
    ``catalog/legacy-migration/README.md`` will not shrug, it will go
    looking, fail, and then improvise around the gap.
    """

    def test_every_backticked_repo_path_exists(self):
        violations: list[str] = []
        checked = 0
        for path in CATALOG_MARKDOWN:
            bases = _resolution_bases(path)
            for lineno, line in enumerate(_lines(path), start=1):
                for match in _BACKTICKED_RE.finditer(line):
                    # A backticked span may be a whole command
                    # (`scripts/configure_hook.py --hook x`); the path is
                    # its first word.
                    parts = match.group(1).split()
                    if not parts:
                        continue
                    token = parts[0]
                    if not _REPO_PATH_RE.match(token):
                        continue
                    if _is_placeholder(token):
                        continue
                    if token in ILLUSTRATIVE_PATHS:
                        continue
                    checked += 1
                    if not any((base / token).exists() for base in bases):
                        violations.append(
                            f"{_where(path, lineno)}: `{token}` resolves to "
                            "nothing"
                        )
        assert checked >= 20, f"only {checked} repo paths checked; regex is off"
        assert not violations, (
            f"{len(violations)} unresolvable repo path reference(s):\n"
            + "\n".join(violations)
        )

    def test_the_allowlist_carries_no_dead_entries(self):
        """An allowlisted path that now exists should stop being allowlisted.

        Otherwise the list only ever grows, and grows into a place where
        real breakage can hide.
        """
        resurrected = [
            f"{token}: {why}"
            for token, why in ILLUSTRATIVE_PATHS.items()
            if (REPO_ROOT / token).exists()
        ]
        assert not resurrected, (
            "allowlisted as illustrative but now real; drop the entry:\n"
            + "\n".join(resurrected)
        )

    def test_the_allowlist_is_still_referenced(self):
        """Drop entries nothing mentions any more."""
        blob = "\n".join(
            path.read_text(encoding="utf-8") for path in CATALOG_MARKDOWN
        )
        unused = [
            token for token in ILLUSTRATIVE_PATHS if f"`{token}" not in blob
        ]
        assert not unused, f"allowlist entries nothing references: {unused}"


# ===========================================================================
# d. Foreign tool namespaces
# ===========================================================================

_MCP_TOKEN_RE = re.compile(
    r"mcp__(?P<server>[A-Za-z0-9_-]+?)__(?P<tool>[A-Za-z0-9_-]*)"
)
"""Any concrete ``mcp__<server>__<tool>`` token.

Non-greedy up to the first ``__`` so a plugin-namespaced server
(``plugin_atlassian_atlassian``) is captured whole. Regex-shaped
matcher examples (``mcp__.*``, ``mcp__{server}__{tool}``) do not match
at all, since ``.`` and ``{`` are outside the class -- which is right:
those are documentation about the naming scheme, not references to a
server."""

THIRD_PARTY_SERVERS: dict[str, str] = {
    # Every entry below is a server WOPR does not ship and does not
    # require. They appear as documentation examples and as optional
    # integrations, and each one is named here so that a NEW foreign
    # prefix appearing in the catalog fails this test instead of
    # blending in.
    "memory": "hook-matcher examples in wopr-create-hooks",
    "filesystem": "hook-matcher examples in wopr-create-hooks",
    "github": "hook-matcher examples in wopr-create-hooks",
    "context7": "library-docs lookup suggested by the authoring skills",
    "ag-mcp": "wopr-doctor reports whether an AG-Grid MCP is registered",
    "plugin_atlassian_atlassian": (
        "the Atlassian plugin's real runtime namespace, verified against a "
        "live session's tool list. `source: jira` in wopr.yml calls "
        "mcp__plugin_atlassian_atlassian__getJiraIssue. This is a THIRD-PARTY "
        "plugin whose runtime name WOPR does not generate, so unlike WOPR's "
        "own tools it is written in runtime form on purpose."
    ),
}


class TestNoForeignToolNamespaceLeaks:
    def test_the_runtime_wopr_prefix_never_appears_in_source(self):
        """The one rule with no allowlist.

        ``mcp__plugin_wopr-core_wopr__x`` is what the GENERATOR emits.
        In source it is a bug in two directions at once: wrong for a
        repo/wheel install today, and stale the moment a plugin is
        renamed. ``build_plugins.rewrite_tool_names`` is the only thing
        allowed to produce it.
        """
        needle = runtime_tool_prefix()
        violations = [
            f"{_where(path, lineno)}: {needle} must not appear in source"
            for path in CATALOG_MARKDOWN
            for lineno, line in enumerate(_lines(path), start=1)
            if needle in line
        ]
        assert not violations, (
            "the generator's runtime prefix leaked back into the catalog:\n"
            + "\n".join(violations)
        )

    def test_no_wopr_server_appears_under_any_plugin_namespace(self):
        """Catches a rename too, e.g. ``mcp__plugin_wopr_wopr__``."""
        violations: list[str] = []
        for path in CATALOG_MARKDOWN:
            for lineno, line in enumerate(_lines(path), start=1):
                for match in _MCP_TOKEN_RE.finditer(line):
                    server = match.group("server")
                    if server.startswith("plugin_") and server.endswith("_wopr"):
                        violations.append(
                            f"{_where(path, lineno)}: mcp__{server}__ is a "
                            "runtime form of WOPR's own server"
                        )
        assert not violations, "\n".join(violations)

    def test_every_server_prefix_is_wopr_or_explicitly_allowed(self):
        violations: list[str] = []
        for path in CATALOG_MARKDOWN:
            for lineno, line in enumerate(_lines(path), start=1):
                for match in _MCP_TOKEN_RE.finditer(line):
                    server = match.group("server")
                    if server == "wopr" or server in THIRD_PARTY_SERVERS:
                        continue
                    violations.append(
                        f"{_where(path, lineno)}: unknown MCP server prefix "
                        f"mcp__{server}__"
                    )
        assert not violations, (
            f"{len(violations)} token(s) naming an MCP server this catalog "
            "does not declare. If the server is real and intentional, add it "
            "to THIRD_PARTY_SERVERS with a reason:\n" + "\n".join(violations)
        )

    def test_the_third_party_allowlist_carries_no_dead_entries(self):
        blob = "\n".join(
            path.read_text(encoding="utf-8") for path in CATALOG_MARKDOWN
        )
        unused = [
            server
            for server in THIRD_PARTY_SERVERS
            if f"mcp__{server}__" not in blob
        ]
        assert not unused, f"allowlisted servers nothing references: {unused}"
