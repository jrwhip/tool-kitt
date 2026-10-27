"""Emit the ``wopr-plugins`` Claude Code marketplace from the catalog.

One catalog pack becomes one plugin. The generated tree is a complete,
installable marketplace: ``.claude-plugin/marketplace.json`` at the
root, one plugin directory per pack, and inside ``wopr-core`` the MCP
server itself (source, a runtime-only ``pyproject.toml``, the packaged
resources the surviving tools read, and a bootstrap shim that launches
it through ``uv``).

Distribution posture (decided 2026-08-21): marketplace only. There is
no ``wopr install`` of any kind and no PyPI dependency at install time.
``/plugin install wopr-core@wopr-marketplace`` copies the plugin into
the plugin cache; the first MCP launch runs
``uv run --project <plugin>/server wopr-serve``, and uv resolves the
two runtime dependencies from PyPI at that point. The only prerequisite
on the user's machine is uv, which is a static binary that provisions
its own Python.

Generation is deterministic and total:

* **Deterministic.** Same catalog in, byte-identical tree out. No
  timestamps, no ordering that depends on filesystem iteration order,
  no host paths embedded in generated content. That is what makes the
  drift test (regenerate, compare) meaningful.
* **Total.** The output directory is wiped and rewritten on every run.
  Nothing is merged, so a file deleted from the catalog cannot survive
  in the emitted tree. The wipe is gated on a marker file
  (:data:`MARKER_NAME`) written at the root of every tree this
  generator produces: an existing non-empty directory without that
  marker is refused, so pointing ``--out`` at the wrong path destroys
  nothing.

What is deliberately NOT emitted:

* ``routing-eval.jsonl`` fixtures. They are dev-time evidence for the
  slimming gate (``check_routing_evals``), read from the source
  catalog, and are useless to an installed plugin.
* Pack-root ``README.md`` files. They document the retired
  ``wopr add <pack>`` install path and would ship stale instructions.
* ``catalog/_core/context/``. The ``get_shared_context`` shim that
  served those documents retired with the rest of the cross-CLI shim
  layer in P1; nothing in a plugin-native world reads them.
* Tests, evals, and lint/type config. The bundle is the runtime
  projection of the package, not a copy of the repo. The ``embeddings``
  extra's deps DO ship (decided in Phase 1): CRAG's semantic half is
  a headline feature, so its ~100MB install weight is paid once at
  first launch rather than pushed onto an opt-in extra nobody
  installs. The model itself still downloads lazily on first use, and
  the sticky-fail path means an offline operator loses only the
  semantic half — the deterministic prefilter keeps working.

One thing IS rewritten on the way out: MCP tool names. See
:data:`SOURCE_TOOL_PREFIX` and :func:`rewrite_tool_names`.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .config import PLUGIN_RESOURCES_DIRNAME, PLUGIN_SERVER_DIRNAME

# ---------------------------------------------------------------------------
# Constants: the shape of the emitted tree
# ---------------------------------------------------------------------------
from .product import (  # noqa: E402  re-exported for callers and tests
    CLI_PROG,
    MARKER_NAME,
    MARKETPLACE_DESCRIPTION,
    MARKETPLACE_NAME,
    MARKETPLACE_OWNER,
    MCP_SERVER_KEY,
    PLUGIN_PREFIX,
    SERVER_ENTRY_POINT,
)
from .tools._routing_eval import find_duplicate_descriptions, scan_catalog_skills

"""Marker file at the marketplace root. Its presence is the ONLY thing
that authorizes this generator to wipe an existing directory."""

PLUGIN_LICENSE = "MIT"

PLUGIN_MANIFEST_DIR = ".claude-plugin"
PLUGIN_MANIFEST_NAME = "plugin.json"
MARKETPLACE_MANIFEST_NAME = "marketplace.json"
MCP_CONFIG_NAME = ".mcp.json"
"""``MCP_SERVER_KEY``: the key this generator writes under ``mcpServers`` in ``.mcp.json``.

Half of the runtime tool namespace. :func:`runtime_tool_prefix` is the
other half's only consumer, so the two cannot drift."""

CORE_PACK = "_core"
"""The pack that carries the server, the shim, and ``.mcp.json``."""

BOOTSTRAP_SCRIPT_REL = "scripts/bootstrap-serve.sh"

PLUGIN_NAME_OVERRIDES: dict[str, str] = {
    "_core": f"{PLUGIN_PREFIX}core",
    "meta-authoring": f"{PLUGIN_PREFIX}meta",
}
"""Pack directory name -> plugin name, where the default rule does not
apply. Every other pack becomes ``wopr-<pack>``."""

COMPONENT_DIRS: tuple[str, ...] = ("commands", "agents", "skills")
"""Claude Code component directories, scanned by the plugin loader at
their default locations. A pack that has none of these ships nothing
and is skipped."""

AUXILIARY_DIRS: tuple[str, ...] = ("hooks", "scripts", "templates", "data")
"""Pack-owned support directories copied verbatim when present.

``hooks/`` is WOPR's own hook source (``*.HOOK.yaml`` manifests plus
the scripts they register), NOT a Claude Code ``hooks/hooks.json``.
Claude Code only loads ``hooks/hooks.json`` by default and no emitted
pack has one, so the directory is inert until an operator runs
``/wopr-configure-*``. See P3-NOTES.md."""

EXCLUDED_FILE_NAMES = frozenset({"routing-eval.jsonl"})
EXCLUDED_DIR_NAMES = frozenset({"__pycache__", "node_modules"})
"""Directories never copied. Dot-prefixed names (``.git``, ``.venv``,
``.mypy_cache``) are excluded by the leading-dot rule instead, which
covers every future cache directory without a maintenance list."""

# ---------------------------------------------------------------------------
# Constants: MCP tool naming
# ---------------------------------------------------------------------------
#
# POLICY (decided 2026-08-22, after a live plugin session found every
# agent tool grant dead on arrival):
#
#   The catalog source names WOPR's MCP tools install-agnostically, as
#   ``mcp__wopr__<tool>``. The generator owns the runtime name.
#
# Why the source form cannot also be the runtime form. Claude Code
# namespaces an MCP server by how it was reached. A server registered
# by hand in ``~/.claude.json`` under the key ``wopr`` presents its
# tools as ``mcp__wopr__<tool>``. The SAME server, shipped inside a
# plugin, presents them as ``mcp__plugin_<plugin>_<server-key>__<tool>``
# — here ``mcp__plugin_wopr-core_wopr__<tool>``, verified against a live
# session's tool list and against the sibling Atlassian plugin's
# ``mcp__plugin_atlassian_atlassian__*``. So there is no single string
# that is correct in both worlds, and the catalog has to pick one.
#
# It picks the short one, for three reasons:
#
# 1. The plugin name is a distribution decision (``PLUGIN_NAME_OVERRIDES``
#    maps ``_core`` -> ``wopr-core`` today and could map it elsewhere
#    tomorrow). Baking a distribution decision into 58 prose references
#    across 7 catalog files means a rename becomes a catalog-wide sed.
# 2. The catalog is also read directly out of the repo by developers and
#    by the wheel install, where the plugin prefix would be a lie.
# 3. One rewrite site is auditable. 58 hand-written long names are not:
#    a typo in an agent's ``tools:`` frontmatter is silent — the grant
#    simply does not match, the tool is not offered, and the agent
#    reports success having written nothing. That is exactly how the
#    CRAG write path died.
#
# Enforcement lives in ``tests/test_prose_contract.py``: every
# ``mcp__wopr__<tool>`` token in the catalog must name a tool
# ``create_app()`` actually registers, and the runtime form must never
# appear in source.
#
# The rewrite applies to EVERY plugin's markdown, not just
# ``wopr-core``'s. ``wopr`` is the only MCP server in the marketplace;
# a skill in ``wopr-crew`` calling ``append_learnings`` is calling the
# server that ``wopr-core`` carries, so it needs ``wopr-core``'s prefix.

SOURCE_TOOL_PREFIX = f"mcp__{MCP_SERVER_KEY}__"
"""How the catalog spells a WOPR MCP tool. Install-agnostic."""

_SOURCE_TOOL_RE = re.compile(
    re.escape(SOURCE_TOOL_PREFIX) + r"(?P<tool>[a-z][a-z0-9_]*)"
)
"""Matches a whole tool reference, never a bare prefix mention.

Requiring a trailing tool name keeps prose that discusses the naming
scheme itself (``the mcp__wopr__ prefix``) out of the rewrite, and
makes the substitution idempotent: the runtime form it produces does
not contain :data:`SOURCE_TOOL_PREFIX` as a substring."""

REWRITTEN_SUFFIXES = frozenset({".md"})
"""File types the rewrite touches.

Markdown only: it is the whole model-facing surface (agent frontmatter,
skill bodies, command bodies, template prose). Scripts and YAML hook
manifests are executed or parsed by machines that do not resolve tool
names, and rewriting them would be scope the policy above does not
justify."""

# ---------------------------------------------------------------------------
# Constants: the server bundle
# ---------------------------------------------------------------------------

SERVER_DEPENDENCIES: tuple[str, ...] = (
    "mcp[cli]>=1.0.0,<2",
    "pyyaml>=6.0",
    "fastembed>=0.7",
    "numpy>=1.24",
)
"""Runtime dependencies, kept in lockstep with ``pyproject.toml`` by
``tests/test_build_plugins.py``: the base dependencies plus the
``embeddings`` extra's pins, exactly. The dev extra (pytest, ruff,
mypy) is dev-time weight and does not ship. The embeddings deps ship
deliberately (Phase 1): the local semantic-search provider is the
default, its ~100MB (fastembed + onnxruntime) resolves once at first
launch, the model downloads lazily on first use, and offline operators
degrade to the deterministic prefilter instead of crashing. The
``bedrock`` extra does NOT ship: boto3 is opt-in for operators who
select that provider."""

BUNDLED_RESOURCES: tuple[tuple[str, ...], ...] = (
    ("crew", "templates"),
    ("crew", "data", "learnings-seed"),
)
"""Catalog subtrees the surviving MCP tools read at run time, copied
into ``<plugin>/server/resources/`` under the same relative layout the
wheel build uses (``hatch_build.py``). ``get_pack_template`` /
``list_pack_templates`` / ``write_spec_stubs`` read the first;
``seed_learnings`` reads the second. ``catalog.yaml`` rides along
separately (``get_help`` loads it)."""


class BuildPluginsError(Exception):
    """Base class for every generation failure."""


class UnsafeOutputDirError(BuildPluginsError):
    """The requested output directory was not produced by this generator."""


class PluginCollisionError(BuildPluginsError):
    """Two emitted plugins would ship the same component name."""


@dataclass(frozen=True)
class EmittedFile:
    """One file to copy: absolute source, marketplace-relative destination."""

    source: Path
    dest: str


@dataclass
class PluginPlan:
    """Everything known about one plugin before anything is written.

    Planning fully before writing is what lets collision detection fail
    the whole run without leaving a half-generated tree on disk.
    """

    pack: str
    name: str
    description: str
    keywords: list[str]
    files: list[EmittedFile] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    @property
    def ships_components(self) -> bool:
        return bool(self.commands or self.agents or self.skills)


@dataclass(frozen=True)
class BuildResult:
    """Summary of one generation run, for the CLI and for tests."""

    out_dir: Path
    marketplace_name: str
    version: str
    plugins: list[PluginPlan]
    file_count: int


# ---------------------------------------------------------------------------
# Version mapping
# ---------------------------------------------------------------------------

_PEP440_DEV_RE = re.compile(r"^(\d+\.\d+\.\d+)\.dev(\d+)$")
_PEP440_PRE_RE = re.compile(r"^(\d+\.\d+\.\d+)(a|b|rc)(\d+)$")
_PRE_LABELS = {"a": "alpha", "b": "beta", "rc": "rc"}


def to_semver(version: str) -> str:
    """Map a PEP 440 package version onto the semver plugin manifests want.

    ``plugin.json`` and ``marketplace.json`` document ``version`` as a
    semantic version. Python packaging uses PEP 440, and the two
    disagree exactly on pre-release spelling: ``1.0.0.dev0`` is a legal
    PEP 440 version and an illegal semver one. Rather than fork the
    version string across the repo, the package keeps PEP 440 as the
    single source of truth and this function projects it.

    ``1.0.0.dev0`` -> ``1.0.0-dev.0``; ``1.2.0rc1`` -> ``1.2.0-rc.1``;
    a plain ``1.2.3`` passes through untouched. Anything else is
    returned as-is: guessing at an unrecognized scheme would be worse
    than shipping the literal string.
    """
    dev = _PEP440_DEV_RE.match(version)
    if dev:
        return f"{dev.group(1)}-dev.{dev.group(2)}"
    pre = _PEP440_PRE_RE.match(version)
    if pre:
        return f"{pre.group(1)}-{_PRE_LABELS[pre.group(2)]}.{pre.group(3)}"
    return version


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def plugin_name_for_pack(pack: str) -> str:
    """Return the plugin name for a catalog pack directory name."""
    return PLUGIN_NAME_OVERRIDES.get(pack, f"{PLUGIN_PREFIX}{pack}")


def server_plugin_name() -> str:
    """The plugin that carries ``.mcp.json``, and therefore the server."""
    return plugin_name_for_pack(CORE_PACK)


def runtime_tool_prefix(
    plugin_name: str | None = None, server_key: str = MCP_SERVER_KEY
) -> str:
    """Build the tool prefix Claude Code exposes for a plugin's MCP server.

    Claude Code composes it from the plugin that declares the server and
    the key that server sits under in ``.mcp.json``:
    ``mcp__plugin_<plugin>_<server-key>__``. Both inputs default to the
    values this generator emits, so the prefix cannot drift from
    :func:`render_mcp_config` without a test noticing.
    """
    return f"mcp__plugin_{plugin_name or server_plugin_name()}_{server_key}__"


def rewrite_tool_names(text: str, prefix: str | None = None) -> str:
    """Rewrite catalog tool references into their runtime form.

    ``mcp__wopr__append_learnings`` becomes
    ``mcp__plugin_wopr-core_wopr__append_learnings``. Frontmatter
    ``tools:`` entries and prose are the same substitution: both are
    plain text as far as this function is concerned, and a grant that
    does not match the runtime name grants nothing.

    Tokens for other MCP servers are left alone, so hook-matcher
    examples (``mcp__memory__.*``) and the crew's Atlassian references
    (``mcp__plugin_atlassian_atlassian__getJiraIssue``) survive intact.
    """
    runtime = prefix if prefix is not None else runtime_tool_prefix()
    return _SOURCE_TOOL_RE.sub(lambda m: runtime + m.group("tool"), text)


def _is_excluded(rel_path: Path) -> bool:
    """True when a path relative to a copy root must not be copied."""
    if rel_path.name in EXCLUDED_FILE_NAMES:
        return True
    return any(
        part.startswith(".") or part in EXCLUDED_DIR_NAMES
        for part in rel_path.parts
    )


def _walk_files(root: Path) -> list[Path]:
    """Every copyable file under ``root``, sorted for determinism."""
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not _is_excluded(p.relative_to(root))
    )


def plan_pack(pack_dir: Path, pack_meta: dict[str, Any]) -> PluginPlan:
    """Build the :class:`PluginPlan` for one catalog pack."""
    pack = pack_dir.name
    plan = PluginPlan(
        pack=pack,
        name=plugin_name_for_pack(pack),
        description=str(pack_meta.get("description") or "").strip(),
        keywords=[str(tag) for tag in pack_meta.get("tags") or []],
    )

    for dirname in (*COMPONENT_DIRS, *AUXILIARY_DIRS):
        source_dir = pack_dir / dirname
        for source in _walk_files(source_dir):
            rel = source.relative_to(pack_dir).as_posix()
            plan.files.append(
                EmittedFile(source=source, dest=f"{plan.name}/{rel}")
            )

    plan.commands = [p.stem for p in _walk_files(pack_dir / "commands")]
    plan.agents = [p.stem for p in _walk_files(pack_dir / "agents")]
    skills_dir = pack_dir / "skills"
    if skills_dir.is_dir():
        plan.skills = sorted(
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").is_file()
        )
    return plan


def plan_plugins(catalog_root: Path, catalog_yaml: Path) -> list[PluginPlan]:
    """Plan every plugin the catalog can produce, in emission order.

    Packs that ship no commands, agents or skills are skipped: an empty
    plugin is noise in ``/plugin`` and cannot do anything.
    """
    if not catalog_root.is_dir():
        raise BuildPluginsError(f"Catalog directory not found: {catalog_root}")

    packs_meta: dict[str, Any] = {}
    if catalog_yaml.is_file():
        loaded = yaml.safe_load(catalog_yaml.read_text(encoding="utf-8")) or {}
        packs_meta = loaded.get("packs") or {}

    plans: list[PluginPlan] = []
    for pack_dir in sorted(catalog_root.iterdir()):
        if not pack_dir.is_dir() or pack_dir.name in EXCLUDED_DIR_NAMES:
            continue
        plan = plan_pack(pack_dir, packs_meta.get(pack_dir.name) or {})
        if plan.ships_components:
            plans.append(plan)
    return plans


# ---------------------------------------------------------------------------
# Cross-plugin checks
# ---------------------------------------------------------------------------


def check_collisions(plans: list[PluginPlan]) -> None:
    """Fail when two plugins would ship the same command, agent or skill.

    Claude Code namespaces plugin components by plugin name, so a
    collision is not fatal to the loader. It IS fatal to routing: two
    identically named skills give the model no content-level reason to
    prefer either, which is the exact failure ``find_duplicate_
    descriptions`` exists to catch one level down. A collision here
    always means a catalog mistake (a file copied between packs instead
    of moved), so the generator refuses rather than emitting it.
    """
    problems: list[str] = []
    for kind in ("commands", "agents", "skills"):
        owners: dict[str, str] = {}
        for plan in plans:
            for name in getattr(plan, kind):
                previous = owners.get(name)
                if previous is not None:
                    problems.append(
                        f"  {kind[:-1]} {name!r} is shipped by both "
                        f"{previous!r} and {plan.name!r}"
                    )
                else:
                    owners[name] = plan.name
    if problems:
        raise PluginCollisionError(
            "Name collisions across emitted plugins:\n"
            + "\n".join(problems)
            + "\nEach command, agent and skill must live in exactly one pack."
        )


def check_skill_descriptions(catalog_root: Path, plans: list[PluginPlan]) -> None:
    """Fail when two emitted skills share a description byte for byte.

    Reuses the routing-eval checker so the generator and
    ``check_routing_evals`` cannot disagree about what a duplicate is.
    Scoped to skills that actually ship: a duplicate between two packs
    that never reach a marketplace is not this command's problem.
    """
    emitted = {name for plan in plans for name in plan.skills}
    skills = [
        skill
        for skill in scan_catalog_skills(catalog_root)
        if skill.path.parent.name in emitted
    ]
    dupes = find_duplicate_descriptions(skills)
    if dupes:
        lines = [
            f"  {a!r} and {b!r} share the description: {desc[:80]!r}"
            for a, b, desc in dupes
        ]
        raise PluginCollisionError(
            "Duplicate skill descriptions across emitted plugins:\n"
            + "\n".join(lines)
            + "\nNothing can route between two skills that describe "
            "themselves identically."
        )


# ---------------------------------------------------------------------------
# Manifest rendering
# ---------------------------------------------------------------------------


def _dump_json(data: dict[str, Any]) -> str:
    """Render a manifest: two-space indent, key order as constructed."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_plugin_manifest(plan: PluginPlan, version: str) -> str:
    """Render one ``.claude-plugin/plugin.json``."""
    manifest: dict[str, Any] = {
        "name": plan.name,
        "description": plan.description,
        "version": version,
        "author": {"name": MARKETPLACE_OWNER},
        "license": PLUGIN_LICENSE,
    }
    if plan.keywords:
        manifest["keywords"] = plan.keywords
    return _dump_json(manifest)


def render_marketplace_manifest(plans: list[PluginPlan], version: str) -> str:
    """Render ``.claude-plugin/marketplace.json`` for the whole tree."""
    entries: list[dict[str, Any]] = []
    for plan in plans:
        entry: dict[str, Any] = {
            "name": plan.name,
            "source": f"./{plan.name}",
            "description": plan.description,
            "version": version,
        }
        if plan.keywords:
            entry["keywords"] = plan.keywords
        entries.append(entry)

    manifest: dict[str, Any] = {
        "name": MARKETPLACE_NAME,
        "owner": {"name": MARKETPLACE_OWNER},
        "description": MARKETPLACE_DESCRIPTION,
        "version": version,
        "plugins": entries,
    }
    return _dump_json(manifest)


def render_mcp_config() -> str:
    """Render ``wopr-core/.mcp.json``.

    ``${CLAUDE_PLUGIN_ROOT}`` is expanded by Claude Code in ``command``,
    ``args`` and ``env`` for stdio servers. ``WOPR_PLUGIN_ROOT`` is
    passed through so the server can find its bundled resources without
    inferring anything from ``__file__`` (see
    :func:`wopr.config.plugin_resources_root`).
    """
    config = {
        "mcpServers": {
            MCP_SERVER_KEY: {
                "command": "${CLAUDE_PLUGIN_ROOT}/" + BOOTSTRAP_SCRIPT_REL,
                "env": {"WOPR_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}"},
            }
        }
    }
    return _dump_json(config)


def render_bootstrap_script() -> str:
    """Render the shim that launches the bundled server through uv.

    The shim exists so ``.mcp.json`` can name one stable command while
    the launch details (uv, the project path, the missing-uv guidance)
    live in a file that can be read and debugged. It resolves the
    plugin root from ``WOPR_PLUGIN_ROOT`` (set by ``.mcp.json``), then
    ``CLAUDE_PLUGIN_ROOT``, then from its own location, so it also
    works when run by hand from a terminal.
    """
    return """#!/usr/bin/env bash
# Launch the WOPR MCP server bundled inside this plugin.
#
# Generated by `wopr build-plugins`. Do not edit by hand: the next
# `/plugin update` overwrites it.
#
# uv is the only prerequisite. It is a static binary that provisions
# its own Python, installs into the user profile, and needs no admin
# rights. First launch resolves the server's two dependencies from
# PyPI into a venv beside the bundled server; later launches reuse it.
set -euo pipefail

plugin_root="${WOPR_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}"
if [ -z "$plugin_root" ]; then
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  plugin_root="$(dirname "$script_dir")"
fi

if ! command -v uv >/dev/null 2>&1; then
  {
    echo "wopr: uv was not found on PATH, and the bundled WOPR MCP server needs it."
    echo "Install uv, then restart Claude Code:"
    echo "  Windows: powershell -c \\"irm https://astral.sh/uv/install.ps1 | iex\\""
    echo "           or: winget install astral-sh.uv"
    echo "  macOS:   brew install uv"
    echo "  Linux:   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "Docs: https://docs.astral.sh/uv/getting-started/installation/"
  } >&2
  exit 1
fi

export WOPR_PLUGIN_ROOT="$plugin_root"
exec uv run --project "$plugin_root/@SERVER_DIR@" @SERVER_ENTRY@
""".replace("@SERVER_DIR@", PLUGIN_SERVER_DIRNAME).replace(
        "@SERVER_ENTRY@", SERVER_ENTRY_POINT
    )


def render_server_pyproject(version: str) -> str:
    """Render the bundled server's ``pyproject.toml``.

    Runtime projection only. The source project's dev extra,
    ruff/mypy/pytest configuration and catalog build hook are all
    absent: none of them is needed to answer an MCP request, and every
    one of them would cost the user resolve time on first launch. The
    ``embeddings`` extra's deps are promoted into the bundle's base
    dependencies (see :data:`SERVER_DEPENDENCIES`) so the semantic
    half of CRAG works out of the box; the ``bedrock`` extra stays
    opt-in.
    """
    deps = "\n".join(f'    "{dep}",' for dep in SERVER_DEPENDENCIES)
    return f"""# Generated by `wopr build-plugins`. Do not edit by hand.
#
# The runtime projection of the WOPR package: the server source plus
# the dependencies it imports at run time (including the embeddings
# stack for CRAG's semantic search). `uv run --project .` resolves
# these on first launch.
[project]
name = "wopr"
version = "{version}"
description = "WOPR MCP server, bundled inside the wopr-core Claude Code plugin"
requires-python = ">=3.10"
dependencies = [
{deps}
]

[project.scripts]
{SERVER_ENTRY_POINT} = "wopr.cli:serve"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wopr"]
"""


def render_marker(version: str) -> str:
    """Render the marker file that authorizes wipe-and-rewrite."""
    return _dump_json(
        {
            "generator": f"{CLI_PROG} build-plugins",
            "generator_version": version,
            "marketplace": MARKETPLACE_NAME,
            "warning": (
                "This directory is regenerated in full on every "
                f"`{CLI_PROG} build-plugins` run. Every file is overwritten. "
                "Edit the catalog, not this tree."
            ),
        }
    )


def render_marketplace_readme(plans: list[PluginPlan], version: str) -> str:
    """Render the marketplace README (install matrix + uv prerequisite)."""
    rows = "\n".join(
        f"| `{plan.name}` | {plan.description} |" for plan in plans
    )
    return f"""# WOPR plugins

Generated by `wopr build-plugins`. Do not hand-edit: this whole tree is
rewritten on every run. Change the catalog in the `wopr` repo instead.

Marketplace: `{MARKETPLACE_NAME}` (version {version})

## Install

```
/plugin marketplace add <path-or-repo>
/plugin install {server_plugin_name()}@{MARKETPLACE_NAME}
```

Install `wopr-core` first: it carries the MCP server every other pack's
skills call. Add the rest as needed.

| Plugin | What it ships |
|--------|---------------|
{rows}

## Prerequisite: uv

`wopr-core` runs its MCP server through [uv](https://docs.astral.sh/uv/).
uv is a static binary, installs into your user profile, needs no admin
rights, and provisions its own Python, so nothing else is required.

- Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`,
  or `winget install astral-sh.uv`
- macOS: `brew install uv`
- Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

On Windows, Claude Code bundles Git Bash, so the bootstrap shim and the
pack scripts run there unchanged.

First MCP launch resolves the server's dependencies and takes a few
seconds. Later launches reuse the resolved environment.
"""


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _prepare_output_dir(out_dir: Path) -> None:
    """Create or clear ``out_dir``, refusing anything we did not generate.

    The generator's contract is wipe-and-rewrite, which is exactly the
    contract that turns a mistyped ``--out`` into data loss. The marker
    file is the guard: an existing, non-empty directory without it is
    refused outright, with the path in the message.
    """
    if out_dir.exists() and not out_dir.is_dir():
        raise UnsafeOutputDirError(
            f"Output path exists and is not a directory: {out_dir}"
        )

    if out_dir.is_dir():
        entries = sorted(out_dir.iterdir())
        if entries and not (out_dir / MARKER_NAME).is_file():
            raise UnsafeOutputDirError(
                f"Refusing to write into {out_dir}: it is not empty and has "
                f"no {MARKER_NAME} marker, so it was not generated by "
                "`wopr build-plugins`. This command wipes and rewrites its "
                "output directory. Pick an empty or previously generated "
                "path, or delete that one yourself first."
            )
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        return

    out_dir.mkdir(parents=True)


def _write_text(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _copy_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def _emit_file(source: Path, dest: Path, prefix: str) -> None:
    """Copy one catalog file, rewriting tool names in markdown.

    Everything else is a byte-for-byte copy, so ``copy2``'s mode
    preservation still covers the executable scripts packs ship.
    """
    if source.suffix.lower() not in REWRITTEN_SUFFIXES:
        _copy_file(source, dest)
        return
    text = source.read_text(encoding="utf-8")
    _write_text(dest, rewrite_tool_names(text, prefix))


def _write_server_bundle(
    core_dir: Path, repo_root: Path, catalog_root: Path, version: str, prefix: str
) -> int:
    """Copy the server into ``wopr-core/server/``. Returns the file count.

    Three parts, in the layout ``uv run --project`` and
    :func:`wopr.config.plugin_resources_root` expect:

    * ``server/src/wopr/`` - the package source, minus caches. Tests,
      evals and repo tooling live outside ``src/`` and never enter.
    * ``server/resources/`` - the catalog subtrees the surviving tools
      read at run time, plus ``catalog.yaml``. Same relative layout as
      the wheel's ``wopr/resources/``, so a plugin install and a pip
      install resolve identically. Markdown here gets the same tool-name
      rewrite as the component tree: ``get_pack_template`` hands this
      content straight to a model, so a source-form tool name in a
      template is as dead as one in a skill body.
    * ``server/pyproject.toml`` - runtime dependencies and the
      ``wopr-serve`` entry point.
    """
    server_dir = core_dir / PLUGIN_SERVER_DIRNAME
    count = 0

    package_src = repo_root / "src" / "wopr"
    for source in _walk_package_files(package_src):
        rel = source.relative_to(package_src)
        _copy_file(source, server_dir / "src" / "wopr" / rel)
        count += 1

    resources_dir = server_dir / PLUGIN_RESOURCES_DIRNAME
    for parts in BUNDLED_RESOURCES:
        subtree = catalog_root.joinpath(*parts)
        for source in _walk_files(subtree):
            rel = source.relative_to(subtree)
            _emit_file(source, resources_dir.joinpath(*parts, *rel.parts), prefix)
            count += 1

    catalog_yaml = repo_root / "catalog.yaml"
    if catalog_yaml.is_file():
        _copy_file(catalog_yaml, resources_dir / "catalog.yaml")
        count += 1

    _write_text(server_dir / "pyproject.toml", render_server_pyproject(version))
    return count + 1


def _walk_package_files(package_src: Path) -> list[Path]:
    """Every file of the server package worth shipping, sorted."""
    if not package_src.is_dir():
        raise BuildPluginsError(f"Server package source not found: {package_src}")
    return sorted(
        p
        for p in package_src.rglob("*")
        if p.is_file()
        and p.suffix not in {".pyc", ".pyo"}
        and not _is_excluded(p.relative_to(package_src))
    )


def build_plugins(out_dir: Path, repo_root: Path) -> BuildResult:
    """Generate the whole marketplace tree at ``out_dir``.

    Args:
        out_dir: Marketplace root. Created if absent; wiped and
            rewritten if it carries this generator's marker file;
            refused otherwise.
        repo_root: The ``wopr`` repo root (holds ``catalog/``,
            ``catalog.yaml`` and ``src/wopr/``).

    Raises:
        UnsafeOutputDirError: ``out_dir`` exists, is non-empty, and was
            not generated by this command.
        PluginCollisionError: two plugins would ship the same component
            name or two emitted skills share a description.
        BuildPluginsError: the catalog or the server source is missing.
    """
    catalog_root = repo_root / "catalog"
    catalog_yaml = repo_root / "catalog.yaml"
    version = to_semver(__version__)

    plans = plan_plugins(catalog_root, catalog_yaml)
    if not plans:
        raise BuildPluginsError(
            f"No pack under {catalog_root} ships commands, agents or skills."
        )
    check_collisions(plans)
    check_skill_descriptions(catalog_root, plans)

    core_plan = next((p for p in plans if p.pack == CORE_PACK), None)
    if core_plan is None:
        raise BuildPluginsError(
            f"Pack {CORE_PACK!r} is missing from {catalog_root}; it carries "
            "the MCP server and cannot be skipped."
        )

    _prepare_output_dir(out_dir)

    # One prefix for the whole tree: `wopr` is the marketplace's only
    # MCP server, and `wopr-core` is the only plugin that declares it.
    prefix = runtime_tool_prefix(core_plan.name)

    file_count = 0
    for plan in plans:
        for emitted in plan.files:
            _emit_file(emitted.source, out_dir / emitted.dest, prefix)
            file_count += 1
        _write_text(
            out_dir / plan.name / PLUGIN_MANIFEST_DIR / PLUGIN_MANIFEST_NAME,
            render_plugin_manifest(plan, version),
        )
        file_count += 1

    core_dir = out_dir / core_plan.name
    _write_text(core_dir / MCP_CONFIG_NAME, render_mcp_config())
    _write_text(
        core_dir / BOOTSTRAP_SCRIPT_REL, render_bootstrap_script(), executable=True
    )
    file_count += 2
    file_count += _write_server_bundle(
        core_dir, repo_root, catalog_root, version, prefix
    )

    _write_text(
        out_dir / PLUGIN_MANIFEST_DIR / MARKETPLACE_MANIFEST_NAME,
        render_marketplace_manifest(plans, version),
    )
    _write_text(out_dir / "README.md", render_marketplace_readme(plans, version))
    _write_text(out_dir / MARKER_NAME, render_marker(version))
    file_count += 3

    return BuildResult(
        out_dir=out_dir,
        marketplace_name=MARKETPLACE_NAME,
        version=version,
        plugins=plans,
        file_count=file_count,
    )


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repo root that holds ``catalog/`` and ``src/wopr/``.

    Walks up from this module's own location, which is correct for both
    an editable install (the repo itself) and a source checkout. A
    non-editable install has no catalog to build from, and the error
    says so rather than emitting an empty marketplace.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "catalog").is_dir() and (candidate / "src" / "wopr").is_dir():
            return candidate
    raise BuildPluginsError(
        "Could not find the wopr repo root (a directory holding both "
        f"catalog/ and src/wopr/) above {here}. `wopr build-plugins` "
        "generates from the source catalog and must run from a checkout."
    )


def _count(n: int, noun: str) -> str:
    """``2, "skill"`` -> ``"2 skills"``; zero renders as the empty string."""
    if n == 0:
        return ""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def format_build_report(result: BuildResult) -> str:
    """Human-readable summary of a completed run."""
    lines = [
        f"Wrote {result.marketplace_name} to {result.out_dir}",
        f"  version: {result.version}",
        f"  plugins: {len(result.plugins)}",
    ]
    for plan in result.plugins:
        parts = [
            _count(len(plan.commands), "command"),
            _count(len(plan.agents), "agent"),
            _count(len(plan.skills), "skill"),
        ]
        parts = [part for part in parts if part]
        suffix = " + bundled MCP server" if plan.pack == CORE_PACK else ""
        lines.append(f"    {plan.name}: {', '.join(parts)}{suffix}")
    lines.append(f"  files: {result.file_count}")
    return "\n".join(lines)
