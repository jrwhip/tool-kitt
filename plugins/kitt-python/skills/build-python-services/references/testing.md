# Testing Python Applications

pytest-based testing for synchronous and asynchronous Python code.

Reference: [pytest Documentation](https://docs.pytest.org/en/stable/), [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/en/latest/)

## Test Framework Stack

- **pytest**: Test runner and assertion framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **unittest.mock**: Mocking (built into Python, no extra install)
- **httpx**: Async HTTP client for FastAPI testing

Install as dev dependencies:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",
]
```

## Test File Organization

```
tests/
    __init__.py
    conftest.py              # Shared fixtures
    test_cli.py              # Tests for CLI module
    test_config.py           # Tests for config module
    services/
        __init__.py
        conftest.py          # Service-specific fixtures
        test_document_service.py
        test_embedding_service.py
    routers/
        __init__.py
        test_health.py
        test_search.py
```

- Test files: `test_*.py` (prefix, not suffix; pytest finds them by default)
- Test functions: `test_<what>_<scenario>_<expected>`
- One test file per source module

## Test Naming

Follow the pattern: `test_<what>_<scenario>_<expected_result>`

```python
def test_chunk_text_short_input_returns_single_chunk():
    ...

def test_chunk_text_long_input_returns_overlapping_chunks():
    ...

def test_search_no_results_returns_empty_list():
    ...

def test_create_document_missing_content_raises_validation_error():
    ...
```

The name should tell you exactly what the test verifies without reading the body.

## Basic Test Structure

```python
def test_chunk_text_basic_splitting():
    """Chunks are created at the correct size with overlap."""
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=200)

    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
```

Use plain `assert` statements. pytest rewrites them to give detailed failure messages. No need for `assertEqual`, `assertTrue`, or any assertion library.

## Fixtures

Use `@pytest.fixture` for setup/teardown. Use `conftest.py` for fixtures shared across test files.

```python
# conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from myservice.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Test settings with safe defaults."""
    return Settings(
        aws_region="us-east-1",
        pinecone_api_key="test-key",
        pinecone_index_name="test-index",
        debug=True,
    )


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Mock Anthropic client that returns a canned response."""
    from anthropic import Anthropic

    client = MagicMock(spec=Anthropic)
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Test response", type="text")]
    mock_message.usage.input_tokens = 10
    mock_message.usage.output_tokens = 20
    client.messages.create.return_value = mock_message
    return client


@pytest.fixture
def mock_async_anthropic_client() -> AsyncMock:
    """Mock async Anthropic client."""
    from anthropic import AsyncAnthropic

    client = AsyncMock(spec=AsyncAnthropic)
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Test response", type="text")]
    client.messages.create.return_value = mock_message
    return client
```

### Fixture Scopes

```python
@pytest.fixture(scope="session")
def expensive_resource():
    """Created once for the entire test session."""
    return load_large_dataset()


@pytest.fixture(scope="module")
def db_connection():
    """Created once per test module."""
    conn = create_connection()
    yield conn
    conn.close()


@pytest.fixture  # scope="function" is the default
def fresh_state():
    """Created fresh for every test."""
    return {}
```

Use `yield` in fixtures to provide teardown logic. Code after `yield` runs after the test completes.

## Parametrize

Use `@pytest.mark.parametrize` for data-driven tests.

```python
import pytest


@pytest.mark.parametrize(
    "input_text, chunk_size, expected_count",
    [
        ("short", 1000, 1),
        ("a" * 2000, 1000, 2),
        ("a" * 3000, 1000, 3),
        ("", 1000, 0),
    ],
)
def test_chunk_text_various_lengths(
    input_text: str, chunk_size: int, expected_count: int
) -> None:
    chunks = chunk_text(input_text, chunk_size=chunk_size, overlap=0)
    assert len(chunks) == expected_count
```

## Async Testing

Use `pytest-asyncio` for testing async code.

Configure in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

With `asyncio_mode = "auto"`, any `async def test_...` function is automatically treated as an async test. No need for `@pytest.mark.asyncio` on every test.

```python
async def test_search_returns_results(
    mock_async_anthropic_client: AsyncMock,
) -> None:
    service = SearchService(client=mock_async_anthropic_client)
    results = await service.search("test query", top_k=5)
    assert len(results) > 0


async def test_generate_answer_uses_context() -> None:
    client = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="The answer is 42.")]
    client.messages.create.return_value = mock_message

    answer = await generate_answer(
        query="What is the answer?",
        context_chunks=[{"text": "The answer is 42.", "score": 0.95, "source": "guide.txt"}],
        client=client,
    )

    assert "42" in answer
    # Verify the context was included in the prompt
    call_args = client.messages.create.call_args
    assert "The answer is 42." in str(call_args)
```

## Mocking

Use `unittest.mock`. Mock at the boundary (the SDK client), not the HTTP layer.

### MagicMock for Sync Code

```python
from unittest.mock import MagicMock, patch


def test_document_service_processes_file(tmp_path):
    """Test that the service reads and chunks a document."""
    # Create a test file
    doc = tmp_path / "test.txt"
    doc.write_text("a" * 2000)

    mock_index = MagicMock()
    service = DocumentService(index=mock_index)
    service.ingest(doc)

    # Verify upsert was called
    mock_index.upsert.assert_called_once()
    vectors = mock_index.upsert.call_args.kwargs["vectors"]
    assert len(vectors) > 0
```

### AsyncMock for Async Code

```python
from unittest.mock import AsyncMock, MagicMock


async def test_chat_endpoint_returns_response(mock_async_anthropic_client):
    service = ChatService(client=mock_async_anthropic_client)
    response = await service.chat("Hello")
    assert response == "Test response"
    mock_async_anthropic_client.messages.create.assert_called_once()
```

### patch for Replacing Dependencies

```python
from unittest.mock import patch


def test_settings_loaded_from_env():
    with patch.dict("os.environ", {"AWS_REGION": "us-west-2", "DEBUG": "true"}):
        settings = Settings()
        assert settings.aws_region == "us-west-2"
        assert settings.debug is True
```

## FastAPI Testing

### Sync Tests with TestClient

```python
from fastapi.testclient import TestClient

from myservice.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

### Async Tests with httpx

For testing async endpoints properly:

```python
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from myservice.main import create_app
from myservice.dependencies import get_search_service


async def test_search_endpoint_returns_results():
    mock_service = AsyncMock()
    mock_service.search.return_value = [
        {"document_id": "doc-1", "score": 0.95, "text": "Result text", "metadata": {}},
    ]

    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: mock_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/search/",
            json={"query": "test query", "top_k": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
```

Use `app.dependency_overrides` to inject mock services in tests.

## Coverage

Run tests with coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

Configuration in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
show_missing = true
fail_under = 80
```

## Test Markers

Use markers for selective test running:

```python
import pytest


@pytest.mark.slow
def test_full_pipeline_integration():
    """Takes a long time, skip in quick CI runs."""
    ...


@pytest.mark.integration
def test_pinecone_connection():
    """Requires a live Pinecone instance."""
    ...
```

Register markers in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests that need external services",
]
```

Run selectively:

```bash
# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m integration
```

## Environment Variables in Tests

Use fixtures to set environment variables. Never read real secrets in tests.

```python
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure no real credentials leak into tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
```

The `monkeypatch` fixture is built into pytest. It automatically restores the original state after each test.

## tmp_path for File Tests

Use the built-in `tmp_path` fixture for tests that need to read/write files:

```python
def test_load_documents_reads_txt_files(tmp_path):
    (tmp_path / "doc1.txt").write_text("Hello world")
    (tmp_path / "doc2.txt").write_text("Goodbye world")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")

    docs = load_documents(tmp_path)
    assert len(docs) == 2  # Only .txt files
```

## What NOT to Do

| Bad Pattern | Correct Pattern | Why |
|------------|----------------|-----|
| `unittest.TestCase` classes | Plain `test_` functions | pytest does not need classes |
| `self.assertEqual(a, b)` | `assert a == b` | pytest rewrites asserts for better messages |
| `print()` in tests | `capfd` fixture or `logging` | Captured output is noise |
| `time.sleep()` in tests | Mock the thing you are waiting for | Sleep makes tests slow and flaky |
| `@SpringBootTest` equivalent (loading everything) | Mock dependencies, test in isolation | Fast, focused tests |
| Mocking HTTP responses | Mock the SDK client (`MagicMock(spec=Anthropic)`) | Test your code, not the HTTP library |
| Sharing mutable state between tests | Fresh fixtures per test | Test isolation prevents flaky tests |
| Reading real API keys in tests | `monkeypatch` to set fake values | Tests must work offline |
| `@pytest.mark.asyncio` on every test | `asyncio_mode = "auto"` in config | Less boilerplate |
