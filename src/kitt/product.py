"""Product identity: every runtime name derived from the product name.

One module owns the strings that make this distribution *this*
distribution: the MCP server key, the plugin and marketplace names,
the environment-variable prefix, the config filename, the home
directory, the logger name. Code that needs one of these imports it
from here instead of spelling the literal, so a rebrand touches this
file plus the things that are content rather than runtime identity.

Deliberately NOT parameterized here, because they are packaging or
content identity rather than runtime identity, and a constant would
only hide the literal from a reviewer:

* the Python package name (``src/kitt``, ``from kitt import ...``) and
  the console-script names in ``pyproject.toml``;
* catalog file and directory names (``catalog/_core/commands/kitt-*``);
* MCP tool names (``propose_kitt_yml``) and the ``mcp__kitt__`` spelling
  the catalog uses, which :mod:`build_plugins` derives from
  :data:`MCP_SERVER_KEY` at build time;
* prose.

Those are renamed by the same scripted pass that renames this file's
values, and the test suite is what proves the pass was complete.
"""

from __future__ import annotations

PRODUCT = "kitt"
"""Lowercase product name. Root of every derived name below."""

PRODUCT_TITLE = "KITT"
"""How the product is written in user-facing text."""

CLI_PROG = PRODUCT
"""The console-script name users type. Matches ``[project.scripts]``."""

SERVER_ENTRY_POINT = f"{PRODUCT}-serve"
"""Console script the plugin bundle launches. Matches ``[project.scripts]``."""

ENV_PREFIX = f"{PRODUCT_TITLE}_"
"""Prefix of every environment variable this product reads."""

HOME_DIRNAME = f".{PRODUCT}"
"""Per-user state directory under ``$HOME``."""

CONFIG_FILENAME = f"{PRODUCT}.yml"
"""Per-workspace config file at the workspace root."""

LEGACY_CONFIG_FILENAME = f".{PRODUCT}.yaml"
"""Older per-workspace config spelling, still read for back-compat."""

LOCK_FILENAME = f"{PRODUCT}.lock.yaml"
"""Installed-packs lock file."""

LOGGER_NAME = PRODUCT
"""Root logger name shared by every module."""

MCP_SERVER_KEY = PRODUCT
"""Key under ``mcpServers`` in the emitted ``.mcp.json``, and the
server's own name. Half of the runtime tool namespace."""

PLUGIN_PREFIX = f"{PRODUCT}-"
"""Every emitted plugin is named ``<prefix><pack>``."""

MARKETPLACE_NAME = f"{PRODUCT}-marketplace"
MARKETPLACE_OWNER = "Jared Whipple"
MARKETPLACE_DESCRIPTION = (
    f"{PRODUCT_TITLE}: a right-sized agent harness for Claude Code, shipped "
    "as one plugin per pack."
)

MARKER_NAME = f".{PRODUCT}-generated"
"""Marker file at the root of every tree the plugin generator writes."""
