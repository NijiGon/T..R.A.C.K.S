import cv2
import mysql.connector

cv2.startWindowThread()

# Create video capture object
cap = cv2.VideoCapture("test.mp4")

#Database connection 
Gerbong = 1 #(asumsi sebagai gerbong nomor 1)
Capacity = 25 #(25 adalah asumsi awal jumlah tempat yg tersedia pada satu gerbong)
conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="",
    database="project"
)
cursor = conn.cursor()

# Define font settings for text overlay
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 1
font_color = (255,255,255)
line_type = 2
prev_contour_centroids = []
fps = 75

# Initialize variables
count = 0
line_pos = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) / 2) + 50

# Create background subtractor object
bgSubtractor = cv2.createBackgroundSubtractorMOG2()

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

    # Process each contour
    contour_objects = []
    for i, contour in enumerate(contours):

        # Find largest contour
        if 3000 < cv2.contourArea(contour):
            M = cv2.moments(contour)
            centroid = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

            # Find previous centroid and difference for this contour
            prev_centroid = None
            prev_dif = None
            for c in prev_contour_centroids:
                if c['index'] == i:
                    prev_centroid = c['centroid']
                    prev_dif = abs(prev_centroid[0] - centroid[0])
                    break

            # Check if current centroid is to the left or right of previous centroid
            if prev_centroid is not None and prev_dif is not None:
                if (centroid[0] < line_pos < prev_centroid[0]) and (prev_dif < 250):
                    direction = "Left"
                    count += 1

                    #Update Count to database
                    query = "UPDATE trains SET jumlah_seat = %s WHERE gerbong = 1"
                    Capacity += 1
                    values = (Capacity,)
                    cursor.execute(query, values)
                    conn.commit()

                    print(f'centroids = {centroid[0]}, line pos = {line_pos}, prev centroids = {prev_centroid[0]}, count = {count}')
                    print(contour_objects)
                    print(prev_contour_centroids)
                elif (centroid[0] > line_pos > prev_centroid[0]) and (prev_dif < 250):
                    direction = "Right"
                    count -= 1

                    #Update Count to database
                    query = "UPDATE trains SET jumlah_seat = %s WHERE gerbong = 1"
                    Capacity -= 1
                    values = (Capacity,)
                    cursor.execute(query, values)
                    conn.commit()

                    print(f'centroids = {centroid[0]}, line pos = {line_pos}, prev centroids = {prev_centroid[0]}, count = {count}')
                    print(contour_objects)
                    print(prev_contour_centroids)
                else:
                    direction = None
                
            else:
                direction = None

            # Save current centroid and difference for this contour
            contour_object = {
                'index': i,
                'centroid': centroid,
                'prev_centroid': prev_centroid,
                'prev_dif': prev_dif,
                'direction': direction
            }
            contour_objects.append(contour_object)

            # Draw contour and centroid on frame
            cv2.drawContours(frame, [contour], 0, (0, 255, 0), 2)
            cv2.circle(frame, centroid, 5, (0, 0, 255), -1)

    # Update previous centroid list
    prev_contour_centroids = []
    for co in contour_objects:
        prev_contour_centroids.append({
            'index': co['index'],
            'centroid': co['centroid']
        })

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
