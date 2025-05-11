from flask import Flask, jsonify
import cv2
import io
import requests
import threading
import time
import serial
import datetime

app = Flask(__name__)

PI1_UPLOAD_URL = "http://192.168.0.161:5071/upload_image/2"

AZURE_TABLE_URL = ""
HEADERS = {
    "Accept": "application/json;odata=nometadata",
    "Content-Type": "application/json"
}

ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
time.sleep(2)

def capture_and_upload():
    """Capture a picture and upload to Pi 1."""
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("[ERROR] Cannot open camera")
        return

    ret, frame = cam.read()
    cam.release()
    if not ret:
        print("[ERROR] Failed to capture image")
        return

    success, imgbuf = cv2.imencode('.jpg', frame)
    if not success:
        print("[ERROR] Encoding failed")
        return

    files = {'file': ('plant_2.jpg', imgbuf.tobytes(), 'image/jpeg')}
    try:
        r = requests.post(PI1_UPLOAD_URL, files=files, timeout=10)
        r.raise_for_status()
        print("[INFO] Uploaded image successfully")
    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")

def send_moisture_data():
    """Read moisture and upload to Azure Table."""
    ser.reset_input_buffer()
    ser.write(b'R') 
    time.sleep(1)

    if ser.in_waiting > 0:
        line = ser.readline().decode('utf-8').rstrip()
        if line.isdigit():
            moisture_value = int(line)
            print(f"[MOISTURE] Moisture Level: {moisture_value}")

            # Determine plant status
            status = "dry" if moisture_value < 300 else "ok"

            # Prepare Azure data
            now = datetime.datetime.now()
            timestamp_str = now.isoformat() + "Z"
            row_key = str(time.time())

            data = {
                "PartitionKey": "Plant2",
                "RowKey": row_key,
                "Timestamp": timestamp_str,
                "moisture": moisture_value,
                "Status": status
            }

            try:
                response = requests.post(AZURE_TABLE_URL, headers=HEADERS, json=data)
                if response.status_code in [200, 201, 204]:
                    print(f"[AZURE] Data sent at {timestamp_str}")
                else:
                    print(f"[AZURE] Failed to send data: {response.status_code} {response.text}")
            except Exception as e:
                print(f"[AZURE] Error sending data: {e}")
        else:
            print("[MOISTURE] Received non-numeric data:", line)

def background_tasks():
    """Run background tasks: Capture photo and send moisture every minute."""
    while True:
        # Start both tasks
        capture_and_upload()
        send_moisture_data()
        # Sleep 60 seconds
        time.sleep(60)

@app.route('/capture', methods=['POST'])
def capture_and_send_on_demand():
    """API to capture image manually on request."""
    capture_and_upload()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    threading.Thread(target=background_tasks, daemon=True).start()
    app.run(host='0.0.0.0', port=5073)
