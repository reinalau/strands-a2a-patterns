"""Shared pytest configuration.

Ensures the case root (multi-agent-trip-planner/) is on sys.path so that
`import common...`, `import orchestrator...` and `import remote_agents...` work
when running pytest from any location.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

_CASE_ROOT = Path(__file__).resolve().parent.parent
if str(_CASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CASE_ROOT))

# Load the .env so tests that depend on GEMINI_API_KEY (the orchestrator-level
# discovery test) can see it. Without this, os.getenv(...) in the skipif would
# not find the key even when the user has configured .env, and those tests would
# always be skipped.
load_dotenv(_CASE_ROOT / ".env")
