"""Pluggable embedding providers for the semantic-search layer.

:mod:`_embeddings` owns the vector *storage* (the ``.npz`` sidecar
format) and the local fastembed model lifecycle. This module owns the
question "which engine produces the vectors": the operator picks a
provider, and everything downstream (sidecar build, append, query
embedding) goes through the :class:`EmbeddingProvider` protocol.

Providers
---------

- ``local`` (:class:`LocalFastembedProvider`) — the default. Wraps the
  existing fastembed + BAAI/bge-small-en-v1.5 path in
  :mod:`_embeddings`; zero behavior change from the pre-provider code.
- ``bedrock`` (:class:`BedrockTitanProvider`) — Amazon Titan Text
  Embeddings V2 via the AWS Bedrock runtime. boto3 is soft-imported and
  never a hard dependency (``pip install 'wopr[bedrock]'``). Without
  boto3, credentials, or a region, ``available()`` is False and search
  degrades to the deterministic prefilter. No AWS call is ever made
  unless the operator explicitly selected this provider.
- ``none`` — semantic search off; the deterministic prefilter is the
  whole retrieval story. :func:`get_active_provider` returns ``None``.

Selection
---------

Resolution order (first hit wins):

1. Env var ``WOPR_EMBEDDING_PROVIDER`` (``local`` | ``bedrock`` |
   ``none``). Machine-level override; wins everywhere.
2. ``wopr.yml`` key ``learnings.embeddings.provider`` in the workspace
   root that owns the corpus (the directory holding LEARNINGS.md).
3. ``local``.

An unrecognized value in either source is logged at WARNING and treated
as unset, so a typo degrades to the default rather than to a crash or
to silently disabled search.

Sidecar compatibility
---------------------

Each provider stamps its :attr:`~EmbeddingProvider.name` and
:attr:`~EmbeddingProvider.dimensions` into the sidecar metadata. A
sidecar built by one provider is never mixed with vectors from another:
:mod:`_learnings_sidecar` treats a name or dimension mismatch as a
rebuild trigger, so switching providers transparently regenerates the
sidecars from the authoritative markdown corpus.

Every provider still requires the ``embeddings`` extra's numpy for the
sidecar math itself (cosine ranking, ``.npz`` I/O). Since the plugin
bundle ships those deps by default (decided in Phase 1), this is only a
constraint for bespoke minimal installs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from . import _embeddings
from ._safe_load import safe_load_yaml

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger("wopr")

PROVIDER_ENV_VAR = "WOPR_EMBEDDING_PROVIDER"
"""Env override for the provider choice. Values: ``local`` | ``bedrock``
| ``none``. Wins over ``wopr.yml``."""

PROVIDER_LOCAL = "local"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_NONE = "none"
KNOWN_PROVIDERS = frozenset({PROVIDER_LOCAL, PROVIDER_BEDROCK, PROVIDER_NONE})

DEFAULT_PROVIDER = PROVIDER_LOCAL

WOPR_YML_FILENAME = "wopr.yml"

LOCAL_PROVIDER_NAME = f"local:{_embeddings.EMBEDDING_MODEL}"
"""Provider-qualified model name the local provider stamps into sidecar
metadata. Distinct from the bare model string older sidecars carry, so
pre-provider sidecars rebuild once on first use (belt to the
format-version bump's suspenders)."""

BEDROCK_MODEL_ID = "amazon.titan-embed-text-v2:0"
BEDROCK_PROVIDER_NAME = f"bedrock:{BEDROCK_MODEL_ID}"
BEDROCK_DIMENSIONS = 1024
"""Titan V2 supports 256/512/1024 output dimensions; WOPR pins 1024 and
requests it explicitly on every call so the sidecar column count can
never depend on an AWS-side default change."""


class EmbeddingProvider(Protocol):
    """What the sidecar layer needs from an embedding engine.

    ``name`` is stamped into sidecar metadata; a mismatch between a
    sidecar's recorded name and the active provider's forces a rebuild.
    ``dimensions`` pins the vector column count the provider produces.
    ``embed`` returns a ``(len(texts), dimensions)`` float32 matrix, or
    ``None`` on any failure (callers fall back to deterministic-only).
    ``available()`` is a cheap, side-effect-free readiness probe: it
    must never download a model or call a network API.
    """

    name: str
    dimensions: int

    def embed(self, texts: list[str]) -> np.ndarray | None: ...

    def available(self) -> bool: ...


class LocalFastembedProvider:
    """The default provider: fastembed + the pinned local ONNX model.

    Thin adapter over :func:`_embeddings.embed_texts`, which keeps the
    model lifecycle (lazy init, ~130MB first download, sticky failure
    flag) exactly where it always lived. Tests that monkeypatch
    ``_embeddings._TextEmbedding`` therefore keep working unchanged.
    """

    name = LOCAL_PROVIDER_NAME
    dimensions = 384  # bge-small-en-v1.5 output width

    def embed(self, texts: list[str]) -> np.ndarray | None:
        return _embeddings.embed_texts(texts)

    def available(self) -> bool:
        # Optimistic before the first embed call: the extra is installed
        # and no init attempt has failed. The first real embed either
        # confirms this or sets the sticky failure flag, after which the
        # probe answers False for the rest of the process.
        return _embeddings.EMBEDDINGS_AVAILABLE and not _embeddings._embedder_init_failed


def _load_boto3() -> Any:
    """Soft-import boto3. Separate function so tests can monkeypatch it."""
    try:
        import boto3
    except ImportError:
        return None
    return boto3


class BedrockTitanProvider:
    """Amazon Titan Text Embeddings V2 through the Bedrock runtime.

    Titan V2 embeds one text per ``invoke_model`` call, so batches loop.
    The client is lazily created on first embed and cached; a creation
    failure is sticky for the process (same posture as the local
    model's download-failure flag, for the same reason: fail once,
    loudly, and let the deterministic path carry the run).

    Nothing here touches AWS unless the operator selected this
    provider: :func:`get_active_provider` only constructs it on an
    explicit ``bedrock`` choice, ``available()`` inspects local
    configuration only, and ``embed`` is the sole network caller.
    """

    name = BEDROCK_PROVIDER_NAME
    dimensions = BEDROCK_DIMENSIONS

    def __init__(self) -> None:
        self._client: Any = None
        self._client_init_failed = False

    def available(self) -> bool:
        """True when boto3 is importable and a credentialed, regioned
        session can be built. No network call: ``get_credentials`` reads
        the local provider chain (env, config, SSO cache, container
        metadata) without invoking STS.
        """
        if self._client_init_failed:
            return False
        if not _embeddings.EMBEDDINGS_AVAILABLE:
            # numpy is the vector substrate for every provider; without
            # the embeddings extra there is nothing to put vectors in.
            return False
        boto3 = _load_boto3()
        if boto3 is None:
            return False
        try:
            session = boto3.session.Session()
            if session.get_credentials() is None:
                return False
            region = session.region_name or os.environ.get("AWS_REGION")
            return region is not None
        except Exception as e:  # botocore raises assorted config errors
            logger.warning("Bedrock provider availability probe failed (%s).", e)
            return False

    def _get_client(self) -> Any:
        if self._client_init_failed:
            return None
        if self._client is None:
            boto3 = _load_boto3()
            if boto3 is None:
                self._client_init_failed = True
                logger.warning(
                    "Bedrock embedding provider selected but boto3 is not "
                    "installed. Install with: pip install 'wopr[bedrock]'. "
                    "Semantic search disabled for this process; the "
                    "deterministic prefilter still works."
                )
                return None
            try:
                self._client = boto3.client("bedrock-runtime")
            except Exception as e:
                self._client_init_failed = True
                logger.warning(
                    "Cannot create a Bedrock runtime client (%s). Check AWS "
                    "credentials and region. Semantic search disabled for "
                    "this process; the deterministic prefilter still works.",
                    e,
                )
                return None
        return self._client

    def embed(self, texts: list[str]) -> np.ndarray | None:
        if not texts or not _embeddings.EMBEDDINGS_AVAILABLE:
            return None
        client = self._get_client()
        if client is None:
            return None
        np = _embeddings.np
        vectors: list[list[float]] = []
        for text in texts:
            try:
                response = client.invoke_model(
                    modelId=BEDROCK_MODEL_ID,
                    body=json.dumps(
                        {"inputText": text, "dimensions": self.dimensions}
                    ),
                )
                payload = json.loads(response["body"].read())
                embedding = payload["embedding"]
            except Exception as e:
                # boto3 raises service-specific classes built at runtime
                # (ClientError subclasses, throttling, auth) that cannot
                # be enumerated statically. Any failure degrades this
                # call to deterministic-only.
                logger.warning(
                    "Bedrock invoke_model failed (%s); returning None.", e
                )
                return None
            if len(embedding) != self.dimensions:
                logger.warning(
                    "Bedrock returned a %d-dim embedding; expected %d. "
                    "Returning None rather than corrupting the sidecar.",
                    len(embedding),
                    self.dimensions,
                )
                return None
            vectors.append(embedding)
        return np.array(vectors, dtype=np.float32)


def _provider_name_from_env() -> str | None:
    raw = os.environ.get(PROVIDER_ENV_VAR)
    if raw is None or not raw.strip():
        return None
    value = raw.strip().lower()
    if value not in KNOWN_PROVIDERS:
        logger.warning(
            "%s=%r is not a known embedding provider (expected one of: %s); "
            "ignoring the override.",
            PROVIDER_ENV_VAR,
            raw,
            ", ".join(sorted(KNOWN_PROVIDERS)),
        )
        return None
    return value


def _provider_name_from_wopr_yml(config_dir: Path) -> str | None:
    yml_path = config_dir / WOPR_YML_FILENAME
    if not yml_path.is_file():
        return None
    data = safe_load_yaml(yml_path)
    if not isinstance(data, dict):
        return None
    learnings = data.get("learnings")
    if not isinstance(learnings, dict):
        return None
    embeddings_cfg = learnings.get("embeddings")
    if not isinstance(embeddings_cfg, dict):
        return None
    raw = embeddings_cfg.get("provider")
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value not in KNOWN_PROVIDERS:
        logger.warning(
            "%s declares learnings.embeddings.provider=%r, which is not a "
            "known provider (expected one of: %s); using the default.",
            yml_path,
            raw,
            ", ".join(sorted(KNOWN_PROVIDERS)),
        )
        return None
    return value


def resolve_provider_name(config_dir: Path | None = None) -> str:
    """Resolve the configured provider name: env, then wopr.yml, then default.

    ``config_dir`` is the directory whose ``wopr.yml`` speaks for the
    corpus — the workspace root holding LEARNINGS.md. ``None`` skips the
    file lookup (outside-workspace mode).
    """
    from_env = _provider_name_from_env()
    if from_env is not None:
        return from_env
    if config_dir is not None:
        from_yml = _provider_name_from_wopr_yml(config_dir)
        if from_yml is not None:
            return from_yml
    return DEFAULT_PROVIDER


# One instance per provider name per process. Instance-level sticky
# failure flags (the Bedrock client, mirroring the local model's
# module-level flag) only work if the instance survives across calls.
_provider_instances: dict[str, EmbeddingProvider] = {}


def get_active_provider(config_dir: Path | None = None) -> EmbeddingProvider | None:
    """Return the configured provider instance, or ``None`` for ``none``.

    The returned provider may still be unavailable (``available()``
    False); callers decide whether to probe. Selecting ``bedrock``
    never triggers an AWS call here — construction is local.
    """
    name = resolve_provider_name(config_dir)
    if name == PROVIDER_NONE:
        return None
    provider = _provider_instances.get(name)
    if provider is None:
        provider = (
            BedrockTitanProvider()
            if name == PROVIDER_BEDROCK
            else LocalFastembedProvider()
        )
        _provider_instances[name] = provider
    return provider
