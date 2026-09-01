"""Routing logic tests (unit layer).

These tests do NOT need the A2AServer running. They work at two levels:

1. The `handle_sensitive_query` tool in isolation: we mock the remote A2AAgent
   to verify the tool forwards the query and returns the response text, without
   touching the network.

2. The orchestrator's routing decision: we verify that, given a sensitive query,
   the orchestrator (real Gemini) invokes the tool, and that given a generic one
   it does not. Since this requires a real LLM call, it is skipped automatically
   if GEMINI_API_KEY is not configured.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Level 1 — the tool in isolation (always runs, no network or LLM)
# ─────────────────────────────────────────────────────────────────────────────


def _fake_agent_result(text: str) -> MagicMock:
    """Build an object shaped like a Strands AgentResult."""
    result = MagicMock()
    result.message = {"content": [{"text": text}]}
    return result


def test_tool_delegates_and_returns_remote_agent_text():
    """The tool must invoke the A2AAgent with the query and return its text."""
    import orchestrator.main as main

    fake_response = "Example balance: $12,345.67 (simulated data)."
    with patch.object(
        main, "_remote_agent", return_value=_fake_agent_result(fake_response)
    ) as mock_remote:
        query = "I want the balance of my account 1234-5678-9"
        # Call the plain delegation function directly (the @tool wrapper just
        # forwards to it), so the test does not depend on Strands internals.
        result = main._delegate_to_local_agent(query)

    mock_remote.assert_called_once_with(query)
    assert result == fake_response


# ─────────────────────────────────────────────────────────────────────────────
# Level 2 — orchestrator routing decision (requires GEMINI_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────

_needs_key = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEY") == "your-gemini-api-key-here",
    reason="Requires a real GEMINI_API_KEY to call the orchestrator (Gemini).",
)


@_needs_key
async def test_orchestrator_delegates_on_sensitive_query():
    """Given sensitive data, the orchestrator must invoke the A2A tool."""
    import orchestrator.main as main

    with patch.object(
        main,
        "_remote_agent",
        return_value=_fake_agent_result("Example balance: $1,000 (simulated)."),
    ) as mock_remote:
        orchestrator = main.build_orchestrator()
        await main.run_once(orchestrator, "Check the balance of my account 1234-5678-9")

    assert mock_remote.called, "The orchestrator should delegate the sensitive query"


@_needs_key
async def test_orchestrator_does_not_delegate_on_generic_query():
    """Given a generic query, the orchestrator must NOT invoke the A2A tool."""
    import orchestrator.main as main

    with patch.object(main, "_remote_agent") as mock_remote:
        orchestrator = main.build_orchestrator()
        await main.run_once(orchestrator, "What are your business hours?")

    assert not mock_remote.called, "The orchestrator should not delegate a generic query"
