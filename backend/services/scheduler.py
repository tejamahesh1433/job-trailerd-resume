import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("main")

DATA_DIR = os.getenv("DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SCHEDULE_CONFIG_FILE = os.path.join(DATA_DIR, "daily_search_schedule.json")

SCHEDULE_TZ = ZoneInfo(os.getenv("SCHEDULE_TZ", "America/New_York"))
DEFAULT_HOUR = 10
DEFAULT_MINUTE = 0
DEFAULT_QUERY = "DevOps Engineer"
DEFAULT_PLATFORMS = ["linkedin", "dice", "indeed", "ziprecruiter"]
DEFAULT_WORK_TYPES = ["remote"]
DEFAULT_CONTRACT_TYPES = ["c2c", "c2h"]

_last_run_at = None
_last_run_result = None


def _load_config() -> dict:
    if os.path.exists(SCHEDULE_CONFIG_FILE):
        try:
            with open(SCHEDULE_CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"enabled": True, "hour": DEFAULT_HOUR, "minute": DEFAULT_MINUTE}


def _save_config(config: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SCHEDULE_CONFIG_FILE, "w") as f:
        json.dump(config, f)


def _next_run_at(now: datetime, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def get_schedule_info() -> dict:
    config = _load_config()
    now = datetime.now(SCHEDULE_TZ)
    next_run = _next_run_at(now, config.get("hour", DEFAULT_HOUR), config.get("minute", DEFAULT_MINUTE))
    return {
        "enabled": config.get("enabled", True),
        "hour": config.get("hour", DEFAULT_HOUR),
        "minute": config.get("minute", DEFAULT_MINUTE),
        "timezone": os.getenv("SCHEDULE_TZ", "America/New_York"),
        "next_run_at": next_run.isoformat() if config.get("enabled", True) else None,
        "last_run_at": _last_run_at,
        "last_run_result": _last_run_result,
    }


def set_schedule(
    enabled: bool,
    hour: int = DEFAULT_HOUR,
    minute: int = DEFAULT_MINUTE,
    query: str = None,
    platforms: list = None,
    work_types: list = None,
    contract_types: list = None,
):
    existing = _load_config()
    config = {
        "enabled": enabled,
        "hour": hour,
        "minute": minute,
        "query": query if query is not None else existing.get("query", DEFAULT_QUERY),
        "platforms": platforms if platforms is not None else existing.get("platforms", DEFAULT_PLATFORMS),
        "work_types": work_types if work_types is not None else existing.get("work_types", DEFAULT_WORK_TYPES),
        "contract_types": contract_types if contract_types is not None else existing.get("contract_types", DEFAULT_CONTRACT_TYPES),
    }
    _save_config(config)


def get_search_params() -> dict:
    """Return the saved search params (query, platforms, work_types, contract_types)
    falling back to defaults — single source of truth for both the scheduler loop
    and the Telegram /search command."""
    config = _load_config()
    return {
        "query": config.get("query", DEFAULT_QUERY),
        "platforms": config.get("platforms", DEFAULT_PLATFORMS),
        "work_types": config.get("work_types", DEFAULT_WORK_TYPES),
        "contract_types": config.get("contract_types", DEFAULT_CONTRACT_TYPES),
    }


async def daily_search_loop(run_search_fn):
    """Sleeps until the configured time (default 10:00 AM America/New_York) every day,
    then runs the Command Center search using the saved config params. Re-reads config
    on every iteration so changes take effect on the next tick without restarting."""
    global _last_run_at, _last_run_result
    while True:
        config = _load_config()
        hour = config.get("hour", DEFAULT_HOUR)
        minute = config.get("minute", DEFAULT_MINUTE)

        if not config.get("enabled", True):
            # Check back in an hour in case it gets re-enabled.
            await asyncio.sleep(3600)
            continue

        now = datetime.now(SCHEDULE_TZ)
        next_run = _next_run_at(now, hour, minute)
        sleep_seconds = (next_run - now).total_seconds()
        logger.info(f"Daily Command Center search scheduled for {next_run.isoformat()} "
                    f"(sleeping {sleep_seconds / 3600:.1f}h)")
        await asyncio.sleep(sleep_seconds)

        # Re-check enabled state in case it was turned off while sleeping.
        if not _load_config().get("enabled", True):
            continue

        try:
            params = get_search_params()
            logger.info(f"Running scheduled daily search: query={params['query']!r} platforms={params['platforms']}")
            result = await asyncio.to_thread(
                run_search_fn,
                params["query"], params["platforms"], params["work_types"], params["contract_types"],
            )
            _last_run_at = datetime.now(SCHEDULE_TZ).isoformat()
            _last_run_result = {"count": result.get("count", 0), "rejected_count": result.get("rejected_count", 0)}
            logger.info(f"Scheduled search complete: {_last_run_result}")
            try:
                from services.telegram_notifier import send_daily_digest
                send_daily_digest(result)
            except Exception as e:
                logger.warning(f"Failed to send Telegram daily digest: {e}")
        except Exception as e:
            logger.error(f"Scheduled daily search failed: {e}")
            _last_run_at = datetime.now(SCHEDULE_TZ).isoformat()
            _last_run_result = {"error": str(e)}
