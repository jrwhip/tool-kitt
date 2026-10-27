"""
Catalog and pack resolution for WOPR.

Handles:
- Loading catalog.yaml (pack and profile definitions)
- Reading .wopr.yaml per-project config
- Resolving which packs to install from CLI flags, config, or interactive selection
- Locating resources across bundled and external catalog sources
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from ._atomic_write import atomic_write_text
from .config import plugin_resources_root
from .models import LockFileData
from .product import HOME_DIRNAME, LEGACY_CONFIG_FILENAME, LOCK_FILENAME, LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def get_bundled_catalog_dir(pack_name: str = "_core") -> Path:
    """Get the bundled catalog directory (ships inside the pip package)."""
    return Path(__file__).parent / "resources" / pack_name


def get_bundled_catalog_yaml() -> Path:
    """Get the bundled catalog.yaml path."""
    return Path(__file__).parent / "catalog.yaml"


def get_repo_catalog_yaml() -> Path:
    """Get the catalog.yaml from the repo root (development mode)."""
    return Path(__file__).parent.parent.parent / "catalog.yaml"


def load_catalog(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load catalog.yaml from the specified path, bundled location, or repo root.

    Args:
        catalog_path: Optional explicit path to a catalog directory.
                      If provided, looks for catalog.yaml inside it or at parent.

    Returns:
        Parsed catalog dict with 'packs' and 'profiles' keys. Typed as
        ``dict[str, Any]`` rather than a stricter shape because this is raw
        YAML parsed from an operator-authored file with no schema
        validation applied here.
    """
    candidates = []

    if catalog_path:
        candidates.append(catalog_path / "catalog.yaml")
        candidates.append(catalog_path.parent / "catalog.yaml")

    # Plugin install: `wopr build-plugins` copies catalog.yaml into the
    # bundled server's resources dir, which neither of the two
    # path-arithmetic candidates below can reach (the server package
    # sits at <plugin>/server/src/wopr/, its resources one level up
    # and outside the package). Set only when WOPR_PLUGIN_ROOT is.
    plugin_resources = plugin_resources_root()
    if plugin_resources is not None:
        candidates.append(plugin_resources / "catalog.yaml")

    # Bundled catalog.yaml (installed via pip)
    candidates.append(get_bundled_catalog_yaml())

    # Repo root catalog.yaml (development mode)
    candidates.append(get_repo_catalog_yaml())

    for candidate in candidates:
        if candidate.exists():
            try:
                return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError) as e:
                logger.warning("Failed to load %s: %s", candidate, e)

    return {"packs": {}, "profiles": {}}


def read_wopr_config(workspace: Path) -> dict[str, Any] | None:
    """Read .wopr.yaml from the workspace root.

    Returns:
        Parsed config dict, or None if no config file exists.
    """
    config_file = workspace / LEGACY_CONFIG_FILENAME
    if not config_file.exists():
        return None

    try:
        return yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to read %s: %s", config_file, e)
        return None


def get_catalog_path(
    cli_catalog: str | None = None,
    config: dict[str, Any] | None = None,
) -> Path | None:
    """Determine the external catalog directory path.

    Resolution order:
    1. --catalog CLI flag
    2. WOPR_CATALOG environment variable
    3. 'catalog' key in .wopr.yaml config
    4. None (use bundled only)
    """
    if cli_catalog:
        return Path(cli_catalog).expanduser().resolve()

    # Read env var directly here rather than threading ``ServerConfig``
    # through every CLI subcommand. ``ServerConfig.from_env()`` is a
    # pure factory and could be constructed without ``ServerContext``,
    # so the bypass is not technically required; routing the CLI
    # subcommands through ``ServerConfig`` is a future cleanup, but
    # the value of doing it now is small (the env var resolution is
    # the same either way) and the cost is touching every CLI
    # subcommand entry point.
    from .config import ENV_WOPR_CATALOG

    env_catalog = os.environ.get(ENV_WOPR_CATALOG)
    if env_catalog:
        return Path(env_catalog).expanduser().resolve()

    if config and "catalog" in config:
        return Path(config["catalog"]).expanduser().resolve()

    # Check if we're running from the repo (development mode)
    repo_catalog = Path(__file__).parent.parent.parent / "catalog"
    if repo_catalog.exists():
        return repo_catalog

    return None


def resolve_packs(
    cli_packs: list[str] | None = None,
    cli_profile: str | None = None,
    config: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
    interactive: bool = False,
    interactive_selector: Callable[[dict[str, Any]], list[str]] | None = None,
) -> list[str]:
    """Resolve the final list of packs to install.

    Resolution order:
    1. --packs CLI flag (explicit list)
    2. --profile CLI flag (named profile from catalog)
    3. .wopr.yaml 'packs' list
    4. Interactive selection (if interactive=True and no config)
    5. Empty list (only _core will be installed)

    _core is always included in the result.

    Args:
        cli_packs: Explicit pack list from CLI (e.g., ["angular", "security"])
        cli_profile: Profile name from CLI (e.g., "angular-team")
        config: Parsed .wopr.yaml config dict
        catalog: Parsed catalog.yaml dict
        interactive: Whether to run interactive selection as fallback

    Returns:
        List of pack names (always includes "_core").
    """
    catalog = catalog or {}
    packs = set()

    if cli_packs:
        packs.update(cli_packs)
    elif cli_profile:
        profiles = catalog.get("profiles", {})
        if cli_profile in profiles:
            packs.update(profiles[cli_profile].get("packs", []))
        else:
            available = list(profiles.keys())
            logger.warning("Profile '%s' not found.", cli_profile)
            if available:
                logger.warning("  Available profiles: %s", ", ".join(available))
    elif config and "packs" in config:
        packs.update(config["packs"])
    elif interactive:
        if interactive_selector is None:
            logger.warning(
                "Interactive pack selection requested but no "
                "``interactive_selector`` callback provided. Returning "
                "core only. Pass the CLI's selector to resolve_packs to "
                "enable the prompt."
            )
        else:
            packs.update(interactive_selector(catalog))

    # _core is always included
    packs.add("_core")

    return sorted(packs)


# ``interactive_pack_selection`` previously lived here. It moved to
# :mod:`cli_setup` (DEMO-123 AC23) so the catalog stays pure logic
# with no ``input()`` or stdout-prompt dependency. ``resolve_packs``
# now reaches the prompt via the ``interactive_selector`` callback;
# the CLI passes the implementation when interactive mode is wanted.


def find_pack_resources(
    pack_name: str,
    catalog_path: Path | None = None,
) -> Path | None:
    """Find the directory for a given pack.

    Checks external catalog first, then bundled resources.

    Args:
        pack_name: Name of the pack (e.g., "_core", "angular")
        catalog_path: Optional external catalog directory

    Returns:
        Path to the pack directory, or None if not found.
    """
    # Check external catalog first
    if catalog_path:
        external = catalog_path / pack_name
        if external.exists():
            return external

    # Check bundled resources
    bundled = get_bundled_catalog_dir(pack_name)
    if bundled.exists():
        return bundled

    return None


def get_global_home() -> Path:
    """Get the global WOPR home directory.

    Resolution order:

    1. ``ServerContext.get().config.wopr_home`` when the server context
       is initialized AND the field is set. This is the configured-once
       value MCP tool paths read at every call.
    2. ``WOPR_HOME`` env var (read directly here). Covers CLI paths
       (``wopr add/remove/init``) where the server context is not yet
       initialized, and covers test fixtures that monkeypatch the env
       var without rebuilding the config.
    3. ``~/.wopr`` as the final default.

    The env-var fallback is deliberate; making this pure-config-only
    would force CLI subcommands to construct a config and force the
    test suite to thread the value through every fixture. Centralizing
    the read in ``ServerConfig.from_env`` already removes the
    fragmentation the perfectionist audit flagged.
    """
    try:
        from .context import ServerContext

        ctx = ServerContext.get()
        if ctx.config.wopr_home:
            return Path(ctx.config.wopr_home).expanduser().resolve()
    except RuntimeError:
        # No server context (CLI subcommand path). Fall through to env.
        pass

    from .config import ENV_WOPR_HOME

    return Path(
        os.environ.get(ENV_WOPR_HOME, str(Path.home() / HOME_DIRNAME))
    ).expanduser().resolve()


def resolve_install_target(
    workspace: Path, is_global: bool
) -> tuple[Path, Path, str]:
    """Resolve ``(shared_dir, lock_dir, label)`` for an install target.

    Used by the read-only ``wopr list`` subcommand so the
    workspace-vs-global split lives in one place: a global install is
    read from ``~/.wopr`` (:func:`get_global_home`), a workspace
    install from the project's ``.ai-cli/`` directory.

    Returns:
        ``(shared_dir, lock_dir, label)`` where ``shared_dir`` is the
        resource copy the MCP resolves from, ``lock_dir`` holds
        ``wopr.lock.yaml``, and ``label`` is a human-facing description
        for logs.
    """
    if is_global:
        home = get_global_home()
        return home / "shared", home, f"global ({home})"
    return (
        workspace / ".ai-cli" / "shared",
        workspace / ".ai-cli",
        str(workspace),
    )


def read_lock_file(lock_dir: Path) -> LockFileData | None:
    """Read the lock file from a directory.

    Args:
        lock_dir: Directory containing ``wopr.lock.yaml``.
                  For workspace installs, pass ``workspace / ".ai-cli"``.
                  For global installs, pass ``get_global_home()``.

    Returns:
        Parsed lock file data, or None if no lock file exists.
    """
    lock_file = lock_dir / LOCK_FILENAME
    if not lock_file.exists():
        return None

    try:
        data = yaml.safe_load(lock_file.read_text(encoding="utf-8")) or {}
        result = LockFileData(
            version=data.get("version", ""),
            installed_packs=data.get("installed_packs", []),
            installed_at=data.get("installed_at", ""),
        )
        if data.get("catalog_source"):
            result["catalog_source"] = data["catalog_source"]
        return result
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to read %s: %s", lock_file, e)
        return None


def write_lock_file(
    lock_dir: Path,
    installed_packs: list[str],
    catalog_source: str | None = None,
    version: str | None = None,
) -> None:
    """Write the lock file to a directory.

    Args:
        lock_dir: Directory to write ``wopr.lock.yaml`` into.
                  For workspace installs, pass ``workspace / ".ai-cli"``.
                  For global installs, pass ``get_global_home()``.
        installed_packs: List of installed pack names
        catalog_source: Path to external catalog (if used)
        version: WOPR version
    """
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_data: LockFileData = {
        "version": version or __version__,
        "installed_packs": sorted(installed_packs),
        "installed_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    if catalog_source:
        lock_data["catalog_source"] = catalog_source

    lock_file = lock_dir / LOCK_FILENAME
    # Atomic write: a crash mid-write leaves the operator with a
    # truncated lock file that breaks ``_load_installed_packs`` (logs
    # at DEBUG and silently returns no packs), which then masks the
    # broken install behind a doctor report claiming nothing is
    # installed. Use the shared helper.
    atomic_write_text(
        lock_file,
        yaml.dump(lock_data, default_flow_style=False, sort_keys=False),
    )

    logger.info("  Wrote lock file: %s", lock_file)
