# 🌱 Plant Monitoring System – Flask Backend

This repository contains the **Flask backend** for a plant monitoring system that reads environmental sensors (temperature, humidity, soil moisture, light), captures plant images, logs data to Azure, and provides a REST API for frontend dashboards and analytics.  

---

## 🚀 Project Overview

The system monitors multiple plants and performs the following tasks:

- Reads **temperature and humidity** using DHT22 sensor  
- Reads **soil moisture** using capacitive sensors via Seesaw I2C  
- Reads **light intensity** via LDR sensor  
- Captures images of plants using USB cameras  
- Uploads sensor data and images to **Azure Blob Storage** and **Azure Table Storage**  
- Provides **REST API endpoints** for frontend dashboards and analytics  
- Runs **background jobs** to log data and capture images at regular intervals  

---

## 🧩 Features & Modules

### 🔹 Sensor Data Logging
- Temperature & Humidity via `DHT22`  
- Soil moisture via `Seesaw` I2C sensor  
- Light intensity via LDR connected to Arduino  

**Key Concepts:** Sensor interfacing, I2C communication, serial communication, data logging  

---

### 🔹 Data Storage
- Uploads sensor readings to **Azure Table Storage**  
- Stores plant images in **Azure Blob Storage**  

**Key Concepts:** Cloud integration, Azure SDK for Python  

---

### 🔹 Image Capture & Processing
- Captures images using USB cameras  
- Supports **automatic** and **on-demand** image capture  
- Uploads images to Azure for remote access  

**Key Concepts:** OpenCV, image processing, threading  

---

### 🔹 Flask API Endpoints
- `/sensor/temperature` – Get latest temperature & humidity  
- `/sensor/temperature/history` – Get temperature & humidity history  
- `/sensor/moisture/<plant_id>` – Get latest soil moisture for a plant  
- `/sensor/moisture/<plant_id>/history` – Get soil moisture history  
- `/sensor/light` – Get latest light intensity  
- `/sensor/light/history` – Get light intensity history  
- `/capture/<plant_id>` – Capture plant image  
- `/upload_image/<plant_id>` – Upload an image manually  
- `/analytics` – View plant image analytics  

**Key Concepts:** REST API design, JSON response, Flask routing  

---

### 🔹 Background Jobs
- Uses `APScheduler` for scheduled tasks  
- Logs sensor data every 60 seconds  
- Captures images at regular intervals  

**Key Concepts:** Task scheduling, threading, real-time monitoring  

---

## 🛠️ Hardware Requirements

- **Raspberry Pi x2** (or similar SBC)  
- **DHT22** temperature & humidity sensor  
- **Capacitive soil moisture sensor** with Seesaw I2C breakout  
- **LDR sensor** via Arduino for light measurement  
- **USB cameras** for image capture  
- **Internet connection** for Azure integration  

---

## 🧰 Software Requirements

- Python 3.x  
- Flask  
- OpenCV (`cv2`)  
- Azure SDKs (`azure-storage-blob`, `azure-data-tables`)  
- Adafruit libraries (`adafruit_dht`, `adafruit_seesaw`)  
- APScheduler  


flask-backend/
├── enviroment.py            # Sensor reading & Azure logging
├── app.py                   # Main Flask application
├── 2ndsetup.py              # Secondary Pi setup for Plant 2
├── templates/               # HTML templates for dashboard & analytics
│   ├── dashboard.html
│   ├── analytics.html
│   └── sidebar.html
├── temp_images/             # Temporary folder for captured images

## ▶️ Running the Backend

1. **Clone the repository and navigate to the backend folder:**  
   `git clone https://github.com/Nawazaz/Plant-monitoring-system.git`  
   `cd Plant-monitoring-system/flask-backend`

2. **Configure environment:**  
   Set environment variables or update Azure keys in `environment.py` and `app.py`.

3. **Start the Flask server:**  
   `python app.py`

4. **Access the dashboard:**  
   Open your browser and go to `http://<Raspberry_Pi_IP>:5071/`

5. **For Plant 2 (secondary Pi):**  
   Run `python 2ndsetup.py` to start background tasks for image capture and moisture logging.


⭐ If you find this project helpful, give it a star!
