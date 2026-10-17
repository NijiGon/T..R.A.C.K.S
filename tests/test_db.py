import os

import pytest
from alembic import command
from alembic.config import Config

from krl import db
from krl.config import load_settings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("KRL_DB_PATH", str(tmp_path / "krl.db"))
    command.upgrade(Config(os.path.join(PROJECT_ROOT, "alembic.ini")), "head")
    engine = db.make_engine(load_settings())
    yield engine
    engine.dispose()


def test_migration_creates_one_row_per_carriage(engine):
    assert db.read_seats(engine) == [(1, 25), (2, 25), (3, 25)]


def test_seat_delta_is_applied(engine):
    db.apply_seat_delta(engine, gerbong=1, delta=-3, capacity=25)
    assert dict(db.read_seats(engine))[1] == 22


def test_seats_never_go_below_zero(engine):
    db.apply_seat_delta(engine, gerbong=1, delta=-100, capacity=25)
    assert dict(db.read_seats(engine))[1] == 0


def test_seats_never_go_above_capacity(engine):
    db.apply_seat_delta(engine, gerbong=1, delta=+5, capacity=25)
    assert dict(db.read_seats(engine))[1] == 25


def test_other_carriages_are_untouched(engine):
    db.apply_seat_delta(engine, gerbong=2, delta=-4, capacity=25)
    assert dict(db.read_seats(engine)) == {1: 25, 2: 21, 3: 25}


def test_delta_for_missing_carriage_changes_nothing(engine):
    db.apply_seat_delta(engine, gerbong=99, delta=-1, capacity=25)
    assert db.read_seats(engine) == [(1, 25), (2, 25), (3, 25)]
