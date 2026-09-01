"""Hotels specialist — an A2A server exposing the `search_hotels` skill.

This process starts a Strands `A2AServer` that:
  1. Wraps a Strands `Agent` running Gemma via Ollama.
  2. Publishes an agent card at /.well-known/agent-card.json advertising a
     single skill: searching hotels. The orchestrator reads this card at runtime
     to decide whether to delegate accommodation searches here.
  3. Serves A2A requests (JSON-RPC) at http://<HOTELS_HOST>:<HOTELS_PORT>.

Run it in its own terminal:
    python -m remote_agents.hotels_server
"""

from a2a.types import AgentSkill
from strands import Agent
from strands.models.ollama import OllamaModel
from strands.multiagent.a2a import A2AServer

from common.config import load_hotels_config
from common.logging_config import setup_logging
from common.prompts import HOTELS_AGENT_SYSTEM_PROMPT
from remote_agents.travel_tools import search_hotels

logger = setup_logging("hotels_server.log", "hotels_server")

_config = load_hotels_config()

# Skill advertised in the agent card, discovered by the orchestrator at runtime.
HOTELS_SKILL = AgentSkill(
    id="search_hotels",
    name="Search Hotels",
    description=(
        "Search available accommodation options for a destination and a number "
        "of nights. Returns hotels with category, area and nightly price."
    ),
    tags=["hotels", "accommodation", "travel", "search"],
    examples=[
        "Find hotels in Barcelona for 5 nights.",
        "Where can I stay in Lisbon?",
    ],
)


def create_agent(context_id: str) -> Agent:
    """Per-conversation agent factory (the A2AServer's recommended mode).

    Args:
        context_id: conversation identifier assigned by the A2A protocol.

    Returns:
        A fresh Strands Agent backed by Gemma via Ollama.
    """
    logger.info("Creating hotels agent for context_id=%s", context_id)

    ollama_model = OllamaModel(
        host=_config.ollama_host,
        model_id=_config.model_id,
        temperature=0.2,
    )

    return Agent(
        name="Hotels Agent",
        description=(
            "Specialist agent that searches accommodation options for a trip "
            "(destination, number of nights)."
        ),
        model=ollama_model,
        system_prompt=HOTELS_AGENT_SYSTEM_PROMPT,
        tools=[search_hotels],
        callback_handler=None,
    )


def build_server() -> A2AServer:
    """Build (without starting) the A2AServer. Separated so it can be tested."""
    return A2AServer(
        agent_factory=create_agent,
        host=_config.host,
        port=_config.port,
        skills=[HOTELS_SKILL],
    )


def main() -> None:
    logger.info(
        "Starting Hotels A2AServer at http://%s:%s (local model: %s via %s)",
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
