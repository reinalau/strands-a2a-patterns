"""Remote A2A agent — processes sensitive queries 100% locally (Gemma / Ollama).

This process starts a Strands `A2AServer` that:
  1. Wraps a Strands `Agent` running Gemma via Ollama.
  2. Automatically publishes its agent card at /.well-known/agent-card.json.
  3. Serves A2A requests (JSON-RPC) at http://<A2A_HOST>:<A2A_PORT>.

The orchestrator (a separate process) talks to this server through an A2AAgent.
Nothing processed here leaves toward an external API: inference happens in the
local Ollama.

Run it in its own terminal:
    python -m remote_agent.server
"""

from strands import Agent
from strands.models.ollama import OllamaModel
from strands.multiagent.a2a import A2AServer

from common.config import load_remote_agent_config
from common.logging_config import setup_logging
from common.prompts import REMOTE_AGENT_SYSTEM_PROMPT
from remote_agent.bank_tools import (
    get_account_balance,
    get_account_holder,
    get_last_transactions,
)

logger = setup_logging("remote_agent.log", "remote_agent")

_config = load_remote_agent_config()


def create_agent(context_id: str) -> Agent:
    """Per-conversation agent factory (the A2AServer's recommended mode).

    The A2AServer calls this function once per `context_id` and reuses the
    returned agent for the following requests in that same conversation. This
    way, two different conversations never share history.

    Args:
        context_id: conversation identifier assigned by the A2A protocol.

    Returns:
        A fresh Strands Agent backed by Gemma via Ollama.
    """
    logger.info("Creating local agent for context_id=%s", context_id)

    ollama_model = OllamaModel(
        host=_config.ollama_host,
        model_id=_config.model_id,
        # Low temperature: we want deterministic, sober answers for a sensitive
        # data context, not creativity.
        temperature=0.2,
    )

    return Agent(
        name="Local Privacy Agent",
        description=(
            "Local agent that processes queries with sensitive data "
            "(balances, account numbers, personal identifiers) without the "
            "information leaving the machine."
        ),
        model=ollama_model,
        system_prompt=REMOTE_AGENT_SYSTEM_PROMPT,
        # Bank tools with fixed data: the agent looks up balances/transactions
        # instead of inventing them with the LLM (as a real agent would query
        # the bank's internal systems).
        tools=[get_account_balance, get_last_transactions, get_account_holder],
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
    )


def main() -> None:
    logger.info(
        "Starting A2AServer at http://%s:%s (local model: %s via %s)",
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
