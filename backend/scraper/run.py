"""
Runs all source scrapers and upserts their events into the SQLite database.

Usage:
    python scraper/run.py

Intended to be run manually for now, and later wired up as a daily cron job /
scheduled task once you're happy with the results.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running this as a script from the backend/ directory.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from db import init_db, SessionLocal  # noqa: E402
from models import Event  # noqa: E402
from sources.osm import fetch_osm_events, SOURCE_NAME as OSM_SOURCE  # noqa: E402
from sources.bourgie import fetch_bourgie_events, SOURCE_NAME as BOURGIE_SOURCE  # noqa: E402

# Each entry: (source_name, fetch_function)
SOURCES = [
    (OSM_SOURCE, fetch_osm_events),
    (BOURGIE_SOURCE, fetch_bourgie_events),
]


def make_event_id(source: str, link: str | None, venue_name: str, date: str | None) -> str:
    """Stable id so re-scraping the same event updates it instead of
    duplicating it. Falls back to venue+date when there's no link
    (e.g. busking spots), matching the schema's id rule."""
    key = f"{source}:{link or venue_name}:{date or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def upsert_events(db, source: str, raw_events: list[dict]) -> tuple[int, int]:
    now = datetime.now(timezone.utc).isoformat()
    created, updated = 0, 0

    for raw in raw_events:
        event_id = make_event_id(source, raw.get("link"), raw["venue_name"], raw.get("date"))
        existing = db.get(Event, event_id)

        if existing:
            for field, value in raw.items():
                setattr(existing, field, value)
            existing.last_updated = now
            updated += 1
        else:
            event = Event(
                id=event_id,
                first_seen=now,
                last_updated=now,
                **raw,
            )
            db.add(event)
            created += 1

    return created, updated


def main():
    init_db()
    db = SessionLocal()

    total_created, total_updated = 0, 0
    for source_name, fetch_fn in SOURCES:
        print(f"Scraping {source_name}...")
        try:
            raw_events = fetch_fn()
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        created, updated = upsert_events(db, source_name, raw_events)
        total_created += created
        total_updated += updated
        print(f"  {len(raw_events)} events found -> {created} new, {updated} updated")

    db.commit()
    db.close()
    print(f"Done. {total_created} new, {total_updated} updated total.")


if __name__ == "__main__":
    main()