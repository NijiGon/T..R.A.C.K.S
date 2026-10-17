import cv2
import mysql.connector

from centroid_tracker import CentroidTracker

cv2.startWindowThread()

# Create video capture object
cap = cv2.VideoCapture("test.mp4")

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
line_pos = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) / 2) + 50

# Create background subtractor object
bgSubtractor = cv2.createBackgroundSubtractorMOG2()
tracker = CentroidTracker(max_distance=250)

while True:
    # Read frame from video capture
    ret, frame = cap.read()

    # Check if frame was successfully read
    if not ret:
        print("Error reading frame from video stream")
        break

    # Convert frame to grayscale and apply Gaussian blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (115, 115), 0)

    # Threshold the frame to create a binary image
    _, thresh = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)

    # Find contours in the binary image
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Keep only large blobs
    blobs = []
    for contour in contours:
        if 3000 < cv2.contourArea(contour):
            M = cv2.moments(contour)
            centroid = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
            blobs.append((contour, centroid))

    # Match blobs to tracks, so each person keeps the same ID across frames
    tracks = tracker.update([centroid for _, centroid in blobs])

    for (contour, _), track in zip(blobs, tracks):
        centroid = track.centroid

        # A track that crossed the line since the last frame changed the count
        if track.prev is not None:
            if centroid[0] < line_pos < track.prev[0]:
                count += 1
                update_seats(+1)
                print(f'track {track.id}: Left, count = {count}')
            elif centroid[0] > line_pos > track.prev[0]:
                count -= 1
                update_seats(-1)
                print(f'track {track.id}: Right, count = {count}')

        # Draw contour and centroid on frame
        cv2.drawContours(frame, [contour], 0, (0, 255, 0), 2)
        cv2.circle(frame, centroid, 5, (0, 0, 255), -1)

    # Draw line in center of frame
    cv2.line(frame, (line_pos, 0), (line_pos, int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))), (0, 255, 255), 2)

    # Draw count and direction text on frame
    cv2.putText(frame, f"Count: {count}", (50, 50), font, font_scale, font_color, line_type)

    # Show frame in window
    cv2.imshow('frame', frame)

    # Quit program when 'q' is pressed
    delay = 1000//fps
    if cv2.waitKey(delay) == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()
cv2.waitKey(1)
