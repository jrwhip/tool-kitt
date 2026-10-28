"""Crew-contract validators for the KITT four-role crew.

The crew pack's reliability bottleneck identified in a colleague's
7-REQ Spring Boot rewrite retrospective was that scout's discovery work
was never reliably handed off to the downstream coder / tester / auditor
agents. Each downstream agent independently re-grepped the codebase at
Opus prices, producing 500k-800k tokens of duplicate discovery per
project. Worse, the lack of a contract let the same entity field name
land in three different forms across three agents (the ``createrEmail``
vs ``creatorEmail`` incident).

This module formalizes the scout -> downstream handoff as a contract
file the orchestrator validates before dispatching the next agent.

Contract location: ``<target_dir>/crew-contracts/<REQ-ID>/scout.md``.
The path keys on REQ-ID so a multi-REQ project keeps contracts side by
side rather than overwriting on each run.

Contract format: a markdown body preceded by a YAML frontmatter block
between ``---`` lines. The frontmatter carries structured fields the
orchestrator can validate without depending on natural-language parsing.
The body holds free-form discovery notes the operator can read for
debugging "why did the coder do X?".

Required frontmatter keys:

* ``req_id`` (string, non-empty) - the active REQ. Operator-readable
  ID matches the on-disk filename component.
* ``generated_at`` (ISO 8601 datetime string) - when the scout wrote
  this contract. Stale contracts may be re-validated by the orchestrator.
* ``files_touched`` (list of relative paths, non-empty) - every file
  the scout identified as in-scope for the REQ. Downstream agents
  must consult this before doing their own discovery.
* ``class_inventory`` (list of objects with ``name`` / ``file`` /
  ``signature`` keys) - the class structure the coder and tester
  agents need to align on. Empty list is allowed (some REQs are
  not class-shaped, e.g., pure config edits).
* ``package_structure`` (string, non-empty) - free-form text describing
  where the relevant packages live in the codebase.

Beyond shape, the validator checks the contract against itself and
against the filesystem. Shape-only validation is a document pretending
to be a control: two contracts produced in live use passed a
shape-only gate while contradicting themselves, one naming
``tests/test_queue.py`` in the frontmatter and ``tests/api/test_queue.py``
in the body, the other inventorying a module the coder was never told
to build. Both defects are deterministically detectable, so they are
now detected:

* **Scope (error).** A ``files_touched`` entry that is absolute,
  contains ``..``, or otherwise resolves outside the contract's
  workspace is rejected. Downstream agents treat the list as an
  edit allowlist; an entry that escapes the workspace is an
  instruction to write somewhere nobody agreed to.
* **Existence (warning).** Entries with no file on disk are reported
  under a single warning. Never an error: a scout legitimately
  enumerates files the coder is about to create, and the same signal
  is what a typo produces, so the operator gets told and decides.
* **Basename drift (warning).** A path-like backticked token in the
  body that shares a basename with a ``files_touched`` entry but
  spells a different relative path is the ``tests/test_queue.py`` vs
  ``tests/api/test_queue.py`` defect exactly. Both spellings are
  named in the warning.
* **Inventory scope (warning).** A ``class_inventory`` entry whose
  ``file`` is absent from ``files_touched`` describes structure in a
  file the contract does not claim will be touched.

The validator returns a structured result the orchestrator skill can
react to: ``ok`` (boolean gate result), ``errors`` (specific reasons
the contract is unusable), ``warnings`` (gaps that do not block
dispatch but the operator should know about).

The orchestrator skill (``kitt-run-crew``) calls
:func:`validate_scout_contract` after scout completes and before
dispatching the coder. A non-ok result aborts the crew with the
errors surfaced to the operator.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# Required frontmatter keys; the validator surfaces a distinct error
# per missing or empty key so the operator (or scout, on a retry) can
# fix exactly the gap.
_REQUIRED_KEYS = (
    "req_id",
    "generated_at",
    "files_touched",
    "class_inventory",
    "package_structure",
)


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return ``(frontmatter_text, body_text)`` from a markdown string.

    Returns ``(None, text)`` if the file does not begin with a YAML
    frontmatter delimiter (``---`` on the first line). This lets the
    validator distinguish "contract was written but lacks frontmatter"
    from "contract was never written."
    """
    stripped = text.lstrip("﻿")  # tolerate accidental BOM
    if not stripped.startswith("---"):
        return None, text
    # Find the closing delimiter. PyYAML can technically parse the
    # whole file when it sees a leading ``---``, but that would
    # silently fold the body into the frontmatter on a malformed
    # contract. Bound the frontmatter manually.
    lines = stripped.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    end_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text
    frontmatter = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    return frontmatter, body


def _validate_frontmatter_dict(
    frontmatter: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for a parsed frontmatter mapping."""
    errors: list[str] = []
    warnings: list[str] = []

    for key in _REQUIRED_KEYS:
        if key not in frontmatter:
            errors.append(f"missing required key `{key}`")
            continue
        value = frontmatter[key]
        # Per-key shape rules. Each rule answers "is this value usable
        # by a downstream agent?". An empty list or empty string is
        # treated as missing because the agent would otherwise have
        # nothing to work with.
        if key == "req_id" and not (isinstance(value, str) and value.strip()):
            errors.append("`req_id` must be a non-empty string")
        elif key == "generated_at":
            # PyYAML auto-parses ISO 8601 timestamps to datetime objects;
            # accept both forms. The orchestrator does not interpret
            # the value (it is operator-facing audit metadata), so
            # either representation is acceptable as long as it is
            # non-empty.
            if isinstance(value, (_dt.datetime, _dt.date)):
                pass  # auto-parsed datetime is acceptable
            elif not (isinstance(value, str) and value.strip()):
                errors.append(
                    "`generated_at` must be a non-empty ISO 8601 string "
                    "(or a YAML-parsed timestamp)"
                )
        elif key == "files_touched":
            if not isinstance(value, list):
                errors.append("`files_touched` must be a list")
            elif not value:
                errors.append(
                    "`files_touched` is empty; scout must enumerate at least "
                    "one file touched by the REQ"
                )
            elif not all(isinstance(item, str) and item.strip() for item in value):
                errors.append(
                    "`files_touched` must contain only non-empty strings"
                )
        elif key == "class_inventory":
            if not isinstance(value, list):
                errors.append("`class_inventory` must be a list")
            else:
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        errors.append(
                            f"`class_inventory[{i}]` must be a mapping with "
                            "keys `name`, `file`, `signature`"
                        )
                        continue
                    missing_subkeys = [
                        k for k in ("name", "file", "signature") if k not in item
                    ]
                    if missing_subkeys:
                        errors.append(
                            f"`class_inventory[{i}]` missing keys: "
                            f"{', '.join(missing_subkeys)}"
                        )
                if not value:
                    # Empty is permitted but flagged as a warning so
                    # the operator notices when the REQ is genuinely
                    # not class-shaped vs scout failing to populate it.
                    warnings.append(
                        "`class_inventory` is empty; this is OK for "
                        "non-class-shaped REQs (config changes, doc "
                        "edits), otherwise the scout under-populated"
                    )
        elif key == "package_structure" and not (
            isinstance(value, str) and value.strip()
        ):
            errors.append(
                "`package_structure` must be a non-empty string describing "
                "where the relevant packages live"
            )

    return errors, warnings


# The directory contracts live under, per the layout documented at the
# top of this module. Its parent is the workspace the contract's
# relative paths are relative to.
_CONTRACTS_DIR_NAME = "crew-contracts"

# Inline code spans in the body. The body is markdown, and every path a
# scout writes in it is backticked by convention, so this is where the
# path-like tokens are.
_BACKTICKED_RE = re.compile(r"`([^`\n]+)`")

# One path segment. Deliberately narrow: no spaces, no glob characters,
# no punctuation that shows up in prose. A token has to be at least two
# such segments joined by ``/`` AND end in an extension before the drift
# check looks at it, so ordinary prose ("see `Invoice`", "run `pytest -q`")
# cannot reach the comparison.
_PATH_SEGMENT = r"[A-Za-z0-9_.@+-]+"
_RELATIVE_PATH_RE = re.compile(rf"^{_PATH_SEGMENT}(?:/{_PATH_SEGMENT})+$")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9_]{1,10}$")


def _normalize_rel(value: str) -> str:
    """Strip the cosmetic differences between two spellings of one path.

    ``./a/b.py``, ``a/b.py`` and ``a/b.py/`` are the same file and must
    not be reported as drift against each other.
    """
    text = value.strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def _resolve_contract_workspace(contract_path: Path) -> Path | None:
    """Return the workspace ``files_touched`` paths are relative to.

    Contracts live at ``<workspace>/crew-contracts/<REQ-ID>/scout.md``,
    so the workspace is the parent of the nearest ancestor named
    ``crew-contracts``. When the contract sits somewhere else (a
    hand-placed file, an ad-hoc validation run), fall back to the
    nearest ancestor carrying a workspace marker.

    Returns ``None`` when neither resolves. That answer is load-bearing:
    the checks that need a base directory (does this file exist? does it
    escape the workspace?) are skipped rather than run against a guessed
    root, because a guessed root turns every relative path into a
    spurious warning.
    """
    for parent in contract_path.parents:
        if parent.name == _CONTRACTS_DIR_NAME:
            return parent.parent
    # Deferred import: ``_workspace_root`` is the learnings module's
    # authority on this question and importing it at module scope would
    # couple contract validation to the learnings import graph for a
    # fallback most calls never take.
    from ._workspace_root import find_workspace_root

    return find_workspace_root(contract_path.parent).root


def _files_touched_entries(frontmatter: dict[str, Any]) -> list[str]:
    """The usable ``files_touched`` strings, or ``[]``.

    Shape problems (not a list, non-string members) are already reported
    as errors by :func:`_validate_frontmatter_dict`; the consistency
    checks skip the offending members rather than reporting them twice.
    """
    value = frontmatter.get("files_touched")
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _scope_errors(files_touched: list[str], workspace: Path | None) -> list[str]:
    """Errors for ``files_touched`` entries that leave the workspace.

    Downstream agents read this list as an edit allowlist. An absolute
    path, a ``..`` traversal, or a symlink that lands outside the
    workspace all mean the same thing: the contract authorizes an edit
    outside the project it was written for.
    """
    errors: list[str] = []
    for entry in files_touched:
        if PurePosixPath(entry).is_absolute() or Path(entry).is_absolute():
            errors.append(
                f"`files_touched` entry `{entry}` is absolute; entries must be "
                "relative to the workspace root so downstream agents resolve "
                "them the same way"
            )
            continue
        if ".." in PurePosixPath(entry).parts:
            errors.append(
                f"`files_touched` entry `{entry}` contains `..`; entries must "
                "not traverse outside the workspace root"
            )
            continue
        if workspace is None:
            continue
        try:
            resolved = (workspace / entry).resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(workspace.resolve()):
            errors.append(
                f"`files_touched` entry `{entry}` resolves to `{resolved}`, "
                f"outside the contract's workspace `{workspace}`"
            )
    return errors


def _missing_file_warnings(
    files_touched: list[str], workspace: Path | None
) -> list[str]:
    """One warning naming every ``files_touched`` entry not on disk.

    A single warning rather than one per file: on a REQ that creates a
    dozen files the per-file form is a wall of noise that trains the
    operator to skip the warnings section.

    Never an error. A scout enumerating files the coder will create is
    doing its job, and that case is indistinguishable from a typo
    without knowing the REQ's intent, which is the operator's call.
    """
    if workspace is None:
        return []
    missing = [entry for entry in files_touched if not (workspace / entry).exists()]
    if not missing:
        return []
    return [
        "`files_touched` entries do not exist on disk, assumed net-new; "
        f"verify not a typo: {', '.join(f'`{entry}`' for entry in missing)}"
    ]


def _looks_like_relative_path(token: str) -> bool:
    """True when a backticked body token is confidently a relative path.

    Conservative on purpose. The drift check exists to catch one defect
    class, and a false positive on prose costs more than a miss: an
    operator who learns the warnings lie stops reading them.
    """
    text = token.strip()
    if not text or text.startswith("/"):
        return False
    if ".." in PurePosixPath(text).parts:
        return False
    return bool(_RELATIVE_PATH_RE.match(text)) and bool(_EXTENSION_RE.search(text))


def _basename_drift_warnings(body: str, files_touched: list[str]) -> list[str]:
    """Warn when the body spells a ``files_touched`` basename differently.

    This is the ``tests/test_queue.py`` vs ``tests/api/test_queue.py``
    defect. Frontmatter and body each look internally coherent; only
    reading both notices that the coder and the tester were handed
    different paths for the same file.

    Same basename plus a different relative path is the whole rule.
    A body token whose path matches a ``files_touched`` entry exactly is
    the contract agreeing with itself, and a body token whose basename
    appears nowhere in ``files_touched`` is an unrelated file the scout
    mentioned in passing.

    The accepted cost: a body that legitimately references a different
    file sharing a basename with an in-scope one (``vendor/x/queue.py``
    beside ``app/queue.py``) gets a warning it does not need. That is a
    warning, the operator reads two paths and moves on, and the
    alternative is not catching the defect this exists to catch.
    """
    declared: dict[str, list[str]] = {}
    for entry in files_touched:
        normalized = _normalize_rel(entry)
        declared.setdefault(PurePosixPath(normalized).name, []).append(normalized)

    seen: set[tuple[str, str]] = set()
    warnings: list[str] = []
    for match in _BACKTICKED_RE.finditer(body):
        token = match.group(1).strip()
        if not _looks_like_relative_path(token):
            continue
        normalized = _normalize_rel(token)
        candidates = declared.get(PurePosixPath(normalized).name)
        if not candidates or normalized in candidates:
            continue
        for candidate in candidates:
            pair = (candidate, normalized)
            if pair in seen:
                continue
            seen.add(pair)
            warnings.append(
                f"path drift: `files_touched` declares `{candidate}` but the "
                f"body says `{normalized}`; the two spellings name the same "
                "file and downstream agents will not agree on which is real"
            )
    return warnings


def _inventory_scope_warnings(
    frontmatter: dict[str, Any], files_touched: list[str]
) -> list[str]:
    """Warn on ``class_inventory`` entries outside ``files_touched``.

    An inventory entry describes structure the coder and tester must
    align on. Naming a file the contract never claims will be touched
    means one of the two lists is wrong, and neither downstream agent
    can tell which.
    """
    inventory = frontmatter.get("class_inventory")
    if not isinstance(inventory, list):
        return []
    declared = {_normalize_rel(entry) for entry in files_touched}
    warnings: list[str] = []
    for i, item in enumerate(inventory):
        if not isinstance(item, dict):
            continue
        file_value = item.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            continue
        if _normalize_rel(file_value) in declared:
            continue
        name = item.get("name")
        label = f"`{name}`" if isinstance(name, str) and name.strip() else f"[{i}]"
        warnings.append(
            f"`class_inventory` entry {label} names file `{file_value.strip()}`, "
            "which is not in `files_touched`; the inventory describes a file "
            "the contract does not claim will be touched"
        )
    return warnings


def _consistency_checks(
    frontmatter: dict[str, Any], body: str, workspace: Path | None
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` from the self-consistency checks.

    Runs after the shape checks and only on values that passed them, so
    a malformed ``files_touched`` produces one shape error rather than a
    shape error plus a pile of derived noise.
    """
    files_touched = _files_touched_entries(frontmatter)
    errors = _scope_errors(files_touched, workspace)
    warnings: list[str] = []
    if files_touched:
        warnings.extend(_missing_file_warnings(files_touched, workspace))
        warnings.extend(_basename_drift_warnings(body, files_touched))
        warnings.extend(_inventory_scope_warnings(frontmatter, files_touched))
    return errors, warnings


def validate_scout_contract(contract_path: str) -> str:
    """Validate a scout contract at the given absolute path.

    Args:
        contract_path: Absolute path of the contract markdown file.

    Returns:
        JSON-encoded result:

            {
              "ok": bool,
              "path": str,
              "errors": list[str],
              "warnings": list[str],
              "frontmatter": dict | None,
              "body_length": int,
            }

        ``ok`` is True only when ``errors`` is empty. Warnings do not
        flip ``ok`` (they are advisory, same posture as doctor's
        readiness warnings). The orchestrator skill aborts the
        crew when ``ok`` is False; warnings are surfaced to the
        operator but do not block.

        Checks run in two passes: frontmatter shape first, then the
        self-consistency checks described in the module docstring
        (path scope, on-disk existence, body/frontmatter basename
        drift, inventory scope). The second pass reads only values
        that survived the first, so one malformed field produces one
        error instead of a cascade.

        Read-only; no file writes. The existence check stats files
        under the contract's workspace and reads nothing.
    """
    errors: list[str] = []
    warnings: list[str] = []
    frontmatter_parsed: dict[str, Any] | None = None
    body_length = 0

    path = Path(contract_path).expanduser()
    if not path.is_absolute():
        return json.dumps({
            "ok": False,
            "path": contract_path,
            "errors": [f"contract_path {contract_path!r} is not absolute"],
            "warnings": [],
            "frontmatter": None,
            "body_length": 0,
        }, indent=2, default=str)

    path = path.resolve()
    if not path.is_file():
        return json.dumps({
            "ok": False,
            "path": str(path),
            "errors": [f"scout contract does not exist at `{path}`"],
            "warnings": [],
            "frontmatter": None,
            "body_length": 0,
        }, indent=2, default=str)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return json.dumps({
            "ok": False,
            "path": str(path),
            "errors": [f"could not read scout contract: {e}"],
            "warnings": [],
            "frontmatter": None,
            "body_length": 0,
        }, indent=2, default=str)

    frontmatter_text, body_text = _split_frontmatter(raw)
    body_length = len(body_text)

    if frontmatter_text is None:
        errors.append(
            "scout contract is missing a YAML frontmatter block (expected "
            "`---` delimiters at top of file)"
        )
    else:
        try:
            loaded = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as e:
            errors.append(f"scout contract frontmatter is not valid YAML: {e}")
        else:
            if not isinstance(loaded, dict):
                errors.append(
                    "scout contract frontmatter must be a YAML mapping "
                    f"(got {type(loaded).__name__})"
                )
            else:
                frontmatter_parsed = loaded
                fm_errors, fm_warnings = _validate_frontmatter_dict(loaded)
                errors.extend(fm_errors)
                warnings.extend(fm_warnings)
                check_errors, check_warnings = _consistency_checks(
                    loaded, body_text, _resolve_contract_workspace(path)
                )
                errors.extend(check_errors)
                warnings.extend(check_warnings)

    # Empty body is allowed (the frontmatter carries the load-bearing
    # data), but a very short body suggests the scout produced no
    # discovery notes; flag for operator awareness.
    if frontmatter_parsed is not None and body_length < 50:
        warnings.append(
            f"contract body is very short ({body_length} chars); the body "
            "should contain discovery notes the operator can read for "
            "debugging downstream decisions"
        )

    return json.dumps({
        "ok": not errors,
        "path": str(path),
        "errors": errors,
        "warnings": warnings,
        "frontmatter": frontmatter_parsed,
        "body_length": body_length,
    }, indent=2, default=str)


def register(mcp: FastMCP) -> None:
    """Register crew-contract tools with the KITT MCP server."""
    mcp.tool()(validate_scout_contract)
