"""Discovery-wiring and routing tests (unit layer).

These tests do NOT need the A2A servers running. They work at two levels:

1. Tool wiring (always runs, no network or LLM): verify the orchestrator is
   equipped with the A2A discovery/delegation tools that the whole dynamic
   pattern depends on (`a2a_list_discovered_agents`, `a2a_discover_agent`,
   `a2a_send_message`).

2. Orchestrator behavior (requires GEMINI_API_KEY): verify that, given an open
   travel request, the real Gemini orchestrator actually DISCOVERS the agents
   before delegating — i.e. it calls `a2a_list_discovered_agents` and then
   delegates via `a2a_send_message`. The provider's network calls are mocked, so
   no real A2A server is needed and the test stays fast: we only care about the
   discovery-driven decision, not the specialists' answers.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

# Tool names exposed by A2AClientToolProvider (must match the SDK).
LIST_TOOL = "a2a_list_discovered_agents"
DISCOVER_TOOL = "a2a_discover_agent"
SEND_TOOL = "a2a_send_message"

# A fake "discovered agents" payload the mocked provider returns, shaped like
# the real tool output. It advertises the three specialists with their skills so
# the orchestrator has something to route on.
_FAKE_AGENTS = {
    "status": "success",
    "total_count": 3,
    "agents": [
        {
            "name": "Flights Agent",
            "description": "Searches flight options for a trip.",
            "url": "http://localhost:9001",
            "skills": [{"id": "search_flights", "name": "Search Flights"}],
        },
        {
            "name": "Hotels Agent",
            "description": "Searches accommodation options for a trip.",
            "url": "http://localhost:9002",
            "skills": [{"id": "search_hotels", "name": "Search Hotels"}],
        },
        {
            "name": "Itinerary Agent",
            "description": "Builds a day-by-day itinerary from a flight and hotel.",
            "url": "http://localhost:9003",
            "skills": [{"id": "build_itinerary", "name": "Build Itinerary"}],
        },
    ],
}


def _tools_called(agent) -> list[str]:
    """Extract the ordered list of tool names the agent invoked.

    Strands records tool invocations as `toolUse` blocks in the content of the
    assistant messages. We scan the message history and collect their names.
    """
    names: list[str] = []
    for message in agent.messages:
        for block in message.get("content", []) or []:
            if isinstance(block, dict) and "toolUse" in block:
                tool_name = block["toolUse"].get("name")
                if tool_name:
                    names.append(tool_name)
    return names


# ─────────────────────────────────────────────────────────────────────────────
# Level 1 — tool wiring (always runs, no network or LLM)
# ─────────────────────────────────────────────────────────────────────────────

_needs_key = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEY") == "your-gemini-api-key-here",
    reason="Requires a real GEMINI_API_KEY to build/call the orchestrator (Gemini).",
)


@_needs_key
def test_orchestrator_is_wired_with_a2a_tools():
    """The orchestrator must expose the three A2A discovery/delegation tools."""
    import orchestrator.main as main

    orchestrator = main.build_orchestrator()
    tool_names = {t.tool_name for t in orchestrator.tool_registry.registry.values()}

    assert {LIST_TOOL, DISCOVER_TOOL, SEND_TOOL}.issubset(tool_names), (
        f"Missing A2A tools. Found: {sorted(tool_names)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Level 2 — orchestrator discovery behavior (requires GEMINI_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────


@_needs_key
async def test_orchestrator_discovers_before_delegating():
    """Given a travel request, the orchestrator must list agents and delegate.

    We mock the provider's async internals so no real A2A server is needed:
    - listing returns the three fake specialists (with skills),
    - discovering any URL succeeds,
    - sending a message returns a canned specialist reply.
    Then we assert the orchestrator called the discovery tool and delegated at
    least once via a2a_send_message.
    """
    import orchestrator.main as main

    fake_send_result = {
        "status": "success",
        "response": {"raw_response": "Example flight/hotel/itinerary result (simulated)."},
        "target_agent_url": "http://localhost:9001",
    }

    with (
        patch.object(
            main._a2a_provider,
            "_list_discovered_agents",
            new=AsyncMock(return_value=_FAKE_AGENTS),
        ),
        patch.object(
            main._a2a_provider,
            "_discover_agent_card_tool",
            new=AsyncMock(return_value={"status": "success", "agent_card": {}}),
        ),
        patch.object(
            main._a2a_provider,
            "_send_message",
            new=AsyncMock(return_value=fake_send_result),
        ),
    ):
        orchestrator = main.build_orchestrator()
        await main.run_once(orchestrator, "I want to go to Barcelona in March for 5 days.")

    trajectory = _tools_called(orchestrator)

    assert LIST_TOOL in trajectory, (
        "The orchestrator should discover the agents (a2a_list_discovered_agents) "
        f"before delegating. Trajectory: {trajectory}"
    )
    assert SEND_TOOL in trajectory, (
        "The orchestrator should delegate at least one subtask via "
        f"a2a_send_message. Trajectory: {trajectory}"
    )
