"""On-disk format primitives for ``LEARNINGS.md``.

Authority for what an entry looks like, how it parses, and what each
parsed entry carries. Shared between :mod:`learnings` (the public API:
search, append, seed, path resolution, scoring) and
:mod:`_learnings_sidecar` (the embeddings vector store paired with the
markdown corpus). Both modules depend on the format primitives here
rather than re-deriving them.

Before this module, the header regex was duplicated across the public
module and ``doctor`` with a comment admitting the duplication; the
entry dataclass and the parser lived only in ``learnings`` and were
not directly importable without dragging the entire MCP-tool surface
along.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LEARNINGS_FILENAME = "LEARNINGS.md"

# Header: `## LRN-YYYY-MM-DD-<letter>: <title>`. Captures the full id,
# the date, and the letter so callers that need any sub-component get
# it without a second regex pass.
ENTRY_HEADER_RE = re.compile(
    r"^## (LRN-(\d{4}-\d{2}-\d{2})-([a-z])):\s+.+$",
    re.MULTILINE,
)

# Fenced ```meta\n...\n``` block holding key/value metadata.
META_BLOCK_RE = re.compile(
    r"^```meta\s*\n(.*?)\n```\s*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class LearningEntry:
    """One distilled learning entry parsed from a LEARNINGS.md file."""

    id: str
    raw: str
    source_path: Path
    entry_date: date | None
    project: str | None
    stack: list[str]
    req_ids: list[str]
    seed: bool = False
    # Provenance of the entry: who authored it (e.g. "crew-auditor",
    # "human"). ``None`` when the meta block has no ``origin`` key —
    # the default for every entry written before the field existed,
    # so absence stays backward compatible.
    origin: str | None = None


def extract_lrn_ids(text: str) -> list[str]:
    """Return the list of LRN ids that appear as section headers in *text*.

    Consumers that only need the ids (not the date or letter
    sub-components) call this helper instead of unpacking the
    three-tuple shape that :data:`ENTRY_HEADER_RE.findall` returns.
    """
    return [match.group(1) for match in ENTRY_HEADER_RE.finditer(text)]


def split_list_value(value: str) -> list[str]:
    """Parse ``[a, b, c]`` or ``a, b, c`` style list values."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_meta_block(meta_text: str) -> dict[str, str]:
    """Parse the contents of a ``meta`` fenced block as ``key: value`` pairs."""
    fields: dict[str, str] = {}
    for line in meta_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def parse_entries(text: str, source_path: Path) -> list[LearningEntry]:
    """Parse all ``## LRN-...`` entries out of a LEARNINGS.md file."""
    entries: list[LearningEntry] = []
    matches = list(ENTRY_HEADER_RE.finditer(text))
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end].rstrip() + "\n"
        entry_id = match.group(1)
        entry_date_str = match.group(2)
        try:
            entry_date: date | None = date.fromisoformat(entry_date_str)
        except ValueError:
            entry_date = None

        meta_match = META_BLOCK_RE.search(raw)
        meta_fields = parse_meta_block(meta_match.group(1)) if meta_match else {}
        stack = split_list_value(meta_fields.get("stack", ""))
        req_ids = split_list_value(meta_fields.get("req", ""))
        project = meta_fields.get("project") or None
        seed = meta_fields.get("seed", "").strip().lower() == "true"
        origin = meta_fields.get("origin", "").strip() or None

        entries.append(LearningEntry(
            id=entry_id,
            raw=raw,
            source_path=source_path,
            entry_date=entry_date,
            project=project,
            stack=stack,
            req_ids=req_ids,
            seed=seed,
            origin=origin,
        ))
    return entries
