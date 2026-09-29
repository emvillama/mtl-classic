from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from db import init_db, get_session
from models import Event

app = FastAPI(title="MTL Classic API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Human-readable labels for each source id, used by the /api/sources
# endpoint so the frontend doesn't have to hardcode display names.
SOURCE_LABELS = {
    "osm": "Orchestre symphonique de Montréal",
    "bourgie": "Salle Bourgie",
    "udem": "Université de Montréal — Faculté de musique",
    "pda": "Place des Arts",
    "bach": "Festival Bach Montréal",
    "jmc": "Jeunesses Musicales Canada",
    "manual": "Known busking spots",
}


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/events")
def get_events(
    db: Session = Depends(get_session),
    source: Optional[str] = Query(
        None, description="Comma-separated list of source ids to include, e.g. 'osm,bourgie'"
    ),
    tier: Optional[str] = Query(
        None, description="Comma-separated list of tiers to include, e.g. 'scheduled,busking_spot'"
    ),
):
    query = db.query(Event)

    if source:
        source_ids = [s.strip() for s in source.split(",") if s.strip()]
        if source_ids:
            query = query.filter(Event.source.in_(source_ids))

    if tier:
        tier_values = [t.strip() for t in tier.split(",") if t.strip()]
        if tier_values:
            query = query.filter(Event.tier.in_(tier_values))

    events = query.all()
    return {"events": [row_to_dict(e) for e in events]}


@app.get("/api/sources")
def get_sources(db: Session = Depends(get_session)):
    """Distinct sources currently in the DB, with a display label and how
    many events each one contributes — lets the frontend build a filter
    list without hardcoding source ids."""
    rows = (
        db.query(Event.source, func.count(Event.id))
        .group_by(Event.source)
        .order_by(Event.source)
        .all()
    )
    return {
        "sources": [
            {
                "id": source_id,
                "label": SOURCE_LABELS.get(source_id, source_id),
                "count": count,
            }
            for source_id, count in rows
        ]
    }


def row_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "tier": e.tier,
        "title": e.title,
        "description": e.description,
        "venue_name": e.venue_name,
        "address": e.address,
        "lat": e.lat,
        "lon": e.lon,
        "date": e.date,
        "start_time": e.start_time,
        "end_time": e.end_time,
        "price_type": e.price_type,
        "price_amount": e.price_amount,
        "category": e.category,
        "source": e.source,
        "link": e.link,
        "recurring": bool(e.recurring),
    }