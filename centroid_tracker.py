import math


class Track:
    def __init__(self, track_id, centroid):
        self.id = track_id
        self.prev = None  # centroid in the previous frame, None if new
        self.centroid = centroid
        self.missing = 0  # frames since this track was last matched


class CentroidTracker:
    """Gives each blob a stable ID by matching centroids between frames."""

    def __init__(self, max_distance=250, max_missing=10):
        self.max_distance = max_distance  # px a centroid may move per frame
        self.max_missing = max_missing  # frames a track survives unmatched
        self.next_id = 0
        self.tracks = []

    def update(self, centroids):
        # Pair every track with every detection that is close enough, closest first
        pairs = []
        for t_index, track in enumerate(self.tracks):
            for d_index, centroid in enumerate(centroids):
                dist = math.dist(track.centroid, centroid)
                if dist <= self.max_distance:
                    pairs.append((dist, t_index, d_index))
        pairs.sort()

        matched_tracks = set()
        matches = [None] * len(centroids)
        for _, t_index, d_index in pairs:
            if t_index in matched_tracks or matches[d_index] is not None:
                continue
            track = self.tracks[t_index]
            track.prev = track.centroid
            track.centroid = centroids[d_index]
            track.missing = 0
            matched_tracks.add(t_index)
            matches[d_index] = track

        # Age unmatched tracks and drop the ones gone for too long
        for t_index, track in enumerate(self.tracks):
            if t_index not in matched_tracks:
                track.missing += 1
        self.tracks = [t for t in self.tracks if t.missing <= self.max_missing]

        # Unmatched detections start new tracks
        for d_index, centroid in enumerate(centroids):
            if matches[d_index] is None:
                track = Track(self.next_id, centroid)
                self.next_id += 1
                self.tracks.append(track)
                matches[d_index] = track

        # Tracks aligned with the input centroids
        return matches
