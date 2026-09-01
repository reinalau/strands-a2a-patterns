"""Real A2A integration test (full discovery + roundtrip), self-contained.

Unlike test_discovery.py, this test exercises the REAL A2A servers
(remote_agents/*.py) and Ollama. You do NOT need to start the servers by hand:
a pytest fixture launches the three of them as subprocesses before the tests and
shuts them down afterwards.

It validates two things against the real servers:

1. Discovery: the orchestrator's A2AClientToolProvider can fetch the three agent
   cards, each exposing a name, description and its skill.
2. Roundtrip: sending a task to one specialist (the flights agent) via the
   provider returns a non-empty response processed locally by Gemma.

Requirements: Ollama running with the model pulled (see the README). If the
servers fail to come up within the timeout (e.g. Ollama is down), the tests are
skipped instead of failing.

How to run it:
    pytest tests/test_a2a_integration.py -v
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from strands_tools.a2a_client import A2AClientToolProvider

# Dedicated test host/ports so we don't collide with servers the user may
# already have running on the default 9001/9002/9003.
_TEST_HOST = "127.0.0.1"
_FLIGHTS_PORT = "9101"
_HOTELS_PORT = "9102"
_ITINERARY_PORT = "9103"

_FLIGHTS_URL = f"http://{_TEST_HOST}:{_FLIGHTS_PORT}"
_HOTELS_URL = f"http://{_TEST_HOST}:{_HOTELS_PORT}"
_ITINERARY_URL = f"http://{_TEST_HOST}:{_ITINERARY_PORT}"
_ALL_URLS = [_FLIGHTS_URL, _HOTELS_URL, _ITINERARY_URL]

# How long to wait for every server to publish its agent card before giving up.
_STARTUP_TIMEOUT_S = 60
# Per-request A2A timeout for the roundtrip. Local Gemma inference is slow, so we
# use a generous value well above the SDK default (300s) to avoid a false
# failure when the model takes several minutes to answer.
_A2A_REQUEST_TIMEOUT_S = 900
_CASE_ROOT = Path(__file__).resolve().parent.parent

# Each specialist: (module to run, env var overriding its port, its test port).
_SPECIALISTS = [
    ("remote_agents.flights_server", "FLIGHTS_PORT", _FLIGHTS_PORT),
    ("remote_agents.hotels_server", "HOTELS_PORT", _HOTELS_PORT),
    ("remote_agents.itinerary_server", "ITINERARY_PORT", _ITINERARY_PORT),
]


def _agent_card_ready(url: str) -> bool:
    """True once the server at `url` publishes its agent card."""
    try:
        with urllib.request.urlopen(f"{url}/.well-known/agent-card.json", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="module")
def a2a_servers():
    """Start the three specialist servers as subprocesses and tear them down.

    Each server binds to its dedicated test port (via the *_PORT env var). If any
    of them does not become reachable within the timeout, the whole module is
    skipped (rather than failing) — typically that means Ollama is not running.
    """
    processes: list[subprocess.Popen] = []
    for module, port_var, port in _SPECIALISTS:
        env = {**os.environ, port_var: port, "A2A_HOST": _TEST_HOST}
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", module],
                cwd=str(_CASE_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        )

    def _terminate_all() -> None:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    deadline = time.time() + _STARTUP_TIMEOUT_S
    try:
        while time.time() < deadline:
            if any(p.poll() is not None for p in processes):
                _terminate_all()
                pytest.skip("A specialist server process exited during startup.")
            if all(_agent_card_ready(url) for url in _ALL_URLS):
                break
            time.sleep(1)
        else:
            _terminate_all()
            pytest.skip(
                f"The A2A servers did not all come up within {_STARTUP_TIMEOUT_S}s "
                "(is Ollama running with the model pulled?)."
            )

        yield _ALL_URLS
    finally:
        _terminate_all()


async def test_discovers_all_three_agent_cards(a2a_servers):
    """The provider must discover the three specialists, each with a name/desc."""
    provider = A2AClientToolProvider(known_agent_urls=list(a2a_servers))

    result = await provider._list_discovered_agents()

    assert result["status"] == "success"
    assert result["total_count"] == 3, f"Expected 3 agents, got {result['total_count']}"
    for agent_card in result["agents"]:
        assert agent_card.get("name"), "Each agent card must have a name"
        assert agent_card.get("description"), "Each agent card must have a description"


async def test_a2a_roundtrip_returns_response(a2a_servers):
    """A real A2A request to the flights specialist must return a non-empty reply.

    We call the provider's `_send_message` (the async logic behind the
    `a2a_send_message` tool) directly, which keeps the test simple and does not
    depend on the Strands tool-streaming internals.

    A generous per-request timeout is used because local Gemma inference can take
    several minutes; the SDK default (300s) is often too short here.
    """
    provider = A2AClientToolProvider(
        known_agent_urls=list(a2a_servers),
        timeout=_A2A_REQUEST_TIMEOUT_S,
    )

    tool_result = await provider._send_message(
        message_text="Find flights from Buenos Aires to Barcelona in March.",
        target_agent_url=_FLIGHTS_URL,
    )

    assert tool_result["status"] == "success"
    assert tool_result["response"], "The specialist's response should not be empty"
