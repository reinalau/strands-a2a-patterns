"""Routing eval — deterministic, the heart of the A2A pattern.

This eval measures the orchestrator's routing DECISION, which is the whole point
of the privacy-aware-routing case: does it delegate to the local agent exactly
when the query is sensitive, and stay local (answer directly) when it is not?

It is deterministic (no LLM judge): we run the real orchestrator, capture which
tools it called, and check that trajectory with code-based evaluators:

- Sensitive query  -> the `handle_sensitive_query` tool MUST appear.  (ToolCalled)
- Generic query    -> that tool must NOT appear.                      (ToolNotCalled)

Requirements: GEMINI_API_KEY in .env (runs the real Gemini orchestrator). It does
NOT need the A2A server: the remote A2AAgent is mocked, because here we only care
about the routing decision, not the remote answer.

Run:
    python -m evals.eval_routing
"""

import sys
from unittest.mock import MagicMock, patch

from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator, ToolCalled
from strands_evals.types import EvaluationData, EvaluationOutput

import orchestrator.main as orch
from evals.dataset import load_cases
from evals.report_io import save_report

# The evals report uses emoji (📊). On Windows the default console encoding
# (cp1252) cannot print them and crashes at display time. Force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Name of the tool that performs the A2A delegation (must match the code).
DELEGATION_TOOL = "handle_sensitive_query"


class ToolNotCalled(Evaluator):
    """Custom deterministic evaluator: passes when a tool was NOT called.

    The SDK ships `ToolCalled` (positive case) but not its negation, which we
    need for generic queries that must be answered directly without delegating.
    """

    def __init__(self, tool_name: str, name: str | None = None):
        super().__init__(name=name)
        self.tool_name = tool_name

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        trajectory = evaluation_case.actual_trajectory or []
        called = self.tool_name in trajectory
        return [
            EvaluationOutput(
                score=0.0 if called else 1.0,
                test_pass=not called,
                reason=(
                    f"tool '{self.tool_name}' "
                    f"{'was called (should NOT have been)' if called else 'was not called'}"
                ),
            )
        ]

    async def evaluate_async(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        return self.evaluate(evaluation_case)


def _tools_called(agent) -> list[str]:
    """Extract the ordered list of tool names the agent invoked.

    Strands records tool invocations as `toolUse` blocks in the content of the
    assistant messages. We scan the message history and collect their names.
    """
    names: list[str] = []
    for message in agent.messages:
        for block in message.get("content", []) or []:
            if isinstance(block, dict) and "toolUse" in block:
                tool_name = block["toolUse"].get("name")
                if tool_name:
                    names.append(tool_name)
    return names


def routing_task(case: Case) -> dict:
    """Run the real orchestrator for one case and return its tool trajectory.

    The remote A2AAgent is mocked so the eval does not need the A2A server and
    stays fast/deterministic — we are testing the routing decision, not the
    remote answer.
    """
    orchestrator = orch.build_orchestrator()

    fake_result = MagicMock()
    fake_result.message = {"content": [{"text": "Example balance: $1,000 (simulated)."}]}

    with patch.object(orch, "_remote_agent", return_value=fake_result):
        result = orchestrator(case.input)

    return {
        "output": str(result),
        "trajectory": _tools_called(orchestrator),
    }


# Test cases live in evals/cases_routing.jsonl (data, not code) so you can edit
# them without touching this file. Each case is tagged "sensitive" or "generic".
CASES_FILE = "cases_routing.jsonl"


def main() -> None:
    cases = load_cases(CASES_FILE)

    # Sensitive cases: the delegation tool MUST have been called.
    sensitive_cases = [c for c in cases if c.metadata["category"] == "sensitive"]
    generic_cases = [c for c in cases if c.metadata["category"] == "generic"]

    print("=== Routing eval: sensitive queries (must delegate) ===")
    exp_sensitive = Experiment(
        cases=sensitive_cases,
        evaluators=[ToolCalled(DELEGATION_TOOL)],
    )
    report_sensitive = exp_sensitive.run_evaluations(routing_task)
    # display() prints the table and continues; run_display() would open an
    # interactive viewer that waits for keyboard input (q to quit).
    report_sensitive.display()
    print(f"Report saved to: {save_report(report_sensitive, 'routing_sensitive')}")

    print("\n=== Routing eval: generic queries (must NOT delegate) ===")
    exp_generic = Experiment(
        cases=generic_cases,
        evaluators=[ToolNotCalled(DELEGATION_TOOL)],
    )
    report_generic = exp_generic.run_evaluations(routing_task)
    report_generic.display()
    print(f"Report saved to: {save_report(report_generic, 'routing_generic')}")


if __name__ == "__main__":
    main()
