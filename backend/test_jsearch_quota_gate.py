"""
Verifies the JSearch 200/month free-tier quota gate in _run_command_center_search.
Isolated from real data (uses a temp DATA_DIR) and makes no real network calls
(requests.get and DDGS.text are mocked).

Run: python test_jsearch_quota_gate.py
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

# Must be set before importing main/database/usage_tracker so they pick up an
# isolated data dir instead of touching the real data/api_usage.json etc.
TMP_DATA_DIR = tempfile.mkdtemp(prefix="jsearch_quota_test_")
os.environ["DATA_DIR"] = TMP_DATA_DIR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
import database  # noqa: E402
from services import usage_tracker  # noqa: E402

database.init_db()
os.environ["RAPIDAPI_KEY"] = os.environ.get("RAPIDAPI_KEY") or "test-key"


def seed_jsearch_usage(count: int):
    """Directly writes `count` jsearch-api usage entries timestamped this month."""
    now = datetime.now().isoformat()
    data = {
        "calls": [
            {
                "timestamp": now,
                "model": "jsearch-api",
                "operation": "auto_search",
                "input_tokens": 1,
                "output_tokens": 0,
                "cost": 0,
            }
            for _ in range(count)
        ],
        "total_cost": 0.0,
    }
    usage_tracker._save_usage(data)


def fake_jsearch_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": []}
    return resp


def run_case(label: str, seeded_count: int):
    seed_jsearch_usage(seeded_count)
    jsearch_calls = {"count": 0}

    def fake_get(url, *args, **kwargs):
        if "jsearch.p.rapidapi.com" in url:
            jsearch_calls["count"] += 1
            return fake_jsearch_response()
        raise AssertionError(f"Unexpected non-JSearch requests.get call to {url}")

    with patch("requests.get", side_effect=fake_get), \
         patch.object(main, "DDGS") as mock_ddgs:
        mock_ddgs.return_value.text.return_value = []
        asyncio.run(main._run_command_center_search("DevOps Engineer", ["linkedin"], [], []))

    remaining_before_run = max(0, usage_tracker.JSEARCH_FREE_MONTHLY_LIMIT - seeded_count)
    print(f"[{label}] seeded={seeded_count} jsearch_requests_made={jsearch_calls['count']} "
          f"(quota remaining at start: {remaining_before_run})")
    return jsearch_calls["count"]


def main_test():
    limit = usage_tracker.JSEARCH_FREE_MONTHLY_LIMIT
    failures = []

    # Case A: fresh quota (0 used) -> JSearch should be called.
    calls_a = run_case("A: quota fresh", 0)
    if calls_a == 0:
        failures.append("Case A: expected JSearch to be called when quota is fresh, but it wasn't")

    # Case B: quota already exhausted (limit used) -> JSearch must NOT be called at all.
    calls_b = run_case("B: quota exhausted", limit)
    if calls_b != 0:
        failures.append(f"Case B: expected 0 JSearch calls once quota is exhausted, got {calls_b}")

    # Case C: quota nearly exhausted (limit - 3 used) -> run must stop within 3 more calls.
    remaining = 3
    calls_c = run_case("C: quota nearly exhausted", limit - remaining)
    if calls_c > remaining:
        failures.append(f"Case C: expected at most {remaining} JSearch calls once only "
                         f"{remaining} remained, got {calls_c}")

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASSED: JSearch quota gate behaves correctly in all cases.")


if __name__ == "__main__":
    main_test()
