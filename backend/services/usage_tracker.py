import os
import json
from datetime import datetime, timedelta
from threading import Lock

DATA_DIR = os.getenv("DATA_DIR", "data")
USAGE_FILE = os.path.join(DATA_DIR, "api_usage.json")

_lock = Lock()

PRICING = {
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 10.00 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
}


def _load_usage() -> dict:
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    return {"calls": [], "total_cost": 0.0}


def _save_usage(data: dict):
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def log_api_call(model: str, operation: str, input_tokens: int = 0, output_tokens: int = 0):
    pricing = PRICING.get(model, {"input": 0, "output": 0})
    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])

    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "operation": operation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost, 6),
    }

    with _lock:
        data = _load_usage()
        data["calls"].append(entry)
        data["total_cost"] = round(data["total_cost"] + cost, 6)
        _save_usage(data)

    return cost


def get_usage_stats() -> dict:
    data = _load_usage()
    calls = data.get("calls", [])

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    today_calls = [c for c in calls if c["timestamp"].startswith(today_str)]
    week_calls = [c for c in calls if c["timestamp"] >= week_ago]
    month_calls = [c for c in calls if c["timestamp"] >= month_ago]

    def _summarize(call_list):
        total_cost = sum(c["cost"] for c in call_list)
        total_input = sum(c["input_tokens"] for c in call_list)
        total_output = sum(c["output_tokens"] for c in call_list)
        by_operation = {}
        by_model = {}
        for c in call_list:
            op = c["operation"]
            by_operation[op] = by_operation.get(op, 0) + 1
            m = c["model"]
            by_model[m] = {
                "calls": by_model.get(m, {}).get("calls", 0) + 1,
                "cost": round(by_model.get(m, {}).get("cost", 0) + c["cost"], 6),
            }
        return {
            "calls": len(call_list),
            "cost": round(total_cost, 4),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "by_operation": by_operation,
            "by_model": by_model,
        }

    # Daily breakdown for the last 7 days
    daily = {}
    for c in week_calls:
        day = c["timestamp"][:10]
        daily[day] = {
            "calls": daily.get(day, {}).get("calls", 0) + 1,
            "cost": round(daily.get(day, {}).get("cost", 0) + c["cost"], 6),
        }

    return {
        "today": _summarize(today_calls),
        "week": _summarize(week_calls),
        "month": _summarize(month_calls),
        "all_time": _summarize(calls),
        "daily_breakdown": daily,
        "projected_monthly": round(_summarize(today_calls)["cost"] * 30, 2),
    }
