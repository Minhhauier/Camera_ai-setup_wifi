import serial
import time
import re
import os
import mqtt_function as function

def temp_gas(client=None):
    ser = None
    last_update = time.time()
    value = [0.0, 0]  # [temperature, gas]
    while True:

        # 1️⃣ Nếu chưa có serial → thử kết nối
        if ser is None:
            if os.path.exists('/dev/ttyUSB0'):
                try:
                    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
                    print("ESP32 connected")
                except Exception as e:
                    print("Serial open failed:", e)
                    time.sleep(3)
                    continue
            else:
                #print("Waiting for ESP32...")
                time.sleep(3)
                continue

        # 2️⃣ Đọc dữ liệu
        try:
            line = ser.readline().decode('utf-8').rstrip()

            if line:
                temperature = re.search(r"Temp=([0-9.]+)C", line)
                if temperature:
                    temp = temperature.group(1)
                    value[0] = float(temp)
                    print("Temperature:", temp, "°C")

                raw_gas = re.search(r"Raw=(\d+)", line)
                if raw_gas:
                    gas = raw_gas.group(1)
                    value[1] = int(gas)
                    print("Gas:", gas)

        except Exception as e:
            print("Serial read error:", e)
            ser.close()
            ser = None
            time.sleep(3)
            continue

        # 3️⃣ Publish mỗi 20 giây
        if time.time() - last_update > 20:
            if client:
                function.publish_value_sensor(value[0], value[1], 0, client)
            last_update = time.time()

        time.sleep(1)