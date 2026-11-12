"""Shared setup for the learning tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _learning_mcp_absent(monkeypatch):
    """There is no learning-mcp in the tests: calls that are not mocked fail fast (connection refused)
    instead of waiting on a name lookup of ``learning-mcp``. Tests that need an answer patch ``_call``."""
    monkeypatch.setenv("LEARNING_MCP_URL", "http://127.0.0.1:9/mcp")
