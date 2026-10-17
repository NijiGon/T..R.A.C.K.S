"""Database access for the seat counts (PostgreSQL). The schema is managed by Alembic (see migrations/)."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def make_engine(settings):
    url = URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
    # pool_pre_ping drops dead connections after a database restart instead of failing the next query
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def read_seats(engine):
    """Return [(gerbong, jumlah_seat), ...] ordered by carriage."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT gerbong, jumlah_seat FROM trains ORDER BY gerbong")).all()
    return [(gerbong, seats) for gerbong, seats in rows]


def apply_seat_delta(engine, gerbong, delta, capacity):
    # Relative, clamped update: the database is the source of truth and the count stays within 0..capacity
    query = text(
        "UPDATE trains SET jumlah_seat = GREATEST(0, LEAST(:capacity, jumlah_seat + :delta)) "
        "WHERE gerbong = :gerbong"
    )
    with engine.begin() as conn:
        result = conn.execute(query, {"capacity": capacity, "delta": delta, "gerbong": gerbong})
    if result.rowcount == 0:
        log.warning("No row for gerbong %s in trains table; seat change of %+d was not stored", gerbong, delta)


class SeatWriter:
    """Sends seat changes to the database. If the database is unreachable, changes are kept and sent later."""

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
