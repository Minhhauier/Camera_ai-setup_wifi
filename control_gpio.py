from gpiozero import Buzzer, Button
from signal import pause
import setup_wifi
import time

# Khởi tạo 1 lần (KHÔNG setup mỗi lần gọi)
buzzer = Buzzer(14)
button = Button(18, pull_up=True)

def control_buzzer(state):
    if state:
        buzzer.on()
    else:
        buzzer.off()

def gpio_function():
    try:
        while True:
            if button.is_pressed:
                print("Button pressed! Starting WiFi provisioning...")
                
                # Chờ thả nút (debounce đơn giản)
                while button.is_pressed:
                    time.sleep(0.1)

                setup_wifi.start_provisioning()

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass