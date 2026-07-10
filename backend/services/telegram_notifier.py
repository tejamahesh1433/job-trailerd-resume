import os
import json
import asyncio
import logging

logger = logging.getLogger("main")

DATA_DIR = os.getenv("DATA_DIR", "data")
NOTIFIED_IDS_FILE = os.path.join(DATA_DIR, "telegram_notified_ids.json")

SECTION_LABELS = {
    'needing_description': 'Jobs Needing Description',
    'ready_to_tailor': 'Ready to Tailor',
    'cover_letters_waiting': 'Cover Letters Waiting',
    'email_drafts_waiting': 'Email Drafts Waiting',
    'tailored_not_applied': 'Tailored, Not Applied',
    'follow_ups_due': 'Follow-ups Due',
}


def _truncate(text: str, max_len: int = 50) -> str:
    """Some legacy records store the FULL scraped job text in the 'title' field, not a
    short title — without this, a single item can turn into a multi-KB wall of text."""
    text = (text or '').strip().split('\n')[0]
    return text[:max_len].strip() + '...' if len(text) > max_len else text


def _load_notified() -> dict:
    if os.path.exists(NOTIFIED_IDS_FILE):
        try:
            with open(NOTIFIED_IDS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_notified(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NOTIFIED_IDS_FILE, "w") as f:
        json.dump(data, f)


def notify_new_action_items():
    """Diff the current Action Queue against what's already been pushed to Telegram,
    and send a message for anything new — a job entering 'ready to tailor', a
    follow-up becoming due, a cover letter generated through the UI, etc. Best-effort:
    never raises, so a Telegram hiccup can't break whatever called this (auto-search,
    the periodic background check)."""
    try:
        from services import telegram_service
        if not telegram_service.is_configured():
            return
        chat_ids = telegram_service.get_known_chat_ids()
        if not chat_ids:
            return

        from database import get_action_queue
        queue = get_action_queue(item_limit=50)
        notified = _load_notified()
        new_lines = []
        changed = False

        for section_key, label in SECTION_LABELS.items():
            bucket = queue.get(section_key) or {'items': []}
            already = set(notified.get(section_key, []))
            new_items = [item for item in bucket['items'] if item['id'] not in already]
            if not new_items:
                continue
            changed = True
            notified[section_key] = sorted(already | {item['id'] for item in new_items})
            for item in new_items[:5]:  # cap per-section spam in one message
                company = item.get('company') or 'Unknown'
                title = _truncate(item.get('title') or '')
                new_lines.append(f"- [{label}] {company}" + (f" - {title}" if title else ""))

        if not changed or not new_lines:
            return

        _save_notified(notified)
        message = "New Command Center activity:\n\n" + "\n".join(new_lines[:20])
        if len(new_lines) > 20:
            message += f"\n...and {len(new_lines) - 20} more."

        for chat_id in chat_ids:
            telegram_service.send_message_sync(chat_id, message)
        logger.info(f"Telegram: pushed {len(new_lines)} new action-queue item(s) to {len(chat_ids)} chat(s)")
    except Exception as e:
        logger.warning(f"Failed to send Telegram action-queue notification: {e}")


async def telegram_notify_loop(interval_seconds: int = 1800):
    """Background loop checking for new Action Queue items every 30 min by default —
    catches things the auto-search's own immediate notify doesn't (a cover letter or
    draft generated through the UI, a follow-up crossing the due-date threshold, etc.)."""
    while True:
        await asyncio.sleep(interval_seconds)
        notify_new_action_items()


def send_daily_digest(search_result: dict):
    """Compose and push the daily auto-search summary — new matches found today plus
    a snapshot of what's currently in the Action Queue. Best-effort, never raises."""
    try:
        from services import telegram_service
        if not telegram_service.is_configured():
            return
        chat_ids = telegram_service.get_known_chat_ids()
        if not chat_ids:
            return

        from database import get_action_queue

        jobs = search_result.get('jobs') or []
        count = search_result.get('count', 0)
        rejected = search_result.get('rejected_count', 0)
        skipped_seen = search_result.get('skipped_seen_count', 0)

        lines = ["Daily Command Center Digest", ""]
        if count:
            lines.append(f"{count} new match(es) found today (filtered {rejected}, skipped {skipped_seen} already-known).")
            top = sorted(jobs, key=lambda j: j.get('score', 0) or 0, reverse=True)[:3]
            for j in top:
                lines.append(f"- {j.get('company', '')} - {_truncate(j.get('title', ''))} ({j.get('score', 0)}%)")
        else:
            lines.append(f"No new matches today (filtered {rejected}, skipped {skipped_seen} already-known).")

        queue = get_action_queue()
        queue_summary = [f"{SECTION_LABELS[k]}: {queue[k]['count']}" for k in SECTION_LABELS if queue.get(k, {}).get('count')]
        if queue_summary:
            lines.append("")
            lines.append("Action Queue: " + ", ".join(queue_summary))

        message = "\n".join(lines)
        for chat_id in chat_ids:
            telegram_service.send_message_sync(chat_id, message)
        logger.info(f"Telegram: sent daily digest to {len(chat_ids)} chat(s)")
    except Exception as e:
        logger.warning(f"Failed to send Telegram daily digest: {e}")
