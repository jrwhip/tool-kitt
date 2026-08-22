"""Declarative hook manifests and per-CLI registration rendering.

The problem this replaces
------------------------

WOPR shipped ``capture-skill-trigger-hook.py`` and
``capture-skill-trigger-hook-copilot.py`` as near-duplicate handlers, each
with its own hand-written ``configure_*.py`` registration script and its own
slash command. The *handlers* genuinely differ -- Copilot's transcript is an
``events.jsonl`` of ``tool.execution_start`` records rather than Claude's
nested ``tool_use`` blocks, and ``agentStop`` supports only
``decision``/``reason`` where ``Stop`` supports non-blocking
``additionalContext`` -- so collapsing them into one script would be wrong.

What was pure duplication is everything *around* the handler: which event to
bind, which config file to write, what the entry JSON looks like, and how to
re-register without duplicating. Porting one hook to Copilot cost an entire
release almost entirely in that layer.

So this module treats a hook the way :mod:`conversion_manifest` already
treats commands and agents: author the wiring once as data, render it per
CLI. A ``<name>.HOOK.yaml`` beside the handlers declares the event, the
handler, and any per-CLI overrides; the renderers below turn one target into
the exact entry shape its CLI expects.

Schema
------

::

    name: capture-skill-trigger
    description: One line, shown by the configure script.
    handler: capture-skill-trigger-hook.py    # default for all targets
    targets:
      claude:
        event: Stop
        matcher: ""                            # optional, Claude only
      copilot:
        event: agentStop
        handler: capture-skill-trigger-hook-copilot.py   # per-CLI override

``handler`` is a bare filename resolved against the manifest's own
directory. Per-target ``handler`` exists precisely because a genuine port
(different transcript format, different output schema) is a different
program, not a different config value -- the manifest records that fact
instead of pretending one file fits both.

Registration is upsert-by-identity
----------------------------------

Both renderers key an existing entry by the handler *filename* appearing in
the command string, not by the full command text. A hook whose absolute path
changed (pipx reinstall, editable -> wheel, a moved catalog) is then
reconciled in place rather than appended alongside its own stale twin. The
semantics are ported from ``webteam-ai-scaffolding``'s bootstrap, which
learned the same lesson: matching on exact command text means every path
change silently doubles the registrations.
"""

from __future__ import annotations

import json
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from ._atomic_write import atomic_write_text

logger = logging.getLogger("wopr")

MANIFEST_SUFFIX = ".HOOK.yaml"

# Where each CLI keeps its project-local hook registrations, relative to the
# project root. Data, not branches, so adding a CLI is one entry.
HOOK_CONFIG_PATHS: dict[str, tuple[str, ...]] = {
    "claude": (".claude", "settings.json"),
    "copilot": (".github", "hooks", "hooks.json"),
}

SUPPORTED_CLIS: frozenset[str] = frozenset(HOOK_CONFIG_PATHS)

# How to invoke a handler, keyed by its suffix: (posix, windows). A
# ``None`` windows entry means "no verified Windows invocation" -- rendering
# a Copilot entry for such a handler raises rather than emitting a command
# that would fail at hook time on Windows. Derived from the suffix rather
# than declared per manifest because the mapping is a property of the file
# type, not of the hook; a manifest may still override it explicitly.
INTERPRETERS: dict[str, tuple[str, str | None]] = {
    ".py": ("python3", "python"),
    ".sh": ("bash", None),
}

# Outcome of an upsert, shared by both renderers so callers can report
# uniformly.
UpsertResult = Literal["registered", "updated", "unchanged"]


class HookManifestError(ValueError):
    """A HOOK.yaml is malformed or names a handler that does not exist."""


@dataclass(frozen=True)
class HookTarget:
    """One CLI's wiring for a hook."""

    cli: str
    event: str
    handler: Path
    matcher: str | None = None


@dataclass(frozen=True)
class HookSpec:
    """A parsed ``<name>.HOOK.yaml``."""

    name: str
    description: str
    path: Path
    targets: dict[str, HookTarget]

    def target(self, cli: str) -> HookTarget:
        """The wiring for ``cli``, or raise naming what IS declared."""
        try:
            return self.targets[cli]
        except KeyError:
            declared = ", ".join(sorted(self.targets)) or "none"
            raise HookManifestError(
                f"hook {self.name!r} declares no {cli!r} target "
                f"(declared: {declared})"
            ) from None


def _require_str(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HookManifestError(f"{where}: {key!r} must be a non-empty string")
    return value.strip()


def parse_hook_manifest(path: Path) -> HookSpec:
    """Parse and validate one ``<name>.HOOK.yaml``.

    Handler existence is checked here rather than at registration time: a
    manifest pointing at a missing script is a packaging bug, and the parity
    test that walks the catalog should fail on it loudly instead of leaving
    an operator to discover it when their hook silently never fires.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise HookManifestError(f"{path}: cannot read hook manifest: {e}") from e
    if not isinstance(raw, dict):
        raise HookManifestError(f"{path}: manifest root must be a mapping")

    name = _require_str(raw, "name", str(path))
    description = _require_str(raw, "description", str(path))
    default_handler = raw.get("handler")

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, dict) or not targets_raw:
        raise HookManifestError(f"{path}: 'targets' must be a non-empty mapping")

    targets: dict[str, HookTarget] = {}
    for cli, spec in targets_raw.items():
        where = f"{path} [targets.{cli}]"
        if cli not in SUPPORTED_CLIS:
            raise HookManifestError(
                f"{where}: unsupported CLI {cli!r} "
                f"(supported: {', '.join(sorted(SUPPORTED_CLIS))})"
            )
        if not isinstance(spec, dict):
            raise HookManifestError(f"{where}: target must be a mapping")

        handler_name = spec.get("handler", default_handler)
        if not isinstance(handler_name, str) or not handler_name.strip():
            raise HookManifestError(
                f"{where}: no handler declared and no top-level 'handler' default"
            )
        if "/" in handler_name or "\\" in handler_name:
            raise HookManifestError(
                f"{where}: handler must be a bare filename beside the manifest, "
                f"got {handler_name!r}"
            )
        handler = (path.parent / handler_name).resolve()
        if not handler.is_file():
            raise HookManifestError(f"{where}: handler not found at {handler}")

        matcher = spec.get("matcher")
        if matcher is not None and not isinstance(matcher, str):
            raise HookManifestError(f"{where}: 'matcher' must be a string")

        targets[cli] = HookTarget(
            cli=cli,
            event=_require_str(spec, "event", where),
            handler=handler,
            matcher=matcher,
        )

    return HookSpec(name=name, description=description, path=path, targets=targets)


def discover_hook_manifests(hooks_dir: Path) -> list[HookSpec]:
    """Parse every ``*.HOOK.yaml`` in ``hooks_dir``, sorted by name."""
    if not hooks_dir.is_dir():
        return []
    specs = [
        parse_hook_manifest(p) for p in sorted(hooks_dir.glob(f"*{MANIFEST_SUFFIX}"))
    ]
    return sorted(specs, key=lambda s: s.name)


def find_hook_manifest(hooks_dir: Path, name: str) -> HookSpec:
    """Look up one hook by declared name, or raise listing what exists."""
    specs = discover_hook_manifests(hooks_dir)
    for spec in specs:
        if spec.name == name:
            return spec
    known = ", ".join(s.name for s in specs) or "none"
    raise HookManifestError(f"no hook named {name!r} in {hooks_dir} (known: {known})")


# ============================================================================
# COMMAND RENDERING
# ============================================================================


def _powershell_quote(path: Path) -> str:
    """Quote a path for PowerShell.

    ``shlex.quote`` emits POSIX single-quote syntax, which PowerShell does
    not interpret the same way, so Windows needs its own convention.
    """
    return '"' + str(path).replace('"', '`"') + '"'


def _interpreters(handler: Path) -> tuple[str, str | None]:
    try:
        return INTERPRETERS[handler.suffix]
    except KeyError:
        raise HookManifestError(
            f"no known interpreter for handler {handler.name!r} "
            f"(known suffixes: {', '.join(sorted(INTERPRETERS))})"
        ) from None


def bash_command(handler: Path) -> str:
    """The POSIX invocation recorded in a hook entry."""
    posix, _ = _interpreters(handler)
    return f"{posix} {shlex.quote(str(handler))}"


def powershell_command(handler: Path) -> str:
    """The Windows invocation recorded in a Copilot hook entry.

    Raises when the handler has no verified Windows invocation: emitting a
    ``bash foo.sh`` command into a PowerShell slot would register a hook
    that simply fails on Windows, which is worse than declining to wire it.
    """
    _, windows = _interpreters(handler)
    if windows is None:
        raise HookManifestError(
            f"handler {handler.name!r} has no Windows invocation; it cannot be "
            f"registered for a CLI that requires one."
        )
    return f"{windows} {_powershell_quote(handler)}"


def render_claude_entry(target: HookTarget) -> dict[str, Any]:
    """Render Claude's nested ``{matcher?, hooks: [{type, command}]}`` entry."""
    entry: dict[str, Any] = {
        "hooks": [{"type": "command", "command": bash_command(target.handler)}]
    }
    if target.matcher is not None:
        entry["matcher"] = target.matcher
    return entry


def render_copilot_entry(target: HookTarget) -> dict[str, Any]:
    """Render Copilot's flat entry.

    ``type`` is mandatory per GitHub's hooks reference, and both ``bash``
    and ``powershell`` are supplied so a Windows session gets a valid
    invocation rather than silently no-op'ing.
    """
    return {
        "type": "command",
        "bash": bash_command(target.handler),
        "powershell": powershell_command(target.handler),
    }


def render_entry(target: HookTarget) -> dict[str, Any]:
    """Dispatch to the renderer for ``target.cli``."""
    if target.cli == "claude":
        return render_claude_entry(target)
    if target.cli == "copilot":
        return render_copilot_entry(target)
    raise HookManifestError(f"no renderer for CLI {target.cli!r}")


# ============================================================================
# UPSERT BY IDENTITY
# ============================================================================


def _identity(handler: Path) -> str:
    """The stable identity of a hook inside a command string.

    The handler filename, not the full command: absolute paths move
    (reinstall, editable -> wheel, relocated catalog) while the script name
    does not. Matching on the full command is what makes re-registration
    append a duplicate instead of reconciling.
    """
    return handler.name


def upsert_claude_hook(
    settings: dict[str, Any], target: HookTarget
) -> UpsertResult:
    """Insert or reconcile ``target`` in a Claude ``settings.json`` mapping.

    Mutates ``settings`` in place. Every other setting and hook is left
    untouched; only the entry whose command carries this handler's identity
    is rewritten.
    """
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookManifestError("settings.json: 'hooks' is not a JSON object")
    entries = hooks.setdefault(target.event, [])
    if not isinstance(entries, list):
        raise HookManifestError(
            f"settings.json: hooks.{target.event} is not a JSON array"
        )

    identity = _identity(target.handler)
    command = bash_command(target.handler)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for hook in entry.get("hooks", []) or []:
            if not isinstance(hook, dict) or identity not in hook.get("command", ""):
                continue
            before = (hook.get("command"), hook.get("type"), entry.get("matcher"))
            hook["command"] = command
            hook["type"] = "command"
            if target.matcher is not None:
                entry["matcher"] = target.matcher
            after = (hook.get("command"), hook.get("type"), entry.get("matcher"))
            return "updated" if after != before else "unchanged"

    entries.append(render_claude_entry(target))
    return "registered"


def upsert_copilot_hook(config: dict[str, Any], target: HookTarget) -> UpsertResult:
    """Insert or reconcile ``target`` in a Copilot ``hooks.json`` mapping.

    Mutates ``config`` in place, including the mandatory ``version: 1``.
    An existing entry is merged with the canonical fields rather than
    skipped, so an install predating a now-required field (``type``)
    self-heals on the next run instead of staying subtly invalid.
    """
    config.setdefault("version", 1)
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookManifestError("hooks.json: 'hooks' is not a JSON object")
    entries = hooks.setdefault(target.event, [])
    if not isinstance(entries, list):
        raise HookManifestError(f"hooks.json: hooks.{target.event} is not a JSON array")

    identity = _identity(target.handler)
    rendered = render_copilot_entry(target)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if identity in str(entry.get("bash", "")) or identity in str(
            entry.get("powershell", "")
        ):
            before = dict(entry)
            entry.update(rendered)
            return "updated" if entry != before else "unchanged"

    entries.append(rendered)
    return "registered"


def upsert_hook(config: dict[str, Any], target: HookTarget) -> UpsertResult:
    """Dispatch to the upsert for ``target.cli``."""
    if target.cli == "claude":
        return upsert_claude_hook(config, target)
    if target.cli == "copilot":
        return upsert_copilot_hook(config, target)
    raise HookManifestError(f"no upsert for CLI {target.cli!r}")


# ============================================================================
# FILE-LEVEL REGISTRATION
# ============================================================================


def hook_config_path(project_root: Path, cli: str) -> Path:
    """Where ``cli`` keeps its project-local hook registrations."""
    try:
        parts = HOOK_CONFIG_PATHS[cli]
    except KeyError:
        raise HookManifestError(f"unsupported CLI {cli!r}") from None
    return project_root.joinpath(*parts)


def load_hook_config(path: Path) -> dict[str, Any]:
    """Read a hook config, or ``{}`` when absent.

    A file that exists but does not parse raises rather than being
    silently replaced: it is operator data, and clobbering a config whose
    JSON has a typo would destroy every other hook and setting in it.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HookManifestError(
            f"{path} contains invalid JSON: {e}. Fix it before re-running; "
            f"refusing to overwrite it."
        ) from e
    except OSError as e:
        raise HookManifestError(f"cannot read {path}: {e}") from e
    if not isinstance(data, dict):
        raise HookManifestError(
            f"{path} parsed as {type(data).__name__}, expected a JSON object."
        )
    return data


def register_hook(
    spec: HookSpec, cli: str, project_root: Path, *, dry_run: bool = False
) -> tuple[UpsertResult, Path]:
    """Register one hook for one CLI in ``project_root``.

    Returns ``(result, config_path)``. Idempotent by construction: a second
    run reports ``unchanged``, and a run after the handler moved reports
    ``updated`` with the entry rewritten in place -- never a duplicate.
    """
    target = spec.target(cli)
    path = hook_config_path(project_root, cli)
    config = load_hook_config(path)
    result = upsert_hook(config, target)

    if not dry_run and result != "unchanged":
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(config, indent=2) + "\n")
    return result, path
