"""Flights specialist — an A2A server exposing the `search_flights` skill.

This process starts a Strands `A2AServer` that:
  1. Wraps a Strands `Agent` running Gemma via Ollama.
  2. Publishes an agent card at /.well-known/agent-card.json advertising a
     single skill: searching flights. The orchestrator reads this card at
     runtime to decide whether to delegate flight searches here.
  3. Serves A2A requests (JSON-RPC) at http://<FLIGHTS_HOST>:<FLIGHTS_PORT>.

The `skills` we pass to A2AServer are what makes DYNAMIC DISCOVERY meaningful:
they are the human-readable description the orchestrator sees when it lists the
available agents, without any hardcoded mapping.

Run it in its own terminal:
    python -m remote_agents.flights_server
"""

from a2a.types import AgentSkill
from strands import Agent
from strands.models.ollama import OllamaModel
from strands.multiagent.a2a import A2AServer

from common.config import load_flights_config
from common.logging_config import setup_logging
from common.prompts import FLIGHTS_AGENT_SYSTEM_PROMPT
from remote_agents.travel_tools import search_flights

logger = setup_logging("flights_server.log", "flights_server")

_config = load_flights_config()

# Skill advertised in the agent card. The orchestrator discovers this text
# (name + description) at runtime and uses it to route flight-related subtasks
# here — nothing about this agent is hardcoded on the orchestrator side.
FLIGHTS_SKILL = AgentSkill(
    id="search_flights",
    name="Search Flights",
    description=(
        "Search available flight options for a route (origin, destination) and "
        "a travel month. Returns airlines, durations and round-trip prices."
    ),
    tags=["flights", "travel", "search"],
    examples=[
        "Find flights from Buenos Aires to Barcelona in March.",
        "What flights are there to Lisbon?",
    ],
)


def create_agent(context_id: str) -> Agent:
    """Per-conversation agent factory (the A2AServer's recommended mode).

    The A2AServer calls this once per `context_id` and reuses the returned agent
    for the following requests in that same conversation, so two conversations
    never share history.

    Args:
        context_id: conversation identifier assigned by the A2A protocol.

    Returns:
        A fresh Strands Agent backed by Gemma via Ollama.
    """
    logger.info("Creating flights agent for context_id=%s", context_id)

    ollama_model = OllamaModel(
        host=_config.ollama_host,
        model_id=_config.model_id,
        # Low temperature: we want deterministic, sober lookups, not creativity.
        temperature=0.2,
    )

    return Agent(
        name="Flights Agent",
        description=(
            "Specialist agent that searches flight options for a trip "
            "(origin, destination, month)."
        ),
        model=ollama_model,
        system_prompt=FLIGHTS_AGENT_SYSTEM_PROMPT,
        tools=[search_flights],
        # No callback handler: we don't want the server to print the stream
        # token by token; structured logging already covers traceability.
        callback_handler=None,
    )


def build_server() -> A2AServer:
    """Build (without starting) the A2AServer. Separated so it can be tested."""
    return A2AServer(
        agent_factory=create_agent,
        host=_config.host,
        port=_config.port,
        skills=[FLIGHTS_SKILL],
    )


def main() -> None:
    logger.info(
        "Starting Flights A2AServer at http://%s:%s (local model: %s via %s)",
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
