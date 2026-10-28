"""
Pack inspection commands for KITT.

Handles the read-only ``list`` and ``catalog`` subcommands. The
mutating ``add`` / ``remove`` pair lived here too in the prior toolset;
both re-ran the per-CLI installer, which does not cross over, so they
are not part of this surface.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .catalog import (
    get_catalog_path,
    load_catalog,
    read_lock_file,
    resolve_install_target,
)
from .product import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def cmd_list(workspace: Path, *, is_global: bool = False) -> int:
    """Show installed packs."""
    _shared_dir, lock_dir, _label = resolve_install_target(workspace, is_global)
    lock = read_lock_file(lock_dir)

    if not lock:
        if is_global:
            logger.info("No global packs installed.")
        else:
            logger.info("No packs installed for this workspace.")
        return 0

    scope = "Global packs" if is_global else "Installed packs"
    packs = lock.get("installed_packs", [])
    logger.info("%s (%d):", scope, len(packs))
    for pack in packs:
        marker = " (always)" if pack == "_core" else ""
        logger.info("  - %s%s", pack, marker)

    if not is_global:
        logger.info("Workspace: %s", workspace)
    if lock.get("catalog_source"):
        logger.info("Catalog: %s", lock["catalog_source"])
    if lock.get("installed_at"):
        logger.info("Installed: %s", lock["installed_at"])

    return 0


def cmd_catalog(catalog_dir_override: str | None = None) -> int:
    """Show all available packs from the catalog."""
    catalog_dir = Path(catalog_dir_override) if catalog_dir_override else get_catalog_path()
    catalog = load_catalog(catalog_dir)
    packs = catalog.get("packs", {})
    profiles = catalog.get("profiles", {})

    logger.info("Available packs (%d):", len(packs))
    for name, info in sorted(packs.items()):
        desc = info.get("description", "")
        tags = info.get("tags", [])
        always = " [always installed]" if info.get("always_installed") else ""
        tag_str = f" ({', '.join(tags)})" if tags else ""
        logger.info("  %s: %s%s%s", name, desc, tag_str, always)

    if profiles:
        logger.info("\nProfiles (%d):", len(profiles))
        for name, info in sorted(profiles.items()):
            desc = info.get("description", "")
            pack_list = ", ".join(info.get("packs", []))
            logger.info("  %s: %s [%s]", name, desc, pack_list)

    return 0
