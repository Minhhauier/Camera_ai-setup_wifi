import time
import paho.mqtt.client as mqtt
import json
import threading
from connect_esp32 import temp_gas
import mqtt_function
import subprocess
import control_gpio
import rtsp_stream


MQTT_BROKER = "broker.chtlab.us"
topic = "SUCAM_" + mqtt_function.serial_number
_client = None

def get_client():
    global _client
    if _client is None:
        _client = mqtt.Client()
        _client.connect(MQTT_BROKER, 1883, 60)
        _client.loop_start()
    return _client

def publish_detected_fire_warning(typ, confidence):
    client = get_client()
    mqtt_function.publish_fire_detected(typ, confidence, client)


def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code " + str(rc))
    client.subscribe(topic)
def on_message(client, userdata, msg):
    print("Received message on topic " + msg.topic)
    try:
        payload = json.loads(msg.payload.decode())
        #print("Fire detected at:", payload.get("timestamp"))
        print("Received payload:", payload)
        if payload.get("command_type") == 200:
            print("BE request OTA")
            mqtt_function.publish_response(200,0,client)
        elif payload.get("command_type") == 201:
            print("BE request stream video")
            if(payload.get("data").get("action") == 1):
                print("Starting video stream")
                rtsp_stream.start_stream()
            elif(payload.get("data").get("action") == 0):
                print("Stopping video stream")
                rtsp_stream.stop_stream()
            mqtt_function.publish_response(201,3,client)
        elif payload.get("command_type") == 202:
            print("BE control camera")
            mqtt_function.publish_response(202,5,client)
        elif payload.get("command_type") == 203:
            print("BE zoom camera")
            mqtt_function.publish_response(203,9,client)
        elif payload.get("command_type") == 204:
            print("BE reboot")
            subprocess.run(["sudo", "reboot"])
        elif payload.get("command_type") == 205:
            print("BE control buzzer")
            if payload.get("data").get("action") == 1:
                print("Turning on buzzer")
                control_gpio.control_buzzer(True)
            elif payload.get("data").get("action") == 0:
                print("Turning off buzzer")
                control_gpio.control_buzzer(False)
            mqtt_function.publish_response(205,0,client)
    except json.JSONDecodeError:
        print("Failed to decode JSON payload")

def main():
    # if client is None:
    #     client = mqtt.Client()
    #     try:
    #         client.connect("broker.chtlab.us", 1883, 60)
    #     except Exception as e:
    #         print("Failed to connect to MQTT broker:", e)
    #         return
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    threading.Thread(target=temp_gas, args=(client,), daemon=True).start()
    try:
        client.connect(MQTT_BROKER, 1883, 60)
        print("Connecting to MQTT broker...")
        client.loop_forever()
    except Exception as e:
        print("Failed to connect to MQTT broker:", e)
if __name__ == "__main__":
    main()