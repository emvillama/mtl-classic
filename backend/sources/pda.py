"""
Scraper for Place des Arts' own "Classical" discipline listing — already
pre-filtered by PDA itself, so no genre classification needed on our end.

Listing (paginated):
    https://www.placedesarts.com/en/discipline/classical?page=N

Event pages:
    https://www.placedesarts.com/en/event/<slug>

IMPORTANT SCOPE NOTE: this listing spans well over 100 pages, mixing past
and upcoming events with no visible date on the listing itself (dates only
appear on each event's own page). Per project decision, this scraper caps
itself to the first MAX_LISTING_PAGES pages rather than walking the whole
thing — that covers the current/near-future season, not the full archive.
If PDA reorders listings differently than "most recent/relevant first" this
cap may need revisiting.

Like OSM, PDA doesn't expose exact ticket prices in static HTML (pricing is
behind a per-performance Ticketmaster handoff), so price_type is classified
via free-event keywords rather than a scraped dollar figure — see OSM's
scraper for the same pattern.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "pda"
LISTING_BASE = "https://www.placedesarts.com/en/discipline/classical"
BASE_URL = "https://www.placedesarts.com"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "pda"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h
MAX_LISTING_PAGES = 6  # deliberately capped — see module docstring

HEADERS = {
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

CATEGORY = "orchestra"

FREE_KEYWORDS = [
    "free", "gratuit", "spree", "in the parks", "journées de la culture",
    "culture days",
]

EVENT_LINK_PATTERN = re.compile(r"/en/event/[a-zA-Z0-9\-]+")

MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
# Matches "December 2 and 3, 2023", "March 19 and 20, 2027", "July 17, 2027"
# — takes the FIRST date only when a range/list of dates is given.
DATE_PATTERN = re.compile(
    rf"(?P<month>{MONTHS})\s+(?P<day>\d{{1,2}})(?:\s+and\s+\d{{1,2}})?,\s+(?P<year>\d{{4}})"
)

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

VENUE_COORDS = {
    "maison symphonique": (45.5092643, -73.5666265),
    "salle wilfrid-pelletier": (45.5083, -73.5670),
    "théâtre maisonneuve": (45.5085, -73.5671),
    "theatre maisonneuve": (45.5085, -73.5671),
    "cinquième salle": (45.5087, -73.5675),
    "salle claude-léveillée": (45.5086, -73.5672),
}
DEFAULT_LAT, DEFAULT_LON = 45.5088, -73.5673  # Place des Arts complex, general


def _cache_path(key: str) -> Path:
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", key)
    return CACHE_DIR / f"{safe_key}.html"


def _get(url: str, cache_key: str) -> str:
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
    urls: list[str] = []
    seen: set[str] = set()

    for page_num in range(1, MAX_LISTING_PAGES + 1):
        page_url = f"{LISTING_BASE}?page={page_num}"
        html = _get(page_url, cache_key=f"listing_page_{page_num}")

        matches = set(EVENT_LINK_PATTERN.findall(html))
        if not matches:
            break

        new_matches = matches - seen
        for path in sorted(matches):
            full_url = urljoin(BASE_URL, path)
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)

        if not new_matches:
            break

    return urls


def _parse_price(title: str, description: str) -> str:
    text = f"{title} {description or ''}".lower()
    if any(keyword in text for keyword in FREE_KEYWORDS):
        return "free"
    return "paid"


def _parse_venue(text: str) -> tuple[str, float, float]:
    for name, (lat, lon) in VENUE_COORDS.items():
        if name in text.lower():
            # Recover the properly-cased venue name from VENUE_COORDS keys
            # by title-casing — good enough for display purposes.
            return name.title(), lat, lon
    return "Place des Arts", DEFAULT_LAT, DEFAULT_LON


def _parse_event_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title:
        return None

    desc_tag = soup.find("meta", attrs={"property": "og:description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else None

    text = soup.get_text(" ", strip=True)

    date_match = DATE_PATTERN.search(text)
    if not date_match:
        return None
    month = MONTH_MAP[date_match.group("month")]
    day = int(date_match.group("day"))
    year = int(date_match.group("year"))
    date_str = f"{year:04d}-{month:02d}-{day:02d}"

    venue_name, lat, lon = _parse_venue(text)
    price_type = _parse_price(title, description)

    return {
        "tier": "scheduled",
        "title": title,
        "description": description,
        "venue_name": venue_name,
        "address": "175 Rue Sainte-Catherine O, Montréal, QC H2X 1Y9",
        "lat": lat,
        "lon": lon,
        "date": date_str,
        "start_time": None,  # only available per-performance behind the ticket widget
        "end_time": None,
        "price_type": price_type,
        "price_amount": None,  # exact price is behind Ticketmaster handoff; see `link`
        "category": CATEGORY,
        "source": SOURCE_NAME,
        "link": url,
        "recurring": False,
    }


def fetch_pda_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    event_urls = _discover_event_urls()

    events = []
    for url in event_urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            html = _get(url, cache_key=f"event_{slug}")
        except requests.RequestException as exc:
            print(f"  [pda] failed to fetch {url}: {exc}")
            continue

        event = _parse_event_page(html, url)
        if event:
            events.append(event)

    return events


if __name__ == "__main__":
    results = fetch_pda_events()
    print(f"Found {len(results)} events")
    for e in results[:10]:
        print(f"  {e['date']}  {e['price_type']:7s} {e['venue_name'][:25]:25s} {e['title']}")