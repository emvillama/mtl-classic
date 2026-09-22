from sqlalchemy import Column, String, Float, Integer, CheckConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)
    tier = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    venue_name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    date = Column(String, nullable=True)        # ISO 8601
    start_time = Column(String, nullable=True)   # ISO 8601
    end_time = Column(String, nullable=True)
    price_type = Column(String, nullable=False)
    price_amount = Column(String, nullable=True)
    category = Column(String, nullable=False)
    source = Column(String, nullable=False)
    link = Column(String, nullable=True)
    recurring = Column(Integer, nullable=False, default=0)
    first_seen = Column(String, nullable=False)
    last_updated = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("tier IN ('scheduled','busking_spot','open_rehearsal')", name="ck_tier"),
        CheckConstraint("price_type IN ('free','paid','unknown')", name="ck_price_type"),
    )