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


class DuplicateFilter:
    """Finds tracks that are a second copy of a person another track already follows.

    ByteTrack sometimes gives one person two IDs for a few frames. Two tracks are one person when
    their boxes overlap in the same frame AND they move together. Moving together is what separates
    a duplicate from a stationary person whose box a walker passes over: the walker moves and the
    stationary track does not. The newer ID of a duplicate pair is ignored.
    """

    def __init__(self, iou_threshold=0.5, velocity_tol=2.0, history=5, identical_iou=0.9):
        self.iou_threshold = iou_threshold
        self.velocity_tol = velocity_tol  # px per frame
        self.history = history
        self.identical_iou = identical_iou  # boxes this alike are duplicates even before there is history
        self._centres = {}  # track_id -> recent (frame, centre_x, centre_y)

    def ignored(self, frame_no, tracks):
        """`tracks` is a list of (track_id, box). Returns the IDs to ignore this frame."""
        for track_id, (x1, y1, x2, y2) in tracks:
            recent = self._centres.setdefault(track_id, [])
            recent.append((frame_no, (x1 + x2) / 2, (y1 + y2) / 2))
            del recent[:-self.history]
        boxes = dict(tracks)

        duplicates = set()
        for i, (id_a, box_a) in enumerate(tracks):
            for id_b, box_b in tracks[i + 1:]:
                iou = box_iou(box_a, box_b)
                if iou < self.iou_threshold:
                    continue
                va, vb = self._velocity(id_a), self._velocity(id_b)
                if va is None or vb is None:
                    if iou >= self.identical_iou:  # not enough history yet, but the boxes are the same box
                        duplicates.add(max(id_a, id_b))
                    continue
                if abs(va[0] - vb[0]) <= self.velocity_tol and abs(va[1] - vb[1]) <= self.velocity_tol:
                    duplicates.add(max(id_a, id_b))
        return duplicates

    def _velocity(self, track_id):
        recent = self._centres.get(track_id, [])
        if len(recent) < self.history:
            return None
        (f0, x0, y0), (f1, x1, y1) = recent[0], recent[-1]
        frames = max(f1 - f0, 1)
        return (x1 - x0) / frames, (y1 - y0) / frames


class LineCounter:
    """Reports a crossing when a track clearly moves from one side of the line to the other.

    A track only changes side after it is more than `margin` pixels past the line, and it has to stay
    there for `confirm_frames` consecutive frames. A person standing on the line, or jittering across
    it, does not count, and neither does a track that enters and leaves on the same side.

    Detector glitches are filtered out. A centre cannot move more than `max_jump_px` per frame, so a
    box that jumps for a frame or two (for example, a stationary person whose box changes shape) is
    ignored. If the track keeps jumping for `resync_frames` frames, the jump is treated as real and
    the track follows it.

    When a track ends and a new track starts close to where the old one was (ByteTrack often does
    this in a crowd), the new track inherits the old track's committed side, and each old track can be
    inherited once. Without this, a person who changes ID in the dead zone would be counted as a first
    sighting and their crossing would be lost.
    """

    def __init__(self, line_x, margin, confirm_frames=3, max_jump_px=40, resync_frames=8,
                 inherit_frames=30, inherit_px=120, prune_after=300):
        self.line_x = line_x
        self.margin = margin
        self.confirm_frames = confirm_frames
        self.max_jump_px = max_jump_px
        self.resync_frames = resync_frames
        self.inherit_frames = inherit_frames
        self.inherit_px = inherit_px
        self.prune_after = prune_after
        # track_id -> _Track
        self._tracks = {}

    def update(self, frame_no, observations):
        """`observations` is a list of (track_id, centre_x). Returns the crossings as (track_id, direction)."""
        present = {track_id for track_id, _ in observations}
        events = []
        for track_id, cx in observations:
            track = self._tracks.get(track_id)
            if track is None:
                track = _Track(cx, frame_no, self._inherit_side(frame_no, cx, present))
                self._tracks[track_id] = track
            if not track.accept(frame_no, cx, self.max_jump_px, self.resync_frames):
                continue

            side = self._clear_side(cx)
            if side is None:
                track.run = 0  # dead zone: start counting the confirmation run again
                track.candidate = None
                continue
            track.run = track.run + 1 if side == track.candidate else 1
            track.candidate = side
            if track.run >= self.confirm_frames and side != track.committed:
                if track.committed is not None:
                    events.append((track_id, side))  # direction of travel
                track.committed = side

        self._prune(frame_no)
        return events

    @classmethod
    def for_fps(cls, line_x, margin, fps, confirm_s=0.3, max_speed_px_s=960.0, resync_s=0.33,
                inherit_s=1.25, prune_s=12.5, inherit_px=120):
        """Build a counter from durations and speeds, so behaviour does not depend on the frame rate.

        `fps` is the rate of the frame indices passed to update(). The defaults are in seconds: 0.3 s to
        confirm a side, and 960 px per second as the largest believable movement. tests/simulate.py was
        tuned at 24 fps, where 3 frames is 0.125 s; 0.3 s is deliberately more conservative for slower
        processing.
        """
        return cls(
            line_x,
            margin,
            confirm_frames=max(1, round(confirm_s * fps)),
            max_jump_px=max_speed_px_s / fps,
            resync_frames=max(1, round(resync_s * fps)),
            inherit_frames=max(1, round(inherit_s * fps)),
            inherit_px=inherit_px,
            prune_after=max(1, round(prune_s * fps)),
        )

    def _clear_side(self, cx):
        if cx < self.line_x - self.margin:
            return LEFT
        if cx > self.line_x + self.margin:
            return RIGHT
        return None

    def _inherit_side(self, frame_no, cx, present):
        """Find a recently lost track near this position, and take its committed side.

        A lost track can be inherited once. Its own entry is kept, so if its ID comes back it still knows its
        side. That matters when a new track steals the side from a track that was only briefly unobserved.
        """
        best = None
        for old_id, track in self._tracks.items():
            if track.committed is None or track.spare == 0 or old_id in present:
                continue
            if frame_no - track.last_seen > self.inherit_frames or abs(track.last_cx - cx) > self.inherit_px:
                continue
            if best is None or abs(track.last_cx - cx) < abs(self._tracks[best].last_cx - cx):
                best = old_id
        if best is None:
            return None
        self._tracks[best].spare = 0
        return self._tracks[best].committed

    def _prune(self, frame_no):
        stale = [t for t, track in self._tracks.items() if frame_no - track.last_seen > self.prune_after]
        for track_id in stale:
            del self._tracks[track_id]


class _Track:
    def __init__(self, cx, frame_no, committed):
        self.last_cx = cx  # position of the last accepted observation
        self.last_seen = frame_no  # last frame the track was observed, accepted or not
        self.committed = committed  # last side the track was confirmed on
        self.candidate = None  # side it is currently moving to
        self.run = 0  # consecutive frames on the candidate side
        self.rejected = 0  # consecutive observations rejected as glitches
        self.spare = 1  # how many new tracks may still inherit this track's side

    def accept(self, frame_no, cx, max_jump_px, resync_frames):
        """Return False for a glitch. Keeps the anchor until the track has jumped for resync_frames."""
        allowed = max_jump_px * (frame_no - self.last_seen)
        if abs(cx - self.last_cx) > allowed and self.rejected < resync_frames:
            self.rejected += 1
            self.last_seen = frame_no
            self.candidate, self.run = None, 0
            return False
        self.rejected = 0
        self.last_cx = cx
        self.last_seen = frame_no
        return True
