"""Real A2A integration test (full roundtrip), self-contained.

Unlike test_routing_logic.py, this test exercises the REAL A2A server
(remote_agent/server.py) and Ollama. You do NOT need to start the server by
hand: a pytest fixture launches it as a subprocess before the tests and shuts
it down afterwards.

It validates two things against the real server:

1. Discovery: the agent card is published and can be read (name + description).
2. Roundtrip: sending a query to the A2AAgent returns a non-empty response
   processed locally by Gemma.

Requirements: Ollama running with the model pulled (see the README). If the
server fails to come up within the timeout (e.g. Ollama is down), the tests are
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

from strands.agent.a2a_agent import A2AAgent

# Dedicated test host/port so we don't collide with a server the user may
# already have running on the default 9000.
_TEST_HOST = "127.0.0.1"
_TEST_PORT = "9010"
_SERVER_URL = f"http://{_TEST_HOST}:{_TEST_PORT}"
_AGENT_CARD_URL = f"{_SERVER_URL}/.well-known/agent-card.json"

# How long to wait for the server to publish its agent card before giving up.
_STARTUP_TIMEOUT_S = 45
_CASE_ROOT = Path(__file__).resolve().parent.parent


def _agent_card_ready() -> bool:
    """True once the server publishes its agent card."""
    try:
        with urllib.request.urlopen(_AGENT_CARD_URL, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="module")
def a2a_server():
    """Start remote_agent.server as a subprocess and tear it down at the end.

    Overrides A2A_HOST/A2A_PORT via the environment so the child server binds to
    the dedicated test port. If the server does not become reachable within the
    timeout, the whole module is skipped (rather than failing) — typically that
    means Ollama is not running.
    """
    env = {**os.environ, "A2A_HOST": _TEST_HOST, "A2A_PORT": _TEST_PORT}
    process = subprocess.Popen(
        [sys.executable, "-m", "remote_agent.server"],
        cwd=str(_CASE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + _STARTUP_TIMEOUT_S
    try:
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.skip("The A2A server process exited during startup.")
            if _agent_card_ready():
                break
            time.sleep(1)
        else:
            process.terminate()
            pytest.skip(
                f"The A2A server did not come up within {_STARTUP_TIMEOUT_S}s "
                "(is Ollama running with the model pulled?)."
            )

        yield _SERVER_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


async def test_agent_card_discovery(a2a_server):
    """The remote agent card must expose a name and description."""
    agent = A2AAgent(endpoint=a2a_server)
    card = await agent.get_agent_card()

    assert card.name, "The agent card must have a name"
    assert card.description, "The agent card must have a description"


def test_a2a_roundtrip_returns_response(a2a_server):
    """A real A2A request must return a non-empty response from Gemma."""
    agent = A2AAgent(endpoint=a2a_server)

    result = agent("I need the balance of my account 1234-5678-9, please.")
    text = result.message["content"][0]["text"]

    assert isinstance(text, str)
    assert text.strip(), "The remote agent's response should not be empty"
