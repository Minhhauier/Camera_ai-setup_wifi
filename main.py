import os
import time
import subprocess

from setup_wifi import start_provisioning
import rtsp_stream   # file RTSP của bạn
import mqtt

import control_gpio
import threading
import connect_esp32 as esp32
SENTINEL = "/home/pi/.wifi_configured"


def wifi_connected():
    for host in ["8.8.8.8", "1.1.1.1", "google.com"]:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "3", host],
                capture_output=True
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False

def ensure_wifi():
    connected = False
    while True:
        if wifi_connected():
            print("WiFi already connected")
            return

        print("WiFi not connected → starting BLE provisioning")
        start_provisioning(background=False)  
        # block tới khi MAIN_LOOP.quit()

        print("BLE stopped. Checking WiFi again...")

        # đợi wifi lên hẳn
        for _ in range(10):
            if wifi_connected():
                print("WiFi connected successfully!")
                connected = True
                return
            time.sleep(1)
        if connected:
            break
        print("WiFi still not connected...")
    


def main():

    ensure_wifi()
    threading.Thread(target=control_gpio.gpio_function, daemon=True).start()
    # threading.Thread(target=esp32.temp_gas, daemon=True).start()
    print("Starting RTSP stream...")
    rtsp_stream.main()
    # print("RTSP stream stopped. Restarting...")
    # rtsp_stream.main()
    


if __name__ == "__main__":
    main()
