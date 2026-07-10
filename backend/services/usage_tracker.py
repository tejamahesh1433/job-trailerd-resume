import os
import json
from datetime import datetime, timedelta
from threading import Lock

DATA_DIR = os.getenv("DATA_DIR", "data")
USAGE_FILE = os.path.join(DATA_DIR, "api_usage.json")

JSEARCH_FREE_MONTHLY_LIMIT = 200

_lock = Lock()

# ESTIMATED rates below, not pulled from a live pricing API. "-latest" aliases resolve
# to whatever model generation Google currently routes them to (confirmed via ListModels
# that the account has access to gemini-3.x models too), so the actual cost per call can
# drift without any code change here. Treat Usage panel dollar figures as directional,
# not exact — re-check https://ai.google.dev/gemini-api/docs/pricing periodically and
# update these numbers if they've moved.
PRICING = {
    "gemini-pro-latest": {"input": 1.25 / 1_000_000, "output": 10.00 / 1_000_000},  # estimate, proxied from 2.5-pro rate
    "gemini-flash-latest": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},  # estimate, proxied from 2.5-flash rate
    "gemini-flash-lite-latest": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},  # estimate, proxied from 2.5-flash-lite rate
    # Decommissioned dated model names — kept only so historical usage-log rows (logged
    # before the -latest migration) still price correctly when displayed.
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 10.00 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "claude-3-haiku-20240307": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-sonnet-5": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "jsearch-api": {"input": 0, "output": 0}, # Free up to 200 searches/month on RapidAPI's free tier
}


def _load_usage() -> dict:
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # log_api_call can run on a background executor thread (e.g. Telegram-
            # triggered AI calls) while a request thread reads this file — an unlucky
            # interleaving can catch a partially-written file. Treat it the same as a
            # missing file rather than 500ing the usage endpoint.
            return {"calls": [], "total_cost": 0.0}
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
    with _lock:
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

    month_prefix = now.strftime("%Y-%m")
    jsearch_used = sum(
        1 for c in calls
        if c["model"] == "jsearch-api" and c["timestamp"].startswith(month_prefix)
    )

    return {
        "today": _summarize(today_calls),
        "week": _summarize(week_calls),
        "month": _summarize(month_calls),
        "all_time": _summarize(calls),
        "daily_breakdown": daily,
        "projected_monthly": round(_summarize(today_calls)["cost"] * 30, 2),
        "jsearch_quota": {
            "used": jsearch_used,
            "limit": JSEARCH_FREE_MONTHLY_LIMIT,
            "remaining": max(0, JSEARCH_FREE_MONTHLY_LIMIT - jsearch_used),
        },
    }
