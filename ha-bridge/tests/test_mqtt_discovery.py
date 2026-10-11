import json
import unittest
from unittest.mock import MagicMock

from biosync_bridge.mqtt_discovery import publish_discovery


class MqttDiscoveryTests(unittest.TestCase):
    def test_node_connectivity_entities_use_expected_topics_and_device(self):
        client = MagicMock()
        publish_discovery(client, "test_root")
        configs = {
            call.args[0]: json.loads(call.args[1])
            for call in client.publish.call_args_list
            if call.args[1]
        }

        for slug, name, key in (
            ("sensor_node", "SensorNode", "SENSOR_NODE"),
            ("relay_node", "RelayNode", "RELAY_NODE"),
        ):
            with self.subTest(node=slug):
                topic = f"homeassistant/binary_sensor/biosync_v4/{slug}/config"
                config = configs[topic]
                self.assertEqual(config["name"], name)
                self.assertEqual(config["unique_id"], f"biosync_v4_{slug}")
                self.assertEqual(
                    config["default_entity_id"], f"binary_sensor.biosync_v4_{slug}"
                )
                self.assertEqual(config["state_topic"], "test_root/state")
                self.assertEqual(
                    config["value_template"],
                    "{% set v = value_json.get('"
                    + key
                    + "') %}{{ 'ON' if v == 'ONLINE' else "
                    "'OFF' if v == 'OFFLINE' else None }}",
                )
                self.assertEqual(config["payload_on"], "ON")
                self.assertEqual(config["payload_off"], "OFF")
                self.assertEqual(config["device_class"], "connectivity")
                self.assertEqual(config["entity_category"], "diagnostic")
                self.assertEqual(config["availability_topic"], "test_root/availability")
                self.assertEqual(
                    config["device"],
                    configs["homeassistant/sensor/biosync_v4/distance_raw/config"][
                        "device"
                    ],
                )

    def test_numeric_templates_accept_only_numbers_and_tolerate_missing_fields(self):
        client = MagicMock()
        publish_discovery(client)
        configs = {
            call.args[0]: json.loads(call.args[1])
            for call in client.publish.call_args_list
            if call.args[1]
        }
        for slug, key in (
            ("distance_raw", "DIST"),
            ("temperature_raw", "TMP"),
            ("turbidity_raw", "TUR"),
            ("tds_raw", "TDS"),
            ("sensor_age", "SENSOR_AGE"),
            ("relay_age", "RELAY_AGE"),
            ("relay_adc_a0", "A0"),
            ("relay_adc_a3", "A3"),
        ):
            with self.subTest(sensor=slug):
                config = configs[f"homeassistant/sensor/biosync_v4/{slug}/config"]
                self.assertEqual(
                    config["value_template"],
                    "{% set v = value_json.get('"
                    + key
                    + "') %}{{ v if v is number else None }}",
                )
                self.assertEqual(config["state_topic"], "biosync_v4/state")
        for slug, key, topic in (
            ("pump_active", "PUMP_ACTIVE", "relay"),
            ("vent_error", "VENT_ERROR", "relay"),
            ("distance_samples", "DIST_RAW", "state"),
        ):
            with self.subTest(sensor=slug):
                config = configs[f"homeassistant/sensor/biosync_v4/{slug}/config"]
                self.assertEqual(
                    config["value_template"], "{{ value_json.get('" + key + "') }}"
                )
                self.assertEqual(config["state_topic"], f"biosync_v4/{topic}")
                self.assertEqual(config["entity_category"], "diagnostic")

    def test_raw_diagnostic_entities_are_truncated_and_always_available(self):
        client = MagicMock()
        publish_discovery(client, "test_root")
        configs = {
            call.args[0]: json.loads(call.args[1])
            for call in client.publish.call_args_list
            if call.args[1]
        }
        for slug, topic in (
            ("usb_raw", "raw"),
            ("sensor_frame_raw", "raw_sensor"),
            ("relay_frame_raw", "raw_relay"),
            ("usb_unknown", "unknown"),
        ):
            with self.subTest(slug=slug):
                config = configs[f"homeassistant/sensor/biosync_v4/{slug}/config"]
                self.assertEqual(config["state_topic"], f"test_root/{topic}")
                self.assertEqual(config["value_template"], "{{ value[:255] }}")
                self.assertEqual(config["entity_category"], "diagnostic")
                self.assertEqual(config["unique_id"], f"biosync_v4_{slug}")
                self.assertNotIn("availability_topic", config)

    def test_retained_configs_for_removed_entities_are_cleared(self):
        client = MagicMock()
        publish_discovery(client, "test_root")
        cleared = {
            call.args[0]
            for call in client.publish.call_args_list
            if call.args[1] == "" and call.kwargs.get("retain") is True
        }
        for slug in ("distance", "temperature", "turbidity", "tds"):
            self.assertIn(f"homeassistant/sensor/biosync_v4/{slug}/config", cleared)
        for name in ("dist_offset", "tur_x1", "tds_a", "tds_threshold"):
            self.assertIn(f"homeassistant/number/biosync_v4/{name}/config", cleared)
        self.assertIn("homeassistant/button/biosync_v4/read_config/config", cleared)


if __name__ == "__main__":
    unittest.main()
