"""Discovery eval — deterministic, the heart of the dynamic A2A pattern.

This eval measures the orchestrator's discovery + delegation TRAJECTORY, which
is the whole point of the multi-agent-trip-planner case: given an open travel
request, does it first DISCOVER the available specialists (read their agent
cards) and then DELEGATE the subtasks to them?

It is deterministic (no LLM judge): we run the real orchestrator, capture which
tools it called, and check that trajectory with code-based evaluators:

- It MUST call `a2a_list_discovered_agents`  -> it discovered.   (ToolCalled)
- It MUST call `a2a_send_message`            -> it delegated.    (ToolCalled)

Requirements: GEMINI_API_KEY in .env (runs the real Gemini orchestrator). It does
NOT need the A2A servers: the provider's network calls are mocked, because here
we only care about the discovery-driven decision, not the specialists' answers.

Run:
    python -m evals.eval_discovery
"""

import sys
from unittest.mock import AsyncMock, patch

from strands_evals import Case, Experiment
from strands_evals.evaluators import ToolCalled

import orchestrator.main as orch
from evals.dataset import load_cases
from evals.report_io import save_report

# The evals report uses emoji. On Windows the default console encoding (cp1252)
# cannot print them and crashes at display time. Force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Tool names exposed by A2AClientToolProvider (must match the SDK).
LIST_TOOL = "a2a_list_discovered_agents"
SEND_TOOL = "a2a_send_message"

# Fake "discovered agents" payload the mocked provider returns, shaped like the
# real tool output, advertising the three specialists with their skills.
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

_FAKE_SEND_RESULT = {
    "status": "success",
    "response": {"raw_response": "Example flight/hotel/itinerary result (simulated)."},
    "target_agent_url": "http://localhost:9001",
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


def discovery_task(case: Case) -> dict:
    """Run the real orchestrator for one case and return its tool trajectory.

    The provider's network calls are mocked so the eval does not need the A2A
    servers and stays fast/deterministic — we are testing the discovery +
    delegation decision, not the specialists' answers.
    """
    with (
        patch.object(
            orch._a2a_provider,
            "_list_discovered_agents",
            new=AsyncMock(return_value=_FAKE_AGENTS),
        ),
        patch.object(
            orch._a2a_provider,
            "_discover_agent_card_tool",
            new=AsyncMock(return_value={"status": "success", "agent_card": {}}),
        ),
        patch.object(
            orch._a2a_provider,
            "_send_message",
            new=AsyncMock(return_value=_FAKE_SEND_RESULT),
        ),
    ):
        orchestrator = orch.build_orchestrator()
        result = orchestrator(case.input)

    return {
        "output": str(result),
        "trajectory": _tools_called(orchestrator),
    }


# Test cases live in evals/cases_discovery.jsonl (data, not code) so you can edit
# them without touching this file.
CASES_FILE = "cases_discovery.jsonl"


def main() -> None:
    cases = load_cases(CASES_FILE)

    print("=== Discovery eval: the orchestrator must DISCOVER the agents ===")
    exp_discover = Experiment(cases=cases, evaluators=[ToolCalled(LIST_TOOL)])
    report_discover = exp_discover.run_evaluations(discovery_task)
    # display() prints the table and continues; run_display() would open an
    # interactive viewer that waits for keyboard input (q to quit).
    report_discover.display()
    print(f"Report saved to: {save_report(report_discover, 'discovery_list')}")

    print("\n=== Discovery eval: the orchestrator must DELEGATE to a specialist ===")
    exp_delegate = Experiment(cases=cases, evaluators=[ToolCalled(SEND_TOOL)])
    report_delegate = exp_delegate.run_evaluations(discovery_task)
    report_delegate.display()
    print(f"Report saved to: {save_report(report_delegate, 'discovery_delegate')}")


if __name__ == "__main__":
    main()
