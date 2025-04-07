import os
import cv2
from flask import Flask, jsonify, render_template, request, send_from_directory
from datetime import datetime
from azure.storage.blob import BlobServiceClient
import io
from apscheduler.schedulers.background import BackgroundScheduler
import re
import time  # Make sure this is at the top of your file

app = Flask(__name__)

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=planthkr;AccountKey=iGqdtOgHh/+eZVmHycDMXXAU3Xd6tP+qW9ouhzCYYhbeKvhwYhpDXnCux5nT7U0J7Jd50+gx5I/X+AStO+QElw==;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "trial"

# Initialize Azure Blob Client
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Directory to store temporary images locally
LOCAL_IMAGE_FOLDER = 'temp_images'
os.makedirs(LOCAL_IMAGE_FOLDER, exist_ok=True)

# Function to upload image to Azure
def upload_to_azure(file_stream, blob_name):
    """Uploads an in-memory file stream to Azure Blob Storage."""
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(file_stream, overwrite=True)
        return f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}"
    except Exception as e:
        print(f"Azure Upload Error: {e}")
        return None

# Function to capture an image and upload it to Azure
def capture_image(plant_id):
    """Captures an image from the camera, stores it locally, and uploads it to Azure."""
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Error: Could not open camera.")
        return None

    # Warm up the camera — read and discard a few frames
    for _ in range(5):
        ret, frame = camera.read()
        time.sleep(0.1)  # Small delay between frames

    # Final capture
    ret, frame = camera.read()
    camera.release()

    if ret:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"plant_{plant_id}_{timestamp}.jpg"
        
        existing_image_path = os.path.join(LOCAL_IMAGE_FOLDER, f"plant_{plant_id}.jpg")
        if os.path.exists(existing_image_path):
            os.remove(existing_image_path)
        
        local_image_path = os.path.join(LOCAL_IMAGE_FOLDER, f"plant_{plant_id}.jpg")
        cv2.imwrite(local_image_path, frame)
        
        with open(local_image_path, 'rb') as f:
            image_stream = io.BytesIO(f.read())

        azure_url = upload_to_azure(image_stream, image_filename)
        return azure_url if azure_url else None
    
    print("Error: Failed to capture image.")
    return None

# Function to automatically capture images for Plant 1 every minute
job_running = False

def capture_image_automatically():
    """Captures image for Plant 1 every minute automatically."""
    global job_running
    if not job_running:  # Ensure the job isn't already running
        job_running = True
        print("Automatically capturing image for Plant 1")
        capture_image(1)
        job_running = False
    else:
        print("Job already running, skipping this cycle.")

# Initialize the scheduler
scheduler = BackgroundScheduler()

# Add job to the scheduler to capture image for Plant 1 every minute
def schedule_image_capture():
    """Schedules the image capture every minute."""
    for job in scheduler.get_jobs():
        job.remove()  # Remove any existing jobs to prevent duplicates
    
    scheduler.add_job(func=capture_image_automatically, trigger="interval", minutes=1)

# Start the scheduler (if it's not already running)
if not scheduler.running:
    schedule_image_capture()
    scheduler.start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/capture/<int:plant_id>', methods=['POST'])
def capture(plant_id):
    """Handles image capture and upload."""
    image_url = capture_image(plant_id)
    if image_url:
        return jsonify({"status": "success", "image_url": image_url})
    return jsonify({"status": "error", "message": "Failed to capture image"})

@app.route('/analytics')
def analytics():
    plant_images = {}
    try:
        # List all blobs in the container
        blob_list = container_client.list_blobs()
        for blob in blob_list:
            # Assuming blob names follow the format: plant_{plant_id}_{timestamp}.jpg
            match = re.match(r"plant_(\d+)_(\d{8}_\d{6})\.jpg", blob.name)
            if match:
                plant_id = match.group(1)
                timestamp_str = match.group(2)  # Extract timestamp
                
                # Convert timestamp to human-readable format
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_timestamp = "Unknown timestamp"

                plant_key = f"Plant {plant_id}"

                if plant_key not in plant_images:
                    plant_images[plant_key] = []

                # Generate public URL
                blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob.name}"
                plant_images[plant_key].append({"url": blob_url, "timestamp": formatted_timestamp})
                
                print(f"Processed: {blob.name} → {formatted_timestamp}")  # Debugging output
            else:
                print(f"Skipping: {blob.name}")  # Debugging output for unmatched filenames

    except Exception as e:
        print(f"Error listing blobs: {e}")

    return render_template('analytics.html', plant_images=plant_images)

@app.route('/temp_images/<filename>')
def serve_image(filename):
    """Serves images stored locally on the server."""
    return send_from_directory(LOCAL_IMAGE_FOLDER, filename)

if __name__ == '__main__':
    # Disable Flask's automatic reloading to prevent the scheduler from being duplicated
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
