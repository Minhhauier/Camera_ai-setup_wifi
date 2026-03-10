import os
import threading
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import subprocess
import json
import time

import mqtt_function as function
import control_gpio

BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

SERVICE_UUID = "a4f3c2b1-9d8e-4c7a-92f1-3e5b6c7d8e90"
CHAR_UUID    = "a4f3c2b1-9d8e-4c7a-92f1-3e5b6c7d8e91"
LOCAL_NAME   = "WIFI_SETUP_" + function.serial_number

# ✅ Gọi 1 lần duy nhất
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)


def wifi_link_connected(expected_ssid=None):
    """Return True when Wi-Fi link is connected (does not require internet)."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        for line in result.stdout.splitlines():
            # Format: DEVICE:TYPE:STATE:CONNECTION
            parts = line.strip().split(":")
            if len(parts) < 4:
                continue

            _, dev_type, state, connection = parts[0], parts[1], parts[2], parts[3]
            if dev_type == "wifi" and state == "connected":
                if expected_ssid is None:
                    return True
                if connection == expected_ssid:
                    return True
        return False
    except Exception as e:
        print("wifi_link_connected error:", e)
        return False


def set_adapter_provisioning_state(enabled):
    try:
        bus = dbus.SystemBus()
        adapter = bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez/hci0")
        props = dbus.Interface(adapter, DBUS_PROP_IFACE)
        props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(enabled))
        props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(enabled))
        print(f"Adapter provisioning state set: enabled={enabled}")
    except Exception as e:
        print("set_adapter_provisioning_state error:", e)


class DBusObject(dbus.service.Object):
    def get_properties(self):
        raise NotImplementedError

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self.get_properties().get(interface, {})


class Application(dbus.service.Object):
    def __init__(self, bus, index=0):
        self.path = f"/org/bluez/example/app{index}"
        self.services = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for char in service.characteristics:
                response[char.get_path()] = char.get_properties()
                for desc in char.descriptors:
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(DBusObject):
    PATH_BASE = "/org/bluez/example/service"

    def __init__(self, bus, index, uuid):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            "org.bluez.GattService1": {
                "UUID": self.uuid,
                "Primary": dbus.Boolean(True),
                "Characteristics": dbus.Array(
                    [char.get_path() for char in self.characteristics],
                    signature="o"
                )
            }
        }


class Characteristic(DBusObject):
    def __init__(self, bus, index, uuid, service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.descriptors = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": self.uuid,
                "Service": self.service.get_path(),
                "Flags": dbus.Array(["write"], signature="s"),
                "Descriptors": dbus.Array(
                    [desc.get_path() for desc in self.descriptors],
                    signature="o"
                )
            }
        }

    @dbus.service.method("org.bluez.GattCharacteristic1",
                         in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        text = bytes(value).decode("utf-8")
        print("Received JSON:", text)
        try:
            data     = json.loads(text)
            ssid     = data["ssid"]
            password = data["pass"]

            print("rescanning Wi-Fi networks...")
            subprocess.run(["nmcli", "device", "wifi", "rescan"])
            time.sleep(3)

            print("Connecting to:", ssid)
            subprocess.run(["nmcli", "connection", "delete", ssid], capture_output=True)
            result = subprocess.run(
                ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
                capture_output=True, text=True, timeout=30
            )
            print("nmcli stdout:", result.stdout)
            print("nmcli stderr:", result.stderr)

            if result.returncode == 0:
                sentinel = "/tmp/wifi_configured"
                with open(sentinel, "w") as f:
                    f.write(ssid)
                print(f"Wi-Fi connected, wrote sentinel {sentinel}")

                #  Restart stream sau 3s
                def do_restart():
                    time.sleep(3)
                    try:
                        import rtsp_stream
                        rtsp_stream.restart_stream()
                    except Exception as e:
                        print("restart stream error:", e)

                threading.Thread(target=do_restart, daemon=True).start()

                # Stop BLE loop when Wi-Fi link is really up (no internet check required)
                try:
                    if MAIN_LOOP is not None:
                        connected = False
                        for _ in range(20):
                            if wifi_link_connected(expected_ssid=ssid) or wifi_link_connected():
                                connected = True
                                break
                            time.sleep(1)

                        if connected:
                            print("Stopping BLE provisioning loop (Wi-Fi link connected)...")
                            GLib.idle_add(stop_provisioning)
                        else:
                            print("Wi-Fi link still not connected after nmcli; keeping BLE running")
                except Exception as e:
                    print("Error while deciding BLE stop:", e)
            else:
                print("nmcli non-zero return code; connection may have failed")

        except json.JSONDecodeError as e:
            print("JSON parse error:", e)
        except KeyError as e:
            print("Missing field in JSON:", e)
        except subprocess.TimeoutExpired:
            print("nmcli timeout")
        except Exception as e:
            print("Unexpected error:", e)


class Advertisement(DBusObject):
    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            "org.bluez.LEAdvertisement1": {
                "Type": dbus.String("peripheral"),
                "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s"),
                "LocalName": dbus.String(LOCAL_NAME),
                "Includes": dbus.Array(["tx-power"], signature="s")
            }
        }

    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
        print("Advertisement released")


def register_app_cb():       print("GATT Application registered successfully")
def register_app_error_cb(e): print("Failed to register GATT application:", e)
def register_ad_cb():        print("Advertisement registered successfully")
def register_ad_error_cb(e): print("Failed to register advertisement:", e)


# ─── State ────────────────────────────────────
MAIN_LOOP    = None
_ble_app     = None
_ble_adv     = None
_ble_svc     = None
_ble_char    = None
_ble_bus     = None
_ble_service_manager = None
_ble_ad_manager = None
_ble_running = False
_ble_counter = 0
# ──────────────────────────────────────────────

def start_provisioning(background=True):
    global MAIN_LOOP, _ble_app, _ble_adv, _ble_svc, _ble_char
    global _ble_bus, _ble_service_manager, _ble_ad_manager
    global _ble_running, _ble_counter
    control_gpio.control_led(True)  # Bật LED khi bắt đầu provisioning
    if _ble_running:
        print("BLE already running, stopping first...")
        stop_provisioning()
        time.sleep(1)

    _ble_counter += 1
    bus = dbus.SystemBus()

    adapter         = bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez/hci0")
    service_manager = dbus.Interface(adapter, GATT_MANAGER_IFACE)
    ad_manager      = dbus.Interface(adapter, LE_ADVERTISING_MANAGER_IFACE)

    _ble_bus = bus
    _ble_service_manager = service_manager
    _ble_ad_manager = ad_manager

    set_adapter_provisioning_state(True)

    app  = Application(bus, _ble_counter)
    svc  = Service(bus, _ble_counter, SERVICE_UUID)
    char = Characteristic(bus, _ble_counter, CHAR_UUID, svc)
    svc.add_characteristic(char)
    app.add_service(svc)

    _ble_app  = app
    _ble_svc  = svc
    _ble_char = char
    _ble_adv  = Advertisement(bus, _ble_counter)

    service_manager.RegisterApplication(
        app.get_path(), {},
        reply_handler=register_app_cb,
        error_handler=register_app_error_cb
    )
    ad_manager.RegisterAdvertisement(
        _ble_adv.get_path(), {},
        reply_handler=register_ad_cb,
        error_handler=register_ad_error_cb
    )

    print("WiFi Provisioning BLE Server Running...")
    MAIN_LOOP    = GLib.MainLoop()
    _ble_running = True

    if background:
        t = threading.Thread(target=MAIN_LOOP.run, daemon=True)
        t.start()
        return t
    else:
        MAIN_LOOP.run()


def stop_provisioning():
    global MAIN_LOOP, _ble_app, _ble_adv, _ble_svc, _ble_char
    global _ble_bus, _ble_service_manager, _ble_ad_manager
    global _ble_running

    _ble_running = False

    # Important: tell BlueZ to stop advertising and unregister GATT app.
    if _ble_ad_manager is not None and _ble_adv is not None:
        try:
            _ble_ad_manager.UnregisterAdvertisement(_ble_adv.get_path())
            print("Advertisement unregistered")
        except Exception as e:
            print("UnregisterAdvertisement error:", e)

    if _ble_service_manager is not None and _ble_app is not None:
        try:
            _ble_service_manager.UnregisterApplication(_ble_app.get_path())
            print("GATT application unregistered")
        except Exception as e:
            print("UnregisterApplication error:", e)

    for obj in [_ble_char, _ble_svc, _ble_adv, _ble_app]:
        if obj is not None:
            try:
                obj.remove_from_connection()
            except Exception as e:
                print(f"remove {type(obj).__name__} error:", e)

    control_gpio.control_led(False)  # Tắt LED khi dừng provisioning

    _ble_app = _ble_adv = _ble_svc = _ble_char = None
    _ble_ad_manager = _ble_service_manager = _ble_bus = None

    # Make adapter non-discoverable/non-pairable after provisioning finishes.
    set_adapter_provisioning_state(False)

    if MAIN_LOOP is not None:
        try:
            GLib.idle_add(MAIN_LOOP.quit)
        except Exception:
            pass
        MAIN_LOOP = None

    print("BLE provisioning stopped completely")


def setup_wifi():
    start_provisioning(background=False)


if __name__ == "__main__":
    start_provisioning(background=False)