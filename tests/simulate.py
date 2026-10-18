"""Simulates people crossing a doorway from an overhead camera, with known ground truth, and scores the counting logic.

People are top-down head boxes, about 40 to 52 px square, which is the geometry the project assumes: one
overhead camera per door.

    uv run python tests/simulate.py

The simulator is deliberately harsh: detection noise, missed detections, ID switches (a new track
for the same person, often near the line), duplicate boxes, people who stop just short of the line,
and people who step up to the line and turn back. Scores count per person whether each true crossing was counted,
once, in the right direction. Timing is not scored.
"""

import random
from dataclasses import dataclass, replace
from itertools import product

from krl.counting import DuplicateFilter, LineCounter

LINE_X = 500
DEEP = 60  # a true crossing counts once the person is this far past the line
HEAD_HALF_MIN, HEAD_HALF_MAX = 20, 26  # top-down head boxes are roughly square, about 40 to 52 px
DUPLICATE_FRAMES = 15


@dataclass(frozen=True)
class Conditions:
    people: int = 60
    speed_px_per_frame: tuple = (2.0, 8.0)
    arrival_gap_frames: tuple = (10, 60)
    noise_px: float = 3.0  # std dev of the centre position error
    miss_prob: float = 0.03  # chance a visible person is not detected in a frame
    id_switch_prob: float = 0.01  # per frame while a person is near the line
    duplicate_prob: float = 0.01  # per frame, chance a second box appears on a person
    linger_prob: float = 0.3  # chance a person stops just short of the line
    turnback_prob: float = 0.1  # chance a person steps up to the line and goes back
    distractors: int = 0  # stationary people near the line who must never count
    flicker_prob: float = 0.02  # per frame, chance a stationary person's box jumps across the line for 2 frames


@dataclass
class Person:
    pid: int
    path: list  # true centre x per frame, relative to the line
    y: float
    start: int
    track_id: int
    distractor: bool = False
    half: float = 23.0  # half the side of the head box


def make_person(rng, pid, start, cond, next_track):
    side = rng.choice([-1, 1])  # the side the person starts on
    speed = rng.uniform(*cond.speed_px_per_frame)
    near = side * 14  # just short of the line, inside the dead zone
    path = []

    x = side * 200  # walk up to the line
    while (x - near) * side > 0:
        path.append(x)
        x -= side * speed
    path.append(near)

    if rng.random() < cond.turnback_prob:  # step back to where they came from
        x = near
        while (side * 200 - x) * side > 0:
            x += side * speed
            path.append(x)
    else:
        if rng.random() < cond.linger_prob:
            path += [near] * rng.randint(5, 40)
        x = near
        while (x + side * 200) * side > 0:  # cross and walk away
            x -= side * speed
            path.append(x)

    half = rng.uniform(HEAD_HALF_MIN, HEAD_HALF_MAX)
    return Person(pid, path, rng.uniform(150, 500), start, next_track, half=half), next_track + 1


def ground_truth(people):
    """(frame, direction, pid) for each time a person clearly crosses from one side to the other."""
    events = []
    for person in people:
        state = None
        for offset, x in enumerate(person.path):
            if abs(x) < DEEP:
                continue
            side = -1 if x < 0 else 1
            if state is not None and side != state:
                events.append((person.start + offset, "Left" if side < 0 else "Right", person.pid))
            state = side
    return sorted(events)


def simulate(cond, seed, margin, inherit_frames, duplicate_iou, inherit_px=120, confirm_frames=3,
             max_jump_px=40, resync_frames=3, trace=None, dup_history=5, dup_velocity_tol=2.0):
    rng = random.Random(seed)
    people, next_track, start = [], 1, 0
    for pid in range(cond.people):
        start += rng.randint(*cond.arrival_gap_frames)
        person, next_track = make_person(rng, pid, start, cond, next_track)
        people.append(person)
    duration = max(p.start + len(p.path) for p in people)
    for i in range(cond.distractors):
        x = rng.uniform(-30, 30)  # stands near the line but never crosses it
        people.append(Person(cond.people + i, [x] * duration, rng.uniform(150, 500), 0, next_track, True,
                             rng.uniform(HEAD_HALF_MIN, HEAD_HALF_MAX)))
        next_track += 1

    truth = ground_truth(people)
    owner = {}  # track id -> pid of the person it belongs to
    counter = LineCounter(LINE_X, margin=margin, confirm_frames=confirm_frames, max_jump_px=max_jump_px,
                          resync_frames=resync_frames, inherit_frames=inherit_frames, inherit_px=inherit_px)
    predicted = []
    duplicates = DuplicateFilter(duplicate_iou, velocity_tol=dup_velocity_tol, history=dup_history)
    copies = {}  # duplicate track id -> (frames left, pid it copies)
    bursts = {}  # pid -> (frames left, offset) for a stationary person's box flicker
    last_frame = duration

    for frame in range(last_frame):
        visible = {}  # pid -> (track id, box) for people detected this frame
        for person in people:
            offset = frame - person.start
            if not 0 <= offset < len(person.path):
                continue
            x = person.path[offset]
            if person.distractor and person.pid not in bursts and rng.random() < cond.flicker_prob:
                bursts[person.pid] = (2, rng.choice([-60, 60]))
            if person.pid in bursts:
                left, offset_x = bursts[person.pid]
                x += offset_x
                bursts[person.pid] = (left - 1, offset_x)
                if left - 1 == 0:
                    del bursts[person.pid]
            if abs(x) < 150 and rng.random() < cond.id_switch_prob:
                person.track_id = next_track
                next_track += 1
            if rng.random() < cond.miss_prob:
                continue
            cx = LINE_X + x + rng.gauss(0, cond.noise_px)
            box = (cx - person.half, person.y - person.half, cx + person.half, person.y + person.half)
            visible[person.pid] = (person.track_id, box)
            owner[person.track_id] = person.pid
            if rng.random() < cond.duplicate_prob:
                copies[next_track] = (DUPLICATE_FRAMES, person.pid)
                owner[next_track] = person.pid
                next_track += 1

        tracks = list(visible.values())
        for dup_id, (left, pid) in list(copies.items()):
            if left == 0:
                del copies[dup_id]
                continue
            copies[dup_id] = (left - 1, pid)
            if pid in visible:
                tracks.append((dup_id, visible[pid][1]))

        ignored = duplicates.ignored(frame, tracks)
        if trace is not None:
            trace.setdefault('owner', owner)
            trace.setdefault('frames', {})[frame] = (tracks, ignored)
        observations = [(tid, (box[0] + box[2]) / 2) for tid, box in tracks if tid not in ignored]
        for track_id, direction in counter.update(frame, observations):
            predicted.append((frame, direction, owner[track_id]))
    return truth, predicted


def score(truth, predicted):
    """Returns (false positives, false negatives): whether each person is counted the right number of times.

    Timing is not scored. Crossings are compared per person and per direction, so a crossing that is
    counted a few frames late still counts as correct. What counts as an error is a missed crossing, an
    extra crossing, or a crossing in the wrong direction.
    """
    false_positives = false_negatives = 0
    for pid in {p for _, _, p in truth} | {p for _, _, p in predicted}:
        for direction in ("Left", "Right"):
            true_n = sum(1 for _, d, p in truth if p == pid and d == direction)
            pred_n = sum(1 for _, d, p in predicted if p == pid and d == direction)
            matched = min(true_n, pred_n)
            false_positives += pred_n - matched
            false_negatives += true_n - matched
    return false_positives, false_negatives


def evaluate(cond, margin, inherit_frames, duplicate_iou, seeds=range(8), inherit_px=120, confirm_frames=3,
             max_jump_px=40, resync_frames=3, dup_history=5, dup_velocity_tol=2.0):
    """Returns (accuracy, errors, true crossings) summed over the seeds."""
    total_truth = total_errors = 0
    for seed in seeds:
        truth, predicted = simulate(cond, seed, margin, inherit_frames, duplicate_iou, inherit_px, confirm_frames,
                                    max_jump_px, resync_frames, dup_history=dup_history,
                                    dup_velocity_tol=dup_velocity_tol)
        false_positives, false_negatives = score(truth, predicted)
        total_truth += len(truth)
        total_errors += false_positives + false_negatives
    return 1 - total_errors / total_truth, total_errors, total_truth


GRID = {
    "noise_px": [2.0, 6.0, 12.0],
    "miss_prob": [0.02, 0.10],
    "id_switch_prob": [0.0, 0.03],
    "duplicate_prob": [0.0, 0.03],
}


def worst_case(margin, inherit_frames, duplicate_iou, inherit_px=80):
    """Lowest accuracy over every combination in GRID, so settings are judged on their weakest conditions."""
    worst = 1.0
    keys = list(GRID)
    for values in product(*(GRID[k] for k in keys)):
        cond = replace(Conditions(), **dict(zip(keys, values)))
        accuracy, _, _ = evaluate(cond, margin, inherit_frames, duplicate_iou, inherit_px=inherit_px)
        worst = min(worst, accuracy)
    return worst


if __name__ == "__main__":
    scenarios = {
        "walkers only": Conditions(),
        "+6 stationary, flicker": Conditions(distractors=6, flicker_prob=0.05),
        "worst grid, +distractors": replace(Conditions(noise_px=12.0, id_switch_prob=0.03,
                                                       duplicate_prob=0.03, miss_prob=0.10,
                                                       distractors=6, flicker_prob=0.05)),
    }
    print("resync  confirm  scenario                    accuracy")
    for resync, confirm in product((3, 8, 15), (1, 3)):
        for name, cond in scenarios.items():
            accuracy, errors, crossings = evaluate(cond, 40, 30, 0.5, confirm_frames=confirm, resync_frames=resync)
            print(f"{resync:>6}  {confirm:>7}  {name:<26} {accuracy:.4f} ({errors}/{crossings})")
