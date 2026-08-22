"""Optional semantic-search layer for CRAG (DEMO-123).

Lives beside :mod:`learnings` so the text/markdown side of CRAG stays
focused on parsing entries and resolving paths, while the vector side
keeps its own dependency surface and storage shape.

This module is import-safe even when the optional ``embeddings`` extra
is not installed:

- ``fastembed`` and ``numpy`` are soft-imported.
- The module-level ``EMBEDDINGS_AVAILABLE`` flag tells callers whether
  the optional dependency is present.
- Every public helper checks the flag and returns a no-op-shaped value
  (``None``, ``[]``) when embeddings are unavailable, so callers can
  branch on availability without repeatedly catching ``ImportError``.

Storage shape
-------------

Each ``LEARNINGS.md`` file is paired with exactly one sibling
``LEARNINGS.embeddings.npz`` sidecar in the same directory. The
multi-location structure mirrors :func:`learnings._resolve_read_paths`:

- Inside a workspace, only the workspace's sidecar is read.
- Outside a workspace, the global sidecar plus every registered
  workspace's sidecar are unioned at read time.

The sidecar carries three arrays plus a metadata block:

- ``vectors``: ``float32`` matrix, shape ``(N, dim)``.
- ``ids``: ``object`` array of entry IDs in the same row order as
  ``vectors``.
- ``meta``: a ``uint8`` array of JSON-encoded bytes for
  ``{model_name, corpus_hash, wopr_version, created_at,
  format_version}``.

The sidecar is regenerated on demand. Source of truth is the markdown
corpus.

Sidecars are ``.gitignore``-d automatically. The
machine-specific binary file never lands in source control (model
version drift between developers would otherwise produce noisy diffs
and merge conflicts on a file that should never be committed).
``tools._gitignore.ensure_sidecar_gitignored`` runs after every
in-workspace ``append_learnings`` / ``seed_learnings`` call and adds
``LEARNINGS.embeddings.npz`` to ``<workspace>/.gitignore`` under a
labelled WOPR section. Idempotent.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import __version__
from .._atomic_write import atomic_write_bytes

# Optional dependencies. ``fastembed`` brings ``onnxruntime`` and the
# embedding model as transitive deps; ``numpy`` is declared explicitly
# in the ``embeddings`` extra so the version constraint is visible.
try:
    import numpy as np
    from fastembed import TextEmbedding as _TextEmbedding

    EMBEDDINGS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in the not-installed path
    np = None  # type: ignore[assignment]
    _TextEmbedding = None  # type: ignore[assignment,misc]
    EMBEDDINGS_AVAILABLE = False

if TYPE_CHECKING:
    # Imported for type-checking only. Production paths gate every
    # ``np.*`` reference on ``EMBEDDINGS_AVAILABLE`` so the runtime
    # ``np = None`` fallback is safe even when annotations reference
    # ``np.ndarray`` (PEP 563 makes annotations lazy strings under
    # ``from __future__ import annotations``).
    import numpy as np

logger = logging.getLogger("wopr")

# Pinned embedding model. Stored as metadata in every sidecar; on read,
# a mismatch between the sidecar's recorded model and this constant
# forces a rebuild. Upgrade procedure: change this constant; the next
# learnings_search call regenerates affected sidecars.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Sidecar filename, always at the same directory level as the paired
# LEARNINGS.md. Auto-added to ``<workspace>/.gitignore`` by
# ``tools._gitignore.ensure_sidecar_gitignored`` after every in-workspace
# ``append_learnings`` / ``seed_learnings`` call.
EMBEDDINGS_SIDECAR_FILENAME = "LEARNINGS.embeddings.npz"

# Format version stamped into every sidecar. Bump when the on-disk
# shape changes (new array, renamed key, etc.); a sidecar with a
# format_version older than this constant triggers a full rebuild.
EMBEDDINGS_SIDECAR_FORMAT_VERSION = 1


# -----------------------------------------------------------------------------
# Sidecar payload type
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SidecarPayload:
    """A loaded sidecar, ready for cosine-similarity ranking.

    ``vectors`` is the row-major matrix of embeddings for the entries
    listed in ``ids`` (same order). Callers must NOT mutate it; the
    frozen dataclass and read-only-style usage are by convention.
    """

    ids: list[str]
    vectors: np.ndarray  # type: ignore[name-defined]
    model_name: str
    corpus_hash: str
    wopr_version: str
    created_at: str
    format_version: int


# -----------------------------------------------------------------------------
# Path + hash helpers (always safe to call, regardless of EMBEDDINGS_AVAILABLE)
# -----------------------------------------------------------------------------


def resolve_sidecar_path(learnings_path: Path) -> Path:
    """Return the sidecar path paired with ``learnings_path``.

    Always the same-directory sibling. Pure function; does not touch
    disk and does not depend on the embeddings extra.
    """
    return learnings_path.parent / EMBEDDINGS_SIDECAR_FILENAME


def corpus_hash(entry_ids: list[str]) -> str:
    """SHA256 digest of sorted entry IDs.

    Stored in the sidecar's metadata. On read, comparing this digest
    against the current LEARNINGS.md's recomputed hash detects
    out-of-band edits (operator removed an entry by hand, an entry
    was renamed, etc.) and triggers a rebuild.

    Sorting first makes the hash insensitive to file order so an
    auditor's append at the end of the file does not invalidate the
    full sidecar (the incremental append path handles that case).
    """
    return hashlib.sha256("|".join(sorted(entry_ids)).encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Sidecar load / save
# -----------------------------------------------------------------------------


def load_sidecar(path: Path) -> SidecarPayload | None:
    """Load a sidecar from disk; return ``None`` on missing / malformed.

    Caller is responsible for deciding what to do with ``None``
    (typically: rebuild from scratch). This function logs at WARNING
    on malformed sidecars because that is operator-facing. A corrupt
    sidecar suggests a partial write or a manual edit gone wrong, both
    of which the operator may want to know about.

    Returns ``None`` (no warning, no logging) when the embeddings
    extra is not installed; the calling code's normal flow already
    branches on ``EMBEDDINGS_AVAILABLE`` before reaching the load
    path, so this is a defensive belt-and-suspenders fallthrough.
    """
    if not EMBEDDINGS_AVAILABLE or not path.is_file():
        return None
    try:
        with np.load(path, allow_pickle=False) as data:
            ids = [str(x) for x in data["ids"]]
            vectors = np.asarray(data["vectors"], dtype=np.float32)
            meta_bytes = bytes(data["meta"])
            meta = json.loads(meta_bytes.decode("utf-8"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning("Cannot load sidecar at %s (%s); will rebuild.", path, e)
        return None
    if not isinstance(meta, dict):
        logger.warning(
            "Sidecar at %s has malformed meta block; will rebuild.", path
        )
        return None
    # Shape consistency: vectors must be a 2-D matrix with one row
    # per id. A mismatch can sneak in if the sidecar was hand-edited
    # or if an old/wrong-format file is sitting at the path. Without
    # this check, downstream ``sidecar.vectors[row]`` lookups would
    # IndexError mid-search.
    if vectors.ndim != 2 or vectors.shape[0] != len(ids):
        logger.warning(
            "Sidecar at %s has inconsistent shape (vectors=%s, ids=%d); "
            "will rebuild.",
            path,
            vectors.shape,
            len(ids),
        )
        return None
    return SidecarPayload(
        ids=ids,
        vectors=vectors,
        model_name=str(meta.get("model_name", "")),
        corpus_hash=str(meta.get("corpus_hash", "")),
        wopr_version=str(meta.get("wopr_version", "")),
        created_at=str(meta.get("created_at", "")),
        format_version=int(meta.get("format_version", 0)),
    )


def save_sidecar(
    path: Path,
    ids: list[str],
    vectors: np.ndarray,
    *,
    model_name: str,
    sidecar_corpus_hash: str,
) -> None:
    """Persist ``(ids, vectors, meta)`` to ``path`` atomically.

    ``model_name`` is the pinned model the vectors were produced with;
    callers MUST pass :data:`EMBEDDING_MODEL` (it is a parameter only
    to make tests trivially able to inject a different value when
    exercising the model-mismatch path).

    ``sidecar_corpus_hash`` is the hash of the entry-ID set the
    vectors cover, produced by :func:`corpus_hash`. Stored in the
    metadata block; on the next read, compared against a freshly
    recomputed hash of the live LEARNINGS.md to detect out-of-band
    edits.

    Caller must ensure ``EMBEDDINGS_AVAILABLE`` before invoking;
    otherwise ``np`` is ``None`` and this function will fail loudly
    with ``AttributeError``. That posture is intentional: silently
    no-op'ing on a save would mask a bug in the calling code.
    """
    meta: dict[str, Any] = {
        "model_name": model_name,
        "corpus_hash": sidecar_corpus_hash,
        "wopr_version": __version__,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "format_version": EMBEDDINGS_SIDECAR_FORMAT_VERSION,
    }
    meta_bytes = json.dumps(meta).encode("utf-8")

    # Use a Unicode-string dtype (np.str_) for the IDs array so the
    # sidecar can be loaded with ``allow_pickle=False`` (the safe
    # default). Object arrays would require pickle deserialization,
    # which we explicitly refuse on load to keep the format trusted
    # against tampered .npz files.
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        ids=np.array(ids, dtype=np.str_),
        vectors=vectors.astype(np.float32),
        meta=np.frombuffer(meta_bytes, dtype=np.uint8),
    )
    atomic_write_bytes(path, buffer.getvalue())


# -----------------------------------------------------------------------------
# Embedding (model lifecycle)
# -----------------------------------------------------------------------------


_embedder_instance: Any = None
_embedder_init_failed: bool = False


def _get_embedder() -> Any:
    """Lazy-init the TextEmbedding instance; cached for process lifetime.

    The first call triggers fastembed's model download (~130MB for
    bge-small-en-v1.5) into ``~/.cache/fastembed/``. Subsequent calls
    in the same process return the cached instance.

    Returns ``None`` in any of three states:

    - Extra not installed (``EMBEDDINGS_AVAILABLE`` is False).
    - A prior init attempt failed (firewall blocking the download,
      ONNX runtime crash, disk full). The ``_embedder_init_failed``
      flag is set so subsequent calls short-circuit without
      re-attempting the ~130MB download. A download-storm per search
      on an air-gapped box would be observable as multi-second
      latency on every crew pre-step. The sticky flag clears
      only on process restart, intentionally: the operator should
      see the failure once, fix the environment (install offline,
      open firewall, free space), then restart.
    - The cache miss + init succeeds on the happy path; subsequent
      calls return the cached instance.
    """
    global _embedder_instance, _embedder_init_failed
    if not EMBEDDINGS_AVAILABLE or _embedder_init_failed:
        return None
    if _embedder_instance is None:
        logger.info(
            "Initializing embedding model %s "
            "(first call may download ~130MB to ~/.cache/fastembed/)",
            EMBEDDING_MODEL,
        )
        try:
            _embedder_instance = _TextEmbedding(model_name=EMBEDDING_MODEL)
        except Exception as e:
            # fastembed init can raise OSError (model download/disk),
            # RuntimeError (ONNX init), ImportError (transitive missing
            # at runtime), and undocumented internals across versions.
            # Catching ``Exception`` is intentional: any failure here
            # should sticky-disable semantic search and let the
            # deterministic prefilter continue. Narrowing risks missing
            # a future fastembed exception type and re-raising into a
            # crash on a fresh install.
            _embedder_init_failed = True
            logger.warning(
                "Embedding model %s failed to initialize (%s). Semantic "
                "search disabled for this process; deterministic prefilter "
                "still works. Fix the environment (offline model, firewall, "
                "disk space) and restart to re-enable.",
                EMBEDDING_MODEL,
                e,
            )
            return None
    return _embedder_instance


def embed_texts(texts: list[str]) -> np.ndarray | None:
    """Embed a batch of texts. Returns ``None`` on unavailability or failure.

    The fastembed API returns a generator; we materialize it into a
    single float32 matrix here so callers can pass it directly to
    NumPy operations (cosine similarity, stacking, etc.).

    Returns ``None`` in any of:

    - Extra not installed.
    - Empty input (caller must handle; we don't know the embedding
      dim until we encode something, so we cannot return a zero-row
      matrix).
    - Embedder init failed (sticky after first failure; see
      :func:`_get_embedder`).
    - The encode call raises (logged at WARNING; the rest of the
      process still works via the deterministic prefilter).
    """
    if not EMBEDDINGS_AVAILABLE or not texts:
        return None
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        vectors = list(embedder.embed(texts))
    except Exception as e:
        # Encode failures span OSError (model cache eviction),
        # RuntimeError (ONNX session crash), MemoryError (large batch),
        # plus undocumented internals across fastembed versions. Catch
        # broadly and log; semantic search degrades to no-results for
        # this call while the deterministic prefilter still works.
        logger.warning("Embedding encode call failed (%s); returning None.", e)
        return None
    return np.array(vectors, dtype=np.float32)
