import os
import cv2
import time

from flask import Flask, jsonify, render_template, request, send_from_directory
from datetime import datetime
from azure.storage.blob import BlobServiceClient
import io
from apscheduler.schedulers.background import BackgroundScheduler
import re
from picamera2 import Picamera2
import numpy as np

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
    """Captures image using Raspberry Pi Camera, saves locally, uploads to Azure, and replaces existing one."""
    try:
        # Initialize Picamera2
        picam2 = Picamera2()
        
        # Configure the camera for still capture
        picam2.configure(picam2.create_still_configuration())
        
        # Start the camera and capture an image
        picam2.start()
        time.sleep(2)  # Allow some time for camera to initialize (if needed)
        
        # Capture the image as a numpy array
        frame = picam2.capture_array()
        
        # Stop the camera after capture
        picam2.stop()

        # Generate filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"plant_{plant_id}_{timestamp}.jpg"
        local_display_filename = f"plant_{plant_id}.jpg"
        local_image_path = os.path.join(LOCAL_IMAGE_FOLDER, local_display_filename)

        # Delete previous local display image if it exists
        if os.path.exists(local_image_path):
            os.remove(local_image_path)

        # Save the captured image locally (for web display)
        cv2.imwrite(local_image_path, frame)

        # Upload the image to Azure Blob Storage
        with open(local_image_path, 'rb') as f:
            image_stream = io.BytesIO(f.read())
        azure_url = upload_to_azure(image_stream, image_filename)

        return azure_url if azure_url else None

    except Exception as e:
        print(f"Error capturing image: {e}")
        return None

# Function to automatically capture images for Plant 1 every minute
def capture_image_automatically():
    """Captures image for Plant 1 every minute automatically."""
    print("Automatically capturing image for Plant 1")
    capture_image(1)

# Initialize the scheduler
scheduler = BackgroundScheduler()

# Add job to the scheduler to capture image for Plant 1 every minute
scheduler.add_job(func=capture_image_automatically, trigger="interval", minutes=1)

# Start the scheduler
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
    app.run(debug=True)
