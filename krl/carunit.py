"""One unit per train car: reads that car's door cameras and records every counted crossing.

All doors are detected in one batched call per step, so a car with four cameras does not run four models.
Each door has its own tracker, duplicate filter and line counter. Crossings go to a durable outbox that
a sync step can send later, so nothing is lost when the network or the process goes down.

Usage:
    uv run python -m krl.carunit car.json
"""

import argparse
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker

from krl.counting import LEFT, RIGHT, DuplicateFilter, LineCounter

PERSON_CLASS = 0
MAX_RECONNECT_DELAY_S = 30

log = logging.getLogger("krl.carunit")


@dataclass
class Door:
    name: str
    source: str  # video file path, or RTSP/HTTP stream URL


@dataclass
class CarConfig:
    car_id: str
    doors: list = field(default_factory=list)
    line_position: float = 0.5  # counting line as a fraction of frame width
    margin_px: int = 40
    seat_freed_direction: str = LEFT
    model_path: str = "yolo11n.pt"
    imgsz: int = 640
    conf: float = 0.2
    processed_fps: float = 10.0  # nominal rate of batched steps; sets the time base for counting and tracking
    track_buffer_s: float = 3.0  # how long a lost track is kept
    outbox_path: str = "data/car.db"

    @classmethod
    def load(cls, path):
        with open(path) as f:
            raw = json.load(f)
        raw["doors"] = [Door(**door) for door in raw.get("doors", [])]
        config = cls(**raw)
        if config.seat_freed_direction not in (LEFT, RIGHT):
            raise ValueError(f"seat_freed_direction must be {LEFT!r} or {RIGHT!r}")
        if not config.doors:
            raise ValueError("config lists no doors")
        return config


@dataclass
class CrossingEvent:
    event_id: str
    car_id: str
    door: str
    occurred_at: float  # Unix time when the step that saw the crossing ran
    direction: str
    seat_delta: int  # +1 when a seat is freed, -1 when one is taken


class Outbox:
    """Durable queue of crossing events. Events are keyed by a UUID, so re-adding one is harmless."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS outbox ("
            " event_id TEXT PRIMARY KEY, car_id TEXT NOT NULL, door TEXT NOT NULL,"
            " occurred_at REAL NOT NULL, direction TEXT NOT NULL, seat_delta INTEGER NOT NULL,"
            " sent INTEGER NOT NULL DEFAULT 0)"
        )
        self._conn.commit()

    def add(self, event):
        self._conn.execute(
            "INSERT OR IGNORE INTO outbox (event_id, car_id, door, occurred_at, direction, seat_delta) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event.event_id, event.car_id, event.door, event.occurred_at, event.direction, event.seat_delta),
        )
        self._conn.commit()

    def pending(self, limit=500):
        rows = self._conn.execute(
            "SELECT event_id, car_id, door, occurred_at, direction, seat_delta FROM outbox "
            "WHERE sent = 0 ORDER BY occurred_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [CrossingEvent(*row) for row in rows]

    def mark_sent(self, event_ids):
        self._conn.executemany("UPDATE outbox SET sent = 1 WHERE event_id = ?", [(i,) for i in event_ids])
        self._conn.commit()

    def close(self):
        self._conn.close()


class FrameReader:
    """Keeps only the newest frame from one door's camera, so a slow step never builds a backlog.

    Video files are read at their own frame rate, so they behave like a live camera. Streams that drop
    are reopened with a growing delay.
    """

    def __init__(self, door):
        self.door = door
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0  # increases every time a new frame arrives
        self._stop = threading.Event()
        self.ended = threading.Event()  # set when a video file runs out
        self._thread = threading.Thread(target=self._run, name=f"reader-{door.name}", daemon=True)
        self._thread.start()

    def latest(self, after_seq):
        """Return (seq, frame) if a frame newer than `after_seq` has arrived, otherwise None."""
        with self._lock:
            if self._frame is None or self._seq <= after_seq:
                return None
            return self._seq, self._frame

    def stop(self):
        self._stop.set()

    def _run(self):
        is_file = os.path.isfile(self.door.source)
        cap = cv2.VideoCapture(self.door.source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        delay = 1
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                cap.release()
                if is_file:
                    self.ended.set()
                    return
                log.warning("Camera %s lost, reconnecting in %ss", self.door.name, delay)
                time.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY_S)
                cap = cv2.VideoCapture(self.door.source)
                continue
            delay = 1
            with self._lock:
                self._frame = frame
                self._seq += 1
            if is_file:
                time.sleep(1 / fps)


class CarPipeline:
    def __init__(self, config, outbox, model=None, clock=time.monotonic):
        self.config = config
        self.outbox = outbox
        self.model = model if model is not None else YOLO(config.model_path)
        self.clock = clock
        self._start = clock()
        self._readers = {door.name: FrameReader(door) for door in config.doors}
        self._last_seq = {door.name: 0 for door in config.doors}
        self._counters = {}
        self._trackers = {}
        self._duplicates = {door.name: DuplicateFilter(iou_threshold=0.5) for door in config.doors}
        self.net = 0  # net seat change since start, for logs

    def step(self):
        """Run one batched detection over every door that has a new frame. Returns how many doors were processed."""
        ready = []
        for name, reader in self._readers.items():
            latest = reader.latest(self._last_seq[name])
            if latest is not None:
                seq, frame = latest
                self._last_seq[name] = seq
                ready.append((name, frame))
        if not ready:
            return 0

        results = self.model.predict(
            [frame for _, frame in ready],
            imgsz=self.config.imgsz,
            conf=self.config.conf,
            classes=[PERSON_CLASS],
            verbose=False,
        )
        index = round((self.clock() - self._start) * self.config.processed_fps)
        for (name, frame), result in zip(ready, results):
            self._process(name, frame, result, index)
        return len(ready)

    def _process(self, name, frame, result, index):
        boxes = result.boxes
        detections = Detections(
            conf=_to_numpy(boxes.conf),
            xywh=_to_numpy(boxes.xywh),
            cls=_to_numpy(boxes.cls),
        )
        tracked = self._tracker(name).update(detections, frame)
        tracks = [(int(row[4]), tuple(float(v) for v in row[:4])) for row in tracked]

        ignored = self._duplicates[name].ignored(index, tracks)
        counter = self._counter(name, frame.shape[1])
        observations = [(tid, (box[0] + box[2]) / 2) for tid, box in tracks if tid not in ignored]
        for _track_id, direction in counter.update(index, observations):
            delta = 1 if direction == self.config.seat_freed_direction else -1
            self.net += delta
            event = CrossingEvent(
                event_id=str(uuid.uuid4()),
                car_id=self.config.car_id,
                door=name,
                occurred_at=time.time(),
                direction=direction,
                seat_delta=delta,
            )
            self.outbox.add(event)
            log.info("%s door %s: %s crossing, seat change %+d", self.config.car_id, name, direction, delta)

    def _counter(self, name, frame_width):
        if name not in self._counters:
            line_x = self.config.line_position * frame_width
            self._counters[name] = LineCounter.for_fps(line_x, self.config.margin_px, self.config.processed_fps)
        return self._counters[name]

    def _tracker(self, name):
        if name not in self._trackers:
            args = SimpleNamespace(
                track_high_thresh=0.25,
                track_low_thresh=0.1,
                new_track_thresh=0.25,
                track_buffer=max(1, round(self.config.track_buffer_s * self.config.processed_fps)),
                match_thresh=0.8,
                fuse_score=True,
            )
            self._trackers[name] = BYTETracker(args)
        return self._trackers[name]

    def finished(self):
        return all(reader.ended.is_set() for reader in self._readers.values())

    def close(self):
        for reader in self._readers.values():
            reader.stop()


class Detections:
    """The detection fields ByteTrack reads, with boolean indexing the way its code expects."""

    def __init__(self, conf, xywh, cls):
        self.conf = conf
        self.xywh = xywh
        self.cls = cls

    def __getitem__(self, mask):
        return Detections(self.conf[mask], self.xywh[mask], self.cls[mask])

    def __len__(self):
        return len(self.conf)


def _to_numpy(value):
    if hasattr(value, "cpu"):
        return value.cpu().numpy()
    return np.asarray(value)


def run(config, clock=time.monotonic, step_wait_s=0.01):
    outbox = Outbox(config.outbox_path)
    pipeline = CarPipeline(config, outbox, clock=clock)
    log.info("Car %s started with %d door(s)", config.car_id, len(config.doors))
    try:
        while True:
            processed = pipeline.step()
            if processed == 0:
                if pipeline.finished():
                    break
                time.sleep(step_wait_s)
    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        pipeline.close()
        outbox.close()
    log.info("Car %s finished, net seat change %+d", config.car_id, pipeline.net)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="path to the car's JSON config")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(CarConfig.load(args.config))


if __name__ == "__main__":
    main()
