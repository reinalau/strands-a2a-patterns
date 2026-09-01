"""Loader for eval test cases stored as JSONL data files.

Keeping the test cases OUT of the eval code (in .jsonl files next to it) means
you can add, edit or remove cases without touching the evaluation logic — the
recommended way to manage evaluation datasets. Each line of the file is one JSON
object with the fields of a `Case` (name, input, optional expected_output,
metadata, ...).
"""

import json
from pathlib import Path

from strands_evals import Case

_EVALS_DIR = Path(__file__).resolve().parent


def load_cases(filename: str) -> list[Case]:
    """Load a list of Case objects from a JSONL file inside evals/.

    Args:
        filename: name of the .jsonl file (e.g. "cases_routing.jsonl").

    Returns:
        The cases parsed from the file, in order.
    """
    path = _EVALS_DIR / filename
    cases: list[Case] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(Case(**json.loads(line)))
    return cases
