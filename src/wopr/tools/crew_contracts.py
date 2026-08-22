"""Crew-contract validators for the WOPR four-role crew.

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

The validator returns a structured result the orchestrator skill can
react to: ``ok`` (boolean gate result), ``errors`` (specific reasons
the contract is unusable), ``warnings`` (gaps that do not block
dispatch but the operator should know about).

The orchestrator skill (``wopr-run-crew``) calls
:func:`validate_scout_contract` after scout completes and before
dispatching the coder. A non-ok result aborts the crew with the
errors surfaced to the operator.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
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

        Read-only; no file writes.
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
    """Register crew-contract tools with the WOPR MCP server."""
    mcp.tool()(validate_scout_contract)
