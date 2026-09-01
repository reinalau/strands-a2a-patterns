"""Helper to persist evaluation reports to disk.

Besides printing the report to the console, we save it as JSON under
evals/outputs/ so each run is kept for later inspection, diffing, or attaching
to the article. Files are timestamped to avoid overwriting previous runs.
"""

from datetime import datetime
from pathlib import Path

from strands_evals import EvaluationReport

_OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def save_report(report: EvaluationReport, name: str) -> Path:
    """Save an evaluation report as timestamped JSON under evals/outputs/.

    Args:
        report: the report returned by Experiment.run_evaluations(...).
        name: short label for the run (e.g. "discovery").

    Returns:
        The path of the written file.
    """
    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _OUTPUTS_DIR / f"{name}_{timestamp}.json"
    report.to_file(str(path))
    return path
