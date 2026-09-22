from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db import init_db, get_session
from models import Event

app = FastAPI(title="MTL Classic API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/events")
def get_events(db: Session = Depends(get_session)):
    events = db.query(Event).all()
    return {"events": [row_to_dict(e) for e in events]}


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