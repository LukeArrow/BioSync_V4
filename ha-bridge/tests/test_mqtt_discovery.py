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
                    "{% set v = value_json." + key + " %}{{ 'ON' if v == 'ONLINE' else "
                    "'OFF' if v == 'OFFLINE' else None }}",
                )
                self.assertEqual(config["payload_on"], "ON")
                self.assertEqual(config["payload_off"], "OFF")
                self.assertEqual(config["device_class"], "connectivity")
                self.assertEqual(config["entity_category"], "diagnostic")
                self.assertEqual(config["availability_topic"], "test_root/availability")
                self.assertEqual(
                    config["device"],
                    configs["homeassistant/sensor/biosync_v4/distance/config"][
                        "device"
                    ],
                )

    def test_numeric_and_unit_sensor_templates_treat_unknown_as_none(self):
        client = MagicMock()
        publish_discovery(client)
        configs = {
            call.args[0]: json.loads(call.args[1])
            for call in client.publish.call_args_list
        }
        for slug, key in (
            ("distance_raw", "DIST"),
            ("temperature_raw", "TMP"),
            ("turbidity_raw", "TUR"),
            ("tds_raw", "TDS"),
        ):
            with self.subTest(sensor=slug):
                config = configs[f"homeassistant/sensor/biosync_v4/{slug}/config"]
                self.assertEqual(
                    config["value_template"],
                    "{% set v = value_json."
                    + key
                    + " %}{{ v if v != 'UNKNOWN' else None }}",
                )

    def test_retained_configs_for_removed_entities_are_cleared(self):
        client = MagicMock()
        publish_discovery(client, "test_root")
        cleared = {
            call.args[0]
            for call in client.publish.call_args_list
            if call.args[1] == "" and call.kwargs.get("retain") is True
        }
        for slug in ("distance", "temperature", "turbidity", "tds"):
            self.assertIn(
                f"homeassistant/sensor/biosync_v4/{slug}/config", cleared
            )
        for name in ("dist_offset", "tur_x1", "tds_a", "tds_threshold"):
            self.assertIn(f"homeassistant/number/biosync_v4/{name}/config", cleared)
        self.assertIn(
            "homeassistant/button/biosync_v4/read_config/config", cleared
        )


if __name__ == "__main__":
    unittest.main()
