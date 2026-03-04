# CAMERA_AI 
This project implements a smart camera system using a Raspberry Pi, which detects fire and sends alerts via MQTT. The system also controls a buzzer through GPIO when fire is detected. The main components of the project include:
- `main.py`: The entry point of the application that initializes the system, ensures Wi-Fi connectivity, and starts the RTSP stream and GPIO control threads.
- `rtsp_stream.py`: Handles the RTSP streaming and fire detection logic. It processes video frames, detects fire, and publishes alerts to MQTT when fire is detected (pushlish alerts when detected 100 frames fire only). You can watch the video stream via RTSP at `http://103.110.86.89:8889/fire` With '/fire' is the channel. The channel can be changed in `rtsp_stream.py`.
- `control_gpio.py`: Contains functions to control the GPIO pins, specifically for activating a buzzer when fire is detected and read button status to start setup wifi mode.
- `mqtt_function.py`: Contains functions to publish MQTT messages.
- `connect_esp32.py`: (Commented out) Intended for connecting to an ESP32 device to read temperature and gas sensor data.
## Setup Instructions
1. **Hardware Setup**:
   - Connect a camera module to the Raspberry Pi.
   - Connect a buzzer to GPIO14 on the Raspberry Pi.
   - Connect a button to GPIO18 on the Raspberry Pi
   - (Optional) Connect an ESP32 device with temperature and gas sensors for enhanced fire detection - In demo version, Esp32 connect to raspberry pi via uart protocol, in production version, it can be connected via Zigbee protocol.
2. **Software Setup**:
   - Install the required libraries and dependencies for the Raspberry Pi, including GStreamer for RTSP streaming, MQTT client libraries, and GPIO control libraries.
        + sudo apt update
        + sudo apt install python3-dbus
        + sudo apt install python3-gi gir1.2-glib-2.0
        + sudo apt install opencv-python
        + sudo apt install python3-numpy
        + pip install tflite-runtime
        + pip install paho-mqtt
        + sudo apt-get install gstreamer1.0-tools gstreamer1.0
   - Configure the MQTT broker settings in `mqtt_function.py` to ensure that the Raspberry Pi can publish messages to the correct MQTT topic.
        + format of subscribe topic: "SUCAM_serial_number" (serial number is the unique identifier of each camera)
        + format of publish topic: "CAMAI/Detectfire"
        ""serial_number and publish topic can be changed in mqtt_function.py""
3. **Running the Application**:
   - Run `main.py` to start the application. The system will check for Wi-Fi connectivity, start the RTSP stream, and begin monitoring for fire. When fire is detected, it will activate the buzzer and publish an alert to MQTT.
## Notes
- if you want your program can run automatically when the Raspberry Pi boots up, you can add the command to run `main.py` in the `rc.local` file or create a systemd service. Follow steps below:
    + create a systemd service file:
        *sudo nano /etc/systemd/system/YOUR_FILE_NAME.service
        *copy and paste the following content into the file (tando is the username, you can change it to your username and change the path to your main.py file for example "/home/tando/Documents/CAMERA_AI/main.py"):
        [Unit]
        Description=Fire AI Camera Service
        After=multi-user.target bluetooth.target
        Wants=bluetooth.target

        [Service]
        Type=simple
        User=tando
        WorkingDirectory=/home/tando/Documents/CAMERA_AI
        ExecStart=/usr/bin/python3 /home/tando/Documents/CAMERA_AI/main.py
        Restart=always
        RestartSec=5
        Environment="HOME=/home/tando"
        Environment="PYTHONUSERBASE=/home/tando/.local"
        Environment="PYTHONPATH=/home/tando/.local/lib/python3.13/site-packages"
        Environment="DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket"
        Environment="PYTHONUNBUFFERED=1"
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=multi-user.target
    + enable the service:
        *sudo systemctl daemon-reload
        *sudo systemctl enable YOUR_FILE_NAME.service
        *sudo systemctl start YOUR_FILE_NAME.service
    + check the status of the service:
        *sudo systemctl status YOUR_FILE_NAME.service
    + view the logs of the service:
        *journalctl -u YOUR_FILE_NAME.service -f
- Ensure that the camera module is properly connected and configured on the Raspberry Pi for the RTSP stream to work correctly.
- The fire detection model used in this project is a TensorFlow Lite model
    
