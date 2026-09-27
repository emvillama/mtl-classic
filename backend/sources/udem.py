"""
Scraper for the Université de Montréal Faculté de musique's own concert
listing. Unlike McGill, this page is not robots.txt-disallowed, and unlike
the Conservatoire, it's a real structured web page rather than a PDF.

Listing pages (TYPO3-powered, paginated):
    https://musique.umontreal.ca/concerts-et-evenements/a-laffiche/
    https://musique.umontreal.ca/concerts-et-evenements/a-laffiche/unp/2/
    ...

Each event links out to its own page on the university's central calendar
system (a different domain — this is normal, not a redirect/error):
    https://calendrier.umontreal.ca/activite/<slug>

Two-stage approach, same shape as the Bourgie scraper:
  1. Walk the paginated "À l'affiche" listing to discover event URLs.
  2. Fetch each event's own page on calendrier.umontreal.ca, which has a
     clean date/time line, an explicit "Gratuit" (free) or price string,
     and a venue/address block.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "udem"
LISTING_BASE = "https://musique.umontreal.ca/concerts-et-evenements/a-laffiche/"

# Default venue/coordinates for the Faculté de musique's own building — most
# events happen here. A handful of events (e.g. off-campus jazz nights at
# "Le Balcon") will get this building's coordinates even though they're
# elsewhere; venue_name/address text itself is still parsed per-event, only
# lat/lon falls back to this default.
DEFAULT_LAT = 45.5049778
DEFAULT_LON = -73.6144602

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "udem"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h — this runs once a day anyway
MAX_LISTING_PAGES = 15  # safety cap

HEADERS = {
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

CATEGORY = "student_recital"

EVENT_LINK_PATTERN = re.compile(
    r"https://calendrier\.umontreal\.ca/activite/[a-zA-Z0-9\-]+"
)

MONTHS_FR = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|"
    "août|aout|septembre|octobre|novembre|décembre|decembre"
)
DAYS_FR = "lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"

DATETIME_PATTERN = re.compile(
    rf"(?:{DAYS_FR})\s+(?P<day>\d{{1,2}})\s+(?P<month>{MONTHS_FR})\s+(?P<year>\d{{4}}),"
    rf"\s+(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}})",
    re.IGNORECASE,
)

MONTH_MAP = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

PRICE_PATTERN = re.compile(r"(\d+(?:[.,]\d{2})?)\s*\$")


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
        page_url = LISTING_BASE if page_num == 1 else f"{LISTING_BASE}unp/{page_num}/"
        html = _get(page_url, cache_key=f"listing_page_{page_num}")

        matches = set(EVENT_LINK_PATTERN.findall(html))
        if not matches:
            break

        new_matches = matches - seen
        for url in sorted(matches):
            if url not in seen:
                seen.add(url)
                urls.append(url)

        if not new_matches:
            break

    return urls


def _parse_datetime(text: str) -> tuple[str | None, str | None]:
    match = DATETIME_PATTERN.search(text)
    if not match:
        return None, None

    month_key = match.group("month").lower()
    month = MONTH_MAP.get(month_key)
    if month is None:
        return None, None

    day = int(match.group("day"))
    year = int(match.group("year"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    return f"{year:04d}-{month:02d}-{day:02d}", f"{hour:02d}:{minute:02d}:00"


def _parse_price(text: str) -> tuple[str, str | None]:
    if re.search(r"\bgratuit\b", text, re.IGNORECASE):
        return "free", None
    match = PRICE_PATTERN.search(text)
    if match:
        return "paid", f"${match.group(1)}"
    return "unknown", None


def _parse_venue(lines: list[str], datetime_line_idx: int) -> tuple[str, str | None]:
    """Venue info sits a few lines after the date/time line, before
    'Partager'. Take the first non-empty line after price/"En personne" as
    the venue name, and join the rest (up to 'Partager') as the address."""
    venue_name = "Faculté de musique, Université de Montréal"
    address = "220 Avenue Vincent-d'Indy, Montréal, QC H2V 2T2"

    block: list[str] = []
    started = False
    for line in lines[datetime_line_idx:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() == "partager":
            break
        if stripped.lower() in ("en personne", "en ligne", "gratuit"):
            started = True
            continue
        if re.match(r"^\d+(?:[.,]\d{2})?\s*\$$", stripped):
            started = True
            continue
        if started:
            block.append(stripped)

    if block:
        venue_name = block[0]
        if len(block) > 1:
            address = ", ".join(block[1:])

    return venue_name, address


def _parse_event_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title:
        return None

    text = soup.get_text("\n", strip=True)
    lines = text.split("\n")

    date_str, start_time = _parse_datetime(text)
    if not date_str:
        return None

    price_type, price_amount = _parse_price(text)

    # Find the line index of the date/time match to anchor venue parsing.
    datetime_line_idx = 0
    for i, line in enumerate(lines):
        if DATETIME_PATTERN.search(line):
            datetime_line_idx = i
            break

    venue_name, address = _parse_venue(lines, datetime_line_idx)

    return {
        "tier": "scheduled",
        "title": title,
        "description": None,
        "venue_name": venue_name,
        "address": address,
        "lat": DEFAULT_LAT,
        "lon": DEFAULT_LON,
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


def fetch_udem_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    event_urls = _discover_event_urls()

    events = []
    for url in event_urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            html = _get(url, cache_key=f"event_{slug}")
        except requests.RequestException as exc:
            print(f"  [udem] failed to fetch {url}: {exc}")
            continue

        event = _parse_event_page(html, url)
        if event:
            events.append(event)

    return events


if __name__ == "__main__":
    results = fetch_udem_events()
    print(f"Found {len(results)} events")
    for e in results[:10]:
        print(f"  {e['date']} {e['start_time']}  {e['price_type']:7s} {e['venue_name'][:30]:30s} {e['title']}")