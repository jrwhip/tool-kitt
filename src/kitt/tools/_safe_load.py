"""Shared safe JSON/YAML readers for the doctor family of modules.

Extracted out of :mod:`doctor` so both it and :mod:`doctor_recommendations`
can use the same implementation without either module importing the other
for it — ``doctor`` re-exports from ``doctor_recommendations`` for backward
compatibility (see the top of ``doctor.py``), so ``doctor_recommendations``
importing back from ``doctor`` for these two helpers created a circular
import. A prior attempt at deduplication tried exactly that and it broke at
runtime (invisible to mypy/ruff, since neither executes imports) — this
module is the actual fix, not a third divergent copy.

Missing or unreadable is logged at DEBUG (expected hot-path noise during a
full workspace scan); a parse failure on a file the caller specifically
asked for is logged at WARNING, since the operator usually wants to know
their pom.xml or package.json is malformed. Both return ``None`` on any
failure so callers can write straight-line probe code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from ..product import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        logger.debug("Cannot read %s as text: %s", path, e)
        return None
    except json.JSONDecodeError as e:
        logger.warning("Cannot parse %s as JSON: %s", path, e)
        return None
    return parsed if isinstance(parsed, dict) else None


def safe_load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        logger.debug("Cannot read %s as text: %s", path, e)
        return None
    except yaml.YAMLError as e:
        logger.warning("Cannot parse %s as YAML: %s", path, e)
        return None
