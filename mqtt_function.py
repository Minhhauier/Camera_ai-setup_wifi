import paho.mqtt.client as mqtt
import json
import time

topic = "CAMAI/Detectfire"
serial_number = "CAMERA_AI_001"

def publish_wifi_infor(ssid, ip, rssi, client=None):
    if client is None:
        client = mqtt.Client()
        try:
            client.connect("broker.chtlab.us", 1883, 60)
        except Exception as e:
            print("Failed to connect to MQTT broker:", e)
            return
    payload = {
        "serial_number": serial_number,
        "command_type": 100,
        "data": {
            "ssid": ssid,
            "ip": ip,
            "rssi": rssi,
            "timestamp": time.time()
        }
    }
    try:
        client.publish(topic, json.dumps(payload))
        print("Published WiFi info:", payload)
    except Exception as e:
        print("Failed to publish WiFi info:", e)

def publish_value_sensor(temp,gas,pos,client=None):
    if client is None:
        client = mqtt.Client()
        try:
            client.connect("broker.chtlab.us", 1883, 60)
        except Exception as e:
            print("Failed to connect to MQTT broker:", e)
            return
    payload = {
        "serial_number": serial_number,
        "command_type": 101,
        "data": {
            "temp": temp,
            "gas": gas,
            "pos": pos,
            "timestamp": time.time()
        }
    }
    try:
        client.publish(topic, json.dumps(payload))
        print("Published sensor data:", payload)
    except Exception as e:
        print("Failed to publish sensor data:", e)

def publish_fire_detected(typ,confidence,client=None):
    if client is None:
        client = mqtt.Client()
        try:
            client.connect("broker.chtlab.us", 1883, 60)
        except Exception as e:
            print("Failed to connect to MQTT broker:", e)
            return
    payload = {
        "serial_number": serial_number,
        "command_type": 102,
        "data": {
            "type": typ,
            "confidence": confidence,
            "timestamp": time.time()
        }
    }
    try:
        client.publish(topic, json.dumps(payload))
        print("Published fire detected:", payload)
    except Exception as e:
        print("Failed to publish fire detected:", e)

def publish_response(cmd,status,client=None):
    if client is None:
        client = mqtt.Client()
        try:
            client.connect("broker.chtlab.us", 1883, 60)
        except Exception as e:
            print("Failed to connect to MQTT broker:", e)
            return
    payload = {
        "serial_number": serial_number,
        "command_type": 103,
        "data": {
            "cmd": cmd,
            "status": status,
            "timestamp": time.time()
        }
    }
    try:        
        client.publish(topic, json.dumps(payload))
        print("Published response:", payload)
    except Exception as e:
        print("Failed to publish response:", e)
