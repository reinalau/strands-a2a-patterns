"""Response-quality eval — LLM-as-a-judge (Gemini) with custom rubrics.

While eval_discovery.py checks the *decision* (discover then delegate), this eval
checks the *quality of the final trip proposal*: after the orchestrator discovers
the specialists and delegates flights/hotels/itinerary, is the integrated answer
correct and grounded in the tool data — not invented?

It runs the FULL A2A flow (orchestrator -> discovery -> the three remote Gemma
agents -> tools) and scores each answer with two `OutputEvaluator` instances,
using Gemini as the judge (configured in evals/judge.py, not Bedrock):

- Correctness rubric  -> does the answer include the key facts from the
  reference (expected_output), e.g. the destination's real highlights or a
  plausible flight/hotel from the mock data?
- Faithfulness rubric -> is the answer grounded in the tool data, with no
  invented flights/hotels/attractions, and not an evasion/refusal?

Why OutputEvaluator (and not CorrectnessEvaluator/FaithfulnessEvaluator): those
are TRACE-level evaluators that require an execution Session (telemetry). Here
the specialists run in SEPARATE processes (the A2A servers), so their spans are
not available in the eval process. OutputEvaluator works at the OUTPUT level
(just the text + the reference), which is exactly what we can capture across the
A2A boundary.

Note: with the small local model (gemma4:e2b-it-qat) the tool call is
intermittent — sometimes an agent evades instead of calling its tool. When that
happens these evals correctly score the answer low. That is a genuine finding
surfaced by evaluation, not a bug in the eval.

Requirements:
- GEMINI_API_KEY in .env (for both the orchestrator and the judge).
- Ollama running with the model pulled.
The three A2A servers are started automatically as subprocesses (like the
integration test); if they do not come up, the eval exits with a clear message.

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

# The evals report uses emoji. On Windows the default console encoding (cp1252)
# cannot print them and crashes at display time. Force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Dedicated test host/ports so we don't collide with servers the user may
# already have running on the default 9001/9002/9003.
_TEST_HOST = "127.0.0.1"
_FLIGHTS_PORT = "9201"
_HOTELS_PORT = "9202"
_ITINERARY_PORT = "9203"

_FLIGHTS_URL = f"http://{_TEST_HOST}:{_FLIGHTS_PORT}"
_HOTELS_URL = f"http://{_TEST_HOST}:{_HOTELS_PORT}"
_ITINERARY_URL = f"http://{_TEST_HOST}:{_ITINERARY_PORT}"
_ALL_URLS = [_FLIGHTS_URL, _HOTELS_URL, _ITINERARY_URL]

_STARTUP_TIMEOUT_S = 60
_CASE_ROOT = Path(__file__).resolve().parent.parent

# Each specialist: (module to run, env var overriding its port, its test port).
_SPECIALISTS = [
    ("remote_agents.flights_server", "FLIGHTS_PORT", _FLIGHTS_PORT),
    ("remote_agents.hotels_server", "HOTELS_PORT", _HOTELS_PORT),
    ("remote_agents.itinerary_server", "ITINERARY_PORT", _ITINERARY_PORT),
]


def _agent_card_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/.well-known/agent-card.json", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _start_servers() -> list[subprocess.Popen]:
    """Start the three A2A servers as subprocesses and wait until all reachable."""
    processes: list[subprocess.Popen] = []
    for module, port_var, port in _SPECIALISTS:
        env = {**os.environ, port_var: port, "A2A_HOST": _TEST_HOST}
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", module],
                cwd=str(_CASE_ROOT),
                env=env,
            )
        )

    deadline = time.time() + _STARTUP_TIMEOUT_S
    while time.time() < deadline:
        if any(p.poll() is not None for p in processes):
            _terminate(processes)
            raise RuntimeError("A specialist server process exited during startup.")
        if all(_agent_card_ready(url) for url in _ALL_URLS):
            return processes
        time.sleep(1)

    _terminate(processes)
    raise RuntimeError(
        f"The A2A servers did not all come up within {_STARTUP_TIMEOUT_S}s "
        "(is Ollama running with the model pulled?)."
    )


def _terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def quality_task(case: Case) -> dict:
    """Run the full flow (orchestrator -> discovery -> the three Gemma agents)."""
    # Point the orchestrator's provider at the test servers for this run. Reuse
    # the configured A2A timeout (raised above the SDK default) because this eval
    # chains three slow local Gemma delegations (flights + hotels + itinerary),
    # which can easily exceed the default 300s per request.
    orch._a2a_provider = orch.A2AClientToolProvider(
        known_agent_urls=list(_ALL_URLS),
        timeout=orch._config.a2a_timeout,
    )
    orchestrator = orch.build_orchestrator()
    result = orchestrator(case.input)
    return {"output": str(result)}


# Test cases (with expected_output as reference) live in
# evals/cases_response_quality.jsonl. The expected values come from the mock
# travel data (remote_agents/travel_tools.py). Edit the data file, not this code.
CASES_FILE = "cases_response_quality.jsonl"


def main() -> None:
    cases = load_cases(CASES_FILE)

    judge = build_judge_model()

    correctness_rubric = (
        "Compare the Output against the ExpectedOutput. "
        "Score 1.0 if the Output includes the same key facts as the "
        "ExpectedOutput (e.g. real points of interest of the destination, or a "
        "plausible flight/hotel), ignoring differences in language, wording or "
        "formatting. "
        "Score 0.0 if those facts are missing, clearly different, or the answer "
        "is an evasion/refusal that does not provide a trip proposal."
    )
    faithfulness_rubric = (
        "Judge whether the Output is grounded in real travel data. "
        "Score 1.0 only if the Output provides a trip proposal (flight, hotel "
        "and/or itinerary) consistent with the ExpectedOutput. "
        "Score 0.0 if the Output invents attractions/flights/hotels that differ "
        "from the ExpectedOutput, or if it evades/refuses instead of planning "
        "(e.g. 'I cannot help', 'contact an agency'). "
        "An evasion is NOT faithful because it fails to deliver the grounded data."
    )

    evaluators = [
        RetryingOutputEvaluator(rubric=correctness_rubric, model=judge, name="Correctness"),
        RetryingOutputEvaluator(rubric=faithfulness_rubric, model=judge, name="Faithfulness"),
    ]

    print("Starting the three A2A servers for the eval...")
    servers = _start_servers()
    try:
        experiment = Experiment(cases=cases, evaluators=evaluators)
        report = experiment.run_evaluations(quality_task)
        print("\n=== Response-quality eval (LLM judge: Gemini) ===")
        # display() prints the table and continues; run_display() would wait for
        # interactive keyboard input.
        report.display()
        print(f"Report saved to: {save_report(report, 'response_quality')}")
    finally:
        _terminate(servers)


if __name__ == "__main__":
    main()
