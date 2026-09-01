"""Response-quality eval — LLM-as-a-judge (Gemini) with custom rubrics.

While eval_routing.py checks the *decision* (delegate or not), this eval checks
the *quality of the delegated answer*: when the local agent handles a sensitive
query, is the reply correct and grounded in the tool data — not invented?

It runs the FULL A2A flow (orchestrator -> A2A -> remote Gemma agent -> tools)
and scores each answer with two `OutputEvaluator` instances, using Gemini as the
judge (configured in evals/judge.py, not Bedrock):

- Correctness rubric -> does the answer contain the correct value from the
  reference (expected_output)?
- Faithfulness rubric -> is the answer grounded, with no invented numbers, and
  not an evasion/refusal?

Why OutputEvaluator (and not CorrectnessEvaluator/FaithfulnessEvaluator): those
are TRACE-level evaluators that require an execution Session (telemetry). In this
case the agent under test runs in a SEPARATE process (the A2A server), so its
spans are not available in the eval process. OutputEvaluator works at the OUTPUT
level (just the text + the reference), which is exactly what we can capture
across the A2A boundary.

Note: with the small local model (gemma4:e2b-it-qat) the tool call is
intermittent — sometimes the agent evades instead of calling the bank tool. When
that happens these evals correctly score the answer low. That is a genuine
finding surfaced by evaluation, not a bug in the eval.

Requirements:
- GEMINI_API_KEY in .env (for both the orchestrator and the judge).
- Ollama running with the model pulled.
The A2A server is started automatically as a subprocess (like the integration
test); if it does not come up, the eval exits with a clear message.

Run:
    python -m evals.eval_response_quality
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from strands_evals import Case, Experiment

import orchestrator.main as orch
from evals.dataset import load_cases
from evals.judge import RetryingOutputEvaluator, build_judge_model
from evals.report_io import save_report

# The evals report uses emoji (📊). On Windows the default console encoding
# (cp1252) cannot print them and crashes at display time. Force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_TEST_HOST = "127.0.0.1"
_TEST_PORT = "9011"
_SERVER_URL = f"http://{_TEST_HOST}:{_TEST_PORT}"
_AGENT_CARD_URL = f"{_SERVER_URL}/.well-known/agent-card.json"
_STARTUP_TIMEOUT_S = 45
_CASE_ROOT = Path(__file__).resolve().parent.parent


def _agent_card_ready() -> bool:
    try:
        with urllib.request.urlopen(_AGENT_CARD_URL, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _start_server() -> subprocess.Popen:
    """Start the A2A server as a subprocess and wait until it is reachable."""
    env = {**os.environ, "A2A_HOST": _TEST_HOST, "A2A_PORT": _TEST_PORT}
    process = subprocess.Popen(
        [sys.executable, "-m", "remote_agent.server"],
        cwd=str(_CASE_ROOT),
        env=env,
    )
    deadline = time.time() + _STARTUP_TIMEOUT_S
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The A2A server process exited during startup.")
        if _agent_card_ready():
            return process
        time.sleep(1)
    process.terminate()
    raise RuntimeError(
        f"The A2A server did not come up within {_STARTUP_TIMEOUT_S}s "
        "(is Ollama running with the model pulled?)."
    )


def quality_task(case: Case) -> dict:
    """Run the full flow (orchestrator -> A2A -> Gemma) and return the answer."""
    # Point the orchestrator's remote agent at the test server for this run.
    orch._remote_agent = orch.A2AAgent(endpoint=_SERVER_URL, name="local_privacy_agent")
    orchestrator = orch.build_orchestrator()
    result = orchestrator(case.input)
    return {"output": str(result)}


# Test cases (with expected_output as reference) live in
# evals/cases_response_quality.jsonl. The expected values come from the mock
# bank (remote_agent/bank_tools.py). Edit the data file, not this code.
CASES_FILE = "cases_response_quality.jsonl"


def main() -> None:
    cases = load_cases(CASES_FILE)

    judge = build_judge_model()

    correctness_rubric = (
        "Compare the Output against the ExpectedOutput. "
        "Score 1.0 if the Output states the same key fact as the ExpectedOutput "
        "(e.g. the same account balance amount or the same account holder name), "
        "ignoring differences in language, wording or formatting. "
        "Score 0.0 if the value is missing, different, or the answer is an "
        "evasion/refusal that does not provide the requested data."
    )
    faithfulness_rubric = (
        "Judge whether the Output is grounded in real account data. "
        "Score 1.0 only if the Output provides the requested account data and it "
        "matches the ExpectedOutput. "
        "Score 0.0 if the Output invents a value that differs from the "
        "ExpectedOutput, or if it evades/refuses instead of giving the data "
        "(e.g. 'technical error', 'contact us through official channels'). "
        "An evasion is NOT faithful because it fails to deliver the grounded data."
    )

    evaluators = [
        RetryingOutputEvaluator(rubric=correctness_rubric, model=judge, name="Correctness"),
        RetryingOutputEvaluator(rubric=faithfulness_rubric, model=judge, name="Faithfulness"),
    ]

    print("Starting A2A server for the eval...")
    server = _start_server()
    try:
        experiment = Experiment(cases=cases, evaluators=evaluators)
        report = experiment.run_evaluations(quality_task)
        print("\n=== Response-quality eval (LLM judge: Gemini) ===")
        # display() prints the table and continues; run_display() would wait for
        # interactive keyboard input.
        report.display()
        print(f"Report saved to: {save_report(report, 'response_quality')}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
