"""
Scraper for the Festival International Bach Montréal (WordPress site).

Program page (everything on one page, no pagination):
    https://festivalbachmontreal.com/en/program/

Concert pages:
    https://festivalbachmontreal.com/en/concerts/<slug>/

Two-stage approach:
  1. The program page lists every event as a link whose text contains the
     title, venue and a date like "Friday - 20 November 2026".
  2. Each concert page has a "concert info" block with a start time
     ("November 20, 2026 7:30 pm") and, for ticketed events, a real price
     range ("from 49 to 125$"). Off-Bach events are titled "Free ...".

Scope notes:
  - The festival also plays in Quebec City (Palais Montcalm); those are
    skipped since this project is Montreal-only.
  - The festival only runs for a few weeks in Nov/Dec, so this source will
    look empty outside of festival season until the next edition's program
    is published.
  - Lat/lon are only filled in for venues where the coordinates are well
    known; everything else is left as None rather than guessed.
"""

import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "bach"
PROGRAM_URL = "https://festivalbachmontreal.com/en/program/"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "bach"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h

HEADERS = {
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

EVENT_LINK_PATTERN = re.compile(r"/en/concerts/[a-zA-Z0-9\-]+/?")

MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

# Listing text: "Friday - 20 November 2026"
LISTING_DATE_PATTERN = re.compile(rf"(\d{{1,2}})\s+({MONTHS})\s+(\d{{4}})")

# Concert page: "November 20, 2026 7:30 pm"
DETAIL_TIME_PATTERN = re.compile(
    rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}\s+(\d{{1,2}}):(\d{{2}})\s*(am|pm)", re.IGNORECASE
)
PRICE_RANGE_PATTERN = re.compile(
    r"from\s+(\d+(?:[.,]\d+)?)\s+to\s+(\d+(?:[.,]\d+)?)\s*\$", re.IGNORECASE
)
PRICE_SINGLE_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*\$")

# venue text (lowercase, as it appears on the program page) ->
# (display name, address, lat, lon). None coordinates = not confidently known.
VENUES = {
    "maison symphonique": ("Maison symphonique", "1600 Rue Saint-Urbain, Montréal, QC H2X 0S1", 45.5092643, -73.5666265),
    "bourgie hall": ("Bourgie Hall", "1339 Rue Sherbrooke O, Montréal, QC H3G 2C6", 45.4989656, -73.5793389),
    "saint joseph's oratory of mount royal": ("Saint Joseph's Oratory of Mount Royal", "3800 Chemin Queen Mary, Montréal, QC H3V 1H6", None, None),
    "notre-dame-de-bon-secours chapel": ("Notre-Dame-de-Bon-Secours Chapel", "400 Rue Saint-Paul E, Montréal, QC H2Y 1H4", None, None),
    "church of st. andrew & st. paul": ("Church of St. Andrew & St. Paul", "1423 Rue du Square-Dorchester O, Montréal, QC", None, None),
    "st. georges church": ("St. George's Church", "1101 Rue Stanley, Montréal, QC", None, None),
    "st. george church": ("St. George's Church", "1101 Rue Stanley, Montréal, QC", None, None),
    "church of st. john the evangelist": ("Church of St. John the Evangelist", "137 Avenue du Président-Kennedy, Montréal, QC", None, None),
    "church of saint-léon-de-westmount": ("Church of Saint-Léon-de-Westmount", "4311 Rue Sainte-Catherine O, Westmount, QC", None, None),
    "théâtre paradoxe": ("Théâtre Paradoxe", None, None, None),
    "le 9e": ("Le 9e", None, None, None),
    "off-festival bach": ("Off-Festival Bach", "Boulevard Saint-Laurent, near Place des Arts, Montréal, QC", None, None),
}
SKIP_VENUES = ("palais montcalm", "quebec city")


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


def _match_venue(text: str):
    lowered = text.lower()
    for key in SKIP_VENUES:
        if key in lowered:
            return "skip"
    # Longest key first so "st. georges church" wins over shorter overlaps.
    for key in sorted(VENUES, key=len, reverse=True):
        if key in lowered:
            return VENUES[key]
    return None


def _parse_listing(html: str) -> list[dict]:
    """Return [{url, title, date, venue_tuple}] from the program page."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not EVENT_LINK_PATTERN.search(href):
            continue
        url = href if href.startswith("http") else f"https://festivalbachmontreal.com{href}"
        if url in seen:
            continue

        full_text = a_tag.get_text(" ", strip=True)
        date_match = LISTING_DATE_PATTERN.search(full_text)
        if not date_match:
            continue

        venue = _match_venue(full_text)
        if venue == "skip":
            continue

        day, month_name, year = date_match.groups()
        date_str = f"{int(year):04d}-{MONTH_MAP[month_name]:02d}-{int(day):02d}"

        # Title = the text before the venue name (falls back to before the
        # weekday/date if the venue couldn't be matched).
        title_part = full_text
        if venue:
            venue_key = next(
                (k for k in sorted(VENUES, key=len, reverse=True) if k in full_text.lower()), None
            )
            if venue_key:
                idx = full_text.lower().find(venue_key)
                title_part = full_text[:idx]
        else:
            title_part = full_text[: date_match.start()]
        # Strip a trailing weekday fragment like "Friday -" if it slipped in.
        title_part = re.sub(
            r"\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*-?\s*$", "", title_part
        ).strip(" -–")
        if not title_part:
            continue

        seen.add(url)
        items.append({"url": url, "title": title_part, "date": date_str, "venue": venue})

    return items


def _parse_detail(html: str) -> tuple[str | None, str, str | None]:
    """Return (start_time, price_type, price_amount) from a concert page."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    start_time = None
    m = DETAIL_TIME_PATTERN.search(text)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        start_time = f"{hour:02d}:{minute:02d}:00"

    # Only look for a price in the "concert info" block when we can find it,
    # so unrelated dollar amounts elsewhere on the page don't leak in.
    info_idx = text.lower().find("concert info")
    info_text = text[info_idx: info_idx + 400] if info_idx != -1 else text

    range_match = PRICE_RANGE_PATTERN.search(info_text)
    if range_match:
        low, high = range_match.group(1), range_match.group(2)
        return start_time, "paid", f"${low}–${high}"

    if re.search(r"\bfree\b|\bgratuit\b", info_text, re.IGNORECASE):
        return start_time, "free", None

    single = PRICE_SINGLE_PATTERN.search(info_text)
    if single:
        return start_time, "paid", f"${single.group(1)}"

    return start_time, "unknown", None


def fetch_bach_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    listing_html = _get(PROGRAM_URL, cache_key="program")
    items = _parse_listing(listing_html)

    events = []
    for item in items:
        slug = item["url"].rstrip("/").rsplit("/", 1)[-1]
        start_time, price_type, price_amount = None, "unknown", None
        try:
            detail_html = _get(item["url"], cache_key=f"event_{slug}")
            start_time, price_type, price_amount = _parse_detail(detail_html)
        except requests.RequestException as exc:
            print(f"  [bach] failed to fetch {item['url']}: {exc}")

        # Titles on the program page start with "Free" for Off-Bach freebies;
        # trust that even if the detail page parse came back unknown.
        if price_type == "unknown" and item["title"].lower().startswith("free"):
            price_type = "free"

        venue = item["venue"]
        if venue:
            venue_name, address, lat, lon = venue
        else:
            venue_name, address, lat, lon = "Festival Bach venue (see link)", None, None, None

        is_orchestra = venue_name == "Maison symphonique"

        events.append({
            "tier": "scheduled",
            "title": item["title"],
            "description": None,
            "venue_name": venue_name,
            "address": address,
            "lat": lat,
            "lon": lon,
            "date": item["date"],
            "start_time": start_time,
            "end_time": None,
            "price_type": price_type,
            "price_amount": price_amount,
            "category": "orchestra" if is_orchestra else "chamber",
            "source": SOURCE_NAME,
            "link": item["url"],
            "recurring": False,
        })

    return events


if __name__ == "__main__":
    results = fetch_bach_events()
    print(f"Found {len(results)} events")
    for e in results[:12]:
        print(
            f"  {e['date']} {e['start_time']}  {e['price_type']:7s} "
            f"{str(e['price_amount']):10s} {e['venue_name'][:28]:28s} {e['title'][:50]}"
        )