"""Per-role model resolution for the KITT four-role crew.

Every crew agent file carries a ``model:`` line (scout ``haiku``; coder,
tester, auditor, evaluator, designer ``sonnet``). Those are static. A
twenty-line config edit and a cross-cutting refactor used to get the
same tier, and the only way to change that was to edit the agent
files or to put every role on the orchestrator's model with
``inherit``. The second option is the one this module exists to
avoid: a run that inherits a top-tier orchestrator model fans the
most expensive model out to the cheapest, most repetitive role.

This module makes the choice per role and per requirement, and it
keeps the choice deterministic. The orchestrator skill calls
:func:`resolve_crew_models` and passes the returned model for each
role on the corresponding ``Agent`` dispatch. No agent decides its own
tier, and no role ever copies another role's model.

Configuration (``kitt.yml``, section ``crew``)::

    crew:
      models:                 # per-role defaults; each line optional
        scout: haiku
        coder: sonnet
        tester: sonnet
        auditor: sonnet
        evaluator: sonnet
        designer: sonnet
      escalation:
        roles: [coder, auditor]   # roles that move with complexity
        high_at_files: 6          # scout contract names >= this many files -> high
        low_at_files: null        # scout contract names <= this many files -> low; null disables

Complexity has three levels, ``low``, ``medium`` and ``high``, and is
read from the first of these that answers:

1. The ``complexity`` argument, when the operator states it outright.
2. ``complexity:`` in the requirement file's frontmatter.
3. The number of ``files_touched`` in the scout contract, compared to
   the configured thresholds.
4. Otherwise ``medium``, which leaves every role on its default.

``high`` moves each escalation role up one tier on the ladder
``haiku -> sonnet -> opus`` (capped at ``opus``); ``low`` moves each
down one tier (floored at ``haiku``). Roles outside ``escalation.roles``
never move. A model value that is not on the ladder (a pinned model
id, for example) is passed through unchanged and excluded from
escalation with a warning.

A malformed ``crew`` section is an error, not a silent fallback: the
orchestrator stops and shows the operator the reason, the same posture
the scout-contract validator takes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .crew_contracts import _files_touched_entries, _split_frontmatter

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# The model ladder, cheapest first. Escalation walks one step along it.
TIERS: tuple[str, ...] = ("haiku", "sonnet", "opus")

# Every crew role the orchestrator can dispatch.
ROLES: tuple[str, ...] = ("scout", "designer", "coder", "tester", "auditor", "evaluator")

# Mirrors the ``model:`` frontmatter in catalog/crew/agents/*.md. Keep in sync.
DEFAULT_MODELS: dict[str, str] = {
    "scout": "haiku",
    "designer": "sonnet",
    "coder": "sonnet",
    "tester": "sonnet",
    "auditor": "sonnet",
    "evaluator": "sonnet",
}

DEFAULT_ESCALATION_ROLES: tuple[str, ...] = ("coder", "auditor")
DEFAULT_HIGH_AT_FILES = 6

COMPLEXITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")

SOURCE_OPERATOR = "operator"
SOURCE_REQ = "req_frontmatter"
SOURCE_CONTRACT = "scout_contract"
SOURCE_DEFAULT = "default"


def _shift(model: str, steps: int) -> str:
    """Move ``model`` ``steps`` places along the ladder, clamped at both ends."""
    index = TIERS.index(model)
    return TIERS[max(0, min(len(TIERS) - 1, index + steps))]


def _read_crew_section(kitt_yml: Path) -> tuple[dict[str, Any], list[str]]:
    """The ``crew`` mapping of ``kitt_yml`` (``{}`` when absent) plus any errors."""
    try:
        data = yaml.safe_load(kitt_yml.read_text(encoding="utf-8"))
    except OSError as e:
        return {}, [f"cannot read {kitt_yml}: {e}"]
    except yaml.YAMLError as e:
        return {}, [f"cannot parse {kitt_yml}: {e}"]
    if not isinstance(data, dict):
        return {}, [f"{kitt_yml} is not a mapping"]
    section = data.get("crew")
    if section is None:
        return {}, []
    if not isinstance(section, dict):
        return {}, ["kitt.yml `crew` must be a mapping"]
    return section, []


def _parse_models(
    section: dict[str, Any], errors: list[str], warnings: list[str]
) -> dict[str, str]:
    """Per-role models: the configured values laid over the defaults."""
    models = dict(DEFAULT_MODELS)
    raw = section.get("models")
    if raw is None:
        return models
    if not isinstance(raw, dict):
        errors.append("kitt.yml `crew.models` must be a mapping of role to model")
        return models
    for role, value in raw.items():
        if role not in ROLES:
            errors.append(
                f"kitt.yml `crew.models.{role}`: unknown role; expected one of {', '.join(ROLES)}"
            )
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"kitt.yml `crew.models.{role}` must be a non-empty string")
            continue
        value = value.strip()
        if value == "inherit":
            errors.append(
                f"kitt.yml `crew.models.{role}`: `inherit` is not allowed; "
                "every role names its own model"
            )
            continue
        if value not in TIERS:
            warnings.append(
                f"kitt.yml `crew.models.{role}` is `{value}`, which is not on the ladder "
                f"({' -> '.join(TIERS)}); it is used as given and never escalated"
            )
        models[role] = value
    return models


def _parse_escalation(section: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """The escalation block: which roles move and what the file-count thresholds are."""
    result: dict[str, Any] = {
        "roles": list(DEFAULT_ESCALATION_ROLES),
        "high_at_files": DEFAULT_HIGH_AT_FILES,
        "low_at_files": None,
    }
    raw = section.get("escalation")
    if raw is None:
        return result
    if not isinstance(raw, dict):
        errors.append("kitt.yml `crew.escalation` must be a mapping")
        return result
    if "roles" in raw:
        roles = raw["roles"]
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            errors.append("kitt.yml `crew.escalation.roles` must be a list of role names")
        else:
            unknown = [r for r in roles if r not in ROLES]
            if unknown:
                errors.append(
                    f"kitt.yml `crew.escalation.roles`: unknown role(s) {', '.join(unknown)}; "
                    f"expected a subset of {', '.join(ROLES)}"
                )
            else:
                result["roles"] = list(dict.fromkeys(roles))
    for key in ("high_at_files", "low_at_files"):
        if key not in raw:
            continue
        value = raw[key]
        if value is None:
            result[key] = None
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(
                f"kitt.yml `crew.escalation.{key}` must be a non-negative integer or null"
            )
        else:
            result[key] = value
    high, low = result["high_at_files"], result["low_at_files"]
    if high is not None and low is not None and low >= high:
        errors.append(
            f"kitt.yml `crew.escalation`: low_at_files ({low}) must be less than "
            f"high_at_files ({high})"
        )
    return result


def _frontmatter_of(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    """The YAML frontmatter mapping of a markdown file, or ``None`` with an error recorded."""
    if not path.is_absolute():
        errors.append(f"{label} path must be absolute, got {path}")
        return None
    if not path.is_file():
        errors.append(f"{label} not found: {path}")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        errors.append(f"cannot read {label} {path}: {e}")
        return None
    frontmatter, _ = _split_frontmatter(text)
    if frontmatter is None:
        return {}
    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError as e:
        errors.append(f"{label} {path} has malformed frontmatter: {e}")
        return None
    return parsed if isinstance(parsed, dict) else {}


def _complexity_from_req(req_path: str, errors: list[str]) -> str | None:
    frontmatter = _frontmatter_of(Path(req_path).expanduser(), "requirement", errors)
    if not frontmatter:
        return None
    value = frontmatter.get("complexity")
    if value is None:
        return None
    if not isinstance(value, str) or value.strip().lower() not in COMPLEXITY_LEVELS:
        errors.append(
            f"requirement {req_path}: `complexity` must be one of "
            f"{', '.join(COMPLEXITY_LEVELS)}, got {value!r}"
        )
        return None
    return value.strip().lower()


def _files_touched_count(contract_path: str, errors: list[str]) -> int | None:
    frontmatter = _frontmatter_of(Path(contract_path).expanduser(), "scout contract", errors)
    if frontmatter is None:
        return None
    return len(_files_touched_entries(frontmatter))


def _complexity_from_count(count: int, escalation: dict[str, Any]) -> str | None:
    high, low = escalation["high_at_files"], escalation["low_at_files"]
    if high is not None and count >= high:
        return "high"
    if low is not None and count <= low:
        return "low"
    return None


def resolve_crew_models(
    kitt_yml_path: str,
    req_path: str = "",
    scout_contract_path: str = "",
    complexity: str = "",
) -> str:
    """Decide which model each crew role runs on for one requirement.

    Args:
        kitt_yml_path: Absolute path of the project's ``kitt.yml`` (the
            home member's file in workspace mode).
        req_path: Optional absolute path of the requirement file. Its
            frontmatter may carry ``complexity: low|medium|high``.
        scout_contract_path: Optional absolute path of the validated
            scout contract. Its ``files_touched`` count is compared to
            the configured thresholds when nothing else states the
            complexity.
        complexity: Optional explicit level from the operator. Wins
            over every other source.

    Returns:
        JSON-encoded result::

            {
              "ok": bool,
              "kitt_yml": str,
              "complexity": "low" | "medium" | "high",
              "complexity_source": "operator" | "req_frontmatter" | "scout_contract" | "default",
              "files_touched": int | null,
              "models": {"scout": "...", "coder": "...", ...},
              "defaults": {...},
              "escalation": {"roles": [...], "high_at_files": int | null,
                             "low_at_files": int | null},
              "adjusted_roles": [...],
              "errors": [...],
              "warnings": [...]
            }

        ``ok`` is False only when ``errors`` is non-empty, and then
        ``models`` still holds the best answer available so the operator
        can see what would have run. The orchestrator stops on errors.
        Read-only; nothing is written.
    """
    errors: list[str] = []
    warnings: list[str] = []
    kitt_yml = Path(kitt_yml_path).expanduser()
    if not kitt_yml.is_absolute():
        errors.append(f"kitt_yml_path must be absolute, got {kitt_yml_path}")
    elif not kitt_yml.is_file():
        errors.append(f"kitt.yml not found: {kitt_yml}")

    section: dict[str, Any] = {}
    if not errors:
        section, section_errors = _read_crew_section(kitt_yml)
        errors.extend(section_errors)
    defaults = _parse_models(section, errors, warnings)
    escalation = _parse_escalation(section, errors)

    level: str | None = None
    source = SOURCE_DEFAULT
    files_touched: int | None = None

    explicit = complexity.strip().lower()
    if explicit:
        if explicit in COMPLEXITY_LEVELS:
            level, source = explicit, SOURCE_OPERATOR
        else:
            errors.append(
                f"complexity must be one of {', '.join(COMPLEXITY_LEVELS)}, got {complexity!r}"
            )
    if level is None and req_path.strip():
        found = _complexity_from_req(req_path.strip(), errors)
        if found is not None:
            level, source = found, SOURCE_REQ
    if scout_contract_path.strip():
        files_touched = _files_touched_count(scout_contract_path.strip(), errors)
        if level is None and files_touched is not None:
            found = _complexity_from_count(files_touched, escalation)
            if found is not None:
                level, source = found, SOURCE_CONTRACT
    if level is None:
        level = "medium"

    models = dict(defaults)
    adjusted: list[str] = []
    steps = {"low": -1, "medium": 0, "high": 1}[level]
    if steps:
        for role in escalation["roles"]:
            current = models[role]
            if current not in TIERS:
                continue  # pinned model id: used as given, never escalated
            moved = _shift(current, steps)
            if moved != current:
                models[role] = moved
                adjusted.append(role)

    return json.dumps(
        {
            "ok": not errors,
            "kitt_yml": str(kitt_yml),
            "complexity": level,
            "complexity_source": source,
            "files_touched": files_touched,
            "models": models,
            "defaults": defaults,
            "escalation": escalation,
            "adjusted_roles": adjusted,
            "errors": errors,
            "warnings": warnings,
        },
        indent=2,
    )


def register(mcp: FastMCP) -> None:
    """Register the crew model resolver with the KITT MCP server."""
    mcp.tool()(resolve_crew_models)
