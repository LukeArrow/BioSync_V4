"""USB-/MQTT-Brücke zwischen dem Mega und Home Assistant."""

import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt
import serial

from .mqtt_discovery import publish_discovery
from .telemetry_parser import (
    TelemetryParseError,
    parse_relay_line,
    parse_telemetry_line,
)

LOG = logging.getLogger("biosync_bridge")
ROOT = os.getenv("BIOSYNC_MQTT_PREFIX", "biosync_v4")
HA_STATUS_TOPIC = "homeassistant/status"
RECONNECT_MIN_DELAY = 1
RECONNECT_MAX_DELAY = 60


class BioSyncBridge:
    def __init__(self, device, baud, broker, port):
        self.device = device
        self.baud = baud
        self.serial = None
        self.serial_lock = threading.Lock()
        self.available = False
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="biosync-v4-bridge",
        )
        username = os.getenv("BIOSYNC_MQTT_USER")
        if username:
            self.client.username_pw_set(username, os.getenv("BIOSYNC_MQTT_PASSWORD"))
        self.client.on_connect = self._on_connect
        self.client.on_connect_fail = self._on_connect_fail
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(RECONNECT_MIN_DELAY, RECONNECT_MAX_DELAY)
        self.client.will_set(f"{ROOT}/availability", "offline", retain=True)
        self.client.connect_async(broker, port, keepalive=60)

    def _on_connect_fail(self, client, userdata):
        LOG.warning("MQTT-Verbindungsversuch fehlgeschlagen; Wiederholung mit Backoff")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            LOG.error("MQTT-Verbindung fehlgeschlagen: %s", reason_code)
            return
        with self.serial_lock:
            client.publish(
                f"{ROOT}/availability",
                "online" if self.available else "offline",
                retain=True,
            )
        publish_discovery(client, ROOT)
        client.publish(f"{ROOT}/config", "", retain=True)
        client.subscribe(
            [
                (f"{ROOT}/command", 0),
                (f"{ROOT}/command/nextion", 0),
                (HA_STATUS_TOPIC, 0),
            ]
        )
        self.send_command("STATUS_REQUEST")

    def _on_message(self, client, userdata, message):
        payload = message.payload.decode("utf-8", errors="replace").strip()
        if message.topic == HA_STATUS_TOPIC:
            if payload == "online":
                publish_discovery(client, ROOT)
                self.send_command("STATUS_REQUEST")
            return
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
            if payload == "STATUS_REQUEST":
                self.send_command(payload)

    def send_command(self, command):
        with self.serial_lock:
            if self.serial is None:
                LOG.warning("USB nicht verbunden; Kommando verworfen: %s", command)
                return
            try:
                self.serial.write((command + "\n").encode("utf-8"))
                self.serial.flush()
            except (serial.SerialException, OSError) as error:
                LOG.warning("USB-Schreibfehler: %s", error)
                self._close_serial_locked()

    def _close_serial_locked(self):
        if self.serial is not None:
            try:
                self.serial.close()
            except (serial.SerialException, OSError) as error:
                LOG.warning("USB-Port konnte nicht geschlossen werden: %s", error)
            finally:
                self.serial = None
        if self.available:
            self.available = False
            self.client.publish(f"{ROOT}/availability", "offline", retain=True)

    def _publish_telemetry(self, values):
        with self.serial_lock:
            self.client.publish(f"{ROOT}/state", json.dumps(values), retain=True)
            if self.serial is not None and not self.available:
                self.available = True
                self.client.publish(f"{ROOT}/availability", "online", retain=True)

    def run(self):
        retry_delay = RECONNECT_MIN_DELAY
        try:
            self.client.loop_start()
            while True:
                try:
                    with self.serial_lock:
                        reopened = self.serial is None
                        if reopened:
                            LOG.info("USB-Verbindungsversuch: %s", self.device)
                            self.serial = serial.Serial(
                                self.device, self.baud, timeout=0.2, write_timeout=1
                            )
                        raw = self.serial.readline()
                    if reopened:
                        LOG.info("USB-Verbindung hergestellt")
                        self.send_command("STATUS_REQUEST")
                except (serial.SerialException, OSError) as error:
                    LOG.warning(
                        "USB-Verbindung verloren: %s; neuer Versuch in %s s",
                        error,
                        retry_delay,
                    )
                    with self.serial_lock:
                        self._close_serial_locked()
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, RECONNECT_MAX_DELAY)
                    continue
                if raw:
                    retry_delay = RECONNECT_MIN_DELAY
                    line = raw.decode("utf-8", errors="replace").strip()
                    self._handle_line(line)
                with self.serial_lock:
                    disconnected = self.serial is None
                if disconnected:
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, RECONNECT_MAX_DELAY)
                    continue
        except KeyboardInterrupt:
            pass
        finally:
            self.client.publish(f"{ROOT}/availability", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            with self.serial_lock:
                self._close_serial_locked()

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
            elif line.startswith("$NEXTION;"):
                self.client.publish(
                    f"{ROOT}/nextion", line[len("$NEXTION;") :], retain=False
                )
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
