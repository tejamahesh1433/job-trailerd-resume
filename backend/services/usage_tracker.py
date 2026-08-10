import logging
import os
import json
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger("main")

DATA_DIR = os.getenv("DATA_DIR", "data")
USAGE_FILE = os.path.join(DATA_DIR, "api_usage.json")
QUOTA_ALERT_FILE = os.path.join(DATA_DIR, "quota_alerts_sent.json")

JSEARCH_FREE_MONTHLY_LIMIT = 200
# Fire a one-time Telegram warning per threshold per calendar month, so a quota
# nearing exhaustion doesn't silently break the next auto-search run.
JSEARCH_ALERT_THRESHOLDS = (80, 95)

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

    if model == "jsearch-api":
        _maybe_send_jsearch_quota_alert()

    return cost


def _jsearch_used_this_month(calls: list) -> int:
    month_prefix = datetime.now().strftime("%Y-%m")
    return sum(
        1 for c in calls
        if c["model"] == "jsearch-api" and c["timestamp"].startswith(month_prefix)
    )


def get_jsearch_usage_this_month() -> int:
    with _lock:
        data = _load_usage()
    return _jsearch_used_this_month(data.get("calls", []))


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

    jsearch_used = _jsearch_used_this_month(calls)

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


def _load_quota_alerts() -> dict:
    if os.path.exists(QUOTA_ALERT_FILE):
        try:
            with open(QUOTA_ALERT_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_quota_alerts(data: dict):
    os.makedirs(os.path.dirname(QUOTA_ALERT_FILE), exist_ok=True)
    with open(QUOTA_ALERT_FILE, "w") as f:
        json.dump(data, f)


def _maybe_send_jsearch_quota_alert():
    """Best-effort, one-time-per-threshold-per-month Telegram warning as JSearch's
    free-tier monthly cap gets close, so it doesn't just silently start failing
    auto-search runs. Never raises — a Telegram/state-file hiccup here must not
    break the JSearch call that triggered it."""
    try:
        month = datetime.now().strftime("%Y-%m")
        with _lock:
            data = _load_usage()
        used = _jsearch_used_this_month(data.get("calls", []))
        pct = int((used / JSEARCH_FREE_MONTHLY_LIMIT) * 100)

        crossed = [t for t in JSEARCH_ALERT_THRESHOLDS if pct >= t]
        if not crossed:
            return

        alerts = _load_quota_alerts()
        jsearch_alerts = alerts.get("jsearch", {})
        if jsearch_alerts.get("month") != month:
            jsearch_alerts = {"month": month, "thresholds_sent": []}
        already_sent = set(jsearch_alerts.get("thresholds_sent", []))

        new_thresholds = [t for t in crossed if t not in already_sent]
        if not new_thresholds:
            return

        highest = max(new_thresholds)
        from services import telegram_service
        if telegram_service.is_configured():
            chat_ids = telegram_service.get_known_chat_ids()
            remaining = max(0, JSEARCH_FREE_MONTHLY_LIMIT - used)
            message = (
                f"JSearch quota warning: {used}/{JSEARCH_FREE_MONTHLY_LIMIT} free searches "
                f"used this month ({highest}%+, {remaining} remaining)."
            )
            for chat_id in chat_ids:
                telegram_service.send_message_sync(chat_id, message)

        jsearch_alerts["thresholds_sent"] = sorted(already_sent | set(new_thresholds))
        alerts["jsearch"] = jsearch_alerts
        _save_quota_alerts(alerts)
    except Exception as e:
        logger.warning(f"Failed to send JSearch quota alert: {e}")
