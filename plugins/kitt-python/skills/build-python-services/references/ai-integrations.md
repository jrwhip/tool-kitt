# AI Integrations

Direct SDK patterns for AI services. No frameworks. No abstractions. Just the SDKs.

Reference: [Anthropic Python SDK](https://docs.anthropic.com/en/api/client-sdks), [AWS Bedrock](https://docs.aws.amazon.com/bedrock/), [Google Vertex AI](https://cloud.google.com/vertex-ai/docs), [Pinecone Python SDK](https://docs.pinecone.io/reference/python-sdk)

## BANNED: LangChain, LangGraph, LlamaIndex

These are banned. Not discouraged. Banned. Reasons:

1. **Security risk.** LangChain sends telemetry by default. In a government shop, any data leakage is a compliance violation.
2. **Abstraction bloat.** LangChain wraps SDKs that are already simple. You add a dependency that changes its API every month for no benefit.
3. **Training data is perpetually wrong.** LangChain's API changes so frequently that LLM training data is always outdated. The code generated will not work.
4. **Debugging is hell.** When something breaks in a five-layer abstraction, you debug the abstraction instead of the actual problem.

The Anthropic SDK, boto3, google-genai, and pinecone are all you need. They are well-documented, stable, and simple.

---

## Anthropic Claude SDK

### Installation

```bash
# Base SDK (direct API)
pip install anthropic

# For AWS Bedrock
pip install "anthropic[bedrock]"

# For Google Vertex AI
pip install "anthropic[vertex]"
```

### Direct API Usage

```python
from anthropic import Anthropic

client = Anthropic()  # Uses ANTHROPIC_API_KEY env var

message = client.messages.create(
    model="claude-sonnet-4-6-20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Explain quantum computing in one paragraph."}
    ],
)
print(message.content[0].text)
```

### AWS Bedrock

For government/enterprise deployments. Traffic stays within your AWS account.

```python
from anthropic import AnthropicBedrock

# Uses AWS credentials from environment/IAM role
client = AnthropicBedrock(aws_region="us-east-1")

message = client.messages.create(
    model="us.anthropic.claude-sonnet-4-6-v1",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Summarize this document."}
    ],
)
```

Bedrock model ID format: `us.anthropic.claude-sonnet-4-6-v1`, `us.anthropic.claude-haiku-4-5-v1`. The prefix (`us.`, `eu.`, etc.) indicates the inference profile region. Check the Bedrock console for available models in your region.

### Google Vertex AI

Alternative to Bedrock for GCP-based deployments.

```python
from anthropic import AnthropicVertex

client = AnthropicVertex(
    project_id="your-gcp-project-id",
    region="us-east5",
)

message = client.messages.create(
    model="claude-sonnet-4-6@20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Summarize this document."}
    ],
)
```

Vertex model ID format: `claude-sonnet-4-6@20250514`, `claude-haiku-4-5@20251022`. The date suffix is the model version.

**Important deprecation:** The `vertexai` SDK's generative model modules were deprecated in June 2025 and will be removed in June 2026. For Google models, use the Google Gen AI SDK (`google-genai`). For Claude on Vertex, continue using `anthropic[vertex]`.

### Async Clients

Use async clients in FastAPI services and any async context. LLM calls have high latency; blocking the event loop is unacceptable.

```python
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex

# Direct API
client = AsyncAnthropic()

# Bedrock
client = AsyncAnthropicBedrock(aws_region="us-east-1")

# Vertex
client = AsyncAnthropicVertex(project_id="...", region="us-east5")

# Usage (identical API, just await the calls)
message = await client.messages.create(
    model="claude-sonnet-4-6-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

### Streaming

Use streaming for long responses to reduce time-to-first-token.

```python
with client.messages.stream(
    model="claude-sonnet-4-6-20250514",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

Async streaming:

```python
async with client.messages.stream(
    model="claude-sonnet-4-6-20250514",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}],
) as stream:
    async for text in stream.text_stream:
        yield text  # In a FastAPI StreamingResponse
```

### Tool Use

Define tools as dicts, handle `tool_use` content blocks, return `tool_result`.

```python
tools = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City and state"},
            },
            "required": ["location"],
        },
    }
]

message = client.messages.create(
    model="claude-sonnet-4-6-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Boston?"}],
)

# Check if the model wants to use a tool
for block in message.content:
    if block.type == "tool_use":
        tool_name = block.name
        tool_input = block.input
        # Execute the tool and return the result
        result = execute_tool(tool_name, tool_input)

        # Send the tool result back
        followup = client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1024,
            tools=tools,
            messages=[
                {"role": "user", "content": "What's the weather in Boston?"},
                {"role": "assistant", "content": message.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    ],
                },
            ],
        )
```

### Error Handling

```python
import anthropic

try:
    message = client.messages.create(...)
except anthropic.RateLimitError:
    # Back off and retry
    logger.warning("Rate limited, retrying after backoff")
except anthropic.APIConnectionError:
    # Network issue
    logger.error("Cannot reach Anthropic API")
except anthropic.APIStatusError as e:
    # Other API error (400, 401, 500, etc.)
    logger.error("API error %d: %s", e.status_code, e.message)
```

The SDK has built-in retry with exponential backoff for transient errors. You can configure it:

```python
client = Anthropic(max_retries=3)  # Default is 2
```

### Token Counting

Estimate token usage before sending large payloads:

```python
token_count = client.messages.count_tokens(
    model="claude-sonnet-4-6-20250514",
    messages=[{"role": "user", "content": large_document}],
)
logger.info("Estimated tokens: %d", token_count.input_tokens)
```

### Current Models (2026)

| Model | ID (Direct/Bedrock) | ID (Vertex) | Best For |
|-------|-------------------|-------------|----------|
| Claude Opus 4.6 | `claude-opus-4-6-20250918` | `claude-opus-4-6@20250918` | Complex reasoning, analysis |
| Claude Sonnet 4.6 | `claude-sonnet-4-6-20250514` | `claude-sonnet-4-6@20250514` | General purpose, best value |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251022` | `claude-haiku-4-5@20251022` | Fast, lightweight tasks |

---

## Pinecone

### Installation

```bash
# Standard
pip install pinecone

# With gRPC for better performance
pip install "pinecone[grpc]"

# With async support
pip install "pinecone[asyncio]"
```

**Note:** The package name is `pinecone`, NOT `pinecone-client`. The package was renamed in v5.1.0. Python 3.10+ is required.

### Basic Usage

```python
from pinecone import Pinecone

pc = Pinecone(api_key="your-api-key")  # Or use PINECONE_API_KEY env var

# Connect to an existing index
index = pc.Index("my-index")

# Upsert vectors
index.upsert(
    vectors=[
        ("doc-1", [0.1, 0.2, 0.3, ...], {"source": "manual.pdf", "page": 1}),
        ("doc-2", [0.4, 0.5, 0.6, ...], {"source": "manual.pdf", "page": 2}),
    ],
    namespace="documents",
)

# Query
results = index.query(
    vector=[0.1, 0.2, 0.3, ...],
    top_k=10,
    include_metadata=True,
    namespace="documents",
    filter={"source": {"$eq": "manual.pdf"}},
)

for match in results.matches:
    print(f"ID: {match.id}, Score: {match.score}")
    print(f"Metadata: {match.metadata}")
```

### Creating an Index

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

pc.create_index(
    name="my-index",
    dimension=1536,  # Match your embedding model's output dimension
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
)
```

### Namespaces

Use namespaces to partition data within an index (multi-tenancy, environment separation).

```python
# Upsert to a specific namespace
index.upsert(vectors=[...], namespace="tenant-abc")

# Query within a namespace
results = index.query(vector=[...], top_k=10, namespace="tenant-abc")
```

### Batch Operations

For bulk ingestion, use batched upserts:

```python
def chunked_upsert(index: Any, vectors: list, namespace: str, batch_size: int = 100) -> None:
    """Upsert vectors in batches."""
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
```

---

## RAG Patterns (Framework-Free)

RAG is simple. It does not require a framework. Here is the entire pattern:

### 1. Document Loading

Read files. That is all "document loading" means.

```python
from pathlib import Path


def load_documents(directory: Path) -> list[dict[str, str]]:
    """Load text documents from a directory."""
    documents = []
    for file_path in directory.rglob("*.txt"):
        content = file_path.read_text(encoding="utf-8")
        documents.append({
            "id": file_path.stem,
            "content": content,
            "source": str(file_path),
        })
    return documents
```

### 2. Chunking

Split text into overlapping chunks. Overlap preserves context at chunk boundaries.

```python
def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks
```

### 3. Embedding

Use the embedding model from your cloud provider or Pinecone's integrated inference.

```python
# Example with Bedrock Titan embeddings (via boto3)
import boto3
import json

bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings from Bedrock Titan."""
    embeddings = []
    for text in texts:
        response = bedrock_runtime.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text}),
        )
        result = json.loads(response["body"].read())
        embeddings.append(result["embedding"])
    return embeddings
```

### 4. Storage

Upsert chunks with metadata into Pinecone.

```python
def store_chunks(
    index: Any,
    chunks: list[str],
    embeddings: list[list[float]],
    source: str,
    namespace: str = "default",
) -> None:
    """Store embedded chunks in Pinecone."""
    vectors = [
        (
            f"{source}-chunk-{i}",
            embedding,
            {"source": source, "chunk_index": i, "text": chunk},
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    # Batch upsert
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        index.upsert(vectors=vectors[i : i + batch_size], namespace=namespace)
```

### 5. Retrieval

Embed the query, search Pinecone, get top-k results.

```python
async def retrieve_context(
    query: str,
    index: Any,
    namespace: str = "default",
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks for a query."""
    query_embedding = get_embeddings([query])[0]
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace,
    )
    return [
        {"text": match.metadata["text"], "score": match.score, "source": match.metadata["source"]}
        for match in results.matches
    ]
```

### 6. Augmentation and Generation

Build a prompt with retrieved context, send to Claude.

```python
async def generate_answer(
    query: str,
    context_chunks: list[dict[str, Any]],
    client: AsyncAnthropicBedrock,
) -> str:
    """Generate an answer using retrieved context."""
    context_text = "\n\n---\n\n".join(chunk["text"] for chunk in context_chunks)

    message = await client.messages.create(
        model="us.anthropic.claude-sonnet-4-6-v1",
        max_tokens=2048,
        system="Answer the question using ONLY the provided context. If the context does not contain the answer, say so.",
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context_text}\n\nQuestion: {query}",
            }
        ],
    )
    return message.content[0].text
```

That is RAG. Six steps. No framework needed.

---

## Security Rules

1. **Never hardcode API keys.** Use environment variables, AWS IAM roles, GCP service accounts, or secret managers.
2. **Never log API keys or tokens.** Redact sensitive values in logs.
3. **Never send PII to external APIs** without explicit authorization. Government data stays on government infrastructure (Bedrock, Vertex).
4. **Always use HTTPS.** The SDKs do this by default. Do not disable TLS verification.
5. **Validate all input** before sending to LLMs. Prompt injection is a real attack vector.

## What NOT to Use

| Banned | Use Instead | Why |
|--------|------------|-----|
| LangChain | Anthropic SDK, boto3, google-genai, pinecone | Security risk, abstraction bloat, outdated training data |
| LangGraph | Direct async orchestration | Unnecessary complexity |
| LlamaIndex | Direct SDK calls + simple Python | Same problems as LangChain |
| FAISS in production | Pinecone | In-memory is not durable or scalable |
| Hardcoded API keys | Environment variables, IAM roles | Security violation |
| `openai` package for Claude | `anthropic` package | Wrong SDK |
