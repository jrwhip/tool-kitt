"""OSV malware tripwire for registered npx/uvx/pipx MCP servers.

Every MCP server WOPR (or an operator) has registered for Claude Code,
Copilot, or Gemini is, in practice, an arbitrary program the CLI will
shell out to on startup. ``npx``/``uvx``/``pipx`` invocations in
particular fetch and run whatever the named package resolves to at
that moment -- there is no local review step. This module cross-checks
those commands against the OSV (Open Source Vulnerabilities) API's
``MAL-*`` advisories: entries OSV's curators have confirmed are
malicious packages, not garden-variety CVEs. Regular vulnerabilities
are deliberately out of scope -- this is a malware tripwire, not a
vulnerability scanner, and conflating the two would make it noisy
enough to ignore, the exact failure mode ``doctor_recommendations``'
dismissal latch (see that module) exists to prevent elsewhere.

Ported from hermes-agent's ``tools/osv_check.py`` (extension malware
check, itself inspired by Block/goose's equivalent). The parsing
semantics carry over almost unchanged -- there's only one reasonable
way to pull a package name out of an npx/uvx invocation -- but the
integration point differs: hermes checks before every subprocess
launch; WOPR has no launch hook for MCP servers it doesn't own; so
this instead becomes a doctor-style, on-demand audit of what's
*already* registered across the three CLI configs.

Two hard constraints not present in the hermes original, called out
explicitly because getting either wrong turns a safety net into an
annoyance:

* **Fail-open, always.** A network error, timeout, or unexpected OSV
  response must never block or error the caller -- it degrades to
  "not checked," never "assume malicious" or "crash." The only thing
  ``MAL-*`` advisories should ever do is warn.
* **Network access is opt-in.** Unlike some network-touching helpers (historically
  read-only, also best-effort), this hits a *third-party* service with
  package names taken from the operator's own MCP config. Doctor tools
  elsewhere in WOPR do local filesystem reads by default; reaching out
  to api.osv.dev should be a decision the caller makes, not a surprise
  side effect of running the doctor. ``check_mcp_servers_for_malware``
  therefore defaults ``enable_network`` to ``False`` and returns a
  ``skipped`` status explaining why, rather than silently phoning home.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..product import LOGGER_NAME
from ._safe_load import safe_load_json as _safe_load_json

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(LOGGER_NAME)

_OSV_ENDPOINT = "https://api.osv.dev/v1/query"

# Per-request bound. OSV's typical latency is ~300ms; this leaves ample
# headroom for a slow-but-working connection while still keeping the
# worst case (an operator running the doctor with no network) bounded
# rather than an indefinite hang. See _check_one/check_mcp_servers_for_malware
# for how a single unreachable result short-circuits the rest of the run.
_TIMEOUT_SECONDS = 5.0


class _OsvUnreachable(Exception):
    """The OSV API could not be reached or gave an unparseable response.

    Raised only by :func:`_query_osv_transport`/:func:`_query_osv` and
    caught immediately by their callers -- never allowed to propagate
    out of this module's public functions. A distinct exception type
    (rather than reusing ``OSError``) so callers that DO want to
    distinguish "unreachable" from "reachable, nothing found" (the
    doctor orchestration below, to short-circuit further checks once
    the network is known to be down) can catch it precisely.
    """


# -----------------------------------------------------------------------------
# Pure parsing: ecosystem + package-name inference from a command/args pair.
# -----------------------------------------------------------------------------


def _infer_ecosystem(command: str) -> str | None:
    """Infer an OSV ecosystem name from an MCP server's launch command."""
    base = Path(command).name.lower()
    if base in {"npx", "npx.cmd"}:
        return "npm"
    if base in {"uvx", "uvx.cmd", "pipx"}:
        return "PyPI"
    return None


def _parse_package_from_args(args: list[Any], ecosystem: str) -> tuple[str | None, str | None]:
    """Extract ``(package_name, version)`` from an npx/uvx/pipx argv.

    Honors npx's explicit install-target flags (``--package=NAME``,
    ``--package NAME``, ``-p NAME``), which name a package distinct
    from the executed binary -- without this, the first bare
    positional (often the binary name, not the package) would be
    mistaken for the package under test.
    """
    package_token: str | None = None
    take_next = False
    for arg in args:
        if not isinstance(arg, str):
            continue
        if take_next:
            package_token = arg
            break
        if arg in ("--package", "-p"):
            take_next = True
            continue
        if arg.startswith("--package="):
            package_token = arg[len("--package="):]
            break
        if arg.startswith("-"):
            continue
        package_token = arg
        break

    if not package_token:
        return None, None
    if ecosystem == "npm":
        return _parse_npm_package(package_token)
    if ecosystem == "PyPI":
        return _parse_pypi_package(package_token)
    return package_token, None


def _parse_npm_package(token: str) -> tuple[str | None, str | None]:
    """Parse ``@scope/name@version`` or ``name@version``."""
    if token.startswith("@"):
        match = re.match(r"^(@[^/]+/[^@]+)(?:@(.+))?$", token)
        if match:
            return match.group(1), match.group(2)
        return token, None
    if "@" in token:
        name, _, version = token.rpartition("@")
        return name, (version if version and version != "latest" else None)
    return token, None


def _parse_pypi_package(token: str) -> tuple[str | None, str | None]:
    """Parse ``name==version`` or ``name[extras]==version``."""
    match = re.match(r"^([a-zA-Z0-9._-]+)(?:\[[^\]]*\])?(?:==(.+))?$", token)
    if match:
        return match.group(1), match.group(2)
    return token, None


# -----------------------------------------------------------------------------
# Network: the sole transport function, isolated so tests mock it directly
# rather than a real socket ever being opened during the test suite.
# -----------------------------------------------------------------------------


def _query_osv_transport(payload: dict[str, Any], *, timeout: float) -> Any:
    """POST ``payload`` to the OSV API and return the parsed JSON response.

    The only function in this module that touches the network. Tests
    must monkeypatch this (not the higher-level callers) so the OSV
    check logic is exercised for real while no test ever opens a socket.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _OSV_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "wopr-osv-check/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # fixed https endpoint
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise _OsvUnreachable(str(e)) from e


def _query_osv(
    package: str, ecosystem: str, version: str | None, *, timeout: float
) -> list[dict[str, Any]]:
    """Query OSV for ``package`` and return only its ``MAL-*`` advisories.

    Raises :class:`_OsvUnreachable` on any network/parse failure; never
    returns a false "clean" result for an unreachable endpoint (that
    distinction matters to the caller, which treats "clean" and
    "couldn't check" very differently).
    """
    payload: dict[str, Any] = {"package": {"name": package, "ecosystem": ecosystem}}
    if version:
        payload["version"] = version
    result = _query_osv_transport(payload, timeout=timeout)
    vulns = result.get("vulns") if isinstance(result, dict) else None
    if not isinstance(vulns, list):
        return []
    return [
        v for v in vulns
        if isinstance(v, dict) and str(v.get("id", "")).startswith("MAL-")
    ]


# -----------------------------------------------------------------------------
# Public: single-package check (fail-open, never raises).
# -----------------------------------------------------------------------------


@dataclass
class _CheckOutcome:
    finding: str | None
    unreachable: bool


def _check_one(command: str, args: list[Any], *, timeout: float) -> _CheckOutcome:
    """Check one command/args pair. Internal: exposes the ``unreachable``
    flag that :func:`check_mcp_servers_for_malware` uses to stop early
    once the network is known to be down, which the public
    :func:`check_package_for_malware` deliberately does not expose (it
    matches the simpler, always-fail-open contract of the hermes-agent
    original).
    """
    ecosystem = _infer_ecosystem(command)
    if not ecosystem:
        return _CheckOutcome(None, False)
    package, version = _parse_package_from_args(args, ecosystem)
    if not package:
        return _CheckOutcome(None, False)
    try:
        malware = _query_osv(package, ecosystem, version, timeout=timeout)
    except _OsvUnreachable as e:
        logger.debug("OSV check unreachable for %s/%s (allowing): %s", ecosystem, package, e)
        return _CheckOutcome(None, True)
    if not malware:
        return _CheckOutcome(None, False)
    ids = ", ".join(str(m.get("id")) for m in malware[:3])
    summaries = "; ".join(str(m.get("summary", m.get("id")))[:100] for m in malware[:3])
    return _CheckOutcome(
        f"BLOCKED: package '{package}' ({ecosystem}) has known malware advisories: "
        f"{ids}. Details: {summaries}",
        False,
    )


def check_package_for_malware(
    command: str, args: list[Any], *, timeout: float = _TIMEOUT_SECONDS
) -> str | None:
    """Check whether an npx/uvx/pipx-launched package has a MAL-* advisory.

    Args:
        command: The launch command (e.g. ``"npx"``, ``"uvx"``). Any
            other command is not this module's concern and returns
            ``None`` immediately.
        args: The argv passed to ``command``.
        timeout: Per-request network timeout in seconds.

    Returns:
        A human-readable block message if OSV reports a ``MAL-*``
        advisory for the resolved package, or ``None`` if the package
        is clean, unparseable, not npx/uvx/pipx, or the check could not
        reach OSV at all. Fail-open by construction: this function
        never raises.
    """
    return _check_one(command, args, timeout=timeout).finding


# -----------------------------------------------------------------------------
# Doctor-facing tool: audit every registered MCP server at once.
# -----------------------------------------------------------------------------


def _enumerate_registered_mcp_entries() -> dict[str, dict[str, Any]]:
    """Merge ``mcpServers`` entries across all three CLI configs, by name.

    Sibling of ``doctor_recommendations._load_registered_mcps``, which
    only needs server *names*; this needs the full entry (``command``/
    ``args``) to know what would actually be launched. The first config
    that defines a given name wins, matching the union-of-names
    semantics the sibling function already documents.
    """
    home = Path.home()
    config_paths = (
        home / ".claude.json",
        home / ".copilot" / "mcp-config.json",
        home / ".gemini" / "settings.json",
    )
    entries: dict[str, dict[str, Any]] = {}
    for config_path in config_paths:
        data = _safe_load_json(config_path)
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if isinstance(entry, dict) and name not in entries:
                entries[name] = entry
    return entries


def check_mcp_servers_for_malware(
    enable_network: bool = False, timeout: float = _TIMEOUT_SECONDS
) -> str:
    """Malware tripwire for every registered npx/uvx/pipx MCP server.

    Cross-checks each ``mcpServers`` entry across Claude Code's
    (``~/.claude.json``), Copilot's (``~/.copilot/mcp-config.json``),
    and Gemini's (``~/.gemini/settings.json``) configs against OSV's
    ``MAL-*`` (confirmed malware) advisories. Regular CVEs are out of
    scope by design -- see the module docstring.

    Args:
        enable_network: The OSV API is a public, third-party service.
            Defaults to ``False`` so running this never reaches the
            network as a surprise side effect; the return value in
            that case is a ``skipped`` status naming the servers that
            *would* be checked, not an error. Pass ``True`` to actually
            query OSV.
        timeout: Per-request timeout in seconds, bounding worst-case
            latency for a single server. The first unreachable result
            stops the run rather than repeating the same timeout once
            per remaining server -- if OSV is unreachable for one
            package it will be unreachable for all of them, and a
            doctor check should never turn into a multi-server hang.

    Returns:
        JSON with a ``status`` (``skipped`` / ``ok`` / ``findings`` /
        ``skipped_offline``), the servers actually queried, and any
        findings. Fail-open throughout: a network problem degrades the
        status to ``skipped_offline`` rather than raising or blocking
        the caller.
    """
    entries = _enumerate_registered_mcp_entries()

    if not enable_network:
        return json.dumps({
            "status": "skipped",
            "reason": (
                "network check is opt-in; pass enable_network=true to query "
                "OSV.dev's MAL-* malware advisories for registered npx/uvx/pipx "
                "MCP servers"
            ),
            "servers_registered": sorted(entries),
        }, indent=2)

    checked: list[str] = []
    findings: list[dict[str, str]] = []
    went_offline = False

    for name, entry in sorted(entries.items()):
        command = entry.get("command")
        args = entry.get("args")
        if not isinstance(command, str) or not isinstance(args, list):
            continue
        if _infer_ecosystem(command) is None:
            continue  # not npx/uvx/pipx -- nothing OSV-checkable here

        outcome = _check_one(command, args, timeout=timeout)
        if outcome.unreachable:
            went_offline = True
            break
        checked.append(name)
        if outcome.finding:
            findings.append({"server_name": name, "message": outcome.finding})

    status = "findings" if findings else ("skipped_offline" if went_offline else "ok")

    return json.dumps({
        "status": status,
        "checked_servers": checked,
        "findings": findings,
        "went_offline": went_offline,
    }, indent=2)


def register(mcp: FastMCP) -> None:
    """Register OSV malware-check tools with the MCP server."""
    mcp.tool()(check_mcp_servers_for_malware)
