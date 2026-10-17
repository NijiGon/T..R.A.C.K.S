"""Seat counts in a SQLite file. The schema is managed by Alembic (see migrations/)."""

import logging
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def make_engine(settings):
    path = settings.db_path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        # WAL lets the display read while the counter writes; busy_timeout waits for the other writer
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def read_seats(engine):
    """Return [(gerbong, jumlah_seat), ...] ordered by carriage."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT gerbong, jumlah_seat FROM trains ORDER BY gerbong")).all()
    return [(gerbong, seats) for gerbong, seats in rows]


def apply_seat_delta(engine, gerbong, delta, capacity):
    # Relative, clamped update: the database is the source of truth and the count stays within 0..capacity.
    # CASE rather than GREATEST/LEAST, which SQLite does not have.
    query = text(
        "UPDATE trains SET jumlah_seat = CASE "
        "WHEN jumlah_seat + :delta < 0 THEN 0 "
        "WHEN jumlah_seat + :delta > :capacity THEN :capacity "
        "ELSE jumlah_seat + :delta END "
        "WHERE gerbong = :gerbong"
    )
    with engine.begin() as conn:
        result = conn.execute(query, {"capacity": capacity, "delta": delta, "gerbong": gerbong})
    if result.rowcount == 0:
        log.warning("No row for gerbong %s in trains table; seat change of %+d was not stored", gerbong, delta)


class SeatWriter:
    """Sends seat changes to the database. If the database is unavailable, changes are kept and sent later."""

    def __init__(self, apply):
        self._apply = apply  # callable(delta) that raises SQLAlchemyError when the database fails
        self._pending = 0

    def change(self, delta):
        self._pending += delta
        self.flush()

    def flush(self):
        if self._pending == 0:
            return True
        try:
            self._apply(self._pending)
        except SQLAlchemyError as error:
            log.warning("Database unavailable, keeping %+d seat change(s) pending: %s", self._pending, error)
            return False
        log.debug("Stored seat change of %+d", self._pending)
        self._pending = 0
        return True

    @property
    def pending(self):
        return self._pending
