"""Runtime context for the WOPR MCP server.

Holds resolved workspace, CLI type, and shared directory accessors.
Created once at startup via ServerContext.init(), accessed via ServerContext.get().
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING

from .catalog import get_global_home
from .config import CliType, ServerConfig
from .product import LOGGER_NAME

if TYPE_CHECKING:
    from typing import Any, TypeAlias

    from mcp.server.fastmcp import Context
    from mcp.server.session import ServerSession

    # Fully parameterized so annotations satisfy disallow_any_generics.
    # No WOPR tool reads ctx.request_context.lifespan_context, hence
    # ``object``; RequestT is the SDK's own default (Any).
    ToolContext: TypeAlias = Context[ServerSession, object, Any]
else:
    # At runtime this is the bare Context class — the exact object the
    # tool annotations named before the alias existed, so runtime
    # behavior is provably unchanged. FastMCP's find_context_parameter()
    # detects the injection target via inspect.isclass(annotation) (or
    # class-valued union args). A parameterized Context[...] currently
    # ALSO passes that check (pydantic generics build real classes), but
    # that is an implementation detail of pydantic/the SDK, not a
    # contract; the bare class is the only form the SDK documents.
    # test_every_ctx_parameter_receives_context_injection pins this —
    # if you change this branch, that test is the tripwire.
    from mcp.server.fastmcp import Context

    ToolContext = Context

logger = logging.getLogger(LOGGER_NAME)


class WorkspaceNotConfiguredError(RuntimeError):
    """No workspace could be resolved from configuration.

    WOPR deliberately does NOT fall back to the server's launch
    directory. A single long-lived MCP server is shared across many git
    worktrees and CLI sessions; binding to whatever directory the
    process happened to spawn in is how a write once landed in an
    unrelated worktree. When nothing valid is configured, resolution
    raises this so the misconfiguration is visible instead of silently
    targeting the wrong project.
    """


class ServerContext:
    """Runtime state for the MCP server.

    Implements a process-wide singleton via :meth:`init` / :meth:`get`
    / :meth:`reset`. Functionally equivalent to a module-level global,
    structured as a class so the lifetime and the reset hook are
    explicit. Use the singleton for request/context state (workspace,
    CLI type, resolved paths); use module-level state with ``global``
    for module-scoped concerns that have no business knowing about the
    server context (see :mod:`tools._embeddings` for an example).
    """

    _instance: ServerContext | None = None

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._workspace: Path | None = None

    @classmethod
    def init(cls, config: ServerConfig) -> ServerContext:
        """Create and store the singleton context."""
        cls._instance = cls(config)
        return cls._instance

    @classmethod
    def get(cls) -> ServerContext:
        """Get the singleton context. Raises if not initialized."""
        if cls._instance is None:
            raise RuntimeError(
                "ServerContext not initialized. Call ServerContext.init() first."
            )
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the singleton context.

        Public hook for tests so they do not reach into the private
        ``_instance`` attribute. Production code does not call this;
        the MCP server is a single-process singleton for its lifetime.
        """
        cls._instance = None

    @property
    def cli_type(self) -> CliType:
        return self.config.cli_type

    @property
    def workspace(self) -> Path:
        if self._workspace is None:
            self._workspace = self._resolve_workspace()
        return self._workspace

    @workspace.setter
    def workspace(self, value: Path) -> None:
        self._workspace = value

    @property
    def core_pack_root(self) -> Path:
        """Path to the bundled ``_core`` pack inside the installed package.

        Not the package root. This is specifically the install-bundled
        copy of the ``_core`` pack's resources, used as the fallback
        for :attr:`shared_dir` when no workspace-local
        ``.ai-cli/shared/`` exists. Named to match what it actually
        returns (the previous name ``package_root`` was misleading;
        callers expected it to be the package's import root).
        """
        return Path(__file__).parent / "resources" / "_core"

    def shared_dir_for(self, workspace: Path | None = None) -> Path:
        """Highest-priority shared-resource directory for this workspace.

        Resolution order:

        1. ``<workspace>/.ai-cli/shared/`` if it exists. This is the
           workspace-local override; teams commit pack content here to
           pin a project to specific pack versions or to layer custom
           content on top of the global install.
        2. :attr:`core_pack_root` otherwise. This is the bundled
           ``_core`` pack inside the installed package, the "always
           available" fallback.

        Note: the global install directory at ``~/.wopr/shared/`` (see
        :attr:`global_shared_dir`) is NOT consulted here. It is unioned
        with this directory in :meth:`resource_dirs`, which is what
        most callers actually use.
        """
        if workspace is not None:
            local_shared = workspace / ".ai-cli" / "shared"
            if local_shared.exists():
                return local_shared
        return self.core_pack_root

    @property
    def shared_dir(self) -> Path:
        return self.shared_dir_for(self.workspace)

    @property
    def commands_dir(self) -> Path:
        return self.shared_dir / "commands"

    @property
    def skills_dir(self) -> Path:
        return self.shared_dir / "skills"

    @property
    def agents_dir(self) -> Path:
        return self.shared_dir / "agents"

    @property
    def context_dir(self) -> Path:
        return self.shared_dir / "context"

    @property
    def global_shared_dir(self) -> Path | None:
        """Global shared resource directory at ``~/.wopr/shared``.

        Returns None if the directory doesn't exist (no global packs installed).
        """
        d = get_global_home() / "shared"
        return d if d.exists() else None

    def resource_dirs(
        self, category: str, workspace: Path | None = None
    ) -> list[Path]:
        """Return resource directories for a category, highest priority first.

        Aggregates two sources, each contributing only if the
        per-category sub-directory exists:

        1. :attr:`shared_dir` ``/ category`` (workspace-local override
           if present, otherwise the bundled ``_core`` pack root).
        2. :attr:`global_shared_dir` ``/ category`` (``~/.wopr/shared/``
           where global ``wopr add`` installs land).

        The list is ordered by descending priority so callers can
        iterate and take the first hit. Cross-source name collisions
        (the same skill exists in both a workspace override and the
        global install) keep the workspace copy; callers walking the
        list left-to-right see it first.
        """
        dirs = []
        workspace_dir = self.shared_dir_for(workspace) / category
        if workspace_dir.exists():
            dirs.append(workspace_dir)
        global_shared = self.global_shared_dir
        if global_shared:
            global_dir = global_shared / category
            if global_dir.exists():
                dirs.append(global_dir)
        return dirs

    def _resolve_workspace(self) -> Path:
        # Only an explicitly configured workspace is honored, and only if
        # it points at a directory that actually exists. There is
        # deliberately NO git-root / cwd fallback. For a shared,
        # long-lived MCP server the previous fallback silently bound
        # state writes to whatever worktree the process was spawned in,
        # which is how a handoff once overwrote an unrelated project. A
        # stale env var pointing at a deleted directory is skipped with a
        # warning; when nothing valid remains we raise rather than guess.
        candidates: list[tuple[Path | None, str]] = [
            (
                Path(self.config.ai_cli_workspace).expanduser().resolve()
                if self.config.ai_cli_workspace
                else None,
                "AI_CLI_WORKSPACE env var",
            ),
            (
                Path(self.config.wopr_workspace).expanduser().resolve()
                if self.config.wopr_workspace
                else None,
                "WOPR_WORKSPACE env var",
            ),
        ]

        for path, source in candidates:
            if path is None:
                continue
            if path.is_dir():
                logger.info("Workspace: %s (from %s)", path, source)
                return path
            logger.warning(
                "Configured workspace %s (%s) does not exist; skipping it.",
                path,
                source,
            )

        raise WorkspaceNotConfiguredError(
            "No WOPR workspace is configured. Set WOPR_WORKSPACE (or "
            "AI_CLI_WORKSPACE) in the MCP server registration to an existing "
            "directory. WOPR does not fall back to the server's launch "
            "directory, to avoid binding to an unrelated worktree."
        )

    def get_available_projects(self) -> list[str]:
        """Get list of available project names in the workspace."""
        try:
            return sorted(
                item.name
                for item in self.workspace.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            )
        except OSError:
            return []

    def find_similar_projects(self, name: str, max_suggestions: int = 3) -> list[str]:
        """Find projects with similar names using fuzzy matching."""
        available = self.get_available_projects()
        if not available:
            return []

        scores = []
        name_lower = name.lower()
        for project in available:
            ratio = SequenceMatcher(None, name_lower, project.lower()).ratio()
            if name_lower in project.lower():
                ratio = max(ratio, 0.8)
            if project.lower().startswith(name_lower):
                ratio = max(ratio, 0.9)
            scores.append((project, ratio))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [p for p, score in scores[:max_suggestions] if score > 0.3]

    def resolve_project_path(
        self, project_name: str, workspace: Path | None = None
    ) -> tuple[Path, str | None]:
        """Resolve a project name to its path with helpful error messages.

        Returns:
            (path, error_message) - If path exists, error_message is None.
            If path doesn't exist, error_message contains helpful suggestions.
        """
        resolved_workspace = (workspace or self.workspace).resolve()
        project_path = (resolved_workspace / project_name).resolve()
        try:
            project_path.relative_to(resolved_workspace)
        except ValueError:
            return project_path, (
                f"Error: Project path '{project_name}' escapes workspace "
                f"'{resolved_workspace}'."
            )

        if project_path.exists():
            return project_path, None

        try:
            available = sorted(
                item.name
                for item in resolved_workspace.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            )
        except OSError:
            available = []

        if not available:
            return project_path, (
                f"Error: Project '{project_name}' not found.\n"
                f"Workspace '{resolved_workspace}' contains no projects.\n"
                f"Hint: Make sure you're using the correct workspace path."
            )

        scores = []
        name_lower = project_name.lower()
        for project in available:
            ratio = SequenceMatcher(None, name_lower, project.lower()).ratio()
            if name_lower in project.lower():
                ratio = max(ratio, 0.8)
            if project.lower().startswith(name_lower):
                ratio = max(ratio, 0.9)
            scores.append((project, ratio))
        scores.sort(key=lambda item: item[1], reverse=True)
        similar = [project for project, score in scores[:3] if score > 0.3]
        if similar:
            suggestions = ", ".join(f"'{p}'" for p in similar)
            return project_path, (
                f"Error: Project '{project_name}' not found.\n"
                f"Did you mean: {suggestions}?\n"
                f"Use list_projects() to see all available projects."
            )
        return project_path, (
            f"Error: Project '{project_name}' not found in workspace.\n"
            f"Available projects: {', '.join(available[:10])}"
            + (f" (and {len(available) - 10} more)" if len(available) > 10 else "")
            + "\n"
            "Use list_projects() to see all projects with details."
        )
