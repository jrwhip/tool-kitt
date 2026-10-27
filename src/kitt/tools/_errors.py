"""Shared error-return contract for MCP tools.

KITT tools return string status messages. The convention is:

* Success: a free-form human-readable message starting with the
  past-tense verb (``"Wrote ..."``, ``"Appended ..."``, ``"Seeded ..."``).
* Failure: a string beginning with the :data:`ERROR_PREFIX` constant
  followed by an operator-facing reason.

Two writer modules (``kitt_yml`` and ``claude_md``) defined identical
copies of this prefix as ``_PROPOSER_ERROR_PREFIX``. The DEMO-123
audit flagged that duplication and the broader pattern of inline
``"Error: ..."`` strings across the tools tree.

This module is the single source of truth for the prefix. Callers who
want to:

* Build an error string: call :func:`error` so the prefix and message
  are joined consistently.
* Detect that a tool returned an error: check
  ``result.startswith(ERROR_PREFIX)``.

The inline ``f"Error: ..."`` literals scattered across the tools tree
are not migrated wholesale by this audit; they keep working as long
as :data:`ERROR_PREFIX` stays ``"Error:"``. A future migration to
JSON return envelopes (or a stricter helper) lands in one place when
the writer's contract is ready to change.
"""

from __future__ import annotations

ERROR_PREFIX = "Error:"


def error(message: str) -> str:
    """Format ``message`` as an MCP-tool error return string.

    Equivalent to ``f"{ERROR_PREFIX} {message}"`` but exposed as a
    helper so callers can switch to a different shape (logging,
    structured envelope, etc.) by editing one place when the
    contract changes.
    """
    return f"{ERROR_PREFIX} {message}"


def is_error(result: str) -> bool:
    """Return True when ``result`` matches the MCP-tool error shape.

    Used by tool composers (e.g. ``write_kitt_yml`` guards against
    accidentally writing a proposer's error output) so the
    detection logic and the prefix definition stay in sync.
    """
    return result.startswith(ERROR_PREFIX)
