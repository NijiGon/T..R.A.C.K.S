from types import SimpleNamespace

import numpy as np
import pytest

from krl.carunit import CarConfig, CarPipeline, Door, Outbox
from krl.counting import LEFT, LineCounter


class FakeBoxes:
    def __init__(self, rows):
        # rows: list of (x1, y1, x2, y2, conf)
        arr = np.array(rows, dtype=float).reshape(-1, 5)
        self.xyxy = arr[:, :4]
        self.conf = arr[:, 4]
        self.cls = np.zeros(len(rows))
        self.xywh = np.column_stack([
            (arr[:, 0] + arr[:, 2]) / 2, (arr[:, 1] + arr[:, 3]) / 2,
            arr[:, 2] - arr[:, 0], arr[:, 3] - arr[:, 1],
        ])


def config(tmp_path, doors):
    return CarConfig(
        car_id="car-07",
        doors=[Door(name, source) for name, source in doors],
        processed_fps=10.0,
        outbox_path=str(tmp_path / "car.db"),
    )


def test_outbox_ignores_an_event_added_twice(tmp_path):
    outbox = Outbox(str(tmp_path / "car.db"))
    from krl.carunit import CrossingEvent
    event = CrossingEvent("e-1", "car-07", "L1", 1.0, LEFT, 1)
    outbox.add(event)
    outbox.add(event)
    assert [e.event_id for e in outbox.pending()] == ["e-1"]
    outbox.mark_sent(["e-1"])
    assert outbox.pending() == []
    outbox.close()


def test_counter_for_fps_converts_seconds_to_frames():
    at_10 = LineCounter.for_fps(320, 40, 10)
    assert at_10.confirm_frames == 3  # 0.3 s at 10 fps
    assert at_10.max_jump_px == pytest.approx(96.0)  # 960 px/s at 10 fps
    at_24 = LineCounter.for_fps(320, 40, 24)
    assert at_24.confirm_frames == 7  # the same 0.3 s at 24 fps


def person_at(cx):
    return (cx - 30, 100, cx + 30, 300, 0.9)


def test_each_door_is_counted_separately_and_tagged(tmp_path):
    # Frame is 640 wide, so the line is at 320 with a 40 px dead zone (280..360).
    # Door L1: a walker comes from the right at a believable speed and crosses to the left.
    # Door R1: someone stands still on the right the whole time.
    # 20 px per step at 10 fps is 200 px/s. Faster walkers can lose the track at this frame rate.
    walker_centres = [450, 450, 450, 430, 410, 390, 370, 350, 330, 310, 290, 270, 250, 230, 210, 190, 170, 170, 170]
    cfg = config(tmp_path, [("L1", "a.mp4"), ("R1", "b.mp4")])
    outbox = Outbox(cfg.outbox_path)

    pipeline = CarPipeline.__new__(CarPipeline)
    pipeline.config = cfg
    pipeline.outbox = outbox
    pipeline._counters = {}
    pipeline._trackers = {}
    from krl.counting import DuplicateFilter
    pipeline._duplicates = {d.name: DuplicateFilter(0.5) for d in cfg.doors}
    pipeline.net = 0

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    for index, cx in enumerate(walker_centres):
        pipeline._process("L1", frame, SimpleNamespace(boxes=FakeBoxes([person_at(cx)])), index, 10.0)
        pipeline._process("R1", frame, SimpleNamespace(boxes=FakeBoxes([person_at(480)])), index, 10.0)

    events = outbox.pending()
    assert [(e.door, e.direction, e.seat_delta) for e in events] == [("L1", LEFT, 1)]
    assert all(e.car_id == "car-07" for e in events)
    outbox.close()


def test_missing_config_fields_are_rejected(tmp_path):
    path = tmp_path / "car.json"
    path.write_text('{"car_id": "car-07", "doors": []}')
    with pytest.raises(ValueError):
        CarConfig.load(str(path))
