"""Counts people crossing the line in one camera feed and updates the seat count for its carriage.

Usage:
    python -m krl.counter                  # uses KRL_SOURCE from .env
    python -m krl.counter --debug-dir out  # also saves a frame for every counted crossing
"""

import argparse
import logging
import os
import time

import cv2
from ultralytics import YOLO

from krl import db
from krl.config import load_settings
from krl.counting import LEFT, RIGHT, DuplicateFilter, LineCounter

PERSON_CLASS = 0  # COCO class id for "person"
FLUSH_EVERY_S = 5  # retry pending seat changes at least this often
MAX_RECONNECT_DELAY_S = 30

log = logging.getLogger("krl.counter")


def annotate(frame, tracks, line_x, count):
    frame = frame.copy()
    cv2.line(frame, (int(line_x), 0), (int(line_x), frame.shape[0]), (0, 255, 255), 2)
    for track_id, (x1, y1, x2, y2) in tracks:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        cv2.putText(frame, str(track_id), (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(frame, f"Net crossings: {count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return frame


def run(settings, debug_dir=None):
    if settings.seat_freed_direction not in (LEFT, RIGHT):
        raise ValueError(f"KRL_SEAT_FREED_DIRECTION must be {LEFT!r} or {RIGHT!r}")

    is_file = os.path.isfile(settings.source)
    engine = db.make_engine(settings)
    writer = db.SeatWriter(lambda delta: db.apply_seat_delta(engine, settings.gerbong, delta, settings.seat_capacity))

    try:
        seats = dict(db.read_seats(engine))
        log.info("Gerbong %s currently has %s seats free", settings.gerbong, seats.get(settings.gerbong, "no row"))
    except Exception as error:  # the counter keeps running and retries writes later
        log.warning("Could not read seat counts at startup: %s", error)

    model = YOLO(settings.model_path)
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    cap = cv2.VideoCapture(settings.source)
    counter = None
    duplicates = DuplicateFilter(settings.duplicate_iou)
    frame_no = 0
    net = 0  # net crossings since start, for logs and debug frames
    delay = 1
    last_flush = time.monotonic()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                cap.release()
                if is_file:
                    log.info("End of video after %d frames, net crossings %+d", frame_no, net)
                    break
                log.warning("Camera stream lost, reconnecting in %ss", delay)
                time.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY_S)
                cap = cv2.VideoCapture(settings.source)
                continue
            delay = 1

            if counter is None:
                counter = LineCounter(settings.line_position * frame.shape[1], settings.line_margin_px)
            frame_no += 1

            results = model.track(
                frame,
                persist=True,
                classes=[PERSON_CLASS],
                conf=settings.conf_threshold,
                imgsz=settings.img_size,
                tracker="bytetrack.yaml",
                verbose=False,
            )
            boxes = results[0].boxes
            tracks = []
            if boxes.id is not None:
                tracks = list(zip(boxes.id.int().tolist(), boxes.xyxy.tolist()))
            ignored = duplicates.ignored(frame_no, tracks)
            observations = [(tid, (box[0] + box[2]) / 2) for tid, box in tracks if tid not in ignored]

            for track_id, direction in counter.update(frame_no, observations):
                delta = 1 if direction == settings.seat_freed_direction else -1
                net += delta
                writer.change(delta)
                log.info("Track %d crossed %s: seat change %+d", track_id, direction, delta)
                if debug_dir:
                    name = os.path.join(debug_dir, f"frame_{frame_no:06d}_track{track_id}_{direction}.png")
                    cv2.imwrite(name, annotate(frame, tracks, counter.line_x, net))

            if time.monotonic() - last_flush >= FLUSH_EVERY_S:
                writer.flush()
                last_flush = time.monotonic()
    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        writer.flush()
        if writer.pending:
            log.error("Exiting with %+d seat change(s) not stored", writer.pending)
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--debug-dir", help="save an annotated frame for each counted crossing here")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(load_settings(), debug_dir=args.debug_dir)


if __name__ == "__main__":
    main()
