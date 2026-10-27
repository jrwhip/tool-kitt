# Python Development Conventions

Core Python patterns and conventions for professional software development.

Reference: [Python 3 Documentation](https://docs.python.org/3/), [PEP 8](https://peps.python.org/pep-0008/), [PEP 484](https://peps.python.org/pep-0484/)

## Python Version

Python 3.10+ minimum. This is the baseline for:
- Structural pattern matching (`match`/`case`)
- Union types with `X | Y` syntax (instead of `Union[X, Y]`)
- `ParamSpec` and `TypeVarTuple` for better generic typing
- Required by the Anthropic SDK, Pinecone SDK, and most modern libraries

## Virtual Environments: MANDATORY

Every project gets its own virtual environment. No exceptions. No global installs.

```bash
# Create
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Install project dependencies
pip install -e ".[dev]"
```

**Never:**
- `sudo pip install` anything
- `pip install` without an active venv
- Share a venv between projects
- Commit the `.venv/` directory

## Type Hints: MANDATORY

Type hints on ALL function signatures, return types, and class attributes. This is not optional.

```python
# CORRECT
def process_document(content: str, max_tokens: int = 1000) -> list[str]:
    """Split document into chunks."""
    chunks: list[str] = []
    # ...
    return chunks


def find_user(user_id: int) -> User | None:
    """Find a user by ID, or return None if not found."""
    # ...


async def embed_text(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    # ...
```

```python
# WRONG: no type hints
def process_document(content, max_tokens=1000):
    chunks = []
    return chunks
```

Use `typing` module for complex types:

```python
from typing import Any, TypeAlias
from collections.abc import Callable, Sequence

# Type aliases for clarity
JsonDict: TypeAlias = dict[str, Any]
Embedding: TypeAlias = list[float]
Handler: TypeAlias = Callable[[str], None]
```

## pathlib.Path for All Path Operations

Use `pathlib.Path` for every path operation. Not `os.path`. Not string concatenation.

```python
# CORRECT
from pathlib import Path

config_dir = Path.home() / ".config" / "myapp"
config_dir.mkdir(parents=True, exist_ok=True)

config_file = config_dir / "settings.yaml"
if config_file.exists():
    content = config_file.read_text(encoding="utf-8")

for py_file in Path("src").rglob("*.py"):
    print(py_file.name)
```

```python
# WRONG: os.path
import os
config_dir = os.path.join(os.path.expanduser("~"), ".config", "myapp")
os.makedirs(config_dir, exist_ok=True)
config_file = os.path.join(config_dir, "settings.yaml")
if os.path.exists(config_file):
    with open(config_file, "r") as f:
        content = f.read()
```

## Logging

Use the `logging` module. `print()` is for user-facing CLI output only.

```python
import logging

logger = logging.getLogger(__name__)

def process_item(item_id: str) -> None:
    logger.info("Processing item %s", item_id)
    try:
        result = do_work(item_id)
        logger.debug("Result: %s", result)
    except ValueError as e:
        logger.error("Failed to process item %s: %s", item_id, e)
        raise
```

Setup at the application entry point only:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
```

**Never:**
- `print()` for diagnostic messages
- `logging.basicConfig()` in library code (only in the application entry point)
- f-strings in logging calls (use `%s` formatting for lazy evaluation): `logger.info("Found %s items", count)` not `logger.info(f"Found {count} items")`

## Exception Handling

Catch specific exceptions. Never bare `except:`. Never `except Exception:` unless you re-raise.

```python
# CORRECT: specific exceptions
try:
    data = json.loads(raw_text)
except json.JSONDecodeError as e:
    logger.error("Invalid JSON: %s", e)
    raise ValueError(f"Could not parse response: {e}") from e
```

```python
# WRONG: catches KeyboardInterrupt, SystemExit, and everything else
try:
    do_something()
except:
    pass

# WRONG: swallows all exceptions silently
try:
    do_something()
except Exception:
    pass
```

If you must catch a broad exception (e.g., top-level error handler), always re-raise or log and continue intentionally:

```python
# ACCEPTABLE: broad catch with explicit handling and re-raise
try:
    run_pipeline()
except Exception:
    logger.exception("Pipeline failed")
    raise
```

## String Formatting

f-strings for all string formatting. No concatenation, no `.format()`, no `%` formatting in application code.

```python
# CORRECT
name = "world"
message = f"Hello, {name}!"
path = f"/api/v1/users/{user_id}/orders"

# WRONG
message = "Hello, " + name + "!"
message = "Hello, {}!".format(name)
message = "Hello, %s!" % name
```

Exception: use `%s` formatting in `logging` calls for lazy evaluation (see Logging section above).

## Naming Conventions

Follow PEP 8:

| Kind | Convention | Example |
|------|-----------|---------|
| Functions, methods, variables | `snake_case` | `process_document`, `user_id` |
| Classes | `PascalCase` | `DocumentProcessor`, `UserService` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Modules | `snake_case` | `document_processor.py` |
| Packages | `snake_case` (no hyphens) | `my_package` |
| Private | Leading underscore | `_internal_helper`, `_cache` |
| "Dunder" | Double underscore | `__init__`, `__repr__` |

**Never:**
- `camelCase` for functions or variables
- Single-letter names (except `i`, `j`, `k` in short loops, `e` for exceptions, `f` for files)
- Abbreviations that aren't universally understood

## Import Ordering

Three groups, separated by blank lines: standard library, third-party, local.

```python
# Standard library
import json
import logging
from pathlib import Path

# Third-party
import yaml
from fastapi import FastAPI, Depends
from pydantic import BaseModel

# Local
from .config import Settings
from .services import UserService
```

Use `ruff` or `isort` to enforce this automatically.

## Dataclasses and Pydantic Models

Use dataclasses for plain data containers. Use Pydantic for data that needs validation, serialization, or comes from external input.

```python
# Dataclass: internal data structures
from dataclasses import dataclass

@dataclass
class ChunkResult:
    text: str
    start_index: int
    end_index: int
    token_count: int
```

```python
# Pydantic: external data (API requests, config, parsed files)
from pydantic import BaseModel, Field

class DocumentRequest(BaseModel):
    content: str = Field(min_length=1)
    max_chunk_size: int = Field(default=1000, gt=0)
    overlap: int = Field(default=200, ge=0)
```

## Subprocess Calls

Use list form. Never `shell=True`.

```python
# CORRECT: list form, no shell injection risk
import subprocess

result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True,
)
```

```python
# WRONG: shell=True is a command injection vulnerability
result = subprocess.run(f"git status {path}", shell=True)
```

## Script Entry Points

Every script that might be imported needs the `__main__` guard.

```python
def main() -> int:
    """Entry point."""
    # ...
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Anti-Pattern Quick Reference

| Bad Pattern | Correct Pattern | Why |
|------------|----------------|-----|
| `os.path.join(a, b)` | `Path(a) / b` | `pathlib` is clearer, safer, cross-platform |
| `print("debug:", x)` | `logger.debug("Value: %s", x)` | Logging is filterable, configurable |
| `except:` / `except Exception:` | `except SpecificError:` | Broad catches hide real bugs |
| `"Hello " + name` | `f"Hello {name}"` | f-strings are faster and clearer |
| `def foo(items=[]):` | `def foo(items=None):` | Mutable defaults are shared across calls |
| `for i in range(len(lst)):` | `for item in lst:` | Direct iteration is Pythonic |
| `if key in dict.keys():` | `if key in dict:` | `.keys()` is unnecessary |
| `subprocess.run(cmd, shell=True)` | `subprocess.run(["cmd", "arg"])` | `shell=True` enables command injection |
| `import *` | `from module import Name` | Wildcard imports pollute the namespace |
| No type hints | Full type hints | Types catch bugs, enable IDE support |
| `sudo pip install` | `python -m venv .venv` | Global installs break system Python |
| `setup.py` | `pyproject.toml` | `setup.py` is legacy, `pyproject.toml` is the standard |
