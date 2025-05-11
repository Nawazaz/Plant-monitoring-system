import adafruit_dht
import board
from datetime import datetime
from azure.data.tables import TableClient
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import time
import serial

dht_sensor = adafruit_dht.DHT22(board.D4)

TEMP_TABLE_SAS_URL = "key"
LIGHT_TABLE_SAS_URL = "key"

temp_table_client = TableClient.from_table_url(TEMP_TABLE_SAS_URL)
light_table_client = TableClient.from_table_url(LIGHT_TABLE_SAS_URL)

def get_ldr_value():
    try:
        arduino = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
        time.sleep(1)
        ldr_value = arduino.readline().decode('utf-8').strip()
        arduino.close()
        return int(ldr_value)
    except Exception as e:
        print(f"LDR read error: {e}")
        return None

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

def log_environmental_data():
    data = get_temperature_and_humidity()
    ldr_value = get_ldr_value()
    timestamp = datetime.utcnow().isoformat()
    row_key = str(datetime.now().timestamp())

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Temp: {data['temperature']}Â°C, Humidity: {data['humidity']}%, LDR: {ldr_value}")

    if data["temperature"] is not None and data["humidity"] is not None:
        try:
            temp_entity = {
                "PartitionKey": "Enviroment",
                "RowKey": row_key,
                "Temperature": data["temperature"],
                "Humidity": data["humidity"]
            }
            temp_table_client.create_entity(entity=temp_entity)
        except Exception as e:
            print(f"Azure Temp Table Insert Error: {e}")

    if ldr_value is not None:
        try:
            light_entity = {
                "PartitionKey": "LightLevel",
                "RowKey": row_key,
                "Light": ldr_value
            }
            light_table_client.create_entity(entity=light_entity)
        except Exception as e:
            print(f"Azure Light Table Insert Error: {e}")

def log_environmental_data_async():
    threading.Thread(target=log_environmental_data).start()

scheduler = BackgroundScheduler()

def schedule_jobs():
    for job in scheduler.get_jobs():
        job.remove()
    scheduler.add_job(func=log_environmental_data_async, trigger="interval", seconds=60, max_instances=3)

if not scheduler.running:
    schedule_jobs()
    scheduler.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Program interrupted. Exiting...")
