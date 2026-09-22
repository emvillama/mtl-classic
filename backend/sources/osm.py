"""
Scraper for the Orchestre symphonique de Montréal (OSM) public calendar.

Source page: https://osm.ca/en/calendar/
This page is server-rendered (not pure JS), so a plain requests + BeautifulSoup
scrape works — no headless browser needed.

NOTE ON SELECTORS:
I built this from a fetched snapshot of the page's rendered content rather than
its raw HTML/CSS class names (I don't have a way to inspect osm.ca's live DOM
directly). The extraction below deliberately avoids depending on CSS class
names — it works off two structural facts that should be stable:
  1. Each concert links to a URL containing "/en/concert/"
  2. The linked <img>'s alt text equals the concert title
  3. A date/time string in the form "Wed, Sep 23 7:30pm" sits in the same
     card as the link

If OSM changes their markup and this stops finding events, open the calendar
page in a browser, right-click an event card -> Inspect, and adjust
CARD_ANCESTOR_LEVELS or the regex below accordingly.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "osm"
CALENDAR_URL = "https://osm.ca/en/calendar/"
VENUE_NAME = "Maison symphonique de Montréal"
VENUE_ADDRESS = "1600 Rue Saint-Urbain, Montréal, QC H2X 0S1"
VENUE_LAT = 45.5092643
VENUE_LON = -73.5666265

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_FILE = CACHE_DIR / "osm_calendar.html"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h, since this runs once a day anyway

HEADERS = {
    # Identify the bot honestly, per the project's scraping etiquette rules.
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

DATE_PATTERN = re.compile(
    r"(?P<dow>Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+"
    r"(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(?P<day>\d{1,2})"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?P<ampm>am|pm))?"
)

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# How many levels up from the <a> tag to look for the date text.
# Adjust this if real events start turning up without dates.
CARD_ANCESTOR_LEVELS = 4


def _get_html() -> str:
    """Fetch the calendar page, using a simple on-disk cache to avoid
    hammering osm.ca on every run (per the project's scraping etiquette)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists():
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age < CACHE_MAX_AGE_SECONDS:
            return CACHE_FILE.read_text(encoding="utf-8")

    resp = requests.get(CALENDAR_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    CACHE_FILE.write_text(resp.text, encoding="utf-8")
    return resp.text


def _infer_year(month: int, day: int) -> int:
    """OSM's calendar text has no year, just 'Wed, Sep 23'. Infer the year by
    assuming the date is the next upcoming occurrence of that month/day."""
    now = datetime.now()
    candidate_year = now.year
    try:
        candidate = datetime(candidate_year, month, day)
    except ValueError:
        candidate = datetime(candidate_year, month, min(day, 28))
    if candidate.date() < now.date():
        candidate_year += 1
    return candidate_year


def _parse_date(match: re.Match) -> tuple[str | None, str | None]:
    month = MONTH_MAP.get(match.group("mon"))
    day = int(match.group("day"))
    if month is None:
        return None, None

    year = _infer_year(month, day)
    date_str = f"{year:04d}-{month:02d}-{day:02d}"

    start_time = None
    if match.group("hour"):
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        ampm = match.group("ampm")
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        start_time = f"{hour:02d}:{minute:02d}:00"

    return date_str, start_time


def fetch_osm_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    html = _get_html()
    soup = BeautifulSoup(html, "html.parser")

    events = []
    seen_keys = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "/en/concert/" not in href and "/en/activity/" not in href:
            continue

        img = a_tag.find("img")
        title = img.get("alt", "").strip() if img else None
        if not title:
            continue

        # Walk up a few ancestor levels looking for a date string nearby.
        container = a_tag
        date_str, start_time = None, None
        for _ in range(CARD_ANCESTOR_LEVELS):
            if container.parent is None:
                break
            container = container.parent
            text = container.get_text(" ", strip=True)
            match = DATE_PATTERN.search(text)
            if match:
                date_str, start_time = _parse_date(match)
                break

        if not date_str:
            # No date found nearby — skip rather than guess.
            continue

        link = href if href.startswith("http") else f"https://osm.ca{href}"

        dedupe_key = (link, date_str, start_time)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        events.append({
            "tier": "scheduled",
            "title": title,
            "description": None,
            "venue_name": VENUE_NAME,
            "address": VENUE_ADDRESS,
            "lat": VENUE_LAT,
            "lon": VENUE_LON,
            "date": date_str,
            "start_time": start_time,
            "end_time": None,
            "price_type": "unknown",  # not shown on the list page; would need the detail page
            "price_amount": None,
            "category": "orchestra",
            "source": SOURCE_NAME,
            "link": link,
            "recurring": False,
        })

    return events


if __name__ == "__main__":
    # Quick manual test: run this file directly to sanity-check extraction
    # before wiring it into the DB.
    results = fetch_osm_events()
    print(f"Found {len(results)} events")
    for e in results[:10]:
        print(f"  {e['date']} {e['start_time']}  {e['title']}")