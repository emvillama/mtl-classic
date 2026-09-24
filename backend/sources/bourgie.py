"""
Scraper for Salle Bourgie (Bourgie Hall), hosted on the Montreal Museum of
Fine Arts' own site — NOT sallebourgie.ca as the project brief assumed.
That domain is just a ticketing/marketing front-end; the actual event data
lives at mbam.qc.ca.

Listing pages:  https://www.mbam.qc.ca/en/salle-bourgie/?page=N
Event pages:    https://www.mbam.qc.ca/en/activities/<slug>/

Two-stage approach:
  1. Walk the paginated listing to discover event URLs. The listing's own
     text is messy (several fields get concatenated with no separators in
     the rendered markup), so we only use it to harvest links.
  2. Fetch each event's own page, which is much cleaner: real ticket price
     ("General public: $65"), a full date/time string, and a clean title.

Both stages are cached on disk so re-running this scraper doesn't hammer
mbam.qc.ca — only genuinely new/stale pages get re-fetched.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "bourgie"
LISTING_URL = "https://www.mbam.qc.ca/en/salle-bourgie/"
BASE_URL = "https://www.mbam.qc.ca"

VENUE_NAME = "Bourgie Hall"
VENUE_ADDRESS = "1339 Rue Sherbrooke O, Montréal, QC H3G 2C6"
VENUE_LAT = 45.4989656
VENUE_LON = -73.5793389

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "bourgie"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h — this runs once a day anyway
MAX_LISTING_PAGES = 15  # safety cap in case pagination loops unexpectedly

HEADERS = {
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

# Salle Bourgie is, per the project brief, a chamber-music venue — every
# event here gets that category rather than trying to parse the specific
# concert series name out of the messy listing markup.
CATEGORY = "chamber"

EVENT_LINK_PATTERN = re.compile(r"/en/activities/[^/\"'#?]+/?")

PRICE_PATTERN = re.compile(r"General public:\s*(Free|\$[\d,]+(?:[.,]\d{2})?)", re.IGNORECASE)

MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"

# Full match: "Tuesday September 29, 2026 at 07:30 pm"
DATETIME_PATTERN = re.compile(
    rf"(?:{DAYS})\s+(?P<month>{MONTHS})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})"
    rf"\s+at\s+(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}})\s*(?P<ampm>am|pm)",
    re.IGNORECASE,
)

# Fallback for date-only / multi-day ranges e.g. "October 21-22, 2026"
DATE_ONLY_PATTERN = re.compile(
    rf"(?P<month>{MONTHS})\s+(?P<day>\d{{1,2}})(?:\s*[-–]\s*\d{{1,2}})?,\s+(?P<year>\d{{4}})",
    re.IGNORECASE,
)

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def _cache_path(key: str) -> Path:
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", key)
    return CACHE_DIR / f"{safe_key}.html"


def _get(url: str, cache_key: str) -> str:
    """Fetch a URL with a simple on-disk cache, per source + slug, so a
    re-run only re-fetches pages older than CACHE_MAX_AGE_SECONDS."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_key)

    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_MAX_AGE_SECONDS:
            return path.read_text(encoding="utf-8")

    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    path.write_text(resp.text, encoding="utf-8")
    return resp.text


def _discover_event_urls() -> list[str]:
    """Walk the paginated listing and collect unique event page URLs."""
    urls: list[str] = []
    seen: set[str] = set()

    for page_num in range(1, MAX_LISTING_PAGES + 1):
        page_url = f"{LISTING_URL}?page={page_num}"
        html = _get(page_url, cache_key=f"listing_page_{page_num}")

        matches = set(EVENT_LINK_PATTERN.findall(html))
        new_matches = matches - seen
        if not matches:
            # No event links at all on this page -> we've run past the end.
            break

        for path in sorted(matches):
            full_url = urljoin(BASE_URL, path)
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)

        if not new_matches:
            # This page repeated a previous page's events (e.g. pagination
            # looped back) -> stop rather than re-scrape forever.
            break

    return urls


def _parse_price(text: str) -> tuple[str, str | None]:
    match = PRICE_PATTERN.search(text)
    if not match:
        return "unknown", None
    value = match.group(1)
    if value.lower() == "free":
        return "free", None
    return "paid", value


def _parse_datetime(text: str) -> tuple[str | None, str | None]:
    match = DATETIME_PATTERN.search(text)
    if match:
        month = MONTH_MAP[match.group("month").title()]
        day = int(match.group("day"))
        year = int(match.group("year"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        ampm = match.group("ampm").lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return f"{year:04d}-{month:02d}-{day:02d}", f"{hour:02d}:{minute:02d}:00"

    match = DATE_ONLY_PATTERN.search(text)
    if match:
        month = MONTH_MAP[match.group("month").title()]
        day = int(match.group("day"))
        year = int(match.group("year"))
        return f"{year:04d}-{month:02d}-{day:02d}", None

    return None, None


def _parse_event_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("meta", attrs={"property": "og:title"})
    title = title_tag["content"].strip() if title_tag and title_tag.get("content") else None
    if not title:
        return None

    desc_tag = soup.find("meta", attrs={"property": "og:description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else None

    page_text = soup.get_text(" ", strip=True)

    date_str, start_time = _parse_datetime(page_text)
    if not date_str:
        # No parseable date -> skip rather than guess (could be a page for
        # a subscription/series bundle rather than a single dated event).
        return None

    price_type, price_amount = _parse_price(page_text)

    return {
        "tier": "scheduled",
        "title": title,
        "description": description,
        "venue_name": VENUE_NAME,
        "address": VENUE_ADDRESS,
        "lat": VENUE_LAT,
        "lon": VENUE_LON,
        "date": date_str,
        "start_time": start_time,
        "end_time": None,
        "price_type": price_type,
        "price_amount": price_amount,
        "category": CATEGORY,
        "source": SOURCE_NAME,
        "link": url,
        "recurring": False,
    }


def fetch_bourgie_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    event_urls = _discover_event_urls()

    events = []
    for url in event_urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            html = _get(url, cache_key=f"event_{slug}")
        except requests.RequestException as exc:
            print(f"  [bourgie] failed to fetch {url}: {exc}")
            continue

        event = _parse_event_page(html, url)
        if event:
            events.append(event)

    return events


if __name__ == "__main__":
    # Quick manual test: run this file directly to sanity-check extraction
    # before wiring it into the DB.
    results = fetch_bourgie_events()
    print(f"Found {len(results)} events")
    for e in results[:10]:
        print(f"  {e['date']} {e['start_time']}  {e['price_type']:7s} {e['price_amount']!s:8s} {e['title']}")