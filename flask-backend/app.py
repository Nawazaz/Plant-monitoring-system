import os
import cv2
from flask import Flask, jsonify, render_template, request, send_from_directory
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableClient
import io
from apscheduler.schedulers.background import BackgroundScheduler
import re
import time
import adafruit_dht
import board
import threading

# Initialize DHT22 sensor on GPIO 4
dht_sensor = adafruit_dht.DHT22(board.D4)

app = Flask(__name__)

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=planthkr;AccountKey=iGqdtOgHh/+eZVmHycDMXXAU3Xd6tP+qW9ouhzCYYhbeKvhwYhpDXnCux5nT7U0J7Jd50+gx5I/X+AStO+QElw==;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "trial"

# Azure Blob Client Initialization
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Azure Table Client Initialization via full SAS URL
TABLE_SAS_URL = "https://planthkr.table.core.windows.net/Temp?sp=raud&st=2025-04-07T15:22:18Z&se=2025-04-08T15:22:18Z&sv=2024-11-04&sig=fsfvAlWmXChJ4ibHv6g%2FJbD0SShsIN92teHZrdJBWoE%3D&tn=Temp"
table_client = TableClient.from_table_url(TABLE_SAS_URL)

# Local temp folder
LOCAL_IMAGE_FOLDER = 'temp_images'
os.makedirs(LOCAL_IMAGE_FOLDER, exist_ok=True)

def get_temperature_and_humidity():
    try:
        temperature_c = dht_sensor.temperature
        humidity = dht_sensor.humidity

        if temperature_c is not None and humidity is not None:
            return {
                "temperature": round(temperature_c, 1),
                "humidity": round(humidity, 1)
            }
        else:
            print("DHT sensor read failed: Received None value(s)")
            return {"temperature": None, "humidity": None}

    except RuntimeError as e:
        print(f"DHT sensor error: {e}")
        return {"temperature": None, "humidity": None}


def upload_to_azure(file_stream, blob_name):
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(file_stream, overwrite=True)
        return f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
    except Exception as e:
        print(f"Azure Upload Error: {e}")
        return None

def capture_image(plant_id):
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Error: Could not open camera.")
        return None

    for _ in range(5):
        ret, frame = camera.read()
        time.sleep(0.1)

    ret, frame = camera.read()
    camera.release()

    if ret:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"plant_{plant_id}_{timestamp}.jpg"
        local_image_path = os.path.join(LOCAL_IMAGE_FOLDER, f"plant_{plant_id}.jpg")

        if os.path.exists(local_image_path):
            os.remove(local_image_path)

        cv2.imwrite(local_image_path, frame)

        with open(local_image_path, 'rb') as f:
            image_stream = io.BytesIO(f.read())

        azure_url = upload_to_azure(image_stream, image_filename)
        return azure_url if azure_url else None
    else:
        print("Error: Failed to capture image.")
        return None

# APScheduler-safe threaded version
def log_temperature_and_humidity():
    data = get_temperature_and_humidity()
    timestamp = datetime.utcnow().isoformat()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Temp: {data['temperature']}°C, Humidity: {data['humidity']}%")

    if data["temperature"] is not None and data["humidity"] is not None:
        try:
            entity = {
                "PartitionKey": "Enviroment",
                "RowKey": timestamp,
                "Temperature": data["temperature"],
                "Humidity": data["humidity"]
            }
            table_client.create_entity(entity=entity)
        except Exception as e:
            print(f"Azure Table Insert Error: {e}")

# Wrap in thread to prevent blocking
def log_temperature_and_humidity_async():
    threading.Thread(target=log_temperature_and_humidity).start()

# Image auto-capture job
job_running = False
def capture_image_automatically():
    global job_running
    if not job_running:
        job_running = True
        print("Automatically capturing image for Plant 1")
        capture_image(1)
        job_running = False
    else:
        print("Job already running, skipping this cycle.")

# Scheduler setup
scheduler = BackgroundScheduler()

def schedule_jobs():
    for job in scheduler.get_jobs():
        job.remove()

    scheduler.add_job(func=capture_image_automatically, trigger="interval", minutes=1, max_instances=2)
    scheduler.add_job(func=log_temperature_and_humidity_async, trigger="interval", seconds=30, max_instances=3)

if not scheduler.running:
    schedule_jobs()
    scheduler.start()

# Flask routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/sensor/temperature')
def get_temperature():
    data = get_temperature_and_humidity()
    return jsonify(data)

@app.route('/capture/<int:plant_id>', methods=['POST'])
def capture(plant_id):
    image_url = capture_image(plant_id)
    if image_url:
        return jsonify({"status": "success", "image_url": image_url})
    return jsonify({"status": "error", "message": "Failed to capture image"})

@app.route('/analytics')
def analytics():
    plant_images = {}
    try:
        blob_list = container_client.list_blobs()
        for blob in blob_list:
            match = re.match(r"plant_(\d+)_(\d{8}_\d{6})\.jpg", blob.name)
            if match:
                plant_id = match.group(1)
                timestamp_str = match.group(2)
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_timestamp = "Unknown timestamp"

                plant_key = f"Plant {plant_id}"
                if plant_key not in plant_images:
                    plant_images[plant_key] = []

                blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}"
                plant_images[plant_key].append({"url": blob_url, "timestamp": formatted_timestamp})
    except Exception as e:
        print(f"Error listing blobs: {e}")

    return render_template('analytics.html', plant_images=plant_images)

@app.route('/temp_images/<filename>')
def serve_image(filename):
    return send_from_directory(LOCAL_IMAGE_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True, use_reloader=False)
