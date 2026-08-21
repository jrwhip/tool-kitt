# Packaging and Distribution

Modern Python packaging with `pyproject.toml`, `src/` layout, and virtual environments.

Reference: [Python Packaging User Guide](https://packaging.python.org/en/latest/), [PEP 621](https://peps.python.org/pep-0621/), [Hatch Documentation](https://hatch.pypa.io/latest/)

## The One File: pyproject.toml

`pyproject.toml` is the single source of truth for project metadata, dependencies, build configuration, and tool configuration. Everything in one file.

```toml
[project]
name = "my-service"
version = "1.0.0"
description = "A service that does useful things"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [
    { name = "Your Name", email = "you@example.com" }
]
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "anthropic[bedrock]>=0.40.0",
    "pinecone>=5.1.0",
    "pydantic-settings>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",
    "ruff>=0.5",
    "mypy>=1.10",
]

[project.scripts]
my-service = "my_service.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_service"]

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.10"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

## Build Backends

| Backend | When to Use |
|---------|------------|
| **Hatch** (hatchling) | Default choice. Used by WOPR. Good for most projects. Handles src layout, force-include, versioning. |
| **setuptools** | Legacy projects migrating from setup.py. Works but more configuration needed. |
| **flit** | Simple pure-Python packages with minimal config. |

All three read from `pyproject.toml`. The build backend is declared in `[build-system]`.

## Project Layout: src/

Use the `src/` layout. Always.

```
my-project/
    pyproject.toml
    README.md
    LICENSE
    src/
        my_package/
            __init__.py
            cli.py
            config.py
            services/
                __init__.py
                document_service.py
    tests/
        __init__.py
        conftest.py
        test_cli.py
        test_document_service.py
```

**Why `src/` layout?**
- Prevents accidental imports of the local (uninstalled) package. Without `src/`, Python can import from the current directory, which masks import errors that only appear after installation.
- Forces you to install the package to test it, catching packaging bugs early.
- Clearly separates source code from project files (tests, docs, config).

**Every package directory must have an `__init__.py` file.** Missing `__init__.py` files cause import failures. This is the most common packaging bug.

## Entry Points

CLI commands are registered in `[project.scripts]`:

```toml
[project.scripts]
my-cli = "my_package.cli:main"
```

This creates an executable `my-cli` that calls `my_package.cli.main()` when the package is installed.

## Dependencies

### Runtime Dependencies

```toml
[project.dependencies]
dependencies = [
    "fastapi>=0.110.0",
    "anthropic>=0.40.0",
]
```

Use `>=` for minimum version. Avoid pinning exact versions in libraries (that is what lock files are for).

### Optional Dependencies (Dev, Test, etc.)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
    "mypy>=1.10",
]
docs = [
    "mkdocs>=1.5",
]
```

Install with: `pip install -e ".[dev]"`

## Version Management

Single source of truth. Pick one location:

**Option A: In `pyproject.toml` (static)**
```toml
[project]
version = "1.0.0"
```

**Option B: In `__init__.py` (dynamic, used by WOPR)**
```python
# src/my_package/__init__.py
__version__ = "1.0.0"
```
```toml
# pyproject.toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/my_package/__init__.py"
```

## Installation

```bash
# Create a virtual environment FIRST
python -m venv .venv
source .venv/bin/activate

# Install in development mode (editable)
pip install -e ".[dev]"

# Install normally (from local source)
pip install .

# Install a CLI tool globally (isolated, using pipx)
pipx install .
```

### Editable Installs

`pip install -e .` installs the package in "editable" mode. Changes to source code take effect immediately without reinstalling. Essential for development.

### pipx for CLI Tools

`pipx` installs Python CLI tools in isolated environments. Use it for tools you want available globally without polluting your project's venv.

```bash
pipx install wopr
pipx install ruff
pipx install mypy
```

## Lock Files

For reproducible deployments, generate a lock file:

```bash
pip freeze > requirements.lock
```

Use this in CI/CD and Docker builds:

```bash
pip install -r requirements.lock
```

`requirements.lock` (or `requirements.txt` used as a lock file) pins exact versions for deployment. It is NOT the project's dependency definition. That lives in `pyproject.toml`.

## .gitignore

Every Python project needs these entries:

```
# Byte-compiled / cached
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
.venv/
venv/

# Distribution
dist/
build/
*.egg-info/

# IDE
.idea/
.vscode/
*.swp

# Environment
.env
.env.local

# Test / Coverage
.coverage
htmlcov/
.pytest_cache/

# mypy
.mypy_cache/
```

## Docker

Build slim, secure images:

```dockerfile
# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Runtime stage
FROM python:3.12-slim

RUN useradd --create-home appuser
USER appuser

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/my-service /usr/local/bin/my-service

EXPOSE 8000
CMD ["my-service"]
```

Rules:
- Use `python:3.12-slim`, not `python:3.12` (full image is 1GB+)
- Run as non-root user
- Multi-stage build to keep the final image small
- Copy only what is needed; do not copy `.venv/`, `tests/`, or `.git/`
- Use `--no-cache-dir` to reduce image size

## What NOT to Do

| Bad Pattern | Correct Pattern | Why |
|------------|----------------|-----|
| `setup.py` as primary config | `pyproject.toml` | `setup.py` is legacy |
| `setup.cfg` for metadata | `pyproject.toml` | Consolidate in one file |
| `requirements.txt` for project definition | `pyproject.toml` for deps, lock file for pinning | Separate concerns |
| Flat layout (package at repo root) | `src/` layout | Prevents import collisions |
| Missing `__init__.py` | Add `__init__.py` to every package directory | Required for Python packages |
| Global `pip install` | `python -m venv .venv` first | Protects system Python |
| Pinning exact versions in libraries | `>=` minimum version | Let the consumer resolve versions |
| Committing `.venv/` | Add to `.gitignore` | Virtual envs are machine-specific |
