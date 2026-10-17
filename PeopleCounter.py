import cv2
import mysql.connector
from ultralytics import YOLO

VIDEO_PATH = "test.mp4"
PERSON_CLASS = 0  # COCO class id for "person"
CONF_THRESHOLD = 0.2
IMG_SIZE = 1024  # larger than the default 640 so small, distant people are detected
DUPLICATE_IOU = 0.5  # two tracks overlapping this much in one frame are one person

#Database connection
GERBONG = 1 #(asumsi sebagai gerbong nomor 1)
SEAT_CAPACITY = 25 #(25 adalah asumsi awal jumlah tempat yg tersedia pada satu gerbong)
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="",
    database="project"
)
cursor = conn.cursor()


def update_seats(delta):
    # Relative, clamped update: the database stays the source of truth
    query = "UPDATE trains SET jumlah_seat = GREATEST(0, LEAST(%s, jumlah_seat + %s)) WHERE gerbong = %s"
    cursor.execute(query, (SEAT_CAPACITY, delta, GERBONG))
    conn.commit()


def box_iou(a, b):
    # Intersection over union of two (x1, y1, x2, y2) boxes
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union


def duplicate_track_ids(tracks):
    # ByteTrack sometimes gives one person two IDs; keep the older ID and ignore the newer
    duplicates = set()
    for i, (id_a, box_a) in enumerate(tracks):
        for id_b, box_b in tracks[i + 1:]:
            if box_iou(box_a, box_b) >= DUPLICATE_IOU:
                duplicates.add(max(id_a, id_b))
    return duplicates


# Define font settings for text overlay
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 1
font_color = (255,255,255)
line_type = 2
fps = 75

# Initialize variables
count = 0
prev_x = {}  # track ID -> horizontal centre in the previous frame
model = YOLO("yolo11n.pt")

# Detect people and track them across frames with ByteTrack
results = model.track(
    source=VIDEO_PATH,
    stream=True,
    classes=[PERSON_CLASS],
    conf=CONF_THRESHOLD,
    imgsz=IMG_SIZE,
    tracker="bytetrack.yaml",
    persist=True,
    verbose=False,
)

for result in results:
    frame = result.orig_img
    line_pos = int(frame.shape[1] / 2) + 50

    if result.boxes.id is not None:
        tracks = [(track_id, box) for track_id, box in zip(result.boxes.id.int().tolist(), result.boxes.xyxy.tolist())]
        duplicates = duplicate_track_ids(tracks)

        # Count a track once per line crossing, using its own previous position
        for track_id, (x1, y1, x2, y2) in tracks:
            cx = (x1 + x2) / 2
            if track_id in prev_x and track_id not in duplicates:
                if cx < line_pos < prev_x[track_id]:
                    count += 1
                    update_seats(+1)
                    print(f'track {track_id}: Left, count = {count}')
                elif cx > line_pos > prev_x[track_id]:
                    count -= 1
                    update_seats(-1)
                    print(f'track {track_id}: Right, count = {count}')
            prev_x[track_id] = cx

            # Draw box and track ID on frame
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(frame, str(track_id), (int(x1), int(y1) - 5), font, 0.6, (0, 255, 0), 2)

    # Draw line in center of frame
    cv2.line(frame, (line_pos, 0), (line_pos, frame.shape[0]), (0, 255, 255), 2)

    # Draw count text on frame
    cv2.putText(frame, f"Count: {count}", (50, 50), font, font_scale, font_color, line_type)

    # Show frame in window
    cv2.imshow('frame', frame)

    # Quit program when 'q' is pressed
    delay = 1000//fps
    if cv2.waitKey(delay) == ord('q'):
        break
cv2.destroyAllWindows()
cv2.waitKey(1)
