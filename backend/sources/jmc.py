"""
Scraper for Jeunesses Musicales Canada's two public concert series at
Joseph-Rouleau Hall (André-Bourbeau House, Montreal): Happy Hour Concerts
(evening, adult) and Cushion Concerts (Sunday mornings, family/kids).

Not robots.txt-blocked (unlike McGill).

Listing pages, each showing every upcoming concert with its next
performance date/time right in the link text:
    https://www.jmcanada.ca/en/public/concerts-and-activities/at-joseph-rouleau-hall/happy-hour-concerts/
    https://www.jmcanada.ca/en/public/concerts-and-activities/at-joseph-rouleau-hall/cushion-concerts/

Concert pages (e.g. https://www.jmcanada.ca/en/concerts/<slug>/) have the
full description/artists and repeat the date under "Concert dates".

PRICING NOTE: both series sell general-admission tickets at a single flat
rate per series (not per concert), shown on each listing page's rates
table. Those flat rates are hardcoded below rather than scraped per-event.
If JMC changes its rates, update HAPPY_HOUR_PRICE / CUSHION_PRICE.
"""

import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "jmc"

SERIES = [
    {
        "key": "happy_hour",
        "listing_url": "https://www.jmcanada.ca/en/public/concerts-and-activities/at-joseph-rouleau-hall/happy-hour-concerts/",
        "price_amount": "$37.37",
        "category": "chamber",
    },
    {
        "key": "cushion",
        "listing_url": "https://www.jmcanada.ca/en/public/concerts-and-activities/at-joseph-rouleau-hall/cushion-concerts/",
        "price_amount": "$20.91",
        "category": "student_recital",  # closest fit for a young-audiences series
    },
]

VENUE_NAME = "Salle Joseph-Rouleau, JMC House"
VENUE_ADDRESS = "305 Avenue du Mont-Royal E, Montréal, QC H2T 1P8"
VENUE_LAT = 45.523096
VENUE_LON = -73.583882

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "jmc"
CACHE_MAX_AGE_SECONDS = 20 * 60 * 60  # ~20h

HEADERS = {
    "User-Agent": "mtl-classic-personal-project/0.1 (personal-use concert finder; contact: <your email>)"
}

# Listing text: "Next performance : October 15, 2026 at 07:00PM"
# (Cushion Concerts show two times, e.g. "...at 10:00AM and 11:30AM" — we
# just take the first one as the representative start time.)
MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
NEXT_PERF_PATTERN = re.compile(
    rf"Next performance\s*:\s*({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\s+at\s+(\d{{1,2}}):(\d{{2}})(AM|PM)",
    re.IGNORECASE,
)
MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

EVENT_LINK_PATTERN = re.compile(r"https://www\.jmcanada\.ca/en/(?:concerts|workshops)/[a-zA-Z0-9\-]+/?")


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


def _parse_listing(html: str) -> list[dict]:
    """Return [{url, title, date, start_time}] from a series listing page."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not EVENT_LINK_PATTERN.match(href):
            continue
        if href in seen:
            continue

        full_text = a_tag.get_text(" ", strip=True)
        match = NEXT_PERF_PATTERN.search(full_text)
        if not match:
            continue

        month_name, day, year, hour, minute, ampm = match.groups()
        month = MONTH_MAP[month_name.title()]
        hour = int(hour)
        if ampm.upper() == "PM" and hour != 12:
            hour += 12
        if ampm.upper() == "AM" and hour == 12:
            hour = 0
        date_str = f"{int(year):04d}-{month:02d}-{int(day):02d}"
        start_time = f"{hour:02d}:{int(minute):02d}:00"

        # Title = text before "Next performance"
        title = full_text[: match.start()].strip()
        # The link text often repeats the title twice (image alt + heading)
        # separated by a space, e.g. "Dance, Rhythm, and Fire Dance, Rhythm,
        # and Fire" -> collapse to one copy.
        words = title.split()
        half = len(words) // 2
        if len(words) % 2 == 0 and words[:half] == words[half:]:
            title = " ".join(words[:half])
        if not title:
            continue

        seen.add(href)
        items.append({"url": href, "title": title, "date": date_str, "start_time": start_time})

    return items


def _parse_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if desc_tag and desc_tag.get("content"):
        return desc_tag["content"].strip()
    return None


def fetch_jmc_events() -> list[dict]:
    """Return a list of normalized event dicts (matching the shared Event
    schema, minus id/first_seen/last_updated which the runner fills in)."""
    events = []

    for series in SERIES:
        html = _get(series["listing_url"], cache_key=f"listing_{series['key']}")
        items = _parse_listing(html)

        for item in items:
            description = None
            try:
                detail_html = _get(item["url"], cache_key=f"event_{item['url'].rstrip('/').rsplit('/', 1)[-1]}")
                description = _parse_description(detail_html)
            except requests.RequestException as exc:
                print(f"  [jmc] failed to fetch {item['url']}: {exc}")

            events.append({
                "tier": "scheduled",
                "title": item["title"],
                "description": description,
                "venue_name": VENUE_NAME,
                "address": VENUE_ADDRESS,
                "lat": VENUE_LAT,
                "lon": VENUE_LON,
                "date": item["date"],
                "start_time": item["start_time"],
                "end_time": None,
                "price_type": "paid",
                "price_amount": series["price_amount"],
                "category": series["category"],
                "source": SOURCE_NAME,
                "link": item["url"],
                "recurring": False,
            })

    return events


if __name__ == "__main__":
    results = fetch_jmc_events()
    print(f"Found {len(results)} events")
    for e in results[:15]:
        print(f"  {e['date']} {e['start_time']}  {e['price_amount']:8s} {e['title'][:50]}")