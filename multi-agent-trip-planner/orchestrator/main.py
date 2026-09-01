"""Orchestrator — Gemini via LiteLLM, with dynamic A2A agent discovery.

This process is the entry point of the use case. It receives an open travel
request and coordinates three specialist agents to build a full trip proposal.

Unlike the privacy-aware-routing case (a single, hardcoded remote agent), here
the orchestrator does NOT know each specialist individually. It is equipped with
`A2AClientToolProvider`, which exposes tools to:
  - list the discovered agents and read their agent cards (name + skills),
  - discover an extra agent by URL, and
  - send a task to a specific agent.

The provider is created once with `known_agent_urls` (the list of A2A servers to
look at). At runtime the model calls those tools to decide which specialist
handles each subtask — the routing is driven by the discovered agent cards, not
by hardcoded mappings.

Requires the three specialist servers to already be running. Run:
    python -m orchestrator.main            # interactive mode
    python -m orchestrator.main "query"    # single query
"""

import asyncio
import sys

from strands import Agent
from strands.models.litellm import LiteLLMModel
from strands_tools.a2a_client import A2AClientToolProvider

from common.config import load_orchestrator_config
from common.logging_config import setup_logging
from common.prompts import ORCHESTRATOR_SYSTEM_PROMPT

logger = setup_logging("orchestrator.log", "orchestrator")

_config = load_orchestrator_config()

# A2A tool provider pointed at the specialist servers. It exposes the discovery
# and delegation tools (a2a_list_discovered_agents, a2a_discover_agent,
# a2a_send_message) to the orchestrator agent. Created once and reused: the
# provider fetches and caches the agent cards on first use.
# The timeout is raised above the SDK default because local Gemma inference is
# slow and the three specialists may queue on a single-parallel Ollama.
_a2a_provider = A2AClientToolProvider(
    known_agent_urls=_config.specialist_agent_urls,
    timeout=_config.a2a_timeout,
)


def build_orchestrator() -> Agent:
    """Build the orchestrator Agent (Gemini + A2A discovery tools).

    Separated from execution so tests can build it without running a query.
    """
    logger.info(
        "Building orchestrator. Known specialist URLs for discovery: %s",
        _config.specialist_agent_urls,
    )

    model = LiteLLMModel(
        client_args={"api_key": _config.gemini_api_key},
        model_id=_config.model_id,
        params={
            # Temperature comes from the .env (ORCHESTRATOR_TEMPERATURE) and
            # defaults to 1.0. Google recommends temperature=1.0 for Gemini 3+:
            # lower values can cause infinite loops and degrade reasoning on
            # multi-step, tool-using tasks like this orchestrator. The knob stays
            # useful for the other providers LiteLLM supports (Anthropic, OpenAI,
            # Bedrock, etc.) if you swap ORCHESTRATOR_MODEL_ID.
            "temperature": _config.temperature,
            # Automatic retries on transient errors (e.g. 503 "high demand",
            # 429 rate limit). LiteLLM retries the completion up to num_retries
            # times with backoff before raising. Cloud APIs fail transiently, so
            # this makes the orchestrator noticeably more robust.
            "num_retries": 2,
        },
    )
    return Agent(
        name="Trip Planner Orchestrator",
        model=model,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        # The provider's `.tools` property yields the A2A discovery/delegation
        # tools. This is what lets the orchestrator find the specialists at
        # runtime instead of talking to a fixed endpoint.
        tools=_a2a_provider.tools,
        # Disable the default callback handler: we stream the answer ourselves
        # via stream_async (see run_once) to print it token by token. Leaving
        # the default handler on would print the same text a second time.
        callback_handler=None,
    )


async def run_once(orchestrator: Agent, query: str) -> str:
    """Stream a single query token by token and return the full response text.

    We iterate the agent's async event stream instead of calling it directly:
    - `event["data"]` carries each text chunk as it is generated; we print it
      immediately so the user sees the answer flow in real time.
    - the final `event["result"]` carries the AgentResult; we read the complete
      message from it and return it (useful for tests and for callers that need
      the string, not just the console output).
    """
    logger.info("Query received: %s", query)

    response = ""
    print("Assistant> ", end="", flush=True)
    async for event in orchestrator.stream_async(query):
        if "data" in event:
            print(event["data"], end="", flush=True)
        elif "result" in event:
            response = event["result"].message["content"][0]["text"]
    print()  # newline after the streamed answer

    logger.info("Final response to user emitted (%d chars)", len(response))
    return response


async def _interactive_loop(orchestrator: Agent) -> None:
    print("Trip-planning assistant. Type 'exit' to quit.\n")
    while True:
        try:
            query = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.lower() in {"exit", "quit", "salir"}:
            break
        if not query:
            continue
        await run_once(orchestrator, query)
        print()


async def main() -> None:
    orchestrator = build_orchestrator()

    # If the query is passed as an argument, resolve it a single time.
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        await run_once(orchestrator, query)
        return

    await _interactive_loop(orchestrator)


if __name__ == "__main__":
    asyncio.run(main())
