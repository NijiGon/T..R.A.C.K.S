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

Requires Python 3.12, MySQL or MariaDB, and Tk for the display (`sudo apt install python3.12 python3.12-venv python3-tk`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt and pytest

cp .env.example .env                  # then set the database password and camera source
```

Create the database and apply the schema:

```sql
CREATE DATABASE krl CHARACTER SET utf8mb4;
CREATE USER 'krl'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL ON krl.* TO 'krl'@'localhost';
```

```bash
alembic upgrade head
```

The first run of the counter downloads the YOLO weights (`yolo11n.pt`, about 6 MB) into the project directory.

## Running

```bash
python -m krl.counter                    # counts from KRL_SOURCE, writes to the database
python -m krl.counter --debug-dir debug  # also saves a frame for each counted crossing
python -m krl.display --fullscreen       # station screen; Escape leaves full screen
```

Run one counter per camera. Each camera sets `KRL_GERBONG` to the carriage it covers.

## Tests

```bash
pytest
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
