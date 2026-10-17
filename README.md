# KRL Seat Availability

Counts passengers entering and leaving a carriage with a camera, keeps the seat count in a
database, and shows it on a station screen.

```
krl/
  config.py      settings from environment variables (.env)
  db.py          database access, and retry of seat changes when the database is down
  counting.py    line-crossing and duplicate-track logic (pure Python, unit tested)
  counter.py     camera loop: YOLO person detection + ByteTrack + counting
  display.py     full-screen seat board (Tkinter)
migrations/      Alembic schema migrations
tests/           unit tests
data/            sample footage (test.mp4)
notebooks/       earlier prototypes, kept for reference
```

## Setup

You need [uv](https://docs.astral.sh/uv/), PostgreSQL 14+, and Tk for the display
(`sudo apt install python3-tk` on Debian/Ubuntu).

```bash
uv sync                               # creates .venv with Python 3.12 and the locked dependencies
cp .env.example .env                  # then set the database password and camera source
```

Create the database user and database:

```bash
sudo -u postgres psql -c "CREATE USER krl WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE krl OWNER krl;"
```

Apply the schema:

```bash
uv run alembic upgrade head
```

Model weights are handled by Ultralytics: on first use it downloads `KRL_MODEL` (default `yolo11n.pt`, about 6 MB)
and caches it. Nothing in this project downloads or stores model files.

Commands below use `uv run`, which runs inside the project environment without activating it.
To activate it instead, run `source .venv/bin/activate`.

## Running

```bash
uv run python -m krl.counter                    # counts from KRL_SOURCE, writes to the database
uv run python -m krl.counter --debug-dir debug  # also saves a frame for each counted crossing
uv run python -m krl.display --fullscreen       # station screen; Escape leaves full screen
```

Run one counter per camera. Each camera sets `KRL_GERBONG` to the carriage it covers.

## Tests

```bash
uv run pytest
```

## Calibrating for a camera

The defaults are starting points, not calibrated values. Before trusting the count at a station:

1. **Line position** (`KRL_LINE_POSITION`): put the line on the doorway, not the middle of the frame.
2. **Seat freed direction** (`KRL_SEAT_FREED_DIRECTION`): confirm which way people travel when they leave.
3. **Margin** (`KRL_LINE_MARGIN_PX`): raise it if people standing in the doorway are counted.
4. **Detection** (`KRL_CONF`, `KRL_IMG_SIZE`): check that people are detected at the camera's distance and angle.
5. **Validate**: hand-count at least 10 minutes of footage from the same camera and compare with the
   crossings logged by `--debug-dir`. Re-check after any camera move or lighting change.

Tune on footage from each camera, not on one clip. A setting that works for one doorway can fail at another.

## Known limits

- Detection runs on people's full bodies, so a camera mounted high and angled down works best.
- A person who leaves the view and comes back gets a new track ID and may be counted again or missed.
- Counts start from the seat values in the database. Restart the board from a known state at the
  start of each day, since the counter cannot see who is already on board.
- Seat changes made while the database is down are kept in memory. If the counter stops before they
  are sent, they are lost and the log says so.
