import cv2
import mysql.connector
from ultralytics import YOLO

VIDEO_PATH = "test.mp4"
PERSON_CLASS = 0  # COCO class id for "person"
CONF_THRESHOLD = 0.3

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
    tracker="bytetrack.yaml",
    persist=True,
    verbose=False,
)

for result in results:
    frame = result.orig_img
    line_pos = int(frame.shape[1] / 2) + 50

    # Count a track once per line crossing, using its own previous position
    if result.boxes.id is not None:
        for track_id, (x1, y1, x2, y2) in zip(result.boxes.id.int().tolist(), result.boxes.xyxy.tolist()):
            cx = (x1 + x2) / 2
            if track_id in prev_x:
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
