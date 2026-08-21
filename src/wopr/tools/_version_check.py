"""Best-effort check for whether the installed WOPR is behind the latest tag.

``wopr --version`` prints the installed version with no comparison to what's
actually current — there's no way for an operator to see they're behind
short of manually checking GitHub. This module adds that comparison as a
soft, non-blocking check surfaced through ``recommend_wopr_setup``.

Deliberately best-effort, matching the posture of ``_embeddings.py``'s
optional-dependency handling: no network access, no git binary, no
connectivity, or an auth prompt the environment can't satisfy are all
normal, expected states — not errors. Every failure mode here degrades to
``latest: None`` rather than raising or blocking the caller.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import NamedTuple

logger = logging.getLogger("wopr")

# Matches the SSH install URL documented in README.md so this check looks at
# the same remote a fresh install would pull from.
REPO_URL = "git@github.com:[client-org]/webteam-ai-tools.git"

_TAG_RE = re.compile(r"refs/tags/v?(\d+)\.(\d+)\.(\d+)$")

# Short — this runs inside a read-only diagnostic call an operator is
# waiting on synchronously. A slow or hanging remote should never make
# recommend_wopr_setup feel broken; skipping the version check entirely is
# always preferable to a multi-second stall.
_TIMEOUT_SECONDS = 2.0


class VersionDrift(NamedTuple):
    installed: str
    latest: str | None
    status: str  # "current" | "behind" | "ahead" | "unknown"


def _parse_version(v: str) -> tuple[int, int, int] | None:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def get_latest_tag(repo_url: str = REPO_URL, timeout: float = _TIMEOUT_SECONDS) -> str | None:
    """Return the highest semver tag on ``repo_url``, or ``None`` on any failure.

    Uses ``git ls-remote`` rather than the GitHub API to reuse whatever SSH
    auth is already configured for the install itself (README's documented
    install path is the same SSH URL), and to avoid an unauthenticated
    API's rate limits. ``GIT_TERMINAL_PROMPT=0`` prevents a hang waiting on
    interactive auth in a non-interactive environment (CI, a background
    MCP server process).
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", repo_url],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.debug("Version check: git ls-remote failed: %s", e)
        return None

    if result.returncode != 0:
        logger.debug("Version check: git ls-remote exited %d: %s", result.returncode, result.stderr)
        return None

    best: tuple[int, int, int] | None = None
    best_tag: str | None = None
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        m = _TAG_RE.search(parts[1])
        if not m:
            continue
        parsed = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if best is None or parsed > best:
            best = parsed
            best_tag = "v" + ".".join(m.groups())

    return best_tag


def check_version_drift(
    installed_version: str,
    repo_url: str = REPO_URL,
    timeout: float = _TIMEOUT_SECONDS,
) -> VersionDrift:
    """Compare ``installed_version`` against the latest tag. Never raises."""
    latest = get_latest_tag(repo_url=repo_url, timeout=timeout)
    if latest is None:
        return VersionDrift(installed=installed_version, latest=None, status="unknown")

    installed_parsed = _parse_version(installed_version)
    latest_parsed = _parse_version(latest)
    if installed_parsed is None or latest_parsed is None:
        return VersionDrift(installed=installed_version, latest=latest, status="unknown")

    if installed_parsed < latest_parsed:
        status = "behind"
    elif installed_parsed > latest_parsed:
        status = "ahead"
    else:
        status = "current"

    return VersionDrift(installed=installed_version, latest=latest, status=status)
