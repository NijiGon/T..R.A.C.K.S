import os
import threading

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from krl import db
from krl.carunit import CrossingEvent, Outbox
from krl.central import create_app
from krl.config import load_settings
from krl.sync import sync_once

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "test-token"


def event(n, direction="Right", delta=-1):
    return CrossingEvent(f"e-{n}", "car-07", "L1", float(n), direction, delta)


@pytest.fixture
def outbox(tmp_path):
    box = Outbox(str(tmp_path / "car.db"))
    yield box
    box.close()


@pytest.fixture
def central(tmp_path, monkeypatch):
    monkeypatch.setenv("KRL_DB_PATH", str(tmp_path / "central.db"))
    command.upgrade(Config(os.path.join(PROJECT_ROOT, "alembic.ini")), "head")
    engine = db.make_engine(load_settings())
    client = TestClient(create_app(engine, TOKEN))
    yield client
    engine.dispose()


def batch_of(events):
    return {
        "car_id": "car-07",
        "events": [
            {"event_id": e.event_id, "door": e.door, "occurred_at": e.occurred_at,
             "direction": e.direction, "seat_delta": e.seat_delta}
            for e in events
        ],
    }


def test_failed_send_keeps_every_event_pending(outbox):
    for n in range(3):
        outbox.add(event(n))
    sent, ok = sync_once(outbox, lambda events: False)
    assert (sent, ok) == (0, False)
    assert len(outbox.pending()) == 3


def test_successful_send_marks_events_sent(outbox):
    for n in range(3):
        outbox.add(event(n))
    sent, ok = sync_once(outbox, lambda events: True)
    assert (sent, ok) == (3, True)
    assert outbox.pending() == []


def test_partial_failure_resends_only_what_was_not_acknowledged(outbox):
    for n in range(5):
        outbox.add(event(n))
    responses = iter([True, False])
    sent, ok = sync_once(outbox, lambda events: next(responses), batch_size=2)
    assert (sent, ok) == (2, False)
    assert sorted(e.event_id for e in outbox.pending()) == ["e-2", "e-3", "e-4"]


def test_central_rejects_a_bad_token(central):
    response = central.post("/v1/events", json=batch_of([event(1)]), headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_central_stores_a_resent_event_only_once(central):
    body = batch_of([event(1), event(2)])
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert central.post("/v1/events", json=body, headers=headers).status_code == 200
    assert central.post("/v1/events", json=body, headers=headers).status_code == 200
    occupancy = central.get("/v1/cars/car-07/occupancy").json()
    assert occupancy == {"car_id": "car-07", "net_by_door": {"L1": -2}}


def test_car_outbox_arrives_at_central_and_is_counted_once(central, outbox):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    for n, (direction, delta) in enumerate([("Right", -1), ("Right", -1), ("Left", 1)]):
        outbox.add(event(n, direction, delta))

    def send(events):
        response = central.post("/v1/events", json=batch_of(events), headers=headers)
        return response.status_code == 200

    sent, ok = sync_once(outbox, send, batch_size=2)
    assert (sent, ok) == (3, True)
    # Sending again changes nothing, because every event is already marked sent and stored
    assert sync_once(outbox, send) == (0, True)
    assert central.get("/v1/cars/car-07/occupancy").json()["net_by_door"] == {"L1": -1}
