# FastAPI Service Patterns

Patterns for building FastAPI services, especially AI-backed services.

Reference: [FastAPI Documentation](https://fastapi.tiangolo.com/), [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)

## Project Structure

```
src/myservice/
    __init__.py
    main.py              # FastAPI app factory, lifespan
    config.py            # Settings via BaseSettings
    dependencies.py      # Shared Depends() providers
    routers/
        __init__.py
        health.py        # /health, /ready
        documents.py     # Domain routes
        search.py        # Domain routes
    models/
        __init__.py
        requests.py      # Pydantic request models
        responses.py     # Pydantic response models
    services/
        __init__.py
        document_service.py
        embedding_service.py
    exceptions.py        # Custom exception classes + handlers
```

## Application Factory and Lifespan

Use the lifespan context manager for startup/shutdown. Do NOT use the deprecated `@app.on_event("startup")`.

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from .config import Settings
from .routers import health, documents, search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up application resources."""
    # Startup: initialize clients, connections, caches
    settings = Settings()
    app.state.settings = settings
    # Initialize your AI clients, DB pools, etc. here
    yield
    # Shutdown: close connections, flush buffers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Document Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
    return app


app = create_app()
```

## Routers

Use `APIRouter` for modular route organization. One router per domain concept.

```python
from fastapi import APIRouter, Depends, HTTPException

from ..models.requests import SearchRequest
from ..models.responses import SearchResponse
from ..services.search_service import SearchService
from ..dependencies import get_search_service

router = APIRouter()


@router.post("/", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """Search documents using semantic similarity."""
    results = await service.search(request.query, request.top_k)
    return SearchResponse(results=results)
```

## Pydantic v2 Models

Use Pydantic v2 models for ALL request and response data. Not dicts. Not dataclasses for API boundaries.

```python
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request with query and optional filters."""
    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=10, ge=1, le=100)
    namespace: str | None = None
    filters: dict[str, str] | None = None


class SearchResult(BaseModel):
    """A single search result."""
    document_id: str
    score: float
    text: str
    metadata: dict[str, str]


class SearchResponse(BaseModel):
    """Search response with results."""
    results: list[SearchResult]
    query: str
    total: int
```

**Never:**
- Return raw dicts from endpoints
- Use `Any` in response models
- Skip validation on request bodies

## Configuration with BaseSettings

Use Pydantic `BaseSettings` for configuration. It reads from environment variables automatically.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Service config
    app_name: str = "document-service"
    debug: bool = False

    # AWS Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "global.anthropic.claude-sonnet-4-6-v1"

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index_name: str = "documents"

    # Vertex AI (alternative to Bedrock)
    gcp_project_id: str = ""
    gcp_region: str = "us-east1"
```

**Never:**
- Hardcode API keys, secrets, or credentials in source code
- Read `os.environ` directly (use `BaseSettings`)
- Commit `.env` files to version control

## Dependency Injection

Use `Depends()` for shared resources. This is FastAPI's version of DI.

```python
from functools import lru_cache

from fastapi import Depends, Request

from .config import Settings


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


async def get_search_service(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SearchService:
    """Provide a SearchService instance."""
    return SearchService(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index_name,
    )
```

## Async Endpoints

Use `async def` for endpoints that perform I/O (LLM calls, database queries, HTTP requests). Use plain `def` for CPU-bound or trivial endpoints.

```python
# CORRECT: async for I/O-bound work
@router.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    response = await client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": request.message}],
    )
    return ChatResponse(text=response.content[0].text)


# CORRECT: sync for trivial operations
@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
```

**Never:**
- Use synchronous SDK clients inside `async def` endpoints (this blocks the event loop)
- Use `asyncio.run()` inside an async endpoint (you are already in an event loop)
- Mix sync and async carelessly

## Error Handling

Use `HTTPException` for expected errors. Use custom exception handlers for domain exceptions.

```python
# exceptions.py
from fastapi import Request
from fastapi.responses import JSONResponse


class ServiceError(Exception):
    """Base exception for service-layer errors."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFoundError(ServiceError):
    def __init__(self, document_id: str):
        super().__init__(f"Document not found: {document_id}", status_code=404)


class RateLimitExceededError(ServiceError):
    def __init__(self):
        super().__init__("Rate limit exceeded, try again later", status_code=429)


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )
```

Register the handler in the app factory:

```python
app.add_exception_handler(ServiceError, service_error_handler)
```

## Middleware

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Health Endpoints

Every service needs health and readiness endpoints.

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns 200 if the process is running."""
    return {"status": "healthy"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness probe. Returns 200 if all dependencies are reachable."""
    # Check database, Pinecone, etc.
    return {"status": "ready"}
```

## Background Tasks

Use `BackgroundTasks` for fire-and-forget work (logging, analytics, cache warming).

```python
from fastapi import BackgroundTasks


async def log_search_analytics(query: str, results_count: int) -> None:
    """Log search analytics asynchronously."""
    # Write to analytics store
    ...


@router.post("/search")
async def search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    results = await service.search(request.query, request.top_k)
    background_tasks.add_task(log_search_analytics, request.query, len(results))
    return SearchResponse(results=results, query=request.query, total=len(results))
```

## Things to Avoid

| Bad Pattern | Correct Pattern | Why |
|------------|----------------|-----|
| `@app.on_event("startup")` | Lifespan context manager | `on_event` is deprecated |
| Raw dicts as responses | Pydantic response models | No validation, no docs |
| `os.environ["KEY"]` | `BaseSettings` | Centralized, validated config |
| Sync SDK in `async def` | Async SDK client | Blocks the event loop |
| Business logic in routes | Service layer | Routes should only translate HTTP |
| Catching all exceptions | Specific exception handlers | Hides real bugs |
