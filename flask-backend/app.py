import os
import cv2
from flask import Flask, jsonify, render_template, request, send_from_directory
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableClient
import io
from apscheduler.schedulers.background import BackgroundScheduler
import re
import time
import board
from adafruit_seesaw.seesaw import Seesaw
import requests
from flask import request
i2c_bus = board.I2C()
ss = Seesaw(i2c_bus, addr=0x36)

MOISTURE_THRESHOLD = 600
app = Flask(__name__)

AZURE_STORAGE_CONNECTION_STRING = "key"
CONTAINER_NAME = "trial"

blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

TABLE_SAS_URL = "key"
table_client = TableClient.from_table_url(TABLE_SAS_URL)

MOISTURE_TABLE_SAS_URL = "key"
moisture_table_client = TableClient.from_table_url(MOISTURE_TABLE_SAS_URL)

LIGHT_TABLE_SAS_URL = "key"
light_table_client = TableClient.from_table_url(LIGHT_TABLE_SAS_URL)
LOCAL_IMAGE_FOLDER = 'temp_images'
os.makedirs(LOCAL_IMAGE_FOLDER, exist_ok=True)


last_fetched_time = None
latest_temperature_data = {"temperature": None, "humidity": None}
last_fetched_lighttime = None
latest_light_data = {"intensity": None}
def get_recent_moisture_data(plant_id, start_date=None, end_date=None, limit=20):
    try:
        entities = list(moisture_table_client.list_entities())
        
        if start_date and end_date:
            try:
                start_ts = datetime.fromisoformat(start_date.replace('Z', '+00:00')).timestamp()
                end_ts   = datetime.fromisoformat(end_date.replace('Z', '+00:00')).timestamp()
            except ValueError:
                return jsonify({"error": "Invalid timestamp format"}), 400
        else:
            # Default to last 7 days if no date range is provided
            cutoff_ts = (datetime.now() - timedelta(days=7)).timestamp()
            start_ts, end_ts = cutoff_ts, datetime.now().timestamp()

        filtered = [
            e for e in entities
            if e["PartitionKey"] == f"Plant{plant_id}"
               and start_ts <= float(e["RowKey"]) <= end_ts
        ]

        filtered.sort(key=lambda x: float(x["RowKey"]), reverse=True)

        return [
            {
                "time": datetime.fromtimestamp(float(e["RowKey"])).strftime("%Y-%m-%d %H:%M"),
                "moisture": e.get("moisture", "N/A")  # use .get() with a fallback
            }
            for e in filtered[:limit]
            if "moisture" in e 
        ]

    except Exception as e:
        print(f"Error fetching moisture history for Plant {plant_id}: {e}")
        return []
def get_latest_moisture_from_azure(plant_id):
    try:
        entities = list(moisture_table_client.list_entities())
        filtered = [
            e for e in entities
            if e["PartitionKey"] == f"Plant{plant_id}"
               and "moisture" in e
        ]
        if not filtered:
            return {"moisture": None, "status": None}

        filtered.sort(key=lambda e: e["RowKey"], reverse=True)
        latest = filtered[0]
        moisture = latest["moisture"]

        # Set threshold based on plant
        threshold = 500 if plant_id == 2 else MOISTURE_THRESHOLD
        status = "dry" if moisture < threshold else "ok"
        
        return {"moisture": moisture, "status": status}
    except Exception as e:
        print(f"Error fetching latest moisture for Plant {plant_id}: {e}")
        return {"moisture": None, "status": None}

def get_recent_temperature_data(start_date=None, end_date=None, limit=20):
    try:
        entities = list(table_client.list_entities())

        if start_date and end_date:
            try:
                start_ts = datetime.fromisoformat(start_date.replace('Z', '+00:00')).timestamp()
                end_ts   = datetime.fromisoformat(end_date.replace('Z', '+00:00')).timestamp()
            except ValueError:
                return jsonify({"error": "Invalid timestamp format"}), 400
        else:
            cutoff_ts = (datetime.now() - timedelta(days=7)).timestamp()
            start_ts, end_ts = cutoff_ts, datetime.now().timestamp()

        filtered = [
            e for e in entities
            if e.get("Temperature") is not None
               and start_ts <= float(e["RowKey"]) <= end_ts
        ]

        # Sort by timestamp descending
        filtered.sort(key=lambda x: float(x["RowKey"]), reverse=True)

        return [
            {
                "time": datetime.fromtimestamp(float(e["RowKey"])).strftime("%Y-%m-%d %H:%M"),
                "temperature": e["Temperature"],
                "humidity": e["Humidity"]
            }
            for e in filtered[:limit]
        ]
    except Exception as e:
        print(f"Error fetching temperature history: {e}")
        return []
def read_soil_moisture():
    """Return a tuple (moisture_value, temp_celsius, status_str)."""
    moisture = ss.moisture_read()
    temp = ss.get_temp()
    status = "dry" if moisture < MOISTURE_THRESHOLD else "ok"
    return moisture, temp, status

def log_moisture_to_azure(moisture, status, plant_id):
    try:
        entity = {
            "PartitionKey": f"Plant{plant_id}",
            "RowKey": str(datetime.now().timestamp()),
            "moisture": moisture,
            "Status": status
        }

        moisture_table_client.create_entity(entity=entity)

        print(f"Moisture data logged to Azure Table for Plant {plant_id}")
    except Exception as e:
        print(f"Error logging moisture data: {e}")


def get_latest_temperature_from_azure():
    global last_fetched_time, latest_temperature_data

    try:
        entities = list(table_client.list_entities())
        
        if not entities:
            return {"temperature": None, "humidity": None}

        entities.sort(key=lambda e: e.get("RowKey", ""), reverse=True)

        latest = entities[0]

        if last_fetched_time is None or latest.get("RowKey") != last_fetched_time:

            temperature = latest.get("Temperature")
            humidity = latest.get("Humidity")

            if temperature is None or humidity is None:
                return {"temperature": None, "humidity": None}

            last_fetched_time = latest.get("RowKey")

            latest_temperature_data = {"temperature": temperature, "humidity": humidity}

            return latest_temperature_data
        
        return latest_temperature_data

    except KeyError as e:
        return {"temperature": None, "humidity": None}
    except Exception as e:
        return {"temperature": None, "humidity": None}

def get_latest_light_from_azure():
    global last_fetched_lighttime, latest_light_data

    try:
        entities = list(light_table_client.list_entities())
        
        if not entities:
            return {"intensity": None}

        entities.sort(key=lambda e: e.get("RowKey", ""), reverse=True)

        latest = entities[0]

        if last_fetched_lighttime is None or latest.get("RowKey") != last_fetched_lighttime:

            intensity = latest.get("Light")

            if intensity is None:
                return {"intensity": None}

            last_fetched_lighttime = latest.get("RowKey")

            latest_light_data = {"intensity": intensity}

            return latest_light_data
        
        return latest_light_data

    except KeyError as e:
        return {"temperature": None}
    except Exception as e:
        return {"temperature": None}
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


job_running = False
def capture_image_automatically():
    global job_running
    if not job_running:
        job_running = True
        print(f"Starting image capture for Plant 1 at {datetime.now()}")
        capture_image(1)
        print(f"Image capture for Plant 1 finished at {datetime.now()}")
        job_running = False
    else:
        print("Job already running, skipping this cycle.")
def log_moisture_automatically():
    try:
        print(f"Logging moisture data for Plant 1 at {datetime.now()}")
        moisture, temp, status = read_soil_moisture()
        log_moisture_to_azure(moisture, status, 1)  # Assuming plant_id is 1
        print(f"Moisture data logged for Plant 1 at {datetime.now()}")
    except Exception as e:
        print(f"Error logging moisture automatically: {e}")

scheduler = BackgroundScheduler()

def schedule_jobs():
    for job in scheduler.get_jobs():
        job.remove()

    scheduler.add_job(func=capture_image_automatically, trigger="interval", minutes=1, max_instances=1)
    scheduler.add_job(func=log_moisture_automatically, trigger="interval", minutes=1, max_instances=1)

if not scheduler.running:
    schedule_jobs()
    scheduler.start()


@app.route('/')
def home():
    return render_template('index.html')
@app.route("/sensor/moisture/<int:plant_id>/history", methods=["GET"])
def get_moisture_history(plant_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    data = get_recent_moisture_data(plant_id, start_date, end_date)
    return jsonify(data)



@app.route("/sensor/temperature/history", methods=["GET"])
def get_temperature_history():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    data = get_recent_temperature_data(start_date, end_date)
    return jsonify(data)


@app.route('/sensor/temperature')
def get_temperature():
    data = get_latest_temperature_from_azure()
    return jsonify(data)

@app.route('/sensor/moisture/<int:plant_id>')
def get_moisture(plant_id):
    if plant_id == 2:
        data = get_latest_moisture_from_azure(2)
        return jsonify({
            "plant_id": plant_id,
            "moisture": data["moisture"],
            "status": data["status"]
        })
    moisture, temp, status = read_soil_moisture()
    return jsonify({
        "plant_id": plant_id,
        "moisture": moisture,
        "temperature": round(temp, 2),
        "status": status
    })

@app.route('/sensor/light')
def get_light():
    data = get_latest_light_from_azure()
    return jsonify(data)

@app.route('/sensor/light/history', methods=["GET"])
def get_light_history():
    start_date = request.args.get("start_date")
    end_date   = request.args.get("end_date")

    if not (start_date and end_date):
        end_ts   = datetime.now().timestamp()
        start_ts = (datetime.now() - timedelta(hours=1)).timestamp()
    else:
        start_ts = datetime.fromisoformat(start_date.replace('Z','+00:00')).timestamp()
        end_ts   = datetime.fromisoformat(end_date.replace('Z','+00:00')).timestamp()

    entities = list(light_table_client.list_entities())
    filtered = [
        e for e in entities
        if start_ts <= float(e["RowKey"]) <= end_ts
        and "Light" in e
    ]
    filtered.sort(key=lambda e: float(e["RowKey"]), reverse=True)
    history = [
        {
          "time": datetime.fromtimestamp(float(e["RowKey"])).strftime("%Y-%m-%d %H:%M"),
          "intensity": e["Light"]
        }
        for e in filtered
    ]
    return jsonify(history)

PI2_URL = "http://192.168.0.185:5073/capture" 

@app.route('/upload_image/<int:plant_id>', methods=['POST'])
def upload_image(plant_id):
    file = request.files.get('file')
    if not file:
        return jsonify({"status":"error","message":"No file uploaded"}), 400

    filename = f"plant_{plant_id}.jpg"
    save_path = os.path.join(LOCAL_IMAGE_FOLDER, filename)
    file.save(save_path)

    with open(save_path, 'rb') as f:
        url = upload_to_azure(io.BytesIO(f.read()), f"plant_{plant_id}_{datetime.now():%Y%m%d_%H%M%S}.jpg")
    return jsonify({"status":"success","local": filename, "azure_url": url})
@app.route('/capture/<int:plant_id>', methods=['POST'])
def capture(plant_id):
    if plant_id == 2:
        try:
            resp = requests.post(PI2_URL, timeout=10)
            resp.raise_for_status()
            return resp.json() 
        except Exception as e:
            return jsonify({"status":"error","message":str(e)}), 500
    else:
        image_url = capture_image(plant_id)
        if image_url:
            return jsonify({"status": "success", "image_url": image_url})
        return jsonify({"status": "error", "message": "Failed to capture image"}), 500
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
    app.run(host='0.0.0.0', port=5071, debug=True, use_reloader=False)
