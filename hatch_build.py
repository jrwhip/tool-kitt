"""Custom hatchling build hook: glob every ``catalog/<pack>`` dir into the wheel.

Replaces the per-pack ``[tool.hatch.build.targets.wheel.force-include]``
list in ``pyproject.toml``. The list-style required a manual edit to
``pyproject.toml`` every time a new pack landed under ``catalog/``;
the audit flagged the brittleness ([TICKET-ID] AC21). This hook
auto-discovers every immediate sub-directory of ``catalog/`` and
adds it to the wheel's force-include map at build time.

Each pack ``catalog/<pack>/`` lands at
``wopr/resources/<pack>/`` inside the installed wheel, matching
the prior explicit-list mapping. The standalone ``catalog.yaml``
manifest also lands at ``wopr/catalog.yaml``.

Hooks register via the ``[tool.hatch.build.targets.wheel.hooks.custom]``
table in ``pyproject.toml``. Hatchling auto-discovers this file at
build time when ``hatch_build.py`` exists at the project root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CatalogForceIncludeHook(BuildHookInterface):
    """Enumerate catalog packs and add each as a wheel force-include entry."""

    PLUGIN_NAME = "catalog-force-include"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Populate ``build_data["force_include"]`` with the catalog packs.

        ``BuildHookInterface.root`` is the project root (where
        ``pyproject.toml`` lives). The catalog source dir is
        ``<root>/catalog``; each immediate sub-directory under it is
        a pack. We map source paths to wheel-internal destinations
        the same way the prior explicit list did:
        ``catalog/<pack>`` → ``wopr/resources/<pack>``.

        Files (not directories) directly under ``catalog/`` are
        ignored. The standalone ``catalog.yaml`` manifest at the
        project root is handled separately below.
        """
        catalog_dir = Path(self.root) / "catalog"
        if not catalog_dir.is_dir():
            return

        force_include = build_data.setdefault("force_include", {})

        for entry in sorted(catalog_dir.iterdir()):
            if not entry.is_dir():
                continue
            src = str(entry.relative_to(self.root))
            dst = f"wopr/resources/{entry.name}"
            force_include[src] = dst

        # The catalog manifest lives at the project root, alongside
        # ``pyproject.toml``. It needs to ride along inside the wheel
        # at the package root so ``catalog.get_bundled_catalog_yaml``
        # finds it post-install.
        catalog_manifest = Path(self.root) / "catalog.yaml"
        if catalog_manifest.is_file():
            force_include["catalog.yaml"] = "wopr/catalog.yaml"
