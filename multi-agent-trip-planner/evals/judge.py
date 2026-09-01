"""Shared LLM judge for the evals of this case.

The Strands Evals SDK defaults its LLM-as-a-judge evaluators to Amazon Bedrock
(Claude). Since this project is explicitly "no AWS account required", we point
the judge at Gemini via LiteLLM instead — the same provider the orchestrator
already uses.

The judge model is what SCORES the responses (Correctness, Faithfulness, ...),
not the agent under test. Reusing Gemini keeps the whole project on a single,
free-tier-friendly credential.
"""

import time

from strands.models.litellm import LiteLLMModel
from strands_evals.evaluators import OutputEvaluator
from strands_evals.types import EvaluationData, EvaluationOutput

from common.config import load_judge_config

_config = load_judge_config()

# Errors from the judge API that are transient and worth retrying (mostly the
# 503 "high demand" that Gemini returns under load). Matched by substring on the
# exception text, since LiteLLM wraps them in several layers.
_TRANSIENT_MARKERS = ("503", "ServiceUnavailable", "high demand", "UNAVAILABLE")


def build_judge_model() -> LiteLLMModel:
    """Return a LiteLLMModel (Gemini) to use as the LLM judge in evaluators.

    Model id and temperature come from the .env (JUDGE_MODEL_ID / JUDGE_TEMPERATURE),
    falling back to the orchestrator's model. Keeping the judge configurable lets
    you point it at a more available model when the orchestrator's one is
    saturated (503). Default temperature 1.0, which Google recommends for
    Gemini 3+ (lower values degrade reasoning) — relevant for a judge.
    """
    return LiteLLMModel(
        client_args={"api_key": _config.gemini_api_key},
        model_id=_config.model_id,
        params={"temperature": _config.temperature},
    )


class RetryingOutputEvaluator(OutputEvaluator):
    """OutputEvaluator that retries on transient judge-API errors.

    The evaluator runs the judge through a Strands Agent, which always streams
    internally. A transient 503 from Gemini therefore surfaces mid-stream, where
    LiteLLM's own `num_retries` cannot recover it. To keep reports clean (so a
    0.0 means "the answer was bad", not "the judge API hiccupped"), we retry the
    whole evaluate() call a few times with backoff when the error looks transient.
    """

    def __init__(self, *args, max_retries: int = 2, backoff_s: float = 3.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_retries = max_retries
        self._backoff_s = backoff_s

    def _is_transient(self, error: Exception) -> bool:
        text = str(error)
        return any(marker in text for marker in _TRANSIENT_MARKERS)

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return super().evaluate(evaluation_case)
            except Exception as error:  # noqa: BLE001 - we re-raise non-transient below
                if not self._is_transient(error) or attempt == self._max_retries:
                    raise
                last_error = error
                time.sleep(self._backoff_s * (attempt + 1))
        # Unreachable, but keeps type checkers happy.
        raise last_error  # type: ignore[misc]
