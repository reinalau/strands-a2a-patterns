"""Configuration loading and validation from environment variables (.env).

Centralizes reading the .env so the server and orchestrator don't duplicate
logic, and so we fail early with a clear message if something critical is
missing.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load the case's .env if present. Does not override already-set variables.
load_dotenv()


@dataclass(frozen=True)
class RemoteAgentConfig:
    """Config for the server process (remote Gemma/Ollama agent)."""

    ollama_host: str
    model_id: str
    host: str
    port: int


@dataclass(frozen=True)
class OrchestratorConfig:
    """Config for the orchestrator process (Gemini via LiteLLM)."""

    gemini_api_key: str
    model_id: str
    remote_agent_url: str
    temperature: float


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


def load_remote_agent_config() -> RemoteAgentConfig:
    return RemoteAgentConfig(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        model_id=os.getenv("REMOTE_MODEL_ID", "gemma4:e2b-it-qat"),
        host=os.getenv("A2A_HOST", "127.0.0.1"),
        port=int(os.getenv("A2A_PORT", "9000")),
    )


def load_orchestrator_config() -> OrchestratorConfig:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your-gemini-api-key-here":
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Copy .env.example to .env and "
            "fill in your Google AI Studio API key "
            "(https://aistudio.google.com/api-keys)."
        )
    return OrchestratorConfig(
        gemini_api_key=api_key,
        model_id=os.getenv("ORCHESTRATOR_MODEL_ID", "gemini/gemini-2.5-flash"),
        remote_agent_url=os.getenv("REMOTE_AGENT_URL", "http://localhost:9000"),
        temperature=float(os.getenv("ORCHESTRATOR_TEMPERATURE", "0.3")),
    )


def load_judge_config() -> JudgeConfig:
    """Load the judge config, falling back to the orchestrator's model if the
    judge-specific vars are not set."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your-gemini-api-key-here":
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Copy .env.example to .env and "
            "fill in your Google AI Studio API key "
            "(https://aistudio.google.com/api-keys)."
        )
    return JudgeConfig(
        gemini_api_key=api_key,
        model_id=os.getenv(
            "JUDGE_MODEL_ID",
            os.getenv("ORCHESTRATOR_MODEL_ID", "gemini/gemini-2.5-flash"),
        ),
        temperature=float(os.getenv("JUDGE_TEMPERATURE", "1.0")),
    )
