import serial
import re
import time
import mqtt_function as function
# ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
# while True:
#     line = ser.readline().decode('utf-8').rstrip()
#     if line:
#         temperature = re.search(r"Temp=([0-9.]+)C", line)
#         # print("Received from ESP32:", line)
#         if temperature:
#             temp = temperature.group(1)
#             print("Temperature:", temp, "°C")
#         raw_gas = re.search(r"Raw=(\d+)", line)
#         if raw_gas:
#             gas = raw_gas.group(1)
#             print("Gas:", gas)
value = [0,0]
def temp_gas(client=None):
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    last_update = time.time()
    while True:
        line = ser.readline().decode('utf-8').rstrip()
        if line:
            temperature = re.search(r"Temp=([0-9.]+)C", line)
            # print("Received from ESP32:", line)
            if temperature:
                temp = temperature.group(1)
                value[0] = float(temp)
                print("Temperature:", temp, "°C")
            raw_gas = re.search(r"Raw=(\d+)", line)
            if raw_gas:
                gas = raw_gas.group(1)
                value[1] = int(gas)
                print("Gas:", gas)
        if time.time() - last_update > 20:  # Cập nhật mỗi 20 giây
            function.publish_value_sensor(value[0],value[1],0,client)
            last_update = time.time()
        time.sleep(1)
        