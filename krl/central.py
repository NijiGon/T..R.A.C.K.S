"""Central ingest service. Cars POST batches of crossing events; the same event is stored only once.

Run it with:
    KRL_INGEST_TOKEN=... uv run uvicorn krl.central:app
"""

import os
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from krl import db
from krl.config import load_settings


class EventIn(BaseModel):
    event_id: str
    door: str
    occurred_at: float
    direction: str
    seat_delta: int


class Batch(BaseModel):
    car_id: str
    events: list[EventIn]


def create_app(engine, token):
    app = FastAPI(title="KRL central ingest")

    @app.post("/v1/events")
    def ingest(batch: Batch, authorization: str | None = Header(default=None)):
        if not token or authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="bad or missing token")
        received_at = time.time()
        with engine.begin() as conn:
            for event in batch.events:
                # ON CONFLICT makes a re-sent event a no-op, so retries from a car are always safe
                conn.execute(
                    text(
                        "INSERT INTO crossing_events "
                        "(event_id, car_id, door, occurred_at, direction, seat_delta, received_at) "
                        "VALUES (:event_id, :car_id, :door, :occurred_at, :direction, :seat_delta, :received_at) "
                        "ON CONFLICT (event_id) DO NOTHING"
                    ),
                    {
                        "event_id": event.event_id,
                        "car_id": batch.car_id,
                        "door": event.door,
                        "occurred_at": event.occurred_at,
                        "direction": event.direction,
                        "seat_delta": event.seat_delta,
                        "received_at": received_at,
                    },
                )
        return {"received": len(batch.events)}

    @app.get("/v1/cars/{car_id}/occupancy")
    def occupancy(car_id: str):
        """Net seat change per door since the events began. Starting seat counts come from the car's setup."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT door, SUM(seat_delta) FROM crossing_events WHERE car_id = :car_id GROUP BY door ORDER BY door"),
                {"car_id": car_id},
            ).all()
        return {"car_id": car_id, "net_by_door": {door: int(total) for door, total in rows}}

    return app


def _default_app():
    settings = load_settings()
    engine = db.make_engine(settings)
    return create_app(engine, os.environ.get("KRL_INGEST_TOKEN", ""))


app = _default_app()
