import unittest
from unittest.mock import MagicMock, call, patch

import serial
from biosync_bridge.main import (
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

    def test_every_mqtt_connect_republishes_discovery_and_requests_config(self):
        with (
            patch("biosync_bridge.main.publish_discovery") as discovery,
            patch.object(self.bridge, "send_command") as send,
        ):
            for _ in range(2):
                self.client.on_connect(self.client, None, {}, 0, None)
            self.assertEqual(discovery.call_args_list, [call(self.client, ROOT)] * 2)
            self.assertEqual(send.call_args_list, [call("GET")] * 2)
            self.assertEqual(self.client.subscribe.call_count, 2)
            self.assertEqual(
                self.client.publish.call_args_list,
                [call(f"{ROOT}/availability", "online", retain=True)] * 2,
            )
            with self.assertLogs("biosync_bridge", level="ERROR"):
                self.client.on_connect(self.client, None, {}, 1, None)
            self.assertEqual(discovery.call_count, 2)

    def test_initial_usb_failure_retries_then_processes_data(self):
        port = MagicMock()
        port.readline.side_effect = [
            b"$CONFIG;DIST_OFFSET=2\n",
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
        port.write.assert_called_once_with(b"GET\n")
        port.close.assert_called_once()
        self.assertEqual(self.bridge.parameters["DIST_OFFSET"], 2)
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
        restored_port.write.assert_called_once_with(b"GET\n")
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
        port.readline.side_effect = [b"$CONFIG;DIST_OFFSET=2\n", OSError("USB")]
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
        lost_port.readline.return_value = b""
        lost_port.write.side_effect = serial.SerialException("Schreibfehler")
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
        restored_port.write.assert_called_once_with(b"GET\n")
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
