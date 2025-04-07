import RPi.GPIO as GPIO
import time

LDR_PIN = 18  # GPIO18, Physical pin 12

def rc_time(pin):
    reading = 0

    # Discharge capacitor
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, False)
    time.sleep(0.1)

    # Switch to input to read charging time
    GPIO.setup(pin, GPIO.IN)

    # Count until pin goes HIGH
    while GPIO.input(pin) == GPIO.LOW:
        reading += 1

    return reading

# Setup
GPIO.setmode(GPIO.BCM)

try:
    while True:
        light_level = rc_time(LDR_PIN)
        print("Light level:", light_level)
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting")
finally:
    GPIO.cleanup()
