import uuid
from datetime import datetime, timezone

from db import init_db, SessionLocal
from models import Event

SPOTS = [
    {
        "title": "STM Métro — Berri-UQAM (Saint-Denis exit)",
        "venue_name": "Berri-UQAM Métro Station",
        "address": "Berri-UQAM Station, Montréal, QC",
        "lat": 45.5157, "lon": -73.5615,
        "description": "One of the STM's designated 'Étoiles du métro' busking spots — no schedule, drop by and see who's playing.",
    },
    {
        "title": "STM Métro — Place-des-Arts (near the Frédéric Back mural)",
        "venue_name": "Place-des-Arts Métro Station",
        "address": "Place-des-Arts Station, Montréal, QC",
        "lat": 45.5088, "lon": -73.5673,
        "description": "Designated busking spot, close to Maison Symphonique — worth checking after OSM concerts let out.",
    },
    {
        "title": "STM Métro — Jean-Talon",
        "venue_name": "Jean-Talon Métro Station",
        "address": "Jean-Talon Station, Montréal, QC",
        "lat": 45.5428, "lon": -73.6136,
        "description": "Designated STM busking spot.",
    },
    {
        "title": "STM Métro — Laurier",
        "venue_name": "Laurier Métro Station",
        "address": "Laurier Station, Montréal, QC",
        "lat": 45.5247, "lon": -73.5824,
        "description": "Designated STM busking spot.",
    },
    {
        "title": "Place Jacques-Cartier / Rue St-Paul",
        "venue_name": "Place Jacques-Cartier",
        "address": "Place Jacques-Cartier, Vieux-Montréal, QC",
        "lat": 45.5085, "lon": -73.5537,
        "description": "Long-running informal busking hub in Old Montreal — mixed street performers including classical guitarists.",
    },
    {
        "title": "Notre-Dame Basilica steps",
        "venue_name": "Basilique Notre-Dame",
        "address": "110 Rue Notre-Dame O, Montréal, QC",
        "lat": 45.5046, "lon": -73.5563,
        "description": "A favored outdoor spot for solo classical performers (guitar, violin) due to foot traffic and acoustics.",
    },
    {
        "title": "Place des Arts arch",
        "venue_name": "Place des Arts",
        "address": "175 Rue Sainte-Catherine O, Montréal, QC",
        "lat": 45.5088, "lon": -73.5673,
        "description": "Buskers often set up here after evening concerts let out.",
    },
]

def main():
    init_db()
    db = SessionLocal()
    now = datetime.now(timezone.utc).isoformat()
    for spot in SPOTS:
        event = Event(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"busking:{spot['venue_name']}")),
            tier="busking_spot",
            title=spot["title"],
            description=spot["description"],
            venue_name=spot["venue_name"],
            address=spot["address"],
            lat=spot["lat"],
            lon=spot["lon"],
            date=None,
            start_time=None,
            end_time=None,
            price_type="free",
            price_amount=None,
            category="busking",
            source="manual",
            link=None,
            recurring=1,
            first_seen=now,
            last_updated=now,
        )
        db.merge(event)
    db.commit()
    db.close()
    print(f"Seeded {len(SPOTS)} busking spots.")

if __name__ == "__main__":
    main()