"""Turns per-frame tracks into line-crossing events. Pure logic, no video or database."""

LEFT = "Left"
RIGHT = "Right"


def box_iou(a, b):
    """Intersection over union of two (x1, y1, x2, y2) boxes."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def duplicate_track_ids(tracks, iou_threshold):
    """Return the IDs to ignore for this frame.

    ByteTrack sometimes gives one person two IDs for a few frames. Two tracks that overlap this much
    in the same frame are one person, so the newer ID is ignored and the older one keeps counting.
    `tracks` is a list of (track_id, box).
    """
    duplicates = set()
    for i, (id_a, box_a) in enumerate(tracks):
        for id_b, box_b in tracks[i + 1:]:
            if box_iou(box_a, box_b) >= iou_threshold:
                duplicates.add(max(id_a, id_b))
    return duplicates


class LineCounter:
    """Reports a crossing when a track clearly moves from one side of the line to the other.

    A track only changes side after it is more than `margin` pixels past the line, so a person
    standing on the line, or jittering across it, does not count. A track that enters and leaves on
    the same side does not count either. Tracks not seen for `prune_after` frames are forgotten.
    """

    def __init__(self, line_x, margin, prune_after=300):
        self.line_x = line_x
        self.margin = margin
        self.prune_after = prune_after
        self._side = {}  # track_id -> LEFT or RIGHT: the last side the track was clearly on
        self._last_seen = {}  # track_id -> frame number

    def update(self, frame_no, observations):
        """`observations` is a list of (track_id, centre_x). Returns the crossings as (track_id, direction)."""
        events = []
        for track_id, cx in observations:
            self._last_seen[track_id] = frame_no
            if cx < self.line_x - self.margin:
                side = LEFT
            elif cx > self.line_x + self.margin:
                side = RIGHT
            else:
                continue  # inside the dead zone: no change of side

            previous = self._side.get(track_id)
            if previous is not None and previous != side:
                events.append((track_id, side))  # direction of travel
            self._side[track_id] = side

        self._prune(frame_no)
        return events

    def _prune(self, frame_no):
        stale = [t for t, seen in self._last_seen.items() if frame_no - seen > self.prune_after]
        for track_id in stale:
            del self._last_seen[track_id]
            self._side.pop(track_id, None)
