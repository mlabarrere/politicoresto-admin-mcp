"""Process-local session state — the acting user used by write tools.

The state lives for the lifetime of the MCP server process (one Claude Desktop
session). It is intentionally not persisted to disk: every restart resets the
acting user, which acts as a safeguard against surprise writes under the wrong
identity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionState:
    """Mutable server state that lives for the process lifetime."""

    acting_user_id: str | None = None


_state = SessionState()


def get_state() -> SessionState:
    """Return the process-wide session state."""
    return _state


def reset_state() -> None:
    """Reset the session state to its defaults.

    Intended for tests. Not exposed as an MCP tool.
    """
    _state.acting_user_id = None


def require_acting_user() -> str:
    """Return the acting user id or raise a clear error.

    Raises:
        RuntimeError: when no acting user has been set. The message points at
            the two tools that resolve the situation.
    """
    if _state.acting_user_id is None:
        raise RuntimeError(
            "No acting user is set. Call set_acting_user(user_id=...) before "
            "any write operation. Use list_profiles() to discover valid user_ids."
        )
    return _state.acting_user_id
