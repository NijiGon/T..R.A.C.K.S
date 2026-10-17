import pytest

from krl.counting import LEFT, RIGHT, LineCounter, box_iou, duplicate_track_ids

LINE = 300
MARGIN = 20


def run(observations_per_frame, line=LINE, margin=MARGIN):
    """Feed one list of (track_id, cx) per frame and return all crossings in order."""
    counter = LineCounter(line, margin)
    events = []
    for frame_no, observations in enumerate(observations_per_frame):
        events += [(frame_no, track_id, direction) for track_id, direction in counter.update(frame_no, observations)]
    return events


def test_walking_right_to_left_is_a_left_crossing():
    events = run([[(1, 400)], [(1, 350)], [(1, 250)], [(1, 200)]])
    assert events == [(2, 1, LEFT)]


def test_walking_left_to_right_is_a_right_crossing():
    events = run([[(1, 200)], [(1, 250)], [(1, 350)]])
    assert events == [(2, 1, RIGHT)]


def test_standing_on_the_line_does_not_count():
    jitter = [290, 310, 295, 305, 300, 288, 312]
    assert run([[(1, x)] for x in jitter]) == []


def test_jitter_inside_the_dead_zone_after_one_side_does_not_count():
    # Side is confirmed on the left, then the track wobbles across the line without clearing the margin
    frames = [[(1, 200)], [(1, 290)], [(1, 310)], [(1, 280)], [(1, 300)]]
    assert run(frames) == []


def test_entering_and_leaving_on_the_same_side_does_not_count():
    assert run([[(1, 400)], [(1, 350)], [(1, 400)], [(1, 500)]]) == []


def test_crossing_and_coming_back_counts_both_directions():
    events = run([[(1, 400)], [(1, 200)], [(1, 400)]])
    assert events == [(1, 1, LEFT), (2, 1, RIGHT)]


def test_fast_walker_who_skips_the_dead_zone_still_counts_once():
    assert run([[(1, 400)], [(1, 100)]]) == [(1, 1, LEFT)]


def test_new_track_that_appears_on_the_far_side_does_not_count():
    assert run([[(1, 100)], [(1, 120)]]) == []


def test_two_people_are_counted_independently():
    events = run([[(1, 400), (2, 200)], [(1, 200), (2, 400)]])
    assert sorted(events) == [(1, 1, LEFT), (1, 2, RIGHT)]


def test_forgotten_track_starts_fresh():
    counter = LineCounter(LINE, MARGIN, prune_after=5)
    counter.update(0, [(1, 400)])
    assert counter.update(10, []) == []  # pruned: no memory of its side
    assert counter.update(11, [(1, 200)]) == []  # so this is just a first sighting


def test_box_iou_identical_and_disjoint_boxes():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_box_iou_degenerate_box_does_not_divide_by_zero():
    assert box_iou((5, 5, 5, 5), (5, 5, 5, 5)) == 0.0


def test_duplicate_is_the_newer_id_when_boxes_overlap():
    tracks = [(201, (133, 166, 403, 512)), (203, (154, 152, 394, 732))]
    assert duplicate_track_ids(tracks, 0.5) == {203}


def test_separate_people_are_not_duplicates():
    tracks = [(1, (0, 0, 100, 200)), (2, (300, 0, 400, 200))]
    assert duplicate_track_ids(tracks, 0.5) == set()


def test_duplicate_ignored_so_the_pair_counts_once():
    # Track 2 is a duplicate of track 1 for the whole walk, so only track 1 may count
    frames = [
        [(1, (380, 0, 420, 100)), (2, (380, 0, 420, 100))],
        [(1, (180, 0, 220, 100)), (2, (180, 0, 220, 100))],
    ]
    counter = LineCounter(LINE, MARGIN)
    events = []
    for frame_no, tracks in enumerate(frames):
        duplicates = duplicate_track_ids(tracks, 0.5)
        observations = [(tid, (box[0] + box[2]) / 2) for tid, box in tracks if tid not in duplicates]
        events += counter.update(frame_no, observations)
    assert events == [(1, LEFT)]
