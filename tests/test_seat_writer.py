from sqlalchemy.exc import OperationalError

from krl.db import SeatWriter


class FlakyDatabase:
    """Records applied deltas; fails while `down` is True."""

    def __init__(self):
        self.down = False
        self.applied = []

    def apply(self, delta):
        if self.down:
            raise OperationalError("UPDATE", {}, Exception("connection refused"))
        self.applied.append(delta)


def test_changes_are_stored_when_the_database_is_up():
    db = FlakyDatabase()
    writer = SeatWriter(db.apply)
    writer.change(+1)
    writer.change(-1)
    assert db.applied == [1, -1]
    assert writer.pending == 0


def test_changes_are_kept_while_the_database_is_down_and_sent_later():
    db = FlakyDatabase()
    writer = SeatWriter(db.apply)
    db.down = True
    writer.change(-1)
    writer.change(-1)
    assert db.applied == []
    assert writer.pending == -2

    db.down = False
    assert writer.flush() is True
    assert db.applied == [-2]
    assert writer.pending == 0


def test_pending_changes_are_sent_as_one_net_change():
    db = FlakyDatabase()
    writer = SeatWriter(db.apply)
    db.down = True
    for delta in (+1, -1, -1, +1, -1):
        writer.change(delta)
    db.down = False
    writer.flush()
    assert db.applied == [-1]


def test_flush_with_nothing_pending_does_nothing():
    db = FlakyDatabase()
    writer = SeatWriter(db.apply)
    assert writer.flush() is True
    assert db.applied == []
