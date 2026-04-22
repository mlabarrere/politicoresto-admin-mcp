"""Tests for `politicoresto_mcp.session`."""

from __future__ import annotations

import pytest

from politicoresto_mcp.session import get_state, require_acting_user, reset_state


def setup_function() -> None:
    reset_state()


def teardown_function() -> None:
    reset_state()


def test_get_state_returns_singleton() -> None:
    assert get_state() is get_state()


def test_initial_acting_user_is_none() -> None:
    assert get_state().acting_user_id is None


def test_require_acting_user_raises_when_unset() -> None:
    with pytest.raises(RuntimeError, match="No acting user is set"):
        require_acting_user()


def test_require_acting_user_returns_when_set() -> None:
    get_state().acting_user_id = "abc-123"
    assert require_acting_user() == "abc-123"


def test_reset_state_clears_acting_user() -> None:
    get_state().acting_user_id = "abc-123"
    reset_state()
    assert get_state().acting_user_id is None
    with pytest.raises(RuntimeError):
        require_acting_user()
