"""Configuration loading and validation from environment variables (.env).

Centralizes reading the .env so the orchestrator and the three specialist
servers don't duplicate logic, and so we fail early with a clear message if
something critical is missing.

Unlike the privacy-aware-routing case (a single hardcoded remote agent), here
the orchestrator does NOT need to know each specialist's URL individually to
talk to it — it discovers capabilities at runtime. What it does need is the
LIST of URLs where those A2A servers live, so `A2AClientToolProvider` can fetch
their agent cards. That list is `SPECIALIST_AGENT_URLS`.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load the case's .env if present. Does not override already-set variables.
load_dotenv()


@dataclass(frozen=True)
class SpecialistAgentConfig:
    """Config shared by the three specialist server processes (Gemma / Ollama).

    Each server binds to its own host:port; the model backend (Ollama) is the
    same for all three.
    """

    ollama_host: str
    model_id: str
    host: str
    port: int


@dataclass(frozen=True)
class OrchestratorConfig:
    """Config for the orchestrator process (Gemini via LiteLLM).

    `specialist_agent_urls` is the list of A2A endpoints the orchestrator hands
    to `A2AClientToolProvider` for runtime discovery. Add or remove a specialist
    here and the orchestrator adapts without any code change.
    """

    gemini_api_key: str
    model_id: str
    specialist_agent_urls: list[str]
    temperature: float
    a2a_timeout: int


@dataclass(frozen=True)
class JudgeConfig:
    """Config for the LLM judge used by the evals (Gemini via LiteLLM).

    The judge is a separate concern from the orchestrator: it can use its own
    model and temperature, which is handy when the orchestrator's model is
    saturated and you want to point the judge at a more available one.
    """

    gemini_api_key: str
    model_id: str
    temperature: float


# Default host/port for each specialist. Kept here as a single source of truth
# so the servers, the orchestrator's discovery list and the tests stay aligned.
FLIGHTS_PORT = 9001
HOTELS_PORT = 9002
ITINERARY_PORT = 9003


def _require_gemini_key() -> str:
    """Read and validate GEMINI_API_KEY, failing early with a clear message."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your-gemini-api-key-here":
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Copy .env.example to .env and "
            "fill in your Google AI Studio API key "
            "(https://aistudio.google.com/api-keys)."
        )
    return api_key


def load_flights_config() -> SpecialistAgentConfig:
    return SpecialistAgentConfig(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model_id=os.getenv("REMOTE_MODEL_ID", "gemma4:e2b-it-qat"),
        host=os.getenv("FLIGHTS_HOST", "127.0.0.1"),
        port=int(os.getenv("FLIGHTS_PORT", str(FLIGHTS_PORT))),
    )


def load_hotels_config() -> SpecialistAgentConfig:
    return SpecialistAgentConfig(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model_id=os.getenv("REMOTE_MODEL_ID", "gemma4:e2b-it-qat"),
        host=os.getenv("HOTELS_HOST", "127.0.0.1"),
        port=int(os.getenv("HOTELS_PORT", str(HOTELS_PORT))),
    )


def load_itinerary_config() -> SpecialistAgentConfig:
    return SpecialistAgentConfig(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model_id=os.getenv("REMOTE_MODEL_ID", "gemma4:e2b-it-qat"),
        host=os.getenv("ITINERARY_HOST", "127.0.0.1"),
        port=int(os.getenv("ITINERARY_PORT", str(ITINERARY_PORT))),
    )


def _default_specialist_urls() -> list[str]:
    """Build the default discovery list from the individual specialist ports."""
    flights_port = os.getenv("FLIGHTS_PORT", str(FLIGHTS_PORT))
    hotels_port = os.getenv("HOTELS_PORT", str(HOTELS_PORT))
    itinerary_port = os.getenv("ITINERARY_PORT", str(ITINERARY_PORT))
    return [
        f"http://localhost:{flights_port}",
        f"http://localhost:{hotels_port}",
        f"http://localhost:{itinerary_port}",
    ]


def load_orchestrator_config() -> OrchestratorConfig:
    api_key = _require_gemini_key()

    # SPECIALIST_AGENT_URLS lets you override the discovery list explicitly
    # (comma-separated). If unset, we derive it from the specialist ports.
    urls_env = os.getenv("SPECIALIST_AGENT_URLS", "").strip()
    if urls_env:
        specialist_urls = [u.strip() for u in urls_env.split(",") if u.strip()]
    else:
        specialist_urls = _default_specialist_urls()

    return OrchestratorConfig(
        gemini_api_key=api_key,
        model_id=os.getenv("ORCHESTRATOR_MODEL_ID", "gemini/gemini-3.5-flash-lite"),
        specialist_agent_urls=specialist_urls,
        temperature=float(os.getenv("ORCHESTRATOR_TEMPERATURE", "1.0")),
        # Per-request A2A timeout (seconds). Local Gemma inference is slow, and
        # with three specialists sharing a single-parallel Ollama the requests
        # can queue. The default (300s) can be too short under that load, so we
        # make it configurable and default it higher.
        a2a_timeout=int(os.getenv("A2A_CLIENT_TIMEOUT", "600")),
    )


def load_judge_config() -> JudgeConfig:
    """Load the judge config, falling back to the orchestrator's model if the
    judge-specific vars are not set."""
    api_key = _require_gemini_key()
    return JudgeConfig(
        gemini_api_key=api_key,
        model_id=os.getenv(
            "JUDGE_MODEL_ID",
            os.getenv("ORCHESTRATOR_MODEL_ID", "gemini/gemini-3.5-flash-lite"),
        ),
        temperature=float(os.getenv("JUDGE_TEMPERATURE", "1.0")),
    )
