"""Itinerary specialist — an A2A server exposing the `build_itinerary` skill.

This process starts a Strands `A2AServer` that:
  1. Wraps a Strands `Agent` running Gemma via Ollama.
  2. Publishes an agent card at /.well-known/agent-card.json advertising a
     single skill: building a day-by-day itinerary. The orchestrator reads this
     card at runtime and, crucially, calls this agent LAST — the itinerary
     depends on the flight and hotel results gathered from the other two
     specialists.
  3. Serves A2A requests (JSON-RPC) at http://<ITINERARY_HOST>:<ITINERARY_PORT>.

Run it in its own terminal:
    python -m remote_agents.itinerary_server
"""

from a2a.types import AgentSkill
from strands import Agent
from strands.models.ollama import OllamaModel
from strands.multiagent.a2a import A2AServer

from common.config import load_itinerary_config
from common.logging_config import setup_logging
from common.prompts import ITINERARY_AGENT_SYSTEM_PROMPT
from remote_agents.travel_tools import get_destination_highlights

logger = setup_logging("itinerary_server.log", "itinerary_server")

_config = load_itinerary_config()

# Skill advertised in the agent card, discovered by the orchestrator at runtime.
ITINERARY_SKILL = AgentSkill(
    id="build_itinerary",
    name="Build Itinerary",
    description=(
        "Combine an already-chosen flight and hotel into a coherent day-by-day "
        "itinerary for the destination, using its main points of interest. "
        "Expects the flight and hotel details as input."
    ),
    tags=["itinerary", "planning", "travel"],
    examples=[
        "Build a 5-day itinerary for Barcelona given this flight and hotel.",
        "Organize the days of the trip using the chosen flight and hotel.",
    ],
)


def create_agent(context_id: str) -> Agent:
    """Per-conversation agent factory (the A2AServer's recommended mode).

    Args:
        context_id: conversation identifier assigned by the A2A protocol.

    Returns:
        A fresh Strands Agent backed by Gemma via Ollama.
    """
    logger.info("Creating itinerary agent for context_id=%s", context_id)

    ollama_model = OllamaModel(
        host=_config.ollama_host,
        model_id=_config.model_id,
        temperature=0.2,
    )

    return Agent(
        name="Itinerary Agent",
        description=(
            "Specialist agent that combines a chosen flight and hotel into a "
            "day-by-day itinerary using the destination's points of interest."
        ),
        model=ollama_model,
        system_prompt=ITINERARY_AGENT_SYSTEM_PROMPT,
        tools=[get_destination_highlights],
        callback_handler=None,
    )


def build_server() -> A2AServer:
    """Build (without starting) the A2AServer. Separated so it can be tested."""
    return A2AServer(
        agent_factory=create_agent,
        host=_config.host,
        port=_config.port,
        skills=[ITINERARY_SKILL],
    )


def main() -> None:
    logger.info(
        "Starting Itinerary A2AServer at http://%s:%s (local model: %s via %s)",
        _config.host,
        _config.port,
        _config.model_id,
        _config.ollama_host,
    )
    logger.info(
        "Agent card available at http://%s:%s/.well-known/agent-card.json",
        _config.host,
        _config.port,
    )
    server = build_server()
    server.serve()


if __name__ == "__main__":
    main()
