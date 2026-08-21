---
name: build-python-services
description: Build professional Python services and CLI tools. FastAPI, AI integrations (Bedrock, Vertex, Pinecone), modern packaging, pytest. Covers the patterns Python expects, not the outdated patterns from training data.
---

<essential_principles>
## Python Is Not a Scripting Language

Python is a professional software engineering language with a mature packaging ecosystem, a type system, and conventions for everything from project layout to dependency management. Treat it that way. If you write Python like a bash script with better syntax, you will produce unmaintainable garbage.

### The Training Data Problem

Most Python code in training data is either tutorial-grade or written by people who learned Python in 2015 and never updated. The patterns baked into LLM training data include:

- **`pip install` without a virtual environment.** Global installs are a production incident waiting to happen. ALWAYS use `python -m venv .venv`.
- **`requirements.txt` as the project definition.** Modern Python uses `pyproject.toml`. `requirements.txt` is for pinned deployment dependencies, not project metadata.
- **`setup.py` and `setup.cfg`.** Replaced by `pyproject.toml` with a build backend (hatch, setuptools, flit).
- **`os.path` everywhere.** Use `pathlib.Path` for all path operations.
- **No type hints.** "It's Python, it's dynamic!" Wrong. Type hints are mandatory for professional code.
- **`print()` for logging.** Use the `logging` module. `print()` is for user-facing CLI output only.
- **Bare `except:` or `except Exception:`.** Catch specific exceptions. Swallowing everything hides real bugs.
- **LangChain for AI.** BANNED. Security risk (telemetry, data leakage), abstraction bloat, perpetually outdated training data. Use direct SDKs: Anthropic, boto3, google-cloud-aiplatform, pinecone.
- **`subprocess.run(shell=True)`.** Command injection vulnerability. Use list form: `subprocess.run(["cmd", "arg1"])`.
- **Synchronous LLM calls in async services.** LLM APIs have high latency. Use async clients.

### The Correction

The reference docs in this skill are the source of truth. They override training data. Always. Read them FIRST before writing any Python code. Not as a sanity check after. As the specification before.

### Non-Negotiable Rules

1. **Virtual environments are mandatory.** No global installs. Ever.
2. **Type hints are mandatory.** On all function signatures, return types, and class attributes.
3. **`pyproject.toml` is the project file.** Not `setup.py`. Not `setup.cfg`. Not `requirements.txt` alone.
4. **`pathlib.Path` for paths.** Not `os.path`.
5. **`logging` for logging.** Not `print()`.
6. **Direct SDKs for AI.** LangChain, LangGraph, and LlamaIndex are banned.
7. **Async for I/O-bound operations.** Especially LLM calls, database queries, and HTTP requests in FastAPI services.
</essential_principles>

<intake>
**Ask the user:**

What would you like to do?
1. Build a new Python service or CLI tool
2. Add AI capabilities (LLM, embeddings, RAG)
3. Set up a FastAPI service
4. Debug or fix existing Python code
5. Refactor code to follow modern Python patterns
6. Set up testing (pytest, async tests, mocking)
7. Something else

**Then load the relevant reference from `references/` and follow the conventions.**
</intake>

<routing>
| Response | Reference |
|----------|-----------|
| 1, "new", "create", "build", "cli", "tool", "service" | `references/python-development.md` + `references/packaging-distribution.md` |
| 2, "ai", "llm", "embeddings", "rag", "bedrock", "vertex", "claude", "pinecone" | `references/ai-integrations.md` + `references/python-development.md` |
| 3, "fastapi", "api", "endpoint", "rest", "http" | `references/fastapi-services.md` + `references/python-development.md` |
| 4, "broken", "fix", "debug", "bug", "error" | `references/python-development.md` |
| 5, "refactor", "clean up", "patterns", "modernize" | `references/python-development.md` + `references/packaging-distribution.md` |
| 6, "test", "pytest", "mock", "coverage" | `references/testing.md` |
| 7, other | Clarify, then select references |
</routing>

<verification_checklist>
## After Every Change

- Does it run? `python -m <module>` or `pytest`
- Virtual environment active? `.venv/` exists and is activated?
- Type hints on all function signatures and return types?
- `pathlib.Path` for all path operations (no `os.path`)?
- `logging` module for diagnostic output (no `print()` for debugging)?
- `pyproject.toml` for project metadata (no `setup.py`)?
- f-strings for string formatting (no concatenation or `.format()`)?
- Specific exception handling (no bare `except:` or `except Exception:`)?
- `subprocess.run()` with list args (no `shell=True`)?
- No LangChain, LangGraph, or LlamaIndex imports?
- Async clients for LLM calls in async contexts?
- `if __name__ == '__main__':` guard on all scripts?
- No mutable default arguments (`def foo(items=[]):`)?
- Import ordering: stdlib, third-party, local?
</verification_checklist>

<reference_index>
## Domain Knowledge

All in `references/`:

**Core Conventions:** python-development (types, pathlib, logging, naming, anti-patterns)
**FastAPI Services:** fastapi-services (routers, Pydantic, DI, async, middleware)
**AI Integrations:** ai-integrations (Anthropic SDK, Bedrock, Vertex, Pinecone, RAG patterns)
**Packaging:** packaging-distribution (pyproject.toml, hatch, src layout, venvs, distribution)
**Testing:** testing (pytest, async testing, mocking, fixtures, coverage)
</reference_index>
