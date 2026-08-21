"""Tests for the optional semantic-search layer ([TICKET-ID]).

Two flavors of tests in this module:

1. **Fast tests** with a mocked embedder. Synthetic vectors are
   produced deterministically from hashes of the input text, so the
   integration paths (sidecar load/save, hash invalidation, model
   mismatch, semantic_top_n ranking) all exercise without downloading
   the real ONNX model. These tests run whenever numpy is available
   in the environment.
2. **Real-model headline test** (AC #11). Uses the actual fastembed
   model to verify the cross-stack semantic match: a FastAPI REQ
   asking about exception handling should surface the Spring Boot
   Pokemon-catch entry. Runs only when the optional ``embeddings``
   extra is installed AND the model has been downloaded; marked
   ``slow`` so CI lanes can skip it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")

from wopr.tools import _embeddings, learnings  # noqa: E402 - import after skip
from wopr.tools._embeddings import (  # noqa: E402 - import after skip
    EMBEDDING_MODEL,
    EMBEDDINGS_AVAILABLE,
    EMBEDDINGS_SIDECAR_FILENAME,
    EMBEDDINGS_SIDECAR_FORMAT_VERSION,
    corpus_hash,
    load_sidecar,
    resolve_sidecar_path,
    save_sidecar,
)

# -----------------------------------------------------------------------------
# Fake embedder: deterministic synthetic vectors for fast tests
# -----------------------------------------------------------------------------


class _FakeTextEmbedding:
    """Stand-in for fastembed.TextEmbedding in mocked tests.

    Produces a deterministic 384-dim vector per input text by seeding
    numpy's RandomState with a hash of the text. Same text in -> same
    vector out. Different texts in -> different vectors out. Vectors
    are NOT semantically meaningful, but they exercise every code path
    that consumes the embedder's output without paying the cost of
    the real model.
    """

    EMBED_DIM = 384

    def __init__(self, model_name: str = "fake-model") -> None:
        self.model_name = model_name

    def embed(self, texts):
        for text in texts:
            seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = numpy.random.RandomState(seed)
            # Normalize so cosine similarity behaves like bge models
            # (L2-normalized output).
            vec = rng.randn(self.EMBED_DIM).astype(numpy.float32)
            vec /= numpy.linalg.norm(vec)
            yield vec


@pytest.fixture
def fake_embedder(monkeypatch):
    """Patch ``_embeddings`` so it uses the deterministic fake.

    Forces ``EMBEDDINGS_AVAILABLE`` True (it already is in the local
    dev env after ``uv sync --extra embeddings``, but the fixture
    makes the test independent of install state). Also resets the
    lazy-init embedder cache so each test gets a fresh fake.
    """
    monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", True)
    monkeypatch.setattr(_embeddings, "_TextEmbedding", _FakeTextEmbedding)
    monkeypatch.setattr(_embeddings, "_embedder_instance", None)
    monkeypatch.setattr(_embeddings, "_embedder_init_failed", False)
    # learnings.py reads ``_embeddings.EMBEDDINGS_AVAILABLE`` directly
    # (the namespaced access intentionally avoids the dual-binding
    # footgun), so the single monkeypatch above suffices for both the
    # storage layer and the search integration.
    return _FakeTextEmbedding


# -----------------------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------------------


class TestPureHelpers:
    def test_resolve_sidecar_path_is_sibling(self, tmp_path: Path):
        learnings_path = tmp_path / "LEARNINGS.md"
        assert resolve_sidecar_path(learnings_path) == (
            tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        )

    def test_resolve_sidecar_path_does_not_touch_disk(self, tmp_path: Path):
        learnings_path = tmp_path / "subdir" / "LEARNINGS.md"
        # No file exists. The helper still returns the prospective path.
        result = resolve_sidecar_path(learnings_path)
        assert result.parent == learnings_path.parent
        assert result.name == EMBEDDINGS_SIDECAR_FILENAME

    def test_corpus_hash_deterministic(self):
        assert corpus_hash(["a", "b", "c"]) == corpus_hash(["a", "b", "c"])

    def test_corpus_hash_order_insensitive(self):
        # Sorting first means file-order is not part of the identity.
        assert corpus_hash(["a", "b", "c"]) == corpus_hash(["c", "b", "a"])

    def test_corpus_hash_differs_when_contents_differ(self):
        assert corpus_hash(["a", "b"]) != corpus_hash(["a", "c"])

    def test_corpus_hash_empty(self):
        # Empty corpus has a stable hash; doesn't crash.
        assert isinstance(corpus_hash([]), str)
        assert len(corpus_hash([])) == 64  # sha256 hex


# -----------------------------------------------------------------------------
# Sidecar save/load round-trip
# -----------------------------------------------------------------------------


class TestSidecarSaveLoad:
    def test_round_trip(self, tmp_path: Path, fake_embedder):
        path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        ids = ["LRN-2024-01-01-a", "LRN-2024-01-01-b"]
        vectors = numpy.array(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=numpy.float32
        )
        save_sidecar(
            path,
            ids,
            vectors,
            model_name=EMBEDDING_MODEL,
            sidecar_corpus_hash="deadbeef",
        )
        assert path.is_file()
        loaded = load_sidecar(path)
        assert loaded is not None
        assert loaded.ids == ids
        numpy.testing.assert_array_equal(loaded.vectors, vectors)
        assert loaded.model_name == EMBEDDING_MODEL
        assert loaded.corpus_hash == "deadbeef"
        assert loaded.format_version == EMBEDDINGS_SIDECAR_FORMAT_VERSION

    def test_load_missing_returns_none(self, tmp_path: Path, fake_embedder):
        assert load_sidecar(tmp_path / "does-not-exist.npz") is None

    def test_load_malformed_returns_none_with_warning(
        self,
        tmp_path: Path,
        fake_embedder,
        caplog: pytest.LogCaptureFixture,
    ):
        path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        path.write_bytes(b"not a real npz file")
        with caplog.at_level("WARNING", logger="wopr"):
            assert load_sidecar(path) is None
        assert any("Cannot load sidecar" in r.message for r in caplog.records)

    def test_save_is_atomic_no_temp_leftover(
        self, tmp_path: Path, fake_embedder
    ):
        path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        save_sidecar(
            path,
            ["LRN-x"],
            numpy.array([[1.0]], dtype=numpy.float32),
            model_name=EMBEDDING_MODEL,
            sidecar_corpus_hash="x",
        )
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
        assert leftovers == [], f"Unexpected temp files: {leftovers}"

    def test_load_rejects_shape_mismatch(
        self,
        tmp_path: Path,
        fake_embedder,
        caplog: pytest.LogCaptureFixture,
    ):
        """A sidecar whose vectors rows count does not match ids length
        is treated as malformed: returns None with a logged WARNING.
        Without this check, downstream ``sidecar.vectors[row]`` would
        IndexError mid-search.
        """
        import io as _io

        path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        # Write a sidecar by hand with mismatched shapes: 3 ids but
        # only 2 vector rows. Bypasses save_sidecar's validation
        # (there is none on save by design; save_sidecar trusts its
        # callers; load_sidecar is the gate).
        import json as _json

        meta_bytes = _json.dumps({
            "model_name": EMBEDDING_MODEL,
            "corpus_hash": "x",
            "wopr_version": "test",
            "created_at": "test",
            "format_version": EMBEDDINGS_SIDECAR_FORMAT_VERSION,
        }).encode("utf-8")
        buf = _io.BytesIO()
        numpy.savez_compressed(
            buf,
            ids=numpy.array(["a", "b", "c"], dtype=numpy.str_),
            vectors=numpy.array([[1.0, 0.0], [0.0, 1.0]], dtype=numpy.float32),
            meta=numpy.frombuffer(meta_bytes, dtype=numpy.uint8),
        )
        path.write_bytes(buf.getvalue())

        with caplog.at_level("WARNING", logger="wopr"):
            assert load_sidecar(path) is None
        assert any("inconsistent shape" in r.message for r in caplog.records)


# -----------------------------------------------------------------------------
# Embed helper
# -----------------------------------------------------------------------------


class TestEmbedderFailureRecovery:
    """The sticky ``_embedder_init_failed`` flag must short-circuit
    subsequent calls so the ~130MB ONNX download is not retried per
    search on a firewalled box.
    """

    def test_init_failure_sets_sticky_flag_and_short_circuits(
        self, monkeypatch, caplog: pytest.LogCaptureFixture
    ):
        construction_calls = {"n": 0}

        class _RaisingEmbedding:
            def __init__(self, *_args, **_kwargs):
                construction_calls["n"] += 1
                raise RuntimeError("simulated firewall / download failure")

        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", True)
        monkeypatch.setattr(_embeddings, "_TextEmbedding", _RaisingEmbedding)
        monkeypatch.setattr(_embeddings, "_embedder_instance", None)
        monkeypatch.setattr(_embeddings, "_embedder_init_failed", False)

        with caplog.at_level("WARNING", logger="wopr"):
            first = _embeddings._get_embedder()
            second = _embeddings._get_embedder()
            third = _embeddings._get_embedder()

        assert first is None and second is None and third is None
        # The constructor is invoked ONCE; subsequent calls are
        # short-circuited by the sticky flag.
        assert construction_calls["n"] == 1
        # The sticky flag is set on the module.
        assert _embeddings._embedder_init_failed is True
        # The operator sees the failure once, with remediation guidance.
        assert any(
            "failed to initialize" in r.message and "restart" in r.message
            for r in caplog.records
        )

    def test_embed_texts_returns_none_when_init_failed(self, monkeypatch):
        """``embed_texts`` honors the sticky failure flag without any
        additional probing; semantic-search callers see ``None`` and
        fall back to deterministic-only."""

        class _RaisingEmbedding:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError("simulated init failure")

        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", True)
        monkeypatch.setattr(_embeddings, "_TextEmbedding", _RaisingEmbedding)
        monkeypatch.setattr(_embeddings, "_embedder_instance", None)
        monkeypatch.setattr(_embeddings, "_embedder_init_failed", False)

        assert _embeddings.embed_texts(["hello"]) is None
        # Second call short-circuits without triggering another init.
        assert _embeddings.embed_texts(["world"]) is None


class TestEmbedTexts:
    def test_returns_none_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", False)
        assert _embeddings.embed_texts(["hello"]) is None

    def test_returns_none_for_empty_input(self, fake_embedder):
        assert _embeddings.embed_texts([]) is None

    def test_returns_matrix_for_valid_input(self, fake_embedder):
        result = _embeddings.embed_texts(["hello", "world"])
        assert result is not None
        assert result.shape == (2, _FakeTextEmbedding.EMBED_DIM)
        assert result.dtype == numpy.float32

    def test_same_text_same_vector(self, fake_embedder):
        a = _embeddings.embed_texts(["the same text"])
        b = _embeddings.embed_texts(["the same text"])
        numpy.testing.assert_array_equal(a, b)

    def test_different_texts_different_vectors(self, fake_embedder):
        a = _embeddings.embed_texts(["foo"])
        b = _embeddings.embed_texts(["bar"])
        assert not numpy.array_equal(a, b)

    def test_get_embedder_propagates_model_name_kwarg(self, fake_embedder):
        """``_get_embedder`` must construct the embedder with the
        pinned ``EMBEDDING_MODEL`` as the ``model_name`` kwarg.

        Catches a regression where a future refactor drops the
        constructor arg and the sidecar metadata silently records the
        wrong model. The ``_FakeTextEmbedding`` records the value
        in ``self.model_name``; this test asserts the round-trip.
        """
        embedder = _embeddings._get_embedder()
        assert embedder is not None
        assert embedder.model_name == EMBEDDING_MODEL


# -----------------------------------------------------------------------------
# Sidecar orchestration in learnings.py
# -----------------------------------------------------------------------------


def _make_entry_markdown(
    *, entry_date: str = "2026-05-13", letter: str = "a",
    title: str = "Sample", stack: str = "spring-boot",
) -> str:
    """Build a LEARNINGS.md entry that the parse regex accepts."""
    return (
        f"## LRN-{entry_date}-{letter}: {title}\n"
        "\n"
        "```meta\n"
        f"date: {entry_date}\n"
        "project: _seed\n"
        f"stack: [{stack}]\n"
        "req: []\n"
        f"auditor_run: seed@{stack}\n"
        "severity: warning\n"
        "```\n"
        "\n"
        "**What happened.** Body.\n"
        "**Why it matters.** Body.\n"
        "**Pattern to encode.** Body.\n"
    )


class TestBuildSidecar:
    def test_returns_none_when_file_missing(self, tmp_path: Path, fake_embedder):
        result = learnings._build_sidecar(tmp_path / "nope.md")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path, fake_embedder):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text("", encoding="utf-8")
        assert learnings._build_sidecar(learnings_path) is None

    def test_returns_none_for_no_entries(self, tmp_path: Path, fake_embedder):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text("# just prose, no LRN entries\n", encoding="utf-8")
        assert learnings._build_sidecar(learnings_path) is None

    def test_builds_and_writes_sidecar(self, tmp_path: Path, fake_embedder):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(
            _make_entry_markdown(letter="a", title="First")
            + "\n"
            + _make_entry_markdown(letter="b", title="Second"),
            encoding="utf-8",
        )
        payload = learnings._build_sidecar(learnings_path)
        assert payload is not None
        assert payload.ids == ["LRN-2026-05-13-a", "LRN-2026-05-13-b"]
        assert payload.model_name == EMBEDDING_MODEL
        # Sidecar landed on disk at the paired location.
        sidecar_path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        assert sidecar_path.is_file()


class TestAppendToSidecar:
    def test_no_op_when_unavailable(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", False)
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(_make_entry_markdown(), encoding="utf-8")
        entries = learnings._parse_entries(
            learnings_path.read_text(encoding="utf-8"), learnings_path
        )
        # Should not raise; should not write a sidecar.
        learnings._append_to_sidecar(learnings_path, entries[0])
        sidecar_path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        assert not sidecar_path.exists()

    def test_full_rebuild_when_no_sidecar_yet(
        self, tmp_path: Path, fake_embedder
    ):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(
            _make_entry_markdown(letter="a") + "\n" + _make_entry_markdown(letter="b"),
            encoding="utf-8",
        )
        entries = learnings._parse_entries(
            learnings_path.read_text(encoding="utf-8"), learnings_path
        )
        # No sidecar yet. Calling _append_to_sidecar triggers a full build.
        learnings._append_to_sidecar(learnings_path, entries[-1])
        sidecar = _embeddings.load_sidecar(tmp_path / EMBEDDINGS_SIDECAR_FILENAME)
        assert sidecar is not None
        # Full rebuild covered both entries.
        assert len(sidecar.ids) == 2

    def test_incremental_append_grows_sidecar(
        self, tmp_path: Path, fake_embedder
    ):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(_make_entry_markdown(letter="a"), encoding="utf-8")
        learnings._build_sidecar(learnings_path)
        assert len(_embeddings.load_sidecar(tmp_path / EMBEDDINGS_SIDECAR_FILENAME).ids) == 1

        # Append a new entry to the file, then call _append_to_sidecar.
        new_entry_text = _make_entry_markdown(letter="b")
        learnings_path.write_text(
            learnings_path.read_text(encoding="utf-8") + "\n" + new_entry_text,
            encoding="utf-8",
        )
        new_entry = learnings._parse_entries(new_entry_text, learnings_path)[0]
        learnings._append_to_sidecar(learnings_path, new_entry)

        sidecar = _embeddings.load_sidecar(tmp_path / EMBEDDINGS_SIDECAR_FILENAME)
        assert sidecar is not None
        assert sidecar.ids == ["LRN-2026-05-13-a", "LRN-2026-05-13-b"]


class TestLoadOrRebuildSidecar:
    def test_returns_none_when_file_missing(self, tmp_path: Path, fake_embedder):
        assert learnings._load_or_rebuild_sidecar(tmp_path / "nope.md") is None

    def test_builds_when_sidecar_missing(self, tmp_path: Path, fake_embedder):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(_make_entry_markdown(), encoding="utf-8")
        assert not (tmp_path / EMBEDDINGS_SIDECAR_FILENAME).exists()
        payload = learnings._load_or_rebuild_sidecar(learnings_path)
        assert payload is not None
        assert (tmp_path / EMBEDDINGS_SIDECAR_FILENAME).is_file()

    def test_rebuilds_on_corpus_hash_mismatch(
        self, tmp_path: Path, fake_embedder, caplog: pytest.LogCaptureFixture
    ):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(_make_entry_markdown(letter="a"), encoding="utf-8")
        learnings._build_sidecar(learnings_path)
        # Mutate LEARNINGS.md out-of-band: add a new entry without
        # going through append_learnings.
        learnings_path.write_text(
            learnings_path.read_text(encoding="utf-8") + "\n" + _make_entry_markdown(letter="b"),
            encoding="utf-8",
        )
        with caplog.at_level("INFO", logger="wopr"):
            payload = learnings._load_or_rebuild_sidecar(learnings_path)
        assert payload is not None
        assert payload.ids == ["LRN-2026-05-13-a", "LRN-2026-05-13-b"]
        assert any("stale" in r.message for r in caplog.records)

    def test_rebuilds_on_model_mismatch(
        self, tmp_path: Path, fake_embedder, monkeypatch,
        caplog: pytest.LogCaptureFixture,
    ):
        learnings_path = tmp_path / "LEARNINGS.md"
        learnings_path.write_text(_make_entry_markdown(), encoding="utf-8")
        # Save a sidecar with an intentionally wrong model name.
        sidecar_path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        save_sidecar(
            sidecar_path,
            ["LRN-2026-05-13-a"],
            numpy.array([[1.0, 0.0, 0.0]], dtype=numpy.float32),
            model_name="some-stale-model",
            sidecar_corpus_hash=corpus_hash(["LRN-2026-05-13-a"]),
        )
        with caplog.at_level("INFO", logger="wopr"):
            payload = learnings._load_or_rebuild_sidecar(learnings_path)
        assert payload is not None
        assert payload.model_name == EMBEDDING_MODEL
        assert any("Rebuilding" in r.message for r in caplog.records)


# -----------------------------------------------------------------------------
# Semantic top-N integration via learnings_search
# -----------------------------------------------------------------------------


@pytest.fixture
def learnings_workspace(tmp_path: Path, monkeypatch):
    """Workspace fixture with a wopr.yml so learnings is in-workspace mode."""
    from wopr.config import ServerConfig
    from wopr.context import ServerContext

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "wopr.yml").write_text("project:\n  slug: test\n", encoding="utf-8")
    home = tmp_path / "wopr-home"
    home.mkdir()
    monkeypatch.setenv("WOPR_HOME", str(home))
    ServerContext.reset()
    ctx = ServerContext.init(ServerConfig(cli_type="claude"))
    ctx.workspace = workspace
    yield workspace
    ServerContext.reset()


class TestLearningsSearchWithSemantic:
    async def test_returns_deterministic_only_without_req_summary(
        self, learnings_workspace: Path, fake_embedder
    ):
        # Two entries with spring-boot tag; deterministic filter alone
        # returns them when stack_tags matches.
        (learnings_workspace / "LEARNINGS.md").write_text(
            _make_entry_markdown(letter="a", title="First", stack="spring-boot"),
            encoding="utf-8",
        )
        result = await learnings.learnings_search(
            req_id="", stack_tags=["spring-boot"], req_summary=""
        )
        assert "First" in result

    async def test_semantic_path_runs_and_builds_sidecar(
        self, learnings_workspace: Path, fake_embedder
    ):
        # With req_summary set AND embeddings available, the semantic
        # path runs: the sidecar gets built as a side effect of the
        # search call. Synthetic vectors don't carry real semantic
        # similarity, so we can't assert WHICH entries surface
        # cross-stack; that proof is the real-model test. What this
        # fast test verifies: the integration is wired correctly,
        # the sidecar materializes on demand, AND the returned
        # candidate set contains the entry (the deterministic floor
        # is matched-on-stack here so the entry comes back regardless
        # of whether the semantic ranking sorts it high).
        (learnings_workspace / "LEARNINGS.md").write_text(
            _make_entry_markdown(letter="a", title="A lesson", stack="spring-boot"),
            encoding="utf-8",
        )
        sidecar_path = learnings_workspace / EMBEDDINGS_SIDECAR_FILENAME
        assert not sidecar_path.exists()
        result = await learnings.learnings_search(
            req_id="",
            stack_tags=["spring-boot"],  # ensures determinstic hit too
            req_summary="any free-text summary triggers the semantic path",
        )
        # The semantic path was exercised, leaving a sidecar behind.
        assert sidecar_path.is_file()
        sidecar = _embeddings.load_sidecar(sidecar_path)
        assert sidecar is not None
        assert sidecar.ids == ["LRN-2026-05-13-a"]
        # The return value carries the entry (would catch a regression
        # that built the sidecar as side effect but dropped the entry
        # from the merged candidate set).
        assert "LRN-2026-05-13-a" in result
        assert "A lesson" in result

    async def test_semantic_path_skipped_when_unavailable(
        self, learnings_workspace: Path, monkeypatch
    ):
        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", False)
        (learnings_workspace / "LEARNINGS.md").write_text(
            _make_entry_markdown(letter="a", title="Spring lesson", stack="spring-boot"),
            encoding="utf-8",
        )
        # req_summary is set but the extra isn't installed; semantic
        # path is silently skipped; deterministic-only returns based
        # on stack mismatch (no python tag on the entry) -> empty.
        result = await learnings.learnings_search(
            req_id="",
            stack_tags=["python"],
            req_summary="how should I handle exceptions in service methods?",
        )
        assert result == ""

    async def test_union_with_dedup(
        self, learnings_workspace: Path, fake_embedder
    ):
        # Both deterministic and semantic paths return the same entry;
        # the merged result must NOT duplicate it.
        (learnings_workspace / "LEARNINGS.md").write_text(
            _make_entry_markdown(letter="a", title="Unique entry", stack="spring-boot"),
            encoding="utf-8",
        )
        result = await learnings.learnings_search(
            req_id="",
            stack_tags=["spring-boot"],
            req_summary="any related summary text",
        )
        # Entry header appears exactly once.
        assert result.count("## LRN-2026-05-13-a") == 1


# -----------------------------------------------------------------------------
# append_learnings sidecar update side-effect
# -----------------------------------------------------------------------------


class TestAppendLearningsUpdatesSidecar:
    async def test_append_triggers_sidecar_creation(
        self, learnings_workspace: Path, fake_embedder
    ):
        entry = _make_entry_markdown(letter="a", title="First seeded entry")
        result = await learnings.append_learnings(str(learnings_workspace), entry_markdown=entry)
        assert result.startswith("Appended")
        sidecar = _embeddings.load_sidecar(
            learnings_workspace / EMBEDDINGS_SIDECAR_FILENAME
        )
        assert sidecar is not None
        assert sidecar.ids == ["LRN-2026-05-13-a"]


# -----------------------------------------------------------------------------
# Doctor: embeddings status + per-workspace sidecar warnings
# -----------------------------------------------------------------------------


class TestDoctorEmbeddingsStatus:
    def test_status_reports_extra_installed(self, fake_embedder):
        from wopr.tools.doctor import _get_embeddings_status

        status = _get_embeddings_status()
        assert status["extra_installed"] is True
        assert status["pinned_model"] == EMBEDDING_MODEL
        assert status["sidecar_filename"] == EMBEDDINGS_SIDECAR_FILENAME

    def test_status_reports_not_installed(self, monkeypatch):
        from wopr.tools.doctor import _get_embeddings_status

        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", False)
        status = _get_embeddings_status()
        assert status["extra_installed"] is False
        # Model name and filename are still reported so operators see
        # what the pin WOULD be if they installed the extra.
        assert status["pinned_model"] == EMBEDDING_MODEL


class TestDoctorSidecarWarnings:
    def test_no_warnings_when_extra_unavailable(
        self, tmp_path: Path, monkeypatch
    ):
        from wopr.tools.doctor import _check_embeddings_sidecar

        monkeypatch.setattr(_embeddings, "EMBEDDINGS_AVAILABLE", False)
        learnings_text = _make_entry_markdown()
        assert _check_embeddings_sidecar(tmp_path, learnings_text) == []

    def test_no_warnings_when_sidecar_absent(
        self, tmp_path: Path, fake_embedder
    ):
        from wopr.tools.doctor import _check_embeddings_sidecar

        # Sidecar doesn't exist (normal first-run state). No warning.
        learnings_text = _make_entry_markdown()
        assert _check_embeddings_sidecar(tmp_path, learnings_text) == []

    def test_emits_model_mismatch_warning(
        self, tmp_path: Path, fake_embedder
    ):
        from wopr.tools.doctor import (
            WARNING_EMBEDDINGS_SIDECAR_MODEL_MISMATCH,
            _check_embeddings_sidecar,
        )

        # Create a sidecar with the wrong model name.
        sidecar_path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        save_sidecar(
            sidecar_path,
            ["LRN-2026-05-13-a"],
            numpy.array([[1.0, 0.0]], dtype=numpy.float32),
            model_name="some-old-model",
            sidecar_corpus_hash=corpus_hash(["LRN-2026-05-13-a"]),
        )
        learnings_text = _make_entry_markdown(letter="a")
        warnings_list = _check_embeddings_sidecar(tmp_path, learnings_text)
        assert any(
            WARNING_EMBEDDINGS_SIDECAR_MODEL_MISMATCH in w for w in warnings_list
        )

    def test_emits_stale_hash_warning(
        self, tmp_path: Path, fake_embedder
    ):
        from wopr.tools.doctor import (
            WARNING_EMBEDDINGS_SIDECAR_STALE,
            _check_embeddings_sidecar,
        )

        # Sidecar records hash for one entry set.
        sidecar_path = tmp_path / EMBEDDINGS_SIDECAR_FILENAME
        save_sidecar(
            sidecar_path,
            ["LRN-2026-05-13-a"],
            numpy.array([[1.0, 0.0]], dtype=numpy.float32),
            model_name=EMBEDDING_MODEL,
            sidecar_corpus_hash=corpus_hash(["LRN-2026-05-13-a"]),
        )
        # But LEARNINGS.md actually has two different entries (b and c).
        learnings_text = (
            _make_entry_markdown(letter="b") + "\n" + _make_entry_markdown(letter="c")
        )
        warnings_list = _check_embeddings_sidecar(tmp_path, learnings_text)
        assert any(
            WARNING_EMBEDDINGS_SIDECAR_STALE in w for w in warnings_list
        )


# -----------------------------------------------------------------------------
# Real-model integration (AC #11): cross-stack semantic match
# -----------------------------------------------------------------------------
#
# Uses the actual fastembed model rather than the fake embedder. Tests
# that the semantic path surfaces a Spring Boot Pokemon-catch entry
# when the REQ is FastAPI-tagged and asks about exception handling.
# This is the headline acceptance test from the [TICKET-ID] ticket:
# the deterministic filter alone returns nothing (no python/fastapi
# tag on the entry), but the semantic match catches the conceptual
# overlap.
#
# Marked slow because the first run downloads the ONNX model
# (~130MB). Skipped when the embeddings extra is not installed.
# -----------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    not EMBEDDINGS_AVAILABLE,
    reason="embeddings extra not installed; install with pip install 'wopr[embeddings]'",
)
class TestRealModelCrossStackMatch:
    async def test_pokemon_catch_matches_fastapi_exception_query(
        self, learnings_workspace: Path
    ):
        """AC #11: semantic search finds a Spring Boot anti-pattern
        entry from a FastAPI-tagged REQ about exception handling.

        The deterministic filter drops the entry (no python/fastapi
        stack tag). The semantic path picks it up via the conceptual
        overlap between "Pokemon catch" and "broad exception handling
        in service functions."

        Real model required: synthetic vectors carry no semantic
        meaning. The first run downloads ~130MB to
        ~/.cache/fastembed/; subsequent runs hit the cached model.
        """
        pokemon_entry = (
            "## LRN-2026-05-13-d: Pokemon catch wrapping every service method is a blocker\n"
            "\n"
            "```meta\n"
            "date: 2026-05-13\n"
            "project: _seed\n"
            "stack: [spring-boot, java]\n"
            "req: []\n"
            "auditor_run: seed@spring-boot\n"
            "severity: blocker\n"
            "seed: true\n"
            "```\n"
            "\n"
            "**What happened.** Service methods wrapped every body in "
            "`try { ... } catch (Exception e) { throw new ServiceException(...) }`. "
            "Bad client input becomes a 500. Stack trace gone.\n"
            "\n"
            "**Why it matters.** Every failure surfaces as the same generic 500. "
            "Legitimate 4xx errors get remapped to 5xx, breaking retry behavior.\n"
            "\n"
            "**Pattern to encode.** Catch specific exceptions; let domain errors "
            "propagate naturally; never wrap a catch-all without preserving cause.\n"
        )
        (learnings_workspace / "LEARNINGS.md").write_text(pokemon_entry, encoding="utf-8")

        # FastAPI REQ; the entry has no python/fastapi tag, so the
        # deterministic filter alone returns nothing.
        deterministic_only = await learnings.learnings_search(
            req_id="",
            stack_tags=["python", "fastapi"],
            req_summary="",
        )
        assert deterministic_only == "", (
            "Deterministic filter should drop the entry without semantic input"
        )

        # Same call but WITH req_summary. The semantic path should
        # rank the Pokemon-catch entry highly because the conceptual
        # match is strong: both reference exception handling in
        # service methods.
        with_semantic = await learnings.learnings_search(
            req_id="",
            stack_tags=["python", "fastapi"],
            req_summary=(
                "How should I handle exceptions in service functions in this "
                "FastAPI project? I want to avoid wrapping every function "
                "in a broad try/except that turns all errors into 500s."
            ),
        )
        assert "Pokemon catch" in with_semantic, (
            "Real-model semantic search should surface the Pokemon-catch "
            "entry from a FastAPI exception-handling REQ"
        )
