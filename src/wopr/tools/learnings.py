"""LEARNINGS retrieval and append for the WOPR crew.

Implements the workspace-vs-system memory model and the deterministic
pre-filter used by Corrective RAG (CRAG). The crew auditor calls
:func:`append_learnings` at end of every gate; the ``wopr-run-crew``
orchestrator calls :func:`learnings_search` before each working-agent step
and hands the result to the ``crew-evaluator`` agent for grading.

Single source of truth per entry. No mirroring. Workspace mode reads only the
workspace's ``LEARNINGS.md``; outside-workspace mode aggregates ``~/.wopr/LEARNINGS.md``
plus every registered workspace's file via ``~/.wopr/workspaces.txt``.

Workspace identity is signalled by ``wopr.yml`` at the workspace root (the
crew pack's source of truth, distinct from ``catalog.read_wopr_config``'s
``.wopr.yaml`` catalog config).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._atomic_write import atomic_write_text
from ..catalog import get_global_home
from ..context import ToolContext
from . import _curator, _embeddings
from ._data_paths import candidate_data_paths
from ._embeddings import (
    EMBEDDING_MODEL,
)
from ._gitignore import ensure_sidecar_gitignored
from ._leak_vet import find_leak_indicators, format_leak_report
from ._learnings_format import (
    ENTRY_HEADER_RE,
    LEARNINGS_FILENAME,
    META_BLOCK_RE,
    LearningEntry,
    parse_entries,
    parse_meta_block,
)
from ._learnings_sidecar import (
    append_to_sidecar as _append_to_sidecar,
)
from ._learnings_sidecar import (
    build_sidecar as _build_sidecar,  # noqa: F401  re-export for tests and downstream callers
)
from ._learnings_sidecar import (
    load_or_rebuild_sidecar as _load_or_rebuild_sidecar,
)
from ._workspace_target import (
    InvalidTargetWorkspaceError,
    resolve_request_workspace,
)

# NOTE: _embeddings.EMBEDDINGS_AVAILABLE is deliberately NOT re-imported here.
# Re-importing it creates a second binding (``learnings.EMBEDDINGS_AVAILABLE``
# and ``_embeddings.EMBEDDINGS_AVAILABLE``) that tests had to monkeypatch
# in two places. Access via ``_embeddings.EMBEDDINGS_AVAILABLE`` so the
# fixture / runtime / test stories all converge on a single source of
# truth.

logger = logging.getLogger("wopr")

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# ``LEARNINGS_FILENAME`` re-exported from ``_learnings_format`` so existing
# ``from .learnings import LEARNINGS_FILENAME`` consumers continue to work.
__all__ = [
    "LEARNINGS_FILENAME",
    "WOPR_YML_FILENAME",
    "WORKSPACES_REGISTRY_FILENAME",
    "LearningEntry",
    "append_learnings",
    "curate_learnings",
    "learnings_path",
    "learnings_search",
    "register",
    "seed_learnings",
]

WORKSPACES_REGISTRY_FILENAME = "workspaces.txt"
WOPR_YML_FILENAME = "wopr.yml"


def _is_in_workspace(workspace: Path) -> bool:
    """A workspace is in scope when ``wopr.yml`` exists at its root."""
    return (workspace / WOPR_YML_FILENAME).exists()


def _resolve_write_path(workspace: Path) -> Path:
    if _is_in_workspace(workspace):
        return workspace / LEARNINGS_FILENAME
    return get_global_home() / LEARNINGS_FILENAME


def _resolve_read_paths(workspace: Path) -> list[Path]:
    """In-workspace mode returns the workspace's file only.

    Outside-workspace mode aggregates the system file plus every registered
    workspace's file. Missing paths are skipped silently.
    """
    if _is_in_workspace(workspace):
        return [workspace / LEARNINGS_FILENAME]

    paths: list[Path] = []
    home = get_global_home()
    system_file = home / LEARNINGS_FILENAME
    if system_file.exists():
        paths.append(system_file)
    registry = home / WORKSPACES_REGISTRY_FILENAME
    if registry.exists():
        try:
            registry_text = registry.read_text(encoding="utf-8")
        except OSError:
            return paths
        for line in registry_text.splitlines():
            entry = line.strip()
            if not entry:
                continue
            candidate = Path(entry) / LEARNINGS_FILENAME
            if candidate.exists():
                paths.append(candidate)
    return paths


def _ensure_workspace_registered(workspace: Path) -> None:
    """Append ``workspace`` to ``~/.wopr/workspaces.txt`` if not already present.

    No-op when the workspace is not actually in scope (no ``wopr.yml``).
    Idempotent: subsequent calls with the same path do nothing.

    Failures to read or write the registry are logged at WARNING and
    swallowed. Registration is best-effort: a failure here only means
    outside-workspace ``learnings_search`` will not aggregate this
    workspace's entries until a later call succeeds. It must not break
    the auditor's append or the operator's search.
    """
    if not _is_in_workspace(workspace):
        return
    home = get_global_home()
    home.mkdir(parents=True, exist_ok=True)
    registry = home / WORKSPACES_REGISTRY_FILENAME
    workspace_str = str(workspace.resolve())
    existing: set[str] = set()
    if registry.exists():
        try:
            registry_text = registry.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(
                "Cannot read workspace registry at %s (%s); skipping "
                "registration. Cross-workspace aggregation will not see "
                "this workspace until a future call succeeds.",
                registry,
                e,
            )
            return
        for line in registry_text.splitlines():
            entry = line.strip()
            if entry:
                existing.add(entry)
    if workspace_str in existing:
        return
    try:
        with registry.open("a", encoding="utf-8") as f:
            f.write(f"{workspace_str}\n")
    except OSError as e:
        logger.warning(
            "Cannot append to workspace registry at %s (%s); the workspace "
            "is not registered. Cross-workspace aggregation will not see "
            "this workspace until a future call succeeds.",
            registry,
            e,
        )


# ``_parse_entries``, ``LearningEntry``, ``_split_list_value``,
# ``_parse_meta_block``, and the meta-block regex live in
# :mod:`_learnings_format` (the on-disk format authority). They are
# re-exported here under their leading-underscore names so existing
# call sites and tests continue to work without filesystem-shaped
# refactor noise.
_parse_entries = parse_entries


def _score_entry(
    entry: LearningEntry,
    req_id: str,
    stack_tags: list[str],
    today: date,
    max_age_days: int,
) -> float | None:
    """Return a relevance score for an entry, or ``None`` to filter it out.

    Filters: an entry must intersect ``stack_tags`` OR exactly match
    ``req_id``. Old entries beyond ``max_age_days`` are dropped unless the
    REQ matches (REQ-specific historical entries stay relevant for that REQ).
    """
    req_match = bool(req_id) and (req_id in entry.req_ids)
    stack_match = not stack_tags or bool(set(entry.stack) & set(stack_tags))

    if not stack_match and not req_match:
        return None

    # Seed entries are foundational lessons distributed with the pack
    # rather than distilled from a specific crew run. They are
    # always relevant when the stack matches; bypass the age cutoff
    # that would otherwise drop them as stale.
    if entry.seed:
        return (2.0 if req_match else 0.0) + (1.0 if stack_match else 0.0)

    if entry.entry_date is None:
        recency_bucket = 0.0
    else:
        age_days = max(0, (today - entry.entry_date).days)
        if age_days <= max_age_days:
            recency_bucket = 1.0 - (age_days / max_age_days) if max_age_days else 1.0
        elif req_match:
            recency_bucket = 0.0
        else:
            return None

    score = 0.0
    if req_match:
        score += 2.0
    if stack_match:
        score += 1.0
    score += 0.5 * recency_bucket
    return score


def _prefilter(
    entries: list[LearningEntry],
    req_id: str,
    stack_tags: list[str],
    max_age_days: int,
    limit: int,
) -> list[LearningEntry]:
    today = datetime.now(tz=timezone.utc).date()
    scored: list[tuple[float, LearningEntry]] = []
    for entry in entries:
        score = _score_entry(entry, req_id, stack_tags, today, max_age_days)
        if score is None:
            continue
        scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


# Allowed shape for the ``origin`` provenance value: a short slug like
# ``crew-auditor`` or ``human``. Deliberately narrow — the value is written
# into the entry's fenced meta block, so newlines/backticks are excluded by
# construction rather than escaped after the fact.
_ORIGIN_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _inject_origin(entry_markdown: str, origin: str) -> str:
    """Return ``entry_markdown`` with ``origin: <value>`` in its meta block.

    Three cases:
    - Meta block already declares ``origin``: the entry's own value wins.
      The caller wrote it deliberately; silently rewriting provenance
      would be worse than the redundancy.
    - Meta block exists without ``origin``: the line is appended inside
      the block.
    - No meta block: one is appended to the entry holding just the
      origin, in the same fenced ``meta`` format ``parse_entries`` reads.
    """
    meta_match = META_BLOCK_RE.search(entry_markdown)
    if meta_match is None:
        return entry_markdown.rstrip() + f"\n\n```meta\norigin: {origin}\n```"
    if "origin" in parse_meta_block(meta_match.group(1)):
        return entry_markdown
    insert_at = meta_match.end(1)
    return entry_markdown[:insert_at] + f"\norigin: {origin}" + entry_markdown[insert_at:]


async def append_learnings(
    target_workspace_path: str = "",
    *,
    entry_markdown: str,
    origin: str = "",
    ctx: ToolContext | None = None,
) -> str:
    """Append a LEARNINGS.md entry to the workspace or system file.

    The entry must start with a valid ``## LRN-YYYY-MM-DD-<letter>: <title>``
    header. The workspace's own ``LEARNINGS.md`` is used when ``wopr.yml`` is
    present at ``target_workspace_path``; otherwise the system file at
    ``~/.wopr/LEARNINGS.md`` is used.

    Concurrency posture: WOPR is operator-driven, so the auditor's
    append is effectively single-writer per gate. The function does
    not take a cross-process lock; two concurrent appenders (rare,
    only possible if two crew runs land at the exact same instant)
    may produce an entry pair with a single blank-line separator
    instead of the conventional double. This is a cosmetic outcome,
    not data loss, and matches the same trade-off documented on the
    workspace-registry writer.

    Args:
        target_workspace_path: Absolute path to the project workspace root,
            and must exist. Optional on Claude Code (defaults to the
            session's project via CLAUDE_PROJECT_DIR); on other CLIs pass it
            explicitly. Determines whether the entry lands in the workspace
            file or the system file (see above).
        entry_markdown: One full entry as markdown. Must include the section
            header line. Entries are appended verbatim, with a blank line
            separator if the target file is already non-empty.
        origin: Optional provenance slug recorded in the entry's meta
            block as ``origin: <value>`` (e.g. ``crew-auditor``,
            ``human``). Default empty: nothing is added, preserving the
            historical entry shape. Entries marked ``origin: human`` are
            exempt from automatic pruning in ``curate_learnings``. If
            ``entry_markdown`` already declares ``origin`` in its meta
            block, the entry's own value wins.
    """
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, ctx, allow_legacy_config=False
        )
    except InvalidTargetWorkspaceError as e:
        return str(e)

    entry_markdown = entry_markdown.strip()
    if not entry_markdown:
        return "Error: empty entry rejected"

    first_line = entry_markdown.splitlines()[0]
    if not ENTRY_HEADER_RE.match(first_line):
        return (
            "Error: entry must start with `## LRN-YYYY-MM-DD-<letter>: "
            f"<title>`. Got: {first_line!r}"
        )

    origin = origin.strip()
    if origin:
        if not _ORIGIN_VALUE_RE.match(origin):
            return (
                "Error: origin must be a short slug like 'crew-auditor' or "
                f"'human' (letters, digits, '.', '_', '-'). Got: {origin!r}"
            )
        # Inject before the leak vet so the vetted text is exactly what
        # gets written.
        entry_markdown = _inject_origin(entry_markdown, origin)

    leak_findings = find_leak_indicators(entry_markdown)
    if leak_findings:
        return format_leak_report(leak_findings)

    target = _resolve_write_path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Wrap both the existence check and the append in one try so a
    # concurrent unlink between them is reported as a single write
    # error rather than masquerading as a Python traceback. The decision
    # about the separator still races (acknowledged in the docstring);
    # the file system call sequence does not.
    try:
        has_existing_content = (
            target.exists() and target.read_text(encoding="utf-8").strip() != ""
        )
        separator = "\n\n" if has_existing_content else ""
        with target.open("a", encoding="utf-8") as f:
            f.write(separator + entry_markdown.rstrip() + "\n")
    except OSError as e:
        return f"Error: failed to write {target}: {e}"

    _ensure_workspace_registered(workspace)
    if _is_in_workspace(workspace):
        ensure_sidecar_gitignored(workspace)

    # Best-effort: keep the sidecar in lockstep with the markdown
    # corpus by embedding just the newly appended entry.
    # ``_append_to_sidecar`` handles the documented soft-failure
    # surfaces (embedder unavailable, embed_texts returns None,
    # save_sidecar raises OSError) and does not propagate them.
    # An unforeseen exception from the numpy/save path would
    # propagate. That is intentional: loud failures from the
    # unexpected, quiet recovery from the documented ones.
    # If the embeddings extra is not installed, this is a no-op.
    if _embeddings.EMBEDDINGS_AVAILABLE:
        parsed = _parse_entries(entry_markdown.rstrip() + "\n", target)
        if parsed:
            _append_to_sidecar(target, parsed[0])

    return f"Appended entry to {target}"


async def learnings_search(
    req_id: str = "",
    stack_tags: list[str] | None = None,
    max_age_days: int = 180,
    limit: int = 20,
    req_summary: str = "",
    target_workspace_path: str = "",
    ctx: ToolContext | None = None,
) -> str:
    """Retrieve the top-N most relevant LEARNINGS entries for the current context.

    In-workspace mode reads ``<workspace>/LEARNINGS.md`` only. Outside-workspace
    mode aggregates ``~/.wopr/LEARNINGS.md`` plus every registered workspace's
    ``<path>/LEARNINGS.md``.

    Two candidate paths run in parallel and the results are unioned:

    1. **Deterministic prefilter.** Keeps entries that intersect
       ``stack_tags`` OR match ``req_id`` exactly. Old entries beyond
       ``max_age_days`` are dropped unless ``req_id`` matches. Fast,
       reproducible, always available.
    2. **Semantic top-N (optional).** When ``req_summary`` is provided
       and the optional ``embeddings`` extra is installed, ranks
       entries by cosine similarity between an embedding of
       ``req_summary`` and per-entry vectors loaded from each
       LEARNINGS.md's paired ``LEARNINGS.embeddings.npz`` sidecar.
       Catches paraphrased queries and cross-stack transfer that the
       deterministic filter would drop.

    The deterministic filter is the floor: when embeddings are not
    installed or ``req_summary`` is empty, ``learnings_search`` falls
    back to deterministic-only and the crew still works.

    Args:
        req_id: Current REQ identifier. Entries listing this REQ get a 2.0
            score boost. Empty string disables the boost.
        stack_tags: Stack identifiers (e.g. ``["spring-boot", "openapi-generator"]``).
            Entries are required to intersect this set unless empty.
        max_age_days: Age threshold in days. Older entries are dropped unless
            ``req_id`` matches the entry.
        limit: Maximum number of entries to return.
        req_summary: Free-text REQ description used by the semantic
            candidate path. Ignored when empty or when embeddings
            extra is not installed.

    Returns:
        A markdown block containing the top-N entries verbatim, separated by
        blank lines. Returns the empty string when nothing matches.
    """
    try:
        workspace = await resolve_request_workspace(target_workspace_path, ctx)
    except InvalidTargetWorkspaceError as e:
        return str(e)

    if stack_tags is None:
        stack_tags = []

    _ensure_workspace_registered(workspace)

    entries: list[LearningEntry] = []
    for path in _resolve_read_paths(workspace):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        entries.extend(_parse_entries(text, path))

    # Deterministic floor: always runs, always cheap.
    tag_hits = _prefilter(entries, req_id, stack_tags, max_age_days, limit)

    # Semantic top-up: best-effort, fails soft. The catch is narrowed
    # to runtime/IO surfaces fastembed and numpy actually raise.
    # KeyboardInterrupt, SystemExit, and MemoryError propagate so an
    # OOM on a huge vstack does not get logged at WARNING and quietly
    # discarded.
    sem_hits: list[LearningEntry] = []
    if _embeddings.EMBEDDINGS_AVAILABLE and req_summary.strip() and entries:
        try:
            sem_hits = _semantic_top_n(entries, req_summary, limit // 2 or 1)
        except (OSError, ValueError, RuntimeError, ImportError) as e:
            logger.warning(
                "Semantic search failed (%s); falling back to deterministic only.",
                e,
            )
            sem_hits = []

    # Union, dedupe by entry ID, preserve order with deterministic first
    # (the cheap+reproducible floor wins ties; semantic candidates
    # backfill the remaining limit).
    seen: set[str] = set()
    merged: list[LearningEntry] = []
    for entry in [*tag_hits, *sem_hits]:
        if entry.id in seen:
            continue
        seen.add(entry.id)
        merged.append(entry)
        if len(merged) >= limit:
            break

    return "\n\n".join(entry.raw.rstrip() for entry in merged)


def _semantic_top_n(
    entries: list[LearningEntry],
    req_summary: str,
    limit: int,
) -> list[LearningEntry]:
    """Rank ``entries`` by cosine similarity to ``req_summary``; top-N.

    Loads each entry's vector from its paired sidecar (one sidecar per
    distinct ``entry.source_path``). Builds a single matrix in entry
    order, encodes ``req_summary``, and ranks by cosine similarity.

    Returns ``[]`` when:
    - embeddings extra is not installed,
    - ``req_summary`` is empty,
    - no entries have a usable sidecar (load failed, model mismatch,
      hash drift the rebuild path could not resolve),
    - the query embedding call fails.

    Logs at INFO/WARNING for each skip reason so operators have
    visibility into why semantic results may be smaller than expected.
    """
    if not _embeddings.EMBEDDINGS_AVAILABLE or not req_summary.strip() or not entries:
        return []

    # ``np`` is bound at module load in ``_embeddings`` under the same
    # try/except that sets ``EMBEDDINGS_AVAILABLE``. The
    # ``EMBEDDINGS_AVAILABLE`` gate above guarantees ``_embeddings.np``
    # is the real numpy module here.
    np = _embeddings.np

    # Group entries by source path so each sidecar is loaded once.
    by_source: dict[Path, list[LearningEntry]] = {}
    for entry in entries:
        by_source.setdefault(entry.source_path, []).append(entry)

    # Walk each source's sidecar. For each source, build a fancy
    # index of the rows we need and slice the sidecar's matrix once.
    # This is much cheaper than appending per-entry rows into a
    # Python list and then ``vstack``-ing the result. The
    # aggregated_entries and per-source matrices are concatenated at
    # the end with a single ``np.concatenate`` call.
    aggregated_entries: list[LearningEntry] = []
    matrices: list[Any] = []
    for source_path, source_entries in by_source.items():
        sidecar = _load_or_rebuild_sidecar(source_path, entries=source_entries)
        if sidecar is None:
            continue
        if sidecar.model_name != EMBEDDING_MODEL:
            # _load_or_rebuild_sidecar should have rebuilt on mismatch;
            # if we still see the wrong model, the rebuild failed.
            # Skip rather than mix incompatible vectors.
            logger.warning(
                "Sidecar for %s uses model %r; expected %r. Skipping "
                "semantic ranking for that source.",
                source_path,
                sidecar.model_name,
                EMBEDDING_MODEL,
            )
            continue
        id_to_row = {id_: i for i, id_ in enumerate(sidecar.ids)}
        rows: list[int] = []
        kept_entries: list[LearningEntry] = []
        for entry in source_entries:
            row = id_to_row.get(entry.id)
            if row is None:
                # Entry exists in LEARNINGS.md but not in sidecar.
                # The rebuild path should have caught this via the
                # corpus_hash mismatch; arriving here means the
                # rebuild failed. Skip the entry.
                continue
            rows.append(row)
            kept_entries.append(entry)
        if rows:
            matrices.append(sidecar.vectors[rows])
            aggregated_entries.extend(kept_entries)

    if not aggregated_entries:
        return []

    # Embed the query. embed_texts returns a (1, dim) matrix.
    query_matrix = _embeddings.embed_texts([req_summary])
    if query_matrix is None or len(query_matrix) == 0:
        return []

    query_vec = query_matrix[0]
    entry_matrix = np.concatenate(matrices, axis=0) if len(matrices) > 1 else matrices[0]

    # Cosine similarity. bge-small-en-v1.5 outputs L2-normalized
    # vectors so the dot product IS the cosine; computing norms
    # explicitly is defensive (cheap, makes the function model-
    # agnostic if EMBEDDING_MODEL ever changes).
    entry_norms = np.linalg.norm(entry_matrix, axis=1)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []
    denom = entry_norms * query_norm
    # Guard against zero-norm entry vectors; mark their similarity 0.
    similarities = np.where(
        denom > 0,
        (entry_matrix @ query_vec) / np.where(denom > 0, denom, 1.0),
        0.0,
    )

    # Take top-N by similarity, descending. Skip non-positive scores
    # (rare with normalized embeddings but possible on edge cases).
    ranked_indices = np.argsort(similarities)[::-1][:limit]
    return [
        aggregated_entries[int(i)]
        for i in ranked_indices
        if similarities[int(i)] > 0.0
    ]


async def learnings_path(
    target_workspace_path: str = "", ctx: ToolContext | None = None
) -> str:
    """Diagnostic: report resolved read/write paths for the current context.

    Distinguishes "no entries yet" from "tool misconfigured." Each
    candidate read path is reported with a populated/empty flag so an
    operator can tell which case applies. The write path is reported
    regardless of whether the file currently exists.
    """
    try:
        workspace = await resolve_request_workspace(target_workspace_path, ctx)
    except InvalidTargetWorkspaceError as e:
        return str(e)
    in_workspace = _is_in_workspace(workspace)
    write_path = _resolve_write_path(workspace)

    # Enumerate the FULL candidate set for reads, then annotate each
    # with present/absent + populated/empty. ``_resolve_read_paths``
    # drops missing entries silently which obscures the misconfigured-
    # vs-empty distinction; recompute the full list here for reporting.
    candidate_reads: list[Path] = []
    if in_workspace:
        candidate_reads.append(workspace / LEARNINGS_FILENAME)
    else:
        home = get_global_home()
        candidate_reads.append(home / LEARNINGS_FILENAME)
        registry = home / WORKSPACES_REGISTRY_FILENAME
        if registry.exists():
            try:
                registry_text = registry.read_text(encoding="utf-8")
            except OSError:
                registry_text = ""
            for line in registry_text.splitlines():
                entry = line.strip()
                if entry:
                    candidate_reads.append(Path(entry) / LEARNINGS_FILENAME)

    lines = [
        f"workspace: {workspace}",
        f"in_workspace: {in_workspace}",
        f"write_path: {write_path}",
    ]
    if write_path.exists():
        try:
            size = write_path.stat().st_size
        except OSError:
            size = -1
        if size >= 0:
            lines.append(f"write_path_status: exists ({size} bytes)")
        else:
            lines.append("write_path_status: exists")
    else:
        lines.append("write_path_status: not yet created")

    lines.append("read_paths:")
    if not candidate_reads:
        lines.append("  (none configured)")
    for p in candidate_reads:
        if not p.exists():
            lines.append(f"  - {p}  [missing]")
            continue
        try:
            size = p.stat().st_size
        except OSError:
            lines.append(f"  - {p}  [exists, size unknown]")
            continue
        if size == 0:
            lines.append(f"  - {p}  [empty]")
        else:
            lines.append(f"  - {p}  [populated, {size} bytes]")
    return "\n".join(lines)


_KNOWN_SEED_STACKS = {"angular", "spring-boot", "fastapi"}


def _candidate_seed_paths(stack: str) -> list[Path]:
    """Candidate filesystem locations for a stack's seed file.

    Source-tree path first (dev iteration), bundled install path
    second. Path math centralized in :mod:`._data_paths`.
    """
    return candidate_data_paths(
        "crew", "data", "learnings-seed", f"{stack}.md",
    )


def seed_learnings(target_workspace_path: str, stack_tags: list[str]) -> str:
    """Append starter LEARNINGS entries to a new project.

    The CRAG retrieval path is useless on day one of a new project
    because the corpus is empty. This tool seeds the project's
    ``LEARNINGS.md`` with curated foundational lessons for the
    detected stack(s) so the first crew run already has
    something to retrieve. Seed entries are marked ``seed: true`` in
    their meta block; the prefilter bypasses the recency cutoff for
    them.

    Args:
        target_workspace_path: Absolute path to the project's
            workspace root (the directory containing ``wopr.yml``).
            Required; this tool does NOT infer the workspace.
        stack_tags: List of stack identifiers to seed. Known values:
            ``angular``, ``spring-boot``, ``fastapi``. Unknown tags
            are silently skipped (the seeded set is conservative;
            stacks without a curated file produce no seeds rather
            than a generic stub).

    Returns:
        Status string. Begins with ``Seeded`` on success listing the
        number of entries appended and the stacks included, or
        ``Error:`` on failure. Also registers the workspace in
        ``~/.wopr/workspaces.txt`` so cross-workspace reads can
        aggregate it.
    """
    if not target_workspace_path:
        return "Error: target_workspace_path is required."
    workspace = Path(target_workspace_path).expanduser()
    if not workspace.is_absolute():
        return f"Error: target_workspace_path {target_workspace_path!r} is not absolute."
    workspace = workspace.resolve()
    if not workspace.is_dir():
        return f"Error: target workspace does not exist: {workspace}"
    if not isinstance(stack_tags, list) or not stack_tags:
        return "Error: stack_tags must be a non-empty list."

    selected: list[tuple[str, Path]] = []
    for stack in stack_tags:
        if stack not in _KNOWN_SEED_STACKS:
            continue
        for candidate in _candidate_seed_paths(stack):
            if candidate.is_file():
                selected.append((stack, candidate))
                break

    if not selected:
        known = ", ".join(sorted(_KNOWN_SEED_STACKS))
        return (
            f"Error: no seed files found for stack_tags={stack_tags!r}. "
            f"Known stacks: {known}."
        )

    target_file = workspace / LEARNINGS_FILENAME
    existing_text = ""
    if target_file.is_file():
        try:
            existing_text = target_file.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error: failed to read {target_file}: {e}"
    existing_ids = {entry.id for entry in _parse_entries(existing_text, target_file)}

    appended: list[str] = []
    pieces: list[str] = [existing_text.rstrip()] if existing_text.strip() else []

    for stack, seed_path in selected:
        try:
            seed_text = seed_path.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error: failed to read seed file {seed_path}: {e}"
        for entry in _parse_entries(seed_text, seed_path):
            if entry.id in existing_ids:
                continue
            pieces.append(entry.raw.rstrip())
            existing_ids.add(entry.id)
            appended.append(f"{entry.id} ({stack})")

    if not appended:
        # Seeds already present; do not rewrite the file.
        _ensure_workspace_registered(workspace)
        if _is_in_workspace(workspace):
            ensure_sidecar_gitignored(workspace)
        return (
            "Seeded 0 entries (all seed entries for the requested stacks "
            "already exist in LEARNINGS.md). Workspace registered."
        )

    final_text = "\n\n".join(pieces).rstrip() + "\n"
    try:
        atomic_write_text(target_file, final_text)
    except OSError as e:
        return f"Error: failed to write {target_file}: {e}"

    _ensure_workspace_registered(workspace)
    if _is_in_workspace(workspace):
        ensure_sidecar_gitignored(workspace)

    return (
        f"Seeded {len(appended)} entries into {target_file}: "
        f"{', '.join(appended)}. Workspace registered."
    )


LEARNINGS_ARCHIVE_FILENAME = "LEARNINGS.archive.md"


async def curate_learnings(
    target_workspace_path: str = "",
    *,
    stale_after_days: int = _curator.DEFAULT_STALE_AFTER_DAYS,
    dry_run: bool = True,
    ctx: ToolContext | None = None,
) -> str:
    """Archive stale, non-seed LEARNINGS.md entries. Dry-run by default.

    Deterministic only — no LLM pass, no consolidation/merging of entry
    content. Modeled on the deterministic half of Hermes Agent's curator
    (``apply_automatic_transitions``); the LLM "umbrella-building" half is
    deliberately not ported (see ``tools/_curator.py`` docstring).

    Never deletes. Archived entries are appended verbatim to a sibling
    ``LEARNINGS.archive.md`` (created if absent) and removed from the live
    file. Seed entries (``seed: true``) are never touched. Entries with no
    parseable date are left alone.

    Args:
        target_workspace_path: Absolute path to the project workspace root.
            Optional on Claude Code (defaults to the session's project via
            CLAUDE_PROJECT_DIR); on other CLIs pass it explicitly.
        stale_after_days: Age threshold in days. Default 365 — a full year,
            deliberately longer than ``learnings_search``'s 180-day
            *retrieval* cutoff (Dim: an entry can be too old to surface by
            default in search results while still being too young to
            archive; those are different questions).
        dry_run: When True (default), reports what would be archived
            without writing anything. Pass False to actually apply.
    """
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, ctx, allow_legacy_config=False
        )
    except InvalidTargetWorkspaceError as e:
        return str(e)

    target = _resolve_write_path(workspace)
    if not target.is_file():
        return f"Nothing to curate: {target} does not exist."

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as e:
        return f"Error: failed to read {target}: {e}"

    entries = _parse_entries(text, target)
    if not entries:
        return f"Nothing to curate: {target} has no parseable entries."

    plan = _curator.plan_curation(
        entries,
        today=datetime.now(timezone.utc).date(),
        stale_after_days=stale_after_days,
    )

    if not plan.archive:
        return (
            f"Nothing to archive in {target} "
            f"({len(entries)} entries checked, 0 older than {stale_after_days} days)."
        )

    archived_ids = [e.id for e in plan.archive]
    summary = (
        f"{'Would archive' if dry_run else 'Archived'} {len(plan.archive)} of "
        f"{len(entries)} entries (older than {stale_after_days} days, non-seed): "
        f"{', '.join(archived_ids)}."
    )
    if dry_run:
        return summary + " Pass dry_run=False to apply."

    kept_text = _curator.render_entries(plan.keep)
    try:
        atomic_write_text(target, kept_text)
    except OSError as e:
        return f"Error: failed to write {target}: {e}"

    archive_target = target.parent / LEARNINGS_ARCHIVE_FILENAME
    archive_addition = _curator.render_entries(plan.archive)
    try:
        existing_archive = (
            archive_target.read_text(encoding="utf-8") if archive_target.is_file() else ""
        )
        if existing_archive.strip():
            new_archive_text = existing_archive.rstrip() + "\n\n" + archive_addition
        else:
            new_archive_text = archive_addition
        atomic_write_text(archive_target, new_archive_text)
    except OSError as e:
        return (
            f"Error: archived entries removed from {target} but failed to write "
            f"{archive_target}: {e}"
        )

    return summary + f" Moved to {archive_target}."


def register(mcp: FastMCP) -> None:
    """Register learnings tools with the MCP server."""
    mcp.tool()(append_learnings)
    mcp.tool()(curate_learnings)
    mcp.tool()(learnings_search)
    mcp.tool()(learnings_path)
    mcp.tool()(seed_learnings)
