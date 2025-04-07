import cv2

for i in range(10):  # Check the first 10 indexes
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Camera found at index {i}")
        cap.release()
