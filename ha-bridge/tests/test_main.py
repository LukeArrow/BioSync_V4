import json
import logging
import unittest
from unittest.mock import MagicMock, call, patch

import serial
from biosync_bridge.main import (
    HA_STATUS_TOPIC,
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
    ROOT,
    BioSyncBridge,
)


class BridgeReconnectTests(unittest.TestCase):
    def setUp(self):
        client_patch = patch("biosync_bridge.main.mqtt.Client")
        self.client_factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.client = self.client_factory.return_value
        self.bridge = BioSyncBridge("/dev/test", 115200, "broker.example", 1883)

    def assert_shutdown(self):
        self.client.publish.assert_any_call(
            f"{ROOT}/availability", "offline", retain=True
        )
        self.client.loop_stop.assert_called_once()
        self.client.disconnect.assert_called_once()
        self.assertIsNone(self.bridge.serial)

    def test_mqtt_connection_logs_success_only_when_connected(self):
        with (
            patch("biosync_bridge.main.publish_discovery"),
            patch.object(self.bridge, "send_command"),
            self.assertLogs("biosync_bridge", level="INFO") as logs,
        ):
            self.bridge._on_connect(self.client, None, {}, 0, None)
        self.assertEqual(logs.output, ["INFO:biosync_bridge:MQTT verbunden"])
        with self.assertLogs("biosync_bridge", level="INFO") as logs:
            self.bridge._on_connect(self.client, None, {}, 1, None)
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].levelno, logging.ERROR)

    def test_unknown_usb_line_warns_and_is_published_raw_and_unknown(self):
        line = "Datenmüll\x00\x1b"
        with self.assertLogs("biosync_bridge", level="WARNING") as logs:
            self.bridge._handle_line(line)
        self.assertEqual(
            logs.output,
            [
                "WARNING:biosync_bridge:Unbekannte USB-Zeile nach "
                f"{ROOT}/unknown: {line!r}"
            ],
        )
        self.assertEqual(
            self.client.publish.call_args_list,
            [
                call(f"{ROOT}/raw", line, retain=True),
                call(f"{ROOT}/unknown", line, retain=True),
            ],
        )

    def test_ack_and_err_lines_are_published_to_ack_topic(self):
        line = "$ACK;COMMAND=STATUS_REQUEST"
        with self.assertLogs("biosync_bridge", level="DEBUG") as logs:
            self.bridge._handle_line(line)
        self.assertEqual(
            logs.output,
            [
                f"DEBUG:biosync_bridge:USB RX: {line}",
                f"DEBUG:biosync_bridge:Bestätigung vom Mega: {line}",
            ],
        )
        self.client.publish.assert_called_with(f"{ROOT}/ack", line, retain=False)
        error = "$ERR;ERROR=UNKNOWN_COMMAND;COMMAND=GET"
        with self.assertLogs("biosync_bridge", level="WARNING"):
            self.bridge._handle_line(error)
        self.client.publish.assert_called_with(f"{ROOT}/ack", error, retain=False)

    def test_raw_frames_are_published_to_raw_sensor_and_raw_relay(self):
        for line, topic, payload in (
            (
                "$RAW_SENSOR;<SENSOR;DIST=1;CK=7B>",
                "raw_sensor",
                "<SENSOR;DIST=1;CK=7B>",
            ),
            ("$RAW_RELAY;OVERFLOW;<RELAY;A0=1", "raw_relay", "OVERFLOW;<RELAY;A0=1"),
        ):
            with self.subTest(topic=topic):
                self.client.publish.reset_mock()
                self.bridge._handle_line(line)
                self.assertEqual(
                    self.client.publish.call_args_list,
                    [
                        call(f"{ROOT}/raw", line, retain=True),
                        call(f"{ROOT}/{topic}", payload, retain=True),
                    ],
                )

    def test_relay_line_is_published_unfiltered(self):
        line = "$RELAY;PUMP_ACTIVE=OFF;A0=900"
        self.bridge._handle_line(line)
        self.client.publish.assert_called_with(
            f"{ROOT}/relay",
            json.dumps({"PUMP_ACTIVE": "OFF", "A0": 900.0}),
            retain=True,
        )

    def test_empty_usb_line_does_not_log_or_publish(self):
        with self.assertNoLogs("biosync_bridge", level="DEBUG"):
            self.bridge._handle_line("")
        self.client.publish.assert_not_called()

    def test_telemetry_logs_rx_and_publishes_raw_state_and_relay(self):
        line = (
            "$TELEMETRY;DIST=100;TMP=-127.0;TUR=512;TDS=420;"
            "PUMP_ACTIVE=IDLE;PUMP_ERROR=IDLE;VENT_ACTIVE=ACTIVE;VENT_ERROR=IDLE;"
            "A0=900;SENSOR_AGE=3"
        )
        with self.assertLogs("biosync_bridge", level="DEBUG") as logs:
            self.bridge._handle_line(line)
        raw, state, relay = self.client.publish.call_args_list
        self.assertEqual(raw, call(f"{ROOT}/raw", line, retain=True))
        self.assertEqual(state.args[0], f"{ROOT}/state")
        self.assertEqual(state.kwargs, {"retain": True})
        values = json.loads(state.args[1])
        self.assertEqual(values["TMP"], -127.0)
        self.assertEqual(values["A0"], 900.0)
        self.assertEqual(
            relay,
            call(
                f"{ROOT}/relay",
                json.dumps(
                    {
                        "PUMP_ACTIVE": "IDLE",
                        "PUMP_ERROR": "IDLE",
                        "VENT_ACTIVE": "ACTIVE",
                        "VENT_ERROR": "IDLE",
                    }
                ),
                retain=True,
            ),
        )
        self.assertEqual(
            logs.output,
            [
                f"DEBUG:biosync_bridge:USB RX: {line}",
                f"DEBUG:biosync_bridge:MQTT state: {values}",
            ],
        )

    def test_telemetry_without_relay_fields_publishes_state_only(self):
        self.bridge._handle_line("$TELEMETRY;SENSOR_NODE=OFFLINE")
        self.assertEqual(
            [entry.args[0] for entry in self.client.publish.call_args_list],
            [f"{ROOT}/raw", f"{ROOT}/state"],
        )

    def test_usb_command_logs_tx_before_writing(self):
        self.bridge.serial = MagicMock()
        with self.assertLogs("biosync_bridge", level="DEBUG") as logs:
            self.bridge.serial.write.side_effect = lambda _: self.assertEqual(
                logs.output, ["DEBUG:biosync_bridge:USB TX: STATUS_REQUEST"]
            )
            self.bridge.send_command("STATUS_REQUEST")
        self.bridge.serial.write.assert_called_once_with(b"STATUS_REQUEST\n")
        self.bridge.serial.flush.assert_called_once()

    def test_invalid_telemetry_is_published_without_warning(self):
        line = "$TELEMETRY;DIST=invalid"
        with self.assertNoLogs("biosync_bridge", level="WARNING"):
            self.bridge._handle_line(line)
        self.client.publish.assert_any_call(f"{ROOT}/raw", line, retain=True)
        self.client.publish.assert_any_call(
            f"{ROOT}/state", json.dumps({"DIST": "invalid"}), retain=True
        )

    def test_commands_are_forwarded_without_validation_except_newlines(self):
        with patch.object(self.bridge, "send_command") as send:
            for topic, payload, expected in (
                (f"{ROOT}/command/nextion", 't0.txt="ä"\r\nx' * 30, None),
                (f"{ROOT}/command/nextion", "", "NEX "),
                (f"{ROOT}/command", "GET", "GET"),
            ):
                self.bridge._on_message(
                    self.client,
                    None,
                    MagicMock(topic=topic, payload=payload.encode("utf-8")),
                )
                if expected is None:
                    expected = "NEX " + payload.replace("\r", "").replace("\n", "")
                send.assert_called_with(expected)
                self.assertNotIn("\n", send.call_args.args[0])

    def test_mqtt_initial_connection_uses_paho_async_retry_and_backoff(self):
        self.client.connect.assert_not_called()
        self.client.connect_async.assert_called_once_with(
            "broker.example", 1883, keepalive=60
        )
        self.client.reconnect_delay_set.assert_called_once_with(
            RECONNECT_MIN_DELAY, RECONNECT_MAX_DELAY
        )
        self.client.will_set.assert_called_once_with(
            f"{ROOT}/availability", "offline", retain=True
        )
        with self.assertLogs("biosync_bridge", level="WARNING"):
            self.client.on_connect_fail(self.client, None)

    def test_every_mqtt_connect_republishes_discovery_and_clears_old_config(self):
        with (
            patch("biosync_bridge.main.publish_discovery") as discovery,
            patch.object(self.bridge, "send_command") as send,
        ):
            for _ in range(2):
                self.client.on_connect(self.client, None, {}, 0, None)
            self.assertEqual(discovery.call_args_list, [call(self.client, ROOT)] * 2)
            self.assertEqual(
                send.call_args_list,
                [call("STATUS_REQUEST"), call("STATUS_REQUEST")],
            )
            self.assertEqual(self.client.subscribe.call_count, 2)
            self.client.subscribe.assert_called_with(
                [
                    (f"{ROOT}/command", 0),
                    (f"{ROOT}/command/nextion", 0),
                    (HA_STATUS_TOPIC, 0),
                ]
            )
            self.assertEqual(
                self.client.publish.call_args_list,
                [
                    call(f"{ROOT}/availability", "offline", retain=True),
                    call(f"{ROOT}/config", "", retain=True),
                ]
                * 2,
            )
            with self.assertLogs("biosync_bridge", level="ERROR"):
                self.client.on_connect(self.client, None, {}, 1, None)
            self.assertEqual(discovery.call_count, 2)

    def test_home_assistant_birth_requests_status_but_offline_does_not(self):
        with (
            patch("biosync_bridge.main.publish_discovery") as discovery,
            patch.object(self.bridge, "send_command") as send,
        ):
            self.bridge._on_message(
                self.client,
                None,
                MagicMock(topic=HA_STATUS_TOPIC, payload=b"online"),
            )
            discovery.assert_called_once_with(self.client, ROOT)
            send.assert_called_once_with("STATUS_REQUEST")

            discovery.reset_mock()
            send.reset_mock()
            self.bridge._on_message(
                self.client,
                None,
                MagicMock(topic=HA_STATUS_TOPIC, payload=b"offline"),
            )
            discovery.assert_not_called()
            send.assert_not_called()

    def test_usb_loss_is_unavailable_until_any_usb_line_after_reconnect(self):
        telemetry = (
            "$TELEMETRY;DIST=100;TMP=25;TUR=512;TDS=420;"
            "PUMP_ACTIVE=IDLE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
        )
        self.bridge.serial = MagicMock()
        self.bridge._handle_line(telemetry)
        self.assertTrue(self.bridge.available)
        self.client.publish.assert_any_call(
            f"{ROOT}/availability", "online", retain=True
        )
        self.bridge.serial = MagicMock()
        self.bridge.serial.write.side_effect = OSError("USB getrennt")
        with self.assertLogs("biosync_bridge", level="WARNING"):
            self.bridge.send_command("STATUS_REQUEST")
        self.assertFalse(self.bridge.available)
        self.assertEqual(
            self.client.publish.call_args_list[-1],
            call(f"{ROOT}/availability", "offline", retain=True),
        )
        self.client.publish.reset_mock()
        with (
            patch("biosync_bridge.main.publish_discovery"),
            patch.object(self.bridge, "send_command"),
        ):
            self.bridge._on_connect(self.client, None, {}, 0, None)
        self.client.publish.assert_any_call(
            f"{ROOT}/availability", "offline", retain=True
        )
        self.client.publish.assert_any_call(f"{ROOT}/config", "", retain=True)
        self.bridge._handle_line("$TELEMETRY;DIST=invalid")
        self.assertFalse(self.bridge.available)
        self.bridge._handle_line(telemetry)
        self.assertFalse(self.bridge.available)
        self.bridge.serial = MagicMock()
        self.client.publish.reset_mock()
        self.bridge._handle_line("$NEXTION;65 00 01 01")
        self.assertTrue(self.bridge.available)
        self.client.publish.assert_any_call(
            f"{ROOT}/availability", "online", retain=True
        )

    def test_usb_read_loss_publishes_offline(self):
        self.bridge.available = True
        port = MagicMock()
        port.readline.side_effect = OSError("USB getrennt")
        with (
            patch("biosync_bridge.main.serial.Serial", return_value=port),
            patch("biosync_bridge.main.time.sleep", side_effect=KeyboardInterrupt()),
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        self.assertFalse(self.bridge.available)
        self.assertGreaterEqual(
            self.client.publish.call_args_list.count(
                call(f"{ROOT}/availability", "offline", retain=True)
            ),
            2,
        )
        self.assert_shutdown()

    def test_initial_usb_failure_retries_without_configuration_request(self):
        port = MagicMock()
        port.readline.side_effect = [
            b"",
            KeyboardInterrupt(),
        ]
        with (
            patch(
                "biosync_bridge.main.serial.Serial",
                side_effect=[OSError("Gerät fehlt"), port],
            ) as open_port,
            patch("biosync_bridge.main.time.sleep") as sleep,
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        self.assertEqual(open_port.call_count, 2)
        open_port.assert_called_with("/dev/test", 115200, timeout=0.2, write_timeout=1)
        sleep.assert_called_once_with(RECONNECT_MIN_DELAY)
        port.write.assert_called_once_with(b"STATUS_REQUEST\n")
        port.close.assert_called_once()
        self.assert_shutdown()

    def test_usb_read_loss_closes_and_reopens_port(self):
        lost_port = MagicMock()
        lost_port.readline.side_effect = serial.SerialException("USB getrennt")
        restored_port = MagicMock()
        restored_port.readline.side_effect = [b"", KeyboardInterrupt()]
        with (
            patch(
                "biosync_bridge.main.serial.Serial",
                side_effect=[lost_port, restored_port],
            ),
            patch("biosync_bridge.main.time.sleep") as sleep,
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        sleep.assert_called_once_with(RECONNECT_MIN_DELAY)
        lost_port.close.assert_called_once()
        restored_port.write.assert_called_once_with(b"STATUS_REQUEST\n")
        restored_port.close.assert_called_once()
        self.assert_shutdown()

    def test_repeated_usb_failure_caps_backoff_and_interrupt_cleans_up(self):
        with (
            patch(
                "biosync_bridge.main.serial.Serial",
                side_effect=serial.SerialException("USB fehlt"),
            ),
            patch(
                "biosync_bridge.main.time.sleep",
                side_effect=[None] * 7 + [KeyboardInterrupt()],
            ) as sleep,
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        self.assertEqual(
            [entry.args[0] for entry in sleep.call_args_list],
            [1, 2, 4, 8, 16, 32, 60, 60],
        )
        self.assert_shutdown()

    def test_received_data_resets_usb_backoff(self):
        port = MagicMock()
        port.readline.side_effect = [b"$NEXTION;00\n", OSError("USB")]
        with (
            patch(
                "biosync_bridge.main.serial.Serial",
                side_effect=[OSError("USB"), OSError("USB"), port],
            ),
            patch(
                "biosync_bridge.main.time.sleep",
                side_effect=[None, None, KeyboardInterrupt()],
            ) as sleep,
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        self.assertEqual([entry.args[0] for entry in sleep.call_args_list], [1, 2, 1])
        self.assert_shutdown()

    def test_usb_write_failure_retries_without_crashing_mqtt_callback(self):
        lost_port = MagicMock()
        lost_port.write.side_effect = serial.SerialException("Schreibfehler")
        restored_port = MagicMock()
        restored_port.readline.side_effect = [b"", KeyboardInterrupt()]
        self.bridge.serial = lost_port
        with self.assertLogs("biosync_bridge", level="WARNING"):
            self.bridge._on_message(
                self.client,
                None,
                MagicMock(topic=f"{ROOT}/command", payload=b"STATUS_REQUEST"),
            )
        lost_port.close.assert_called_once()
        with (
            patch("biosync_bridge.main.serial.Serial", return_value=restored_port),
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        restored_port.write.assert_called_once_with(b"STATUS_REQUEST\n")
        self.assert_shutdown()

    def test_usb_close_failure_does_not_prevent_shutdown(self):
        port = MagicMock()
        port.readline.side_effect = KeyboardInterrupt()
        port.close.side_effect = OSError("Gerät entfernt")
        with (
            patch("biosync_bridge.main.serial.Serial", return_value=port),
            self.assertLogs("biosync_bridge", level="INFO"),
        ):
            self.bridge.run()
        self.assert_shutdown()


if __name__ == "__main__":
    unittest.main()
