"""USB-/MQTT-Brücke zwischen dem Mega und Home Assistant."""

import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt
import serial

from .conversions import convert_telemetry
from .mqtt_discovery import PARAMETERS, publish_discovery
from .telemetry_parser import (
    TelemetryParseError,
    parse_config_line,
    parse_relay_line,
    parse_telemetry_line,
)

LOG = logging.getLogger("biosync_bridge")
ROOT = os.getenv("BIOSYNC_MQTT_PREFIX", "biosync_v4")


class BioSyncBridge:
    def __init__(self, device, baud, broker, port):
        self.serial = serial.Serial(device, baud, timeout=0.2)
        self.serial_lock = threading.Lock()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="biosync-v4-bridge",
        )
        username = os.getenv("BIOSYNC_MQTT_USER")
        if username:
            self.client.username_pw_set(username, os.getenv("BIOSYNC_MQTT_PASSWORD"))
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(broker, port, keepalive=60)
        self.client.loop_start()
        self.client.publish(f"{ROOT}/availability", "online", retain=True)
        self.parameters = {}

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            LOG.error("MQTT-Verbindung fehlgeschlagen: %s", reason_code)
            return
        publish_discovery(client, ROOT)
        client.subscribe(
            [
                (f"{ROOT}/command", 0),
                (f"{ROOT}/command/nextion", 0),
                (f"{ROOT}/number/+/set", 0),
            ]
        )
        self.send_command("GET")

    def _on_message(self, client, userdata, message):
        payload = message.payload.decode("utf-8", errors="replace").strip()
        if message.topic == f"{ROOT}/command/nextion":
            if (
                payload
                and len(payload) <= 120
                and all(0x20 <= ord(char) < 0x7F for char in payload)
            ):
                self.send_command("NEX " + payload)
            else:
                LOG.warning("Ungültiges Nextion-Kommando verworfen")
        elif message.topic == f"{ROOT}/command":
            if payload in ("GET", "STATUS_REQUEST"):
                self.send_command(payload)
        elif message.topic.startswith(f"{ROOT}/number/"):
            name = message.topic.rsplit("/", 2)[-2]
            if name not in PARAMETERS:
                return
            try:
                value = float(payload)
            except ValueError:
                LOG.warning("Ungültiger Parameterwert für %s", name)
                return
            minimum, maximum, _, _ = PARAMETERS[name]
            if not minimum <= value <= maximum:
                LOG.warning("Parameterwert außerhalb des Bereichs: %s", name)
                return
            self.send_command(f"SET {name} {value:.8g}")

    def send_command(self, command):
        with self.serial_lock:
            self.serial.write((command + "\n").encode("utf-8"))
            self.serial.flush()

    def _publish_telemetry(self, values):
        result = convert_telemetry(values, self.parameters)
        self.client.publish(f"{ROOT}/state", json.dumps(result), retain=True)

    def run(self):
        last_request = time.monotonic()
        try:
            while True:
                raw = self.serial.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    self._handle_line(line)
                if time.monotonic() - last_request > 30:
                    self.send_command("GET")
                    last_request = time.monotonic()
        except KeyboardInterrupt:
            pass
        finally:
            self.client.publish(f"{ROOT}/availability", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            self.serial.close()

    def _handle_line(self, line):
        try:
            if line.startswith("$TELEMETRY;"):
                self._publish_telemetry(parse_telemetry_line(line))
            elif line.startswith("$RELAY;"):
                self.client.publish(
                    f"{ROOT}/relay",
                    json.dumps(parse_relay_line(line)),
                    retain=True,
                )
            elif line.startswith("$CONFIG;"):
                self.parameters.update(parse_config_line(line))
                self.client.publish(f"{ROOT}/config", json.dumps(self.parameters), retain=True)
            elif line.startswith("$NEXTION;"):
                self.client.publish(f"{ROOT}/nextion", line[len("$NEXTION;") :], retain=False)
        except TelemetryParseError as error:
            LOG.warning("Ungültige USB-Zeile verworfen: %s (%s)", line, error)


def main():
    logging.basicConfig(level=os.getenv("BIOSYNC_LOG_LEVEL", "INFO"))
    bridge = BioSyncBridge(
        os.getenv("BIOSYNC_SERIAL", "/dev/ttyACM0"),
        int(os.getenv("BIOSYNC_BAUD", "115200")),
        os.getenv("BIOSYNC_MQTT_HOST", "localhost"),
        int(os.getenv("BIOSYNC_MQTT_PORT", "1883")),
    )
    bridge.run()


if __name__ == "__main__":
    main()
