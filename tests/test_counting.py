import pytest

from krl.counting import LEFT, RIGHT, DuplicateFilter, LineCounter, box_iou

LINE = 300
MARGIN = 20


def run(observations_per_frame, line=LINE, margin=MARGIN, confirm_frames=1):
    """Feed one list of (track_id, cx) per frame and return all crossings in order."""
    counter = LineCounter(line, margin, confirm_frames=confirm_frames, max_jump_px=10**9)
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


def moving_pair(shift_a, shift_b, frames=6, id_a=201, id_b=203):
    """Two overlapping boxes that move by shift_a and shift_b pixels per frame."""
    results = []
    for f in range(frames):
        a = (133 + shift_a * f, 166, 403 + shift_a * f, 512)
        b = (154 + shift_b * f, 152, 394 + shift_b * f, 732)
        results.append([(id_a, a), (id_b, b)])
    return results


def test_duplicate_is_the_newer_id_when_tracks_move_together():
    dup = DuplicateFilter(iou_threshold=0.5)
    ignored = set()
    for frame_no, tracks in enumerate(moving_pair(shift_a=5, shift_b=5)):
        ignored = dup.ignored(frame_no, tracks)
    assert ignored == {203}


def test_stationary_track_under_a_walker_is_not_a_duplicate():
    # The walker (newer ID) moves across a stationary person's box: both must keep counting
    dup = DuplicateFilter(iou_threshold=0.5)
    ignored = set()
    for frame_no, tracks in enumerate(moving_pair(shift_a=0, shift_b=8, id_a=1, id_b=2)):
        ignored = dup.ignored(frame_no, tracks)
    assert ignored == set()


def test_separate_people_are_not_duplicates():
    dup = DuplicateFilter(iou_threshold=0.5)
    tracks = [(1, (0, 0, 100, 200)), (2, (300, 0, 400, 200))]
    for frame_no in range(6):
        assert dup.ignored(frame_no, tracks) == set()


def test_duplicate_ignored_so_the_pair_counts_once():
    # Tracks 1 and 2 are identical boxes walking left together; only track 1 may count
    counter = LineCounter(LINE, MARGIN, confirm_frames=1, max_jump_px=10**9)
    dup = DuplicateFilter(iou_threshold=0.5)
    events = []
    for frame_no in range(10):
        cx = 400 - 25 * frame_no
        box = (cx - 30, 100, cx + 30, 300)
        tracks = [(1, box), (2, box)]
        duplicates = dup.ignored(frame_no, tracks)
        observations = [(tid, (b[0] + b[2]) / 2) for tid, b in tracks if tid not in duplicates]
        events += counter.update(frame_no, observations)
    assert events == [(1, LEFT)]


def test_id_switch_inside_the_dead_zone_keeps_the_crossing():
    # Line at 300, dead zone 280..320. Track 1 is on the right, gets a new ID inside the dead zone,
    # then the new track clears to the left
    frames = [
        [(1, 400)],
        [(1, 310)],
        [(2, 305)],
        [(2, 290)],
        [(2, 200)],
    ]
    assert run(frames) == [(4, 2, LEFT)]


def test_new_track_far_from_any_lost_track_does_not_inherit_a_side():
    frames = [
        [(1, 600)],
        [(2, 100)],
    ]
    assert run(frames) == []


def test_one_frame_flicker_across_the_line_does_not_count():
    # A stationary person's box jumps across the line for one frame, then returns
    frames = [[(1, 400)], [(1, 200)], [(1, 400)], [(1, 400)], [(1, 400)]]
    assert run(frames, confirm_frames=3) == []


def test_crossing_counts_once_the_new_side_is_confirmed():
    # Walker is confirmed on the right first, then is confirmed on the left on the third frame there
    frames = [[(1, 400)], [(1, 400)], [(1, 400)], [(1, 200)], [(1, 190)], [(1, 180)], [(1, 170)]]
    assert run(frames, confirm_frames=3) == [(5, 1, LEFT)]


def test_two_frame_flicker_does_not_count():
    frames = [[(1, 400)], [(1, 200)], [(1, 190)], [(1, 400)], [(1, 400)]]
    assert run(frames, confirm_frames=3) == []
