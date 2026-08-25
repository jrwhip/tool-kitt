"""Sidecar orchestration: ties the markdown corpus to the vector store.

The :mod:`_embeddings` module is a leaf utility: it knows how to save
vectors to an ``.npz`` sidecar and load them back, plus the local
model's lifecycle. :mod:`_embedding_providers` owns which engine
produces the vectors. Neither knows what a LEARNINGS.md is, where one
lives, or how to parse one. This module supplies the missing glue,
deciding WHEN to build a sidecar from scratch, when to append a single
new entry, and when an existing sidecar is stale and needs a rebuild.

Split out of :mod:`learnings` so the corpus parser, the search API,
and the sidecar orchestration are three concerns with three modules
instead of one 1000-line file. Same external surface: callers
(test code, ``learnings_search``, ``append_learnings``) reach the
same helpers; ``learnings`` re-exports them so existing import paths
continue to work.

Provider resolution: every helper accepts an optional ``provider``.
When the caller has already resolved one (``learnings_search`` resolves
once per search so all sidecars in a run use the same engine), it is
passed through; otherwise the helper resolves it from the corpus's own
directory (``get_active_provider(learnings_path.parent)``), which is
where the owning ``wopr.yml`` lives.

Every helper here is a no-op when the embeddings extra is not
installed, when the configured provider is ``none``, or when the
provider is unavailable (returns ``None`` or just early-returns).
Callers MUST NOT assume a sidecar exists after a build call; the
``None`` path is load-bearing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from . import _embeddings
from ._embedding_providers import EmbeddingProvider, get_active_provider
from ._embeddings import SidecarPayload
from ._learnings_format import LearningEntry, parse_entries

logger = logging.getLogger("wopr")


def _resolve_provider(
    learnings_path: Path, provider: EmbeddingProvider | None
) -> EmbeddingProvider | None:
    """The provider to use for ``learnings_path``'s sidecar, or ``None``.

    ``None`` means "semantic layer off for this corpus": the operator
    configured ``none``, or the configured provider reports itself
    unavailable (no boto3/credentials for bedrock; extra missing or
    sticky init failure for local).
    """
    if provider is None:
        provider = get_active_provider(learnings_path.parent)
    if provider is None or not provider.available():
        return None
    return provider


def build_sidecar(
    learnings_path: Path,
    entries: list[LearningEntry] | None = None,
    provider: EmbeddingProvider | None = None,
) -> SidecarPayload | None:
    """Embed every entry in ``learnings_path`` and write the sidecar.

    Full rebuild. Use when the sidecar is missing, when its
    ``corpus_hash`` does not match the live entry set, or when its
    ``model_name``/``dimensions``/``format_version`` do not match the
    active provider and format.

    Args:
        learnings_path: Path to the LEARNINGS.md that pairs with this
            sidecar. Used to locate the sidecar destination via
            :func:`_embeddings.resolve_sidecar_path`.
        entries: Pre-parsed entries to embed. When ``None`` (the
            default), this function reads and parses
            ``learnings_path`` itself. Callers that have already
            parsed the file (e.g. :func:`learnings_search`) pass
            ``entries`` to avoid the redundant read+parse.
        provider: Already-resolved embedding provider, or ``None`` to
            resolve from the corpus directory's configuration.

    Returns the freshly built payload (reflecting the same data
    persisted to disk), or ``None`` if the embeddings extra is not
    installed, no provider is active, the source file is missing, the
    file contains no parseable entries, or the embedding call fails.
    """
    if not _embeddings.EMBEDDINGS_AVAILABLE or not learnings_path.is_file():
        return None
    provider = _resolve_provider(learnings_path, provider)
    if provider is None:
        return None
    if entries is None:
        try:
            text = learnings_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(
                "Cannot read %s for sidecar build: %s", learnings_path, e
            )
            return None
        entries = parse_entries(text, learnings_path)
    if not entries:
        return None
    ids = [e.id for e in entries]
    texts = [e.raw for e in entries]
    vectors = provider.embed(texts)
    if vectors is None:
        logger.warning(
            "Embedding call returned no vectors for %s; sidecar not built.",
            learnings_path,
        )
        return None
    sidecar_corpus_hash = _embeddings.corpus_hash(ids)
    sidecar_path = _embeddings.resolve_sidecar_path(learnings_path)
    try:
        _embeddings.save_sidecar(
            sidecar_path,
            ids,
            vectors,
            model_name=provider.name,
            sidecar_corpus_hash=sidecar_corpus_hash,
        )
    except OSError as e:
        logger.warning("Cannot write sidecar at %s: %s", sidecar_path, e)
        return None
    # Read the sidecar back to get the canonical metadata the
    # downstream consumers may rely on (wopr_version, created_at,
    # format_version). Falling back to the just-built values keeps
    # the function honest even if the disk readback fails for any
    # reason (rare; the write just succeeded).
    refreshed = _embeddings.load_sidecar(sidecar_path)
    if refreshed is not None:
        return refreshed
    return SidecarPayload(
        ids=ids,
        vectors=vectors,
        model_name=provider.name,
        corpus_hash=sidecar_corpus_hash,
        wopr_version=__version__,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        format_version=_embeddings.EMBEDDINGS_SIDECAR_FORMAT_VERSION,
        dimensions=int(vectors.shape[1]) if vectors.ndim == 2 else 0,
    )


def append_to_sidecar(
    learnings_path: Path,
    entry: LearningEntry,
    provider: EmbeddingProvider | None = None,
) -> None:
    """Embed one new entry and append to the paired sidecar. O(1).

    Called by :func:`append_learnings` after the entry has been
    persisted to LEARNINGS.md. If the sidecar does not yet exist, or
    was built by a different provider/format, a full rebuild is
    triggered (the corpus is presumably small if no sidecar exists;
    rebuild cost is bounded).

    Concurrency posture (matches the markdown writer's
    documented stance): the read-then-write window is unprotected.
    Two concurrent ``append_learnings`` calls landing in the same
    millisecond can produce a sidecar that misses one of the two
    appended entries: the loser's vector is silently dropped from
    the sidecar even though both entries are in LEARNINGS.md. This
    is recoverable on the next ``learnings_search`` call because
    the hash-mismatch detection rebuilds the sidecar from the
    authoritative markdown corpus. WOPR is operator-driven and
    single-writer-per-gate in practice, so the race window is
    effectively never hit; the recovery path makes the outcome
    eventually consistent. If the system grows multi-writer
    deployment, take an advisory ``fcntl.flock`` on the sidecar
    path across the read+write.

    No-op when the embeddings extra is not installed or no provider is
    active. Failures (embedding error, write error) are logged at
    WARNING and swallowed; the markdown append succeeded already, so
    the sidecar being out of sync is recoverable on the next
    ``learnings_search`` via the hash-mismatch rebuild path.
    """
    if not _embeddings.EMBEDDINGS_AVAILABLE:
        return
    provider = _resolve_provider(learnings_path, provider)
    if provider is None:
        return
    sidecar_path = _embeddings.resolve_sidecar_path(learnings_path)
    existing = _embeddings.load_sidecar(sidecar_path)
    if (
        existing is None
        or existing.model_name != provider.name
        or existing.format_version != _embeddings.EMBEDDINGS_SIDECAR_FORMAT_VERSION
    ):
        # No usable sidecar; rebuild from scratch so the new entry is
        # captured alongside every other entry in the file.
        build_sidecar(learnings_path, provider=provider)
        return
    new_vectors = provider.embed([entry.raw])
    if new_vectors is None:
        logger.warning(
            "Could not embed new entry %s; sidecar at %s left stale "
            "until next rebuild.",
            entry.id,
            sidecar_path,
        )
        return
    # ``_embeddings.np`` is bound at module load under the same
    # try/except that sets ``EMBEDDINGS_AVAILABLE``; we are already
    # past the ``EMBEDDINGS_AVAILABLE`` early-return at the top of this
    # function, so the real numpy module is available.
    np = _embeddings.np

    ids = [*existing.ids, entry.id]
    vectors = np.vstack([existing.vectors, new_vectors])
    sidecar_corpus_hash = _embeddings.corpus_hash(ids)
    try:
        _embeddings.save_sidecar(
            sidecar_path,
            ids,
            vectors,
            model_name=provider.name,
            sidecar_corpus_hash=sidecar_corpus_hash,
        )
    except OSError as e:
        logger.warning(
            "Cannot update sidecar at %s with appended entry %s: %s",
            sidecar_path,
            entry.id,
            e,
        )


def load_or_rebuild_sidecar(
    learnings_path: Path,
    entries: list[LearningEntry] | None = None,
    provider: EmbeddingProvider | None = None,
) -> SidecarPayload | None:
    """Load the sidecar paired with ``learnings_path``, rebuilding if stale.

    Rebuild triggers, in order:
    1. Sidecar missing on disk (or unloadable/malformed).
    2. Sidecar's ``format_version`` does not match
       :data:`_embeddings.EMBEDDINGS_SIDECAR_FORMAT_VERSION` (older OR
       newer: a sidecar written by a future format is just as
       unreadable as a stale one, and the markdown corpus is always
       there to rebuild from).
    3. Sidecar's ``model_name`` does not match the active provider's
       ``name`` (covers both model upgrades and provider switches).
    4. Sidecar's recorded ``dimensions`` do not match the active
       provider's (belt to trigger 3's suspenders; a mixed-width
       matrix must never reach the cosine ranking).
    5. Sidecar's ``corpus_hash`` does not match the freshly computed
       hash of the live LEARNINGS.md's entry IDs.

    Args:
        learnings_path: Path to the source LEARNINGS.md file.
        entries: Pre-parsed entries. When provided, this function
            uses them to compute the corpus hash without re-reading
            and re-parsing the file. Callers that have already
            grouped entries by source (e.g. :func:`_semantic_top_n`)
            pass them in.
        provider: Already-resolved embedding provider, or ``None`` to
            resolve from the corpus directory's configuration.

    Returns ``None`` when the embeddings extra is not installed, no
    provider is active, the LEARNINGS.md is missing or empty, or any
    rebuild attempt fails.
    """
    if not _embeddings.EMBEDDINGS_AVAILABLE or not learnings_path.is_file():
        return None
    provider = _resolve_provider(learnings_path, provider)
    if provider is None:
        return None
    sidecar_path = _embeddings.resolve_sidecar_path(learnings_path)
    existing = _embeddings.load_sidecar(sidecar_path)
    if existing is None:
        return build_sidecar(learnings_path, entries=entries, provider=provider)
    if existing.format_version != _embeddings.EMBEDDINGS_SIDECAR_FORMAT_VERSION:
        logger.info(
            "Sidecar at %s has format_version %d; expected %d. Rebuilding.",
            sidecar_path,
            existing.format_version,
            _embeddings.EMBEDDINGS_SIDECAR_FORMAT_VERSION,
        )
        return build_sidecar(learnings_path, entries=entries, provider=provider)
    if existing.model_name != provider.name:
        logger.info(
            "Sidecar at %s uses model %r; expected %r. Rebuilding.",
            sidecar_path,
            existing.model_name,
            provider.name,
        )
        return build_sidecar(learnings_path, entries=entries, provider=provider)
    if existing.dimensions != provider.dimensions:
        logger.info(
            "Sidecar at %s carries %d-dim vectors; provider %s produces "
            "%d. Rebuilding.",
            sidecar_path,
            existing.dimensions,
            provider.name,
            provider.dimensions,
        )
        return build_sidecar(learnings_path, entries=entries, provider=provider)
    if entries is None:
        try:
            text = learnings_path.read_text(encoding="utf-8")
        except OSError:
            return None
        entries = parse_entries(text, learnings_path)
    if not entries:
        return None
    current_hash = _embeddings.corpus_hash([e.id for e in entries])
    if existing.corpus_hash != current_hash:
        logger.info(
            "Sidecar at %s is stale (corpus hash changed); rebuilding.",
            sidecar_path,
        )
        return build_sidecar(learnings_path, entries=entries, provider=provider)
    return existing
