"""LEARNINGS retrieval and append for the WOPR crew.

Implements the workspace-vs-system memory model and the deterministic
pre-filter used by Corrective RAG (CRAG). The crew auditor calls
:func:`append_learnings` at end of every gate; the ``wopr-run-crew``
orchestrator calls :func:`learnings_search` once per crew run, before
Step 1, and hands the result to the ``crew-evaluator`` agent for grading
only when the prefilter returns more than five candidates.

Single source of truth per entry. No mirroring. Workspace mode reads only the
workspace's ``LEARNINGS.md``; outside-workspace mode aggregates ``~/.wopr/LEARNINGS.md``
plus every registered workspace's file via ``~/.wopr/workspaces.txt``.

Workspace identity is resolved by :func:`._workspace_root.find_workspace_root`,
which every tool in this module shares: seed, append, curate and the read
path all ask the same question and get the same answer. A directory is a
workspace root when it carries ``wopr.yml`` **or** ``LEARNINGS.md``; otherwise
the search walks up parent by parent, nearest match wins, stopping at the git
toplevel. That module's docstring is the authority on the algorithm and on the
multi-package repository loop (``wopr.yml`` in subpackages, corpus at the repo
root) it exists to close. ``wopr.yml`` here is the crew pack's source of truth,
distinct from ``catalog.read_wopr_config``'s ``.wopr.yaml`` catalog config.

When resolution fails, these tools say so. ``~/.wopr/LEARNINGS.md`` is used
only when the caller named no target at all; a caller who named a directory
that does not resolve gets an error listing the searched paths, never a
silent write somewhere else.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .._atomic_write import atomic_write_text
from ..catalog import get_global_home
from ..context import ToolContext
from . import _curator, _embeddings
from ._data_paths import candidate_data_paths
from ._embedding_providers import (
    EmbeddingProvider,
    get_active_provider,
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
from ._workspace_root import (
    MARKER_FILENAMES,
    WOPR_YML_FILENAME,
    WorkspaceRoot,
    find_workspace_root,
    has_marker,
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
    "MARKER_FILENAMES",
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

# Outcome of one :func:`_ensure_workspace_registered` call. Returned
# rather than swallowed so a status message can report what actually
# happened instead of asserting an outcome the code may have skipped.
RegistrationResult = Literal[
    "added",  # the root was appended to workspaces.txt on this call
    "already-registered",  # it was already there; nothing written
    "not-a-workspace",  # no marker at the path; registration skipped
    "failed",  # the registry could not be read or written
]


@dataclass(frozen=True)
class _CorpusTarget:
    """Which ``LEARNINGS.md`` a write-side tool acts on, and who owns it."""

    #: The file to write. Always set.
    file: Path

    #: The workspace root that owns ``file``, or ``None`` when ``file``
    #: is the system corpus under ``~/.wopr``. Callers use this to decide
    #: whether registration and the ``.gitignore`` touch-up apply: both
    #: are workspace concepts and neither means anything for the system
    #: corpus.
    root: Path | None


def _resolve_corpus_target(
    workspace: Path, *, explicit_target: bool
) -> _CorpusTarget | str:
    """Resolve the corpus a write-side tool should act on, or say why not.

    Returns a :class:`_CorpusTarget`, or an error string ready to be
    handed straight back to the caller (this module's tools report
    failure by returning ``Error: ...`` rather than raising).

    The asymmetry between the two failure paths is the whole point of
    the function. ``~/.wopr/LEARNINGS.md`` is a reasonable home for an
    entry when the caller named no target: there is no expectation to
    violate. It is never a reasonable home for an entry when the caller
    DID name a target that turned out not to resolve, because the entry
    then lands somewhere the caller will never look. That case is an
    error.
    """
    resolution = find_workspace_root(workspace)
    if resolution.root is not None:
        return _CorpusTarget(
            file=resolution.root / LEARNINGS_FILENAME, root=resolution.root
        )
    if explicit_target:
        return _unresolved_workspace_error(workspace, resolution)
    return _CorpusTarget(file=get_global_home() / LEARNINGS_FILENAME, root=None)


def _unresolved_workspace_error(workspace: Path, resolution: WorkspaceRoot) -> str:
    """Error text for a named target that resolves to no workspace root.

    Deliberately verbose. This replaces a silent fallback to
    ``~/.wopr/LEARNINGS.md`` that produced a corpus nobody could find,
    so the message has to name the searched paths and the fix.
    """
    return (
        f"Error: no workspace root found for {workspace}, so nothing was "
        f"written. {resolution.explain()} Create wopr.yml or LEARNINGS.md at "
        "the directory that should own the corpus (seed_learnings writes "
        "LEARNINGS.md and is the supported way to do this for a repo whose "
        "wopr.yml files live in subpackages), or pass a target path inside "
        "an existing workspace."
    )


def _resolve_read_paths(root: Path | None) -> list[Path]:
    """In-workspace mode returns the resolved root's file only.

    Outside-workspace mode (``root`` is ``None``) aggregates the system file
    plus every registered workspace's file. Missing paths are skipped
    silently.
    """
    if root is not None:
        return [root / LEARNINGS_FILENAME]

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


def _ensure_workspace_registered(workspace: Path) -> RegistrationResult:
    """Append ``workspace`` to ``~/.wopr/workspaces.txt`` if not already present.

    Callers pass an already-resolved workspace root. The marker check
    is kept as a guard so a path that carries no marker is skipped
    rather than registering a directory whose corpus nothing owns.
    Idempotent: subsequent calls with the same path do nothing.

    Failures to read or write the registry are logged at WARNING and
    swallowed. Registration is best-effort: a failure here only means
    outside-workspace ``learnings_search`` will not aggregate this
    workspace's entries until a later call succeeds. It must not break
    the auditor's append or the operator's search.

    Returns:
        Which of the four things actually happened. Callers that report
        registration to an operator must use this instead of asserting
        success; a skipped registration reported as "registered" is how
        an orphaned corpus goes unnoticed.
    """
    if not has_marker(workspace):
        return "not-a-workspace"
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
            return "failed"
        for line in registry_text.splitlines():
            entry = line.strip()
            if entry:
                existing.add(entry)
    if workspace_str in existing:
        return "already-registered"
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
        return "failed"
    return "added"


def _registration_note(result: RegistrationResult, workspace: Path) -> str:
    """Human-readable, and true, sentence for a registration outcome.

    The point of the function: ``seed_learnings`` used to append the
    literal string "Workspace registered." to its result whether or not
    registration ran, including the case where the code explicitly
    skipped it. Every status message now derives from what happened.
    """
    if result == "added":
        return "Workspace registered."
    if result == "already-registered":
        return "Workspace already registered."
    if result == "not-a-workspace":
        markers = " or ".join(MARKER_FILENAMES)
        return (
            f"Registration skipped: no {markers} at {workspace}, so there is "
            "no workspace root to register."
        )
    return (
        "Registration failed: the workspace registry could not be updated "
        "(see the WOPR log). Cross-workspace search will not see this "
        "workspace until a later call succeeds."
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
    header.

    Where it lands: the workspace root that owns ``target_workspace_path``
    is resolved by walking up from that path to the nearest directory
    carrying ``wopr.yml`` or ``LEARNINGS.md``, stopping at the git toplevel
    (see :mod:`._workspace_root`). That root's ``LEARNINGS.md`` gets the
    entry. When no root is found, the outcome depends on how the call was
    made: a call that named ``target_workspace_path`` gets an error naming
    every directory searched and writes nothing, while a call that named no
    target at all falls back to the system file at ``~/.wopr/LEARNINGS.md``.
    An entry is never quietly diverted away from a workspace the caller
    named.

    Concurrency posture: WOPR is operator-driven, so the auditor's
    append is effectively single-writer per gate. The function does
    not take a cross-process lock; two concurrent appenders (rare,
    only possible if two crew runs land at the exact same instant)
    may produce an entry pair with a single blank-line separator
    instead of the conventional double. This is a cosmetic outcome,
    not data loss, and matches the same trade-off documented on the
    workspace-registry writer.

    Args:
        target_workspace_path: Absolute path to the project this entry
            belongs to, and must exist. Normally the workspace root, but any
            existing directory inside the workspace works: resolution walks
            up. Optional on Claude Code (defaults to the session's project
            via CLAUDE_PROJECT_DIR); on other CLIs pass it explicitly.
            Determines whether the entry lands in the workspace file or the
            system file (see above).
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
    explicit_target = bool(target_workspace_path and str(target_workspace_path).strip())
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

    resolved = _resolve_corpus_target(workspace, explicit_target=explicit_target)
    if isinstance(resolved, str):
        return resolved
    target = resolved.file
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

    if resolved.root is not None:
        _ensure_workspace_registered(resolved.root)
        ensure_sidecar_gitignored(resolved.root)

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

    In-workspace mode reads ``<workspace root>/LEARNINGS.md`` only, where the
    root is resolved by the same walk-up ``append_learnings`` uses, so reads
    and writes always address the same file. Outside-workspace mode (no root
    resolved) aggregates ``~/.wopr/LEARNINGS.md`` plus every registered
    workspace's ``<path>/LEARNINGS.md``.

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

    root = find_workspace_root(workspace).root
    if root is not None:
        _ensure_workspace_registered(root)

    entries: list[LearningEntry] = []
    for path in _resolve_read_paths(root):
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
    #
    # The provider is resolved ONCE per search, from the resolved
    # workspace root's configuration (env override first), so every
    # sidecar consulted in this call uses the same engine. ``none`` or
    # an unavailable provider (bedrock without credentials, local
    # extra missing) skips the semantic path entirely: deterministic
    # results, no network call, no crash.
    sem_hits: list[LearningEntry] = []
    if _embeddings.EMBEDDINGS_AVAILABLE and req_summary.strip() and entries:
        provider = get_active_provider(root)
        if provider is not None and provider.available():
            try:
                sem_hits = _semantic_top_n(
                    entries, req_summary, limit // 2 or 1, provider
                )
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
    provider: EmbeddingProvider,
) -> list[LearningEntry]:
    """Rank ``entries`` by cosine similarity to ``req_summary``; top-N.

    Loads each entry's vector from its paired sidecar (one sidecar per
    distinct ``entry.source_path``), embedding with ``provider`` — the
    single engine the caller resolved for this whole search. Builds a
    single matrix in entry order, encodes ``req_summary``, and ranks by
    cosine similarity.

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
        sidecar = _load_or_rebuild_sidecar(
            source_path, entries=source_entries, provider=provider
        )
        if sidecar is None:
            continue
        if sidecar.model_name != provider.name:
            # _load_or_rebuild_sidecar should have rebuilt on mismatch;
            # if we still see the wrong model, the rebuild failed.
            # Skip rather than mix incompatible vectors.
            logger.warning(
                "Sidecar for %s uses model %r; expected %r. Skipping "
                "semantic ranking for that source.",
                source_path,
                sidecar.model_name,
                provider.name,
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

    # Embed the query. provider.embed returns a (1, dim) matrix.
    query_matrix = provider.embed([req_summary])
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

    Reports the resolved workspace root alongside the requested
    workspace, because on a multi-package repo the two differ and the
    difference is exactly what an operator debugging a missing entry
    needs to see. When no root resolves, every searched directory is
    listed.

    Also reports the semantic layer's state: the active embedding
    provider (env override / ``wopr.yml`` / default), whether it is
    available, and the write path's sidecar (presence, entry count,
    dimensions). See :func:`_embeddings_status_lines`.
    """
    explicit_target = bool(target_workspace_path and str(target_workspace_path).strip())
    try:
        workspace = await resolve_request_workspace(target_workspace_path, ctx)
    except InvalidTargetWorkspaceError as e:
        return str(e)
    resolution = find_workspace_root(workspace)
    root = resolution.root
    in_workspace = resolution.found

    # Enumerate the FULL candidate set for reads, then annotate each
    # with present/absent + populated/empty. ``_resolve_read_paths``
    # drops missing entries silently which obscures the misconfigured-
    # vs-empty distinction; recompute the full list here for reporting.
    candidate_reads: list[Path] = []
    if root is not None:
        candidate_reads.append(root / LEARNINGS_FILENAME)
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
        f"workspace_root: {root if root is not None else '(none found)'}",
        f"in_workspace: {in_workspace}",
    ]
    if root is None:
        lines.append(f"searched: {', '.join(str(p) for p in resolution.searched)}")
        if resolution.git_toplevel is not None:
            lines.append(f"search_boundary: git toplevel {resolution.git_toplevel}")
        else:
            lines.append("search_boundary: filesystem root")

    # Ask the same resolver append_learnings and curate_learnings ask, so
    # the diagnostic cannot drift from the behavior it describes. A
    # returned error string means those tools would refuse this target.
    resolved = _resolve_corpus_target(workspace, explicit_target=explicit_target)
    write_path = None if isinstance(resolved, str) else resolved.file

    if write_path is None:
        lines.append("write_path: (unresolved)")
        lines.append(
            "write_path_status: append_learnings would refuse this target; no "
            "workspace root was found and a target path was named explicitly."
        )
    else:
        lines.append(f"write_path: {write_path}")
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

    lines.extend(_embeddings_status_lines(root, write_path))
    return "\n".join(lines)


def _embeddings_status_lines(root: Path | None, write_path: Path | None) -> list[str]:
    """Embeddings half of the ``learnings_path`` diagnostic.

    Reports the resolved provider (same resolution ``learnings_search``
    uses: env override, then the workspace root's ``wopr.yml``, then
    the ``local`` default), whether it is currently available, and the
    state of the write path's paired sidecar. Together these answer
    "why did my search return deterministic-only results" without the
    operator spelunking logs.
    """
    lines = ["embeddings:"]
    provider = get_active_provider(root)
    if provider is None:
        lines.append("  provider: none (semantic search disabled by configuration)")
        return lines
    lines.append(f"  provider: {provider.name}")
    if provider.available():
        lines.append("  provider_available: True")
    elif not _embeddings.EMBEDDINGS_AVAILABLE:
        lines.append(
            "  provider_available: False (embeddings extra not installed; "
            "deterministic prefilter only)"
        )
    else:
        lines.append(
            "  provider_available: False (provider not ready — see the WOPR "
            "log; deterministic prefilter only)"
        )
    if write_path is None:
        lines.append("  sidecar: (no resolved corpus)")
        return lines
    sidecar_path = _embeddings.resolve_sidecar_path(write_path)
    if not sidecar_path.is_file():
        lines.append(f"  sidecar: {sidecar_path}  [missing]")
        return lines
    if not _embeddings.EMBEDDINGS_AVAILABLE:
        # load_sidecar needs numpy; without the extra we can only
        # report presence, not contents.
        lines.append(
            f"  sidecar: {sidecar_path}  "
            "[present; install the embeddings extra to inspect]"
        )
        return lines
    sidecar = _embeddings.load_sidecar(sidecar_path)
    if sidecar is None:
        lines.append(
            f"  sidecar: {sidecar_path}  [unreadable; will rebuild on next search]"
        )
        return lines
    lines.append(
        f"  sidecar: {sidecar_path}  "
        f"[present, {len(sidecar.ids)} entries, {sidecar.dimensions} dims, "
        f"model {sidecar.model_name}]"
    )
    return lines


# Stacks with a curated seed file in ``catalog/crew/data/learnings-seed/``.
# Deliberately only stacks a shipped pack serves; a stack without a
# shipped pack gets no seeds (Phase 1 dropped spring-boot's on exactly
# that ground).
_KNOWN_SEED_STACKS = {"angular", "fastapi"}


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

    Writes ``<target_workspace_path>/LEARNINGS.md`` and nowhere else.
    That is deliberate and load-bearing: ``LEARNINGS.md`` is itself a
    workspace-root marker, so seeding a directory is how an operator
    declares which directory owns the corpus. For a repository whose
    ``wopr.yml`` files live in subpackages, seeding the repo root is
    what makes later ``append_learnings`` and ``learnings_search``
    calls from the repo root resolve there (see
    :mod:`._workspace_root`).

    Args:
        target_workspace_path: Absolute path to the directory that
            should own the corpus, normally the project's workspace
            root (the directory containing ``wopr.yml``, or the repo
            root of a multi-package repo). Required; this tool does
            NOT infer the workspace.
        stack_tags: List of stack identifiers to seed. Known values:
            ``angular``, ``fastapi``. Unknown tags are silently
            skipped (the seeded set is conservative; stacks without
            a curated file produce no seeds rather than a generic
            stub).

    Returns:
        Status string. Begins with ``Seeded`` on success listing the
        number of entries appended and the stacks included, or
        ``Error:`` on failure. The status ends with what registration
        in ``~/.wopr/workspaces.txt`` actually did on this call:
        registered, already registered, skipped, or failed. It never
        claims an outcome the code did not reach.
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
        note = _registration_note(_ensure_workspace_registered(workspace), workspace)
        if has_marker(workspace):
            ensure_sidecar_gitignored(workspace)
        return (
            "Seeded 0 entries (all seed entries for the requested stacks "
            f"already exist in LEARNINGS.md). {note}"
        )

    final_text = "\n\n".join(pieces).rstrip() + "\n"
    try:
        atomic_write_text(target_file, final_text)
    except OSError as e:
        return f"Error: failed to write {target_file}: {e}"

    # Registration runs AFTER the write, not before: the file just
    # written is itself the marker that makes ``workspace`` a workspace
    # root, which is what lets a multi-package repo root be registered
    # at all.
    note = _registration_note(_ensure_workspace_registered(workspace), workspace)
    ensure_sidecar_gitignored(workspace)

    return (
        f"Seeded {len(appended)} entries into {target_file}: "
        f"{', '.join(appended)}. {note}"
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

    Curates the same file ``append_learnings`` writes and
    ``learnings_search`` reads, resolved the same way, and refuses on the
    same terms: a named target that resolves to no workspace root is an
    error, not a quiet redirect to ``~/.wopr/LEARNINGS.md``. Curation
    rewrites a corpus, so curating the wrong one is worse than curating
    none.

    Args:
        target_workspace_path: Absolute path to the project workspace root
            or any path inside it. Optional on Claude Code (defaults to the
            session's project via CLAUDE_PROJECT_DIR); on other CLIs pass it
            explicitly.
        stale_after_days: Age threshold in days. Default 365 — a full year,
            deliberately longer than ``learnings_search``'s 180-day
            *retrieval* cutoff (Dim: an entry can be too old to surface by
            default in search results while still being too young to
            archive; those are different questions).
        dry_run: When True (default), reports what would be archived
            without writing anything. Pass False to actually apply.
    """
    explicit_target = bool(target_workspace_path and str(target_workspace_path).strip())
    try:
        workspace = await resolve_request_workspace(
            target_workspace_path, ctx, allow_legacy_config=False
        )
    except InvalidTargetWorkspaceError as e:
        return str(e)

    resolved = _resolve_corpus_target(workspace, explicit_target=explicit_target)
    if isinstance(resolved, str):
        return resolved
    target = resolved.file
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
