import os
import re
import json
import asyncio
import logging

logger = logging.getLogger("main")

DATA_DIR = os.getenv("DATA_DIR", "data")
SEEN_FILE = os.path.join(DATA_DIR, "inbox_reply_seen.json")
MATCHES_FILE = os.path.join(DATA_DIR, "inbox_reply_matches.json")

# Generic legal-entity suffixes stripped before matching so "Ecolab Inc." matches
# "Ecolab" in an email subject/sender that (reasonably) omits the suffix.
_SUFFIX_RE = re.compile(r'\b(inc|llc|ltd|corp|corporation|co|company|group|technologies|technology|solutions|systems|consulting)\.?\b', re.I)

# ATS/mail-platform domains that many DIFFERENT companies send through — a sender
# address on one of these tells us nothing about which company it's from (unlike, say,
# "recruiting@virtasant.com"), so domain-based matching is skipped for these and falls
# through to the text-based match instead.
_SHARED_SENDING_DOMAINS = {
    'greenhouse.io', 'lever.co', 'myworkdayjobs.com', 'workday.com', 'icims.com',
    'smartrecruiters.com', 'bamboohr.com', 'ashbyhq.com', 'taleo.net',
    'successfactors.com', 'jobvite.com', 'breezy.hr', 'workable.com',
    'recruiterbox.com', 'jazzhr.com', 'gmail.com', 'outlook.com', 'yahoo.com',
    'linkedin.com', 'indeed.com', 'ziprecruiter.com', 'dice.com',
}

FOLLOW_UP_SUGGESTIONS = {
    'interview': 'Reply promptly to confirm/schedule the interview.',
    'assessment': 'Complete it before the deadline.',
    'rejection': 'Consider a polite thank-you / keep-in-touch note.',
    'offer': 'Review and respond to the offer.',
    'reminder': 'Action needed — check the details.',
    'applied': 'Just a confirmation — no action needed yet.',
    'verification': 'Check whether this needs a response.',
}


def _normalize_company(name: str) -> str:
    name = (name or '').lower()
    name = _SUFFIX_RE.sub('', name)
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def _extract_sender_domain(sender: str) -> str:
    m = re.search(r'@([\w.-]+\.\w+)', sender or '')
    return m.group(1).lower() if m else ''


def _domain_root(domain: str) -> str:
    """'mail.virtasant.com' -> 'virtasant' — the label right before the TLD, which is
    usually the company's own name for a company-run mail domain."""
    parts = domain.split('.')
    return parts[-2] if len(parts) >= 2 else domain


def _normalize_title(title: str) -> str:
    title = (title or '').lower()
    title = re.sub(r'[^a-z0-9 ]', ' ', title)
    return re.sub(r'\s+', ' ', title).strip()


def match_message_to_application(message: dict, applications: list) -> dict | None:
    """Cheap, zero-cost match (no AI call), tried in order of confidence:
    1. Sender domain — e.g. "recruiting@virtasant.com" matching tracked company
       "Virtasant" — catches replies whose subject/snippet don't mention the company at
       all. Skipped for shared ATS/mail-provider/job-board domains (a Greenhouse or
       Gmail address doesn't identify which company it's from).
    2. Company name text match against sender/subject/snippet — the longest/most-
       specific match wins if more than one application's name appears.
    3. Job title text match — only for titles specific enough (20+ normalized chars)
       that a coincidental match across unrelated postings is unlikely; a generic title
       like "DevOps Engineer" alone would false-positive across dozens of postings, so
       this tier only fires when nothing more specific matched."""
    sender_domain = _extract_sender_domain(message.get('from', ''))
    if sender_domain and sender_domain not in _SHARED_SENDING_DOMAINS:
        domain_root = _normalize_company(_domain_root(sender_domain))
        if len(domain_root) >= 3:
            for app in applications:
                if _normalize_company(app.get('company', '')) == domain_root:
                    return app

    haystack = f"{message.get('from', '')} {message.get('subject', '')} {message.get('snippet', '')}".lower()
    best = None
    best_len = 0
    for app in applications:
        norm = _normalize_company(app.get('company', ''))
        if len(norm) < 3:
            continue
        if norm in haystack and len(norm) > best_len:
            best = app
            best_len = len(norm)
    if best:
        return best

    haystack_title = _normalize_title(f"{message.get('subject', '')} {message.get('snippet', '')}")
    best_title = None
    best_title_len = 0
    for app in applications:
        norm_title = _normalize_title(app.get('title', ''))
        if len(norm_title) < 20:
            continue
        if norm_title in haystack_title and len(norm_title) > best_title_len:
            best_title = app
            best_title_len = len(norm_title)
    return best_title


def _load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _save_json(path: str, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def get_unhandled_inbox_replies(limit: int = 10) -> list:
    """Matched inbox replies the user hasn't dismissed yet, most recent first — feeds
    the Command Center Action Queue's 'Inbox Replies' bucket."""
    matches = _load_json(MATCHES_FILE, [])
    unhandled = [m for m in matches if not m.get('handled')]
    unhandled.sort(key=lambda m: m.get('message_id', ''), reverse=True)
    return unhandled[:limit], len(unhandled)


def mark_inbox_reply_handled(message_id: str) -> bool:
    matches = _load_json(MATCHES_FILE, [])
    changed = False
    for m in matches:
        if m.get('message_id') == message_id:
            m['handled'] = True
            changed = True
    if changed:
        _save_json(MATCHES_FILE, matches)
    return changed


def check_inbox_for_replies() -> list:
    """Best-effort, never raises. Looks at recent inbox mail, matches it against active
    applications, records any NEW match (dedup via a persisted seen-id set so the same
    email is never notified twice), and pushes a Telegram notification suggesting a
    follow-up. Returns the list of newly-recorded matches."""
    try:
        from services import gmail_service
        if not gmail_service.is_connected().get('connected'):
            return []

        from database import get_active_applications
        applications = get_active_applications()
        if not applications:
            return []

        try:
            search_result = gmail_service.search_inbox("newer_than:3d", max_results=25, category="all")
        except RuntimeError as e:
            logger.warning(f"Inbox reply check: could not search inbox: {e}")
            return []
        messages = search_result.get("messages", [])
        if not messages:
            return []

        try:
            from services.ai_service import classify_inbox_messages
            from services import inbox_cache
            cached, uncached = inbox_cache.split_cached(messages)
            ai_categories = dict(cached)
            if uncached:
                fresh = classify_inbox_messages(uncached)
                ai_categories.update(fresh)
                inbox_cache.store(uncached, fresh)
        except Exception as e:
            logger.warning(f"Inbox reply check: AI classification failed, using local rules: {e}")
            ai_categories = {}
        for m in messages:
            ai_cat = ai_categories.get(m['id'])
            if ai_cat and ai_cat != 'other':
                m['category'] = ai_cat

        # seen_list is the ORDERED source of truth (append-only, in discovery order);
        # seen_ids is just an in-memory set for O(1) lookup. Truncating must slice the
        # ordered list, not sort seen_ids — Gmail message ids are opaque strings with no
        # guaranteed correlation between lexicographic order and recency, so sorting
        # before truncating can evict a just-seen id while keeping a much older one,
        # causing an already-processed email to be reprocessed and re-notified later.
        seen_list = _load_json(SEEN_FILE, [])
        seen_ids = set(seen_list)
        newly_seen = []
        matches = _load_json(MATCHES_FILE, [])
        new_matches = []

        for m in messages:
            if m['id'] in seen_ids:
                continue
            app = match_message_to_application(m, applications)
            seen_ids.add(m['id'])
            newly_seen.append(m['id'])
            if not app:
                continue
            entry = {
                'message_id': m['id'], 'record_id': app['id'], 'company': app['company'],
                'title': app['title'], 'from': m.get('from', ''), 'subject': m.get('subject', ''),
                'snippet': m.get('snippet', ''), 'category': m.get('category', 'all'),
                'category_label': m.get('category_label', 'All'), 'date': m.get('date', ''),
                'handled': False,
            }
            matches.append(entry)
            new_matches.append(entry)

        _save_json(SEEN_FILE, (seen_list + newly_seen)[-2000:])
        if new_matches:
            _save_json(MATCHES_FILE, matches[-200:])
            _notify_new_matches(new_matches)

        return new_matches
    except Exception as e:
        logger.warning(f"check_inbox_for_replies failed: {e}")
        return []


def _notify_new_matches(new_matches: list):
    try:
        from services import telegram_service
        if not telegram_service.is_configured():
            return
        chat_ids = telegram_service.get_known_chat_ids()
        if not chat_ids:
            return
        for entry in new_matches:
            suggestion = FOLLOW_UP_SUGGESTIONS.get(entry['category'], 'Consider sending a follow-up.')
            title_part = f" — {entry['title'][:60]}" if entry['title'] else ""
            message = (
                f"Reply from {entry['company']}{title_part}\n"
                f"{entry['category_label']}: {entry['subject'][:100]}\n"
                f"{suggestion}"
            )
            for chat_id in chat_ids:
                telegram_service.send_message_sync(chat_id, message)
        logger.info(f"Inbox reply check: notified Telegram of {len(new_matches)} new matched repl(y/ies)")
    except Exception as e:
        logger.warning(f"Failed to send inbox-reply Telegram notification: {e}")


async def inbox_reply_check_loop(interval_seconds: int = 1800):
    """Background loop checking for new application replies every 30 min by default —
    same cadence as the Action Queue's own Telegram notify loop."""
    while True:
        await asyncio.sleep(interval_seconds)
        check_inbox_for_replies()
