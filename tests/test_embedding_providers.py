"""Tests for the pluggable embedding-provider layer (Phase 1).

Covers:

1. Provider selection: env var beats ``kitt.yml`` beats the ``local``
   default; ``none`` disables the semantic layer; unknown values fall
   through to the next source.
2. The Bedrock Titan provider: soft boto3 import, credential probing,
   the per-text ``invoke_model`` loop, and its failure surfaces. boto3
   is always mocked — no test here may reach AWS.
3. Graceful degradation end to end: ``learnings_search`` with an
   unavailable or disabled provider returns deterministic results,
   builds no sidecar, and makes no AWS call.

The local provider's model lifecycle is covered by
``tests/test_embeddings.py``; this module only asserts the adapter
delegates correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")

from kitt.tools import _embedding_providers, learnings  # noqa: E402
from kitt.tools._embedding_providers import (  # noqa: E402
    BEDROCK_MODEL_ID,
    BEDROCK_PROVIDER_NAME,
    LOCAL_PROVIDER_NAME,
    PROVIDER_ENV_VAR,
    BedrockTitanProvider,
    LocalFastembedProvider,
    get_active_provider,
    resolve_provider_name,
)
from kitt.tools._embeddings import EMBEDDINGS_SIDECAR_FILENAME  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_provider_state(monkeypatch):
    """Fresh provider cache and no env override for every test.

    The per-process instance cache exists so sticky failure flags
    survive across calls in production; in tests it would leak a
    failed Bedrock client from one test into the next.
    """
    monkeypatch.setattr(_embedding_providers, "_provider_instances", {})
    monkeypatch.delenv(PROVIDER_ENV_VAR, raising=False)


# -----------------------------------------------------------------------------
# Selection: env -> kitt.yml -> default
# -----------------------------------------------------------------------------


class TestProviderSelection:
    def test_default_is_local(self, tmp_path: Path):
        assert resolve_provider_name(None) == "local"
        assert resolve_provider_name(tmp_path) == "local"  # no kitt.yml
        assert isinstance(get_active_provider(None), LocalFastembedProvider)

    def test_kitt_yml_provider_is_read(self, tmp_path: Path):
        (tmp_path / "kitt.yml").write_text(
            "learnings:\n  embeddings:\n    provider: bedrock\n",
            encoding="utf-8",
        )
        assert resolve_provider_name(tmp_path) == "bedrock"
        assert isinstance(get_active_provider(tmp_path), BedrockTitanProvider)

    def test_env_overrides_kitt_yml(self, tmp_path: Path, monkeypatch):
        (tmp_path / "kitt.yml").write_text(
            "learnings:\n  embeddings:\n    provider: bedrock\n",
            encoding="utf-8",
        )
        monkeypatch.setenv(PROVIDER_ENV_VAR, "local")
        assert resolve_provider_name(tmp_path) == "local"

    def test_none_disables_the_provider(self, monkeypatch):
        monkeypatch.setenv(PROVIDER_ENV_VAR, "none")
        assert resolve_provider_name(None) == "none"
        assert get_active_provider(None) is None

    def test_kitt_yml_none_disables_without_env(self, tmp_path: Path):
        (tmp_path / "kitt.yml").write_text(
            "learnings:\n  embeddings:\n    provider: none\n",
            encoding="utf-8",
        )
        assert get_active_provider(tmp_path) is None

    def test_unknown_env_value_falls_through_with_warning(
        self, monkeypatch, caplog: pytest.LogCaptureFixture
    ):
        monkeypatch.setenv(PROVIDER_ENV_VAR, "gpu-cluster-9000")
        with caplog.at_level("WARNING", logger="kitt"):
            assert resolve_provider_name(None) == "local"
        assert any("not a known embedding provider" in r.message for r in caplog.records)

    def test_unknown_yml_value_falls_through_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        (tmp_path / "kitt.yml").write_text(
            "learnings:\n  embeddings:\n    provider: whatever\n",
            encoding="utf-8",
        )
        with caplog.at_level("WARNING", logger="kitt"):
            assert resolve_provider_name(tmp_path) == "local"
        assert any("not a known provider" in r.message for r in caplog.records)

    def test_malformed_learnings_section_falls_through(self, tmp_path: Path):
        # ``learnings: just-a-string`` must not crash the resolver.
        (tmp_path / "kitt.yml").write_text(
            "learnings: nonsense\n", encoding="utf-8"
        )
        assert resolve_provider_name(tmp_path) == "local"

    def test_provider_instances_are_cached_per_name(self):
        first = get_active_provider(None)
        second = get_active_provider(None)
        assert first is second

    def test_provider_names_are_qualified_and_distinct(self):
        assert LOCAL_PROVIDER_NAME.startswith("local:")
        assert BEDROCK_PROVIDER_NAME.startswith("bedrock:")
        assert LocalFastembedProvider.name != BedrockTitanProvider.name
        assert LocalFastembedProvider.dimensions == 384
        assert BedrockTitanProvider.dimensions == 1024


# -----------------------------------------------------------------------------
# Bedrock provider, boto3 fully mocked
# -----------------------------------------------------------------------------


class _FakeBoto3:
    """Just enough of boto3's surface for the provider's two call sites."""

    def __init__(self, *, credentials: object = "creds", region: str | None = "us-east-1",
                 client: object = None):
        self._credentials = credentials
        self._region = region
        self._client = client
        self.client_calls: list[str] = []
        outer = self

        class _Session:
            def get_credentials(self):
                return outer._credentials

            @property
            def region_name(self):
                return outer._region

        class _SessionModule:
            Session = _Session

        self.session = _SessionModule()

    def client(self, service_name: str):
        self.client_calls.append(service_name)
        return self._client


class _FakeBedrockClient:
    """Records every invoke_model call; returns a fixed embedding."""

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions
        self.calls: list[dict] = []

    def invoke_model(self, *, modelId: str, body: str):
        self.calls.append({"modelId": modelId, "body": json.loads(body)})

        class _Body:
            def __init__(self, payload: bytes):
                self._payload = payload

            def read(self):
                return self._payload

        embedding = [0.5] * self.dimensions
        return {"body": _Body(json.dumps({"embedding": embedding}).encode("utf-8"))}


class TestBedrockTitanProvider:
    def test_unavailable_without_boto3(self, monkeypatch):
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: None)
        assert BedrockTitanProvider().available() is False

    def test_unavailable_without_credentials(self, monkeypatch):
        fake = _FakeBoto3(credentials=None)
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        assert BedrockTitanProvider().available() is False

    def test_unavailable_without_region(self, monkeypatch):
        fake = _FakeBoto3(region=None)
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        monkeypatch.delenv("AWS_REGION", raising=False)
        assert BedrockTitanProvider().available() is False

    def test_available_with_credentials_and_region(self, monkeypatch):
        fake = _FakeBoto3()
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        provider = BedrockTitanProvider()
        assert provider.available() is True
        # The probe is local-only: no client was ever constructed.
        assert fake.client_calls == []

    def test_embed_loops_invoke_model_per_text(self, monkeypatch):
        client = _FakeBedrockClient()
        fake = _FakeBoto3(client=client)
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        provider = BedrockTitanProvider()
        result = provider.embed(["first text", "second text"])
        assert result is not None
        assert result.shape == (2, 1024)
        assert result.dtype == numpy.float32
        # Titan V2 embeds one text per call; the batch loops.
        assert len(client.calls) == 2
        assert client.calls[0]["modelId"] == BEDROCK_MODEL_ID
        assert client.calls[0]["body"] == {"inputText": "first text", "dimensions": 1024}
        assert client.calls[1]["body"] == {"inputText": "second text", "dimensions": 1024}

    def test_embed_returns_none_on_wrong_dimension_response(
        self, monkeypatch, caplog: pytest.LogCaptureFixture
    ):
        client = _FakeBedrockClient(dimensions=256)  # AWS-side surprise
        fake = _FakeBoto3(client=client)
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        provider = BedrockTitanProvider()
        with caplog.at_level("WARNING", logger="kitt"):
            assert provider.embed(["text"]) is None
        assert any("expected 1024" in r.message for r in caplog.records)

    def test_embed_returns_none_on_invoke_failure(
        self, monkeypatch, caplog: pytest.LogCaptureFixture
    ):
        class _RaisingClient:
            def invoke_model(self, **_kwargs):
                raise RuntimeError("simulated throttling")

        fake = _FakeBoto3(client=_RaisingClient())
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        provider = BedrockTitanProvider()
        with caplog.at_level("WARNING", logger="kitt"):
            assert provider.embed(["text"]) is None
        assert any("invoke_model failed" in r.message for r in caplog.records)

    def test_missing_boto3_at_embed_time_is_sticky(self, monkeypatch):
        load_calls = {"n": 0}

        def _counting_load():
            load_calls["n"] += 1
            return None

        monkeypatch.setattr(_embedding_providers, "_load_boto3", _counting_load)
        provider = BedrockTitanProvider()
        assert provider.embed(["a"]) is None
        assert provider.embed(["b"]) is None
        # The import is attempted once; the sticky flag short-circuits
        # subsequent calls (and flips available() to False).
        assert load_calls["n"] == 1
        assert provider.available() is False

    def test_empty_input_returns_none_without_client(self, monkeypatch):
        fake = _FakeBoto3(client=_FakeBedrockClient())
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: fake)
        provider = BedrockTitanProvider()
        assert provider.embed([]) is None
        assert fake.client_calls == []


# -----------------------------------------------------------------------------
# End-to-end degradation through learnings_search
# -----------------------------------------------------------------------------


def _make_entry(stack: str = "fastapi") -> str:
    return (
        "## LRN-2026-05-13-a: Sample lesson\n"
        "\n"
        "```meta\n"
        "date: 2026-05-13\n"
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


@pytest.fixture
def search_workspace(tmp_path: Path, monkeypatch):
    """Workspace + isolated KITT_HOME, mirroring test_embeddings.py."""
    from kitt.config import ServerConfig
    from kitt.context import ServerContext

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "kitt.yml").write_text("project:\n  slug: test\n", encoding="utf-8")
    home = tmp_path / "kitt-home"
    home.mkdir()
    monkeypatch.setenv("KITT_HOME", str(home))
    ServerContext.reset()
    ctx = ServerContext.init(ServerConfig(cli_type="claude"))
    ctx.workspace = workspace
    yield workspace
    ServerContext.reset()


class TestSearchDegradation:
    async def test_bedrock_without_boto3_degrades_to_deterministic(
        self, search_workspace: Path, monkeypatch
    ):
        """The operator selected bedrock on a box with no boto3 and no
        credentials: no crash, no AWS call, deterministic results, no
        sidecar."""
        monkeypatch.setenv(PROVIDER_ENV_VAR, "bedrock")
        monkeypatch.setattr(_embedding_providers, "_load_boto3", lambda: None)
        (search_workspace / "LEARNINGS.md").write_text(
            _make_entry(stack="fastapi"), encoding="utf-8"
        )
        result = await learnings.learnings_search(
            req_id="",
            stack_tags=["fastapi"],
            req_summary="how do I handle exceptions in async services?",
        )
        # Deterministic floor still returns the stack-matched entry.
        assert "Sample lesson" in result
        # The semantic path never ran: no sidecar was built.
        assert not (search_workspace / EMBEDDINGS_SIDECAR_FILENAME).exists()

    async def test_provider_none_disables_semantic_path(
        self, search_workspace: Path, monkeypatch
    ):
        monkeypatch.setenv(PROVIDER_ENV_VAR, "none")
        (search_workspace / "LEARNINGS.md").write_text(
            _make_entry(stack="fastapi"), encoding="utf-8"
        )
        result = await learnings.learnings_search(
            req_id="",
            stack_tags=["fastapi"],
            req_summary="a summary that would otherwise trigger the semantic path",
        )
        assert "Sample lesson" in result
        assert not (search_workspace / EMBEDDINGS_SIDECAR_FILENAME).exists()

    async def test_append_learnings_skips_sidecar_when_provider_none(
        self, search_workspace: Path, monkeypatch
    ):
        monkeypatch.setenv(PROVIDER_ENV_VAR, "none")
        result = await learnings.append_learnings(
            str(search_workspace), entry_markdown=_make_entry()
        )
        assert result.startswith("Appended")
        assert not (search_workspace / EMBEDDINGS_SIDECAR_FILENAME).exists()

    def test_server_module_imports_cleanly_with_bedrock_selected(
        self, monkeypatch
    ):
        """Selecting bedrock must never break server startup: boto3 is
        soft-imported and only touched from inside an embed call."""
        monkeypatch.setenv(PROVIDER_ENV_VAR, "bedrock")
        from kitt.server import create_app

        app = create_app()
        assert app is not None
