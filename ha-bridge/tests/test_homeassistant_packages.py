import ast
import math
import unittest
from pathlib import Path

import yaml
from biosync_bridge.mqtt_discovery import SENSORS
from jinja2.nativetypes import NativeEnvironment

PACKAGES = Path(__file__).resolve().parents[2] / "homeassistant" / "packages"


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate YAML key")
        return super().construct_mapping(node, deep=deep)


def is_number(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


class PackageTemplates:
    """Execute package Jinja, not HA's entity lifecycle or statistics engine."""

    def __init__(self):
        self.packages = {
            path.stem: yaml.load(path.read_text(), Loader=UniqueKeyLoader)
            for path in PACKAGES.glob("*.yaml")
        }
        self.entities = {}
        for package in self.packages.values():
            for block in package["template"]:
                for domain in ("sensor", "binary_sensor"):
                    for entity in block.get(domain, []):
                        self.entities[entity["default_entity_id"]] = (domain, entity)
        self.states = {}
        self.attributes = {}
        self.dependencies = set()
        self.env = NativeEnvironment()
        self.env.globals.update(
            states=self.get_state,
            state_attr=self.get_attribute,
            is_number=is_number,
            is_state=lambda entity, value: self.get_state(entity) == value,
        )

    def get_state(self, entity):
        self.dependencies.add(entity)
        return self.states.get(entity, "unknown")

    def get_attribute(self, entity, attribute):
        self.dependencies.add(entity)
        return self.attributes.get(entity, {}).get(attribute)

    def render(self, expression):
        value = self.env.from_string(str(expression)).render()
        if isinstance(value, str):
            value = value.strip()
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass
        return value

    def evaluate(self, entity_id):
        domain, entity = self.entities[entity_id]
        # Render the state even when unavailable to catch unsafe divisions/casts.
        value = self.render(entity["state"])
        available = self.render(entity.get("availability", "{{ true }}"))
        if not available:
            state = "unavailable"
        elif value is None:
            state = "unknown"
        elif domain == "binary_sensor":
            state = "on" if value else "off"
        else:
            state = str(value).strip()
        self.states[entity_id] = state
        self.attributes[entity_id] = {
            key: self.render(expression)
            for key, expression in entity.get("attributes", {}).items()
        }
        return state

    def evaluate_diagnostics(self):
        # Independent source lists precede their counts; no self-reference.
        self.evaluate("sensor.biosync_v4_distance_cm")
        self.evaluate("sensor.biosync_v4_temperature_celsius")
        for block in self.packages["biosync_v4_diagnostics"]["template"]:
            for domain in ("binary_sensor", "sensor"):
                for entry in block.get(domain, []):
                    self.evaluate(entry["default_entity_id"])

    def healthy_inputs(self):
        self.attributes["sensor.biosync_v4_distance"] = {"unit_of_measurement": "cm"}
        self.attributes["sensor.biosync_v4_temperature"] = {"unit_of_measurement": "°C"}
        self.states.update(
            {
                "input_number.biosync_v4_empty_distance": "170",
                "input_number.biosync_v4_full_distance": "10",
                "input_boolean.biosync_maintenance": "off",
                "binary_sensor.biosync_v4_sensor_node": "on",
                "binary_sensor.biosync_v4_relay_node": "on",
                "sensor.biosync_v4_level_cm": "80",
                "sensor.biosync_v4_level_percent": "50",
                "sensor.biosync_v4_level_deviation_percent": "0",
                "sensor.biosync_v4_temperature_difference": "0",
                "sensor.biosync_v4_turbidity_deviation_percent": "0",
                "sensor.biosync_v4_tds_deviation_percent": "0",
            }
        )
        for slug, value in (
            ("distance", "90"),
            ("temperature", "20"),
            ("turbidity", "100"),
            ("tds", "200"),
        ):
            self.states[f"sensor.biosync_v4_{slug}"] = value
            self.states[f"sensor.biosync_v4_{slug}_raw"] = value
            self.states[f"sensor.biosync_v4_{slug}_mean_14d"] = value
        self.states["sensor.biosync_v4_level_mean_14d"] = "80"
        for relay in ("pump", "vent"):
            self.states[f"sensor.biosync_v4_{relay}_active"] = "IDLE"
            self.states[f"sensor.biosync_v4_{relay}_error"] = "IDLE"
        self.evaluate("sensor.biosync_v4_distance_cm")
        self.evaluate("sensor.biosync_v4_temperature_celsius")


class HomeAssistantPackageTests(unittest.TestCase):
    def setUp(self):
        self.ha = PackageTemplates()
        self.ha.healthy_inputs()

    def state(self, slug):
        self.ha.evaluate("sensor.biosync_v4_distance_cm")
        self.ha.evaluate("sensor.biosync_v4_temperature_celsius")
        return self.ha.evaluate(f"sensor.biosync_v4_{slug}")

    def diagnostic(self, slug):
        return self.ha.states[f"sensor.biosync_v4_{slug}"]

    def test_structure_ids_and_dependencies(self):
        with self.assertRaises(ValueError):
            yaml.load("template: []\ntemplate: []", Loader=UniqueKeyLoader)
        ids = []
        external = {f"sensor.biosync_v4_{slug}" for slug in SENSORS}
        external |= {
            "binary_sensor.biosync_v4_sensor_node",
            "binary_sensor.biosync_v4_relay_node",
        }
        for package in self.ha.packages.values():
            for domain in ("input_number", "input_boolean"):
                external |= {f"{domain}.{slug}" for slug in package.get(domain, {})}
            for entity in package.get("sensor", []):
                self.assertEqual(entity["platform"], "statistics")
                ids.append(entity["unique_id"])
                external.add(f"sensor.{entity['name']}")
        graph = {}
        for entity_id, (_, entity) in self.ha.entities.items():
            ids.append(entity["unique_id"])
            self.assertEqual(entity_id.split(".")[1], entity["unique_id"])
            self.ha.dependencies.clear()
            self.ha.evaluate(entity_id)
            graph[entity_id] = self.ha.dependencies.copy()
            self.assertLess(len(self.ha.states[entity_id]), 255)
        self.assertEqual(len(ids), len(set(ids)))
        allowed = external | self.ha.entities.keys()
        for dependencies in graph.values():
            self.assertLessEqual(dependencies, allowed)

        def visit(entity, ancestors):
            self.assertNotIn(entity, ancestors, "Cyclic template dependency")
            for dependency in graph.get(entity, set()):
                visit(dependency, ancestors | {entity})

        for entity in graph:
            visit(entity, set())
        for path in PACKAGES.glob("*.yaml"):
            text = path.read_text()
            self.assertNotIn("biosync_displaynode_usb_bridge_", text)
            self.assertNotIn("technikraum_", text)
            self.assertNotIn("last_changed", text)
            self.assertNotIn("last_updated", text)

    def test_statistics_use_calibrated_sources_and_level_not_distance(self):
        stats = self.ha.packages["biosync_v4_calculations"]["sensor"]
        self.assertEqual(len(stats), 4)
        self.assertEqual(
            {sensor["entity_id"] for sensor in stats},
            {
                "sensor.biosync_v4_level_cm",
                "sensor.biosync_v4_temperature_celsius",
                "sensor.biosync_v4_turbidity",
                "sensor.biosync_v4_tds",
            },
        )
        for sensor in stats:
            self.assertEqual(sensor["max_age"], {"days": 14})
            self.assertEqual(sensor["state_characteristic"], "average_step")
            self.assertGreaterEqual(sensor["sampling_size"], 14 * 24 * 3600)

    def test_geometry_persists_independently_of_calibration(self):
        package = self.ha.packages["biosync_v4_calculations"]
        for helper in package["input_number"].values():
            self.assertNotIn("initial", helper)
        flag = package["input_boolean"]["biosync_v4_geometry_initialized"]
        self.assertNotIn("initial", flag)
        automation = package["automation"][0]
        self.assertEqual(
            automation["condition"][0]["entity_id"],
            "input_boolean.biosync_v4_geometry_initialized",
        )
        self.assertNotIn("biosync_calibration_initialized", str(package))

    def test_geometry_clamping_and_observable_saturation(self):
        for distance, cm, percent, outside in (
            (170, 0, 0, "off"),
            (90, 80, 50, "off"),
            (10, 160, 100, "off"),
            (0, 170, 100, "on"),
            (180, 0, 0, "on"),
            (-5, 175, 100, "on"),
        ):
            with self.subTest(distance=distance):
                self.ha.states["sensor.biosync_v4_distance"] = str(distance)
                self.assertEqual(float(self.state("level_cm")), cm)
                self.assertEqual(float(self.state("level_percent")), percent)
                self.assertEqual(
                    self.ha.evaluate("binary_sensor.biosync_v4_out_of_geometry"),
                    outside,
                )
        for full in ("170", "180", "unknown", "unavailable", "abc"):
            self.ha.states["input_number.biosync_v4_full_distance"] = full
            self.assertEqual(self.state("level_cm"), "unavailable")
            self.assertEqual(self.state("level_percent"), "unavailable")
        for empty in ("0", "10", "unknown", "unavailable", "abc"):
            self.ha.healthy_inputs()
            self.ha.states["input_number.biosync_v4_empty_distance"] = empty
            self.assertEqual(self.state("level_cm"), "unavailable")
            self.assertEqual(self.state("level_percent"), "unavailable")

    def test_invalid_numeric_inputs_never_become_zero(self):
        pairs = {
            "distance_cm": ["sensor.biosync_v4_distance"],
            "temperature_celsius": ["sensor.biosync_v4_temperature"],
            "level_cm": ["sensor.biosync_v4_distance"],
            "level_percent": ["sensor.biosync_v4_distance"],
            "level_deviation_percent": [
                "sensor.biosync_v4_level_cm",
                "sensor.biosync_v4_level_mean_14d",
            ],
            "tds_deviation_percent": [
                "sensor.biosync_v4_tds",
                "sensor.biosync_v4_tds_mean_14d",
            ],
            "turbidity_deviation_percent": [
                "sensor.biosync_v4_turbidity",
                "sensor.biosync_v4_turbidity_mean_14d",
            ],
            "temperature_difference": [
                "sensor.biosync_v4_temperature",
                "sensor.biosync_v4_temperature_mean_14d",
            ],
            "tds_ntu_ratio": [
                "sensor.biosync_v4_tds",
                "sensor.biosync_v4_turbidity",
            ],
        }
        for slug, inputs in pairs.items():
            for entity in inputs:
                for invalid in ("unknown", "unavailable", "abc", "nan", "inf"):
                    with self.subTest(slug=slug, entity=entity, invalid=invalid):
                        self.ha.healthy_inputs()
                        self.ha.states[entity] = invalid
                        self.assertEqual(self.state(slug), "unavailable")

    def test_positive_denominators_identical_units_and_calibrated_ratio(self):
        for slug in ("level", "tds", "turbidity"):
            for baseline in ("0", "-1"):
                self.ha.states[f"sensor.biosync_v4_{slug}_mean_14d"] = baseline
                self.assertEqual(self.state(f"{slug}_deviation_percent"), "unavailable")
        self.ha.states["sensor.biosync_v4_level_mean_14d"] = "40"
        self.assertEqual(float(self.state("level_deviation_percent")), 100)
        self.ha.states["sensor.biosync_v4_tds_raw"] = "1000"
        self.ha.states["sensor.biosync_v4_turbidity_raw"] = "500"
        self.assertEqual(float(self.state("tds_ntu_ratio")), 2)
        for denominator in ("0", "-1"):
            self.ha.states["sensor.biosync_v4_turbidity"] = denominator
            self.assertEqual(self.state("tds_ntu_ratio"), "unavailable")

    def test_zero_and_negative_temperature_baselines_are_valid(self):
        for current, mean, expected in ((-10, 0, -10), (0, -10, 10), (0, 0, 0)):
            self.ha.states["sensor.biosync_v4_temperature"] = str(current)
            self.ha.states["sensor.biosync_v4_temperature_mean_14d"] = str(mean)
            self.assertEqual(float(self.state("temperature_difference")), expected)

    def test_distance_and_temperature_display_units_are_normalized(self):
        for unit, value in (
            ("mm", 900),
            ("cm", 90),
            ("m", 0.9),
            ("km", 0.0009),
            ("in", 90 / 2.54),
            ("ft", 90 / 30.48),
            ("yd", 90 / 91.44),
            ("mi", 90 / 160934.4),
        ):
            self.ha.states["sensor.biosync_v4_distance"] = str(value)
            self.ha.attributes["sensor.biosync_v4_distance"]["unit_of_measurement"] = (
                unit
            )
            self.assertAlmostEqual(float(self.state("distance_cm")), 90)
            self.assertEqual(float(self.state("level_cm")), 80)
            self.assertEqual(float(self.state("level_percent")), 50)
            self.ha.evaluate_diagnostics()
            self.assertEqual(
                self.ha.states["binary_sensor.biosync_v4_out_of_geometry"], "off"
            )
        for unit, value in (("°C", 25), ("°F", 77), ("K", 298.15)):
            self.ha.states["sensor.biosync_v4_temperature"] = str(value)
            self.ha.attributes["sensor.biosync_v4_temperature"][
                "unit_of_measurement"
            ] = unit
            self.ha.states["sensor.biosync_v4_temperature_mean_14d"] = "20"
            self.assertEqual(float(self.state("temperature_difference")), 5)
            self.ha.evaluate_diagnostics()
            self.assertEqual(self.diagnostic("process_warnings"), "0")
        for entity, normalized in (
            ("distance", "distance_cm"),
            ("temperature", "temperature_celsius"),
        ):
            for unit in (None, "unknown", "unsupported"):
                self.ha.healthy_inputs()
                self.ha.attributes[f"sensor.biosync_v4_{entity}"][
                    "unit_of_measurement"
                ] = unit
                self.assertEqual(self.state(normalized), "unavailable")
                self.ha.evaluate_diagnostics()
                self.assertEqual(
                    self.ha.states["binary_sensor.biosync_v4_configuration_problem"],
                    "on",
                )
                self.assertEqual(
                    self.ha.states["binary_sensor.biosync_v4_communication_problem"],
                    "off",
                )

    def test_relays_unknown_and_disconnected_nodes(self):
        for relay in ("pump", "vent"):
            for value, fault, communication in (
                ("ERROR", "on", "off"),
                ("IDLE", "off", "off"),
                ("UNKNOWN", "unavailable", "on"),
                ("unknown", "unavailable", "on"),
                ("unavailable", "unavailable", "on"),
            ):
                self.ha.healthy_inputs()
                self.ha.states[f"sensor.biosync_v4_{relay}_error"] = value
                self.ha.evaluate_diagnostics()
                self.assertEqual(
                    self.ha.states[f"binary_sensor.biosync_v4_{relay}_fault"], fault
                )
                self.assertEqual(
                    self.ha.states["binary_sensor.biosync_v4_communication_problem"],
                    communication,
                )
                if value != "IDLE":
                    self.assertEqual(self.diagnostic("diagnostic_level"), "ALARM")
        for node in ("sensor_node", "relay_node"):
            for value in ("off", "unknown", "unavailable"):
                self.ha.healthy_inputs()
                self.ha.states[f"binary_sensor.biosync_v4_{node}"] = value
                self.ha.states["input_boolean.biosync_maintenance"] = "on"
                self.ha.evaluate_diagnostics()
                self.assertEqual(self.diagnostic("diagnostic_level"), "ALARM")
        for relay in ("pump", "vent"):
            for value in ("ACTIVE", "IDLE", "UNKNOWN", "unavailable"):
                self.ha.healthy_inputs()
                self.ha.states[f"sensor.biosync_v4_{relay}_active"] = value
                self.assertEqual(
                    self.ha.evaluate("binary_sensor.biosync_v4_communication_problem"),
                    "off" if value in ("ACTIVE", "IDLE") else "on",
                )

    def test_startup_and_missing_diagnostic_status_never_clear_alarm(self):
        self.ha.states.clear()
        self.ha.evaluate_diagnostics()
        self.assertEqual(self.diagnostic("diagnostic_level"), "ALARM")
        self.assertEqual(
            self.ha.states["binary_sensor.biosync_v4_communication_problem"], "on"
        )
        self.ha.healthy_inputs()
        self.ha.evaluate_diagnostics()
        for cause in ("pump_fault", "vent_fault", "raw_invalid", "out_of_geometry"):
            self.ha.states[f"binary_sensor.biosync_v4_{cause}"] = "unavailable"
            self.assertEqual(self.ha.evaluate("binary_sensor.biosync_v4_alarm"), "on")
            self.ha.states[f"binary_sensor.biosync_v4_{cause}"] = "off"

    def test_hardware_limits_and_configuration_are_separate(self):
        for slug, low, high in (
            ("distance", 0, 500),
            ("temperature", -20, 60),
            ("turbidity", 0, 1023),
            ("tds", 0, 1023),
        ):
            for value, expected in (
                (low, "off"),
                (high, "off"),
                (low - 1, "on"),
                (high + 1, "on"),
            ):
                self.ha.healthy_inputs()
                self.ha.states[f"sensor.biosync_v4_{slug}_raw"] = str(value)
                self.assertEqual(
                    self.ha.evaluate("binary_sensor.biosync_v4_raw_invalid"), expected
                )
        self.ha.healthy_inputs()
        self.ha.states["sensor.biosync_v4_tds"] = "unavailable"
        self.ha.evaluate_diagnostics()
        self.assertEqual(
            self.ha.states["binary_sensor.biosync_v4_communication_problem"], "off"
        )
        self.assertEqual(
            self.ha.states["binary_sensor.biosync_v4_configuration_problem"], "on"
        )

    def test_missing_data_and_baselines_are_not_healthy(self):
        for entity in (
            "sensor.biosync_v4_distance_raw",
            "sensor.biosync_v4_tds_raw",
            "sensor.biosync_v4_temperature_raw",
            "sensor.biosync_v4_turbidity_raw",
        ):
            for value in ("unknown", "unavailable", "abc"):
                self.ha.healthy_inputs()
                self.ha.states[entity] = value
                self.ha.evaluate_diagnostics()
                self.assertEqual(self.diagnostic("diagnostic_level"), "ALARM")
        self.ha.healthy_inputs()
        self.ha.states["sensor.biosync_v4_level_deviation_percent"] = "unavailable"
        self.ha.evaluate_diagnostics()
        self.assertEqual(self.diagnostic("diagnostic_level"), "WARNUNG")
        self.ha.states["sensor.biosync_v4_level_percent"] = "unknown"
        self.ha.evaluate_diagnostics()
        self.assertEqual(self.diagnostic("process_warnings"), "0")
        self.assertNotIn(
            "Füllstand unter 15 %",
            self.ha.attributes["sensor.biosync_v4_process_warnings"]["meldungen"],
        )

    def test_threshold_counts_messages_and_priority(self):
        self.ha.evaluate_diagnostics()
        self.assertEqual(self.diagnostic("diagnostic_level"), "OK")
        self.ha.states["input_boolean.biosync_maintenance"] = "on"
        self.ha.evaluate_diagnostics()
        self.assertEqual(self.diagnostic("diagnostic_level"), "INFO")
        for slug, boundary, beyond in (
            ("turbidity_deviation_percent", 25, 25.01),
            ("tds_deviation_percent", -25, -25.01),
            ("temperature_difference", -8, -8.01),
            ("level_percent", 15, 14.99),
            ("level_percent", 95, 95.01),
        ):
            self.ha.healthy_inputs()
            self.ha.states[f"sensor.biosync_v4_{slug}"] = str(boundary)
            self.ha.evaluate_diagnostics()
            self.assertEqual(self.diagnostic("process_warnings"), "0")
            self.ha.states[f"sensor.biosync_v4_{slug}"] = str(beyond)
            self.ha.evaluate_diagnostics()
            messages = self.ha.attributes["sensor.biosync_v4_process_warnings"][
                "meldungen"
            ]
            self.assertEqual(len(messages), 1)
            self.assertEqual(self.diagnostic("process_warnings"), str(len(messages)))
            self.assertEqual(self.diagnostic("diagnostic_level"), "WARNUNG")

    def test_long_all_cause_list_is_not_a_sensor_state(self):
        for entity in ("turbidity_deviation_percent", "tds_deviation_percent"):
            self.ha.states[f"sensor.biosync_v4_{entity}"] = "30"
        self.ha.states["sensor.biosync_v4_temperature_difference"] = "9"
        self.ha.states["sensor.biosync_v4_level_percent"] = "10"
        self.ha.states["sensor.biosync_v4_pump_error"] = "ERROR"
        self.ha.states["sensor.biosync_v4_vent_error"] = "ERROR"
        self.ha.states["sensor.biosync_v4_temperature_raw"] = "61"
        self.ha.states["sensor.biosync_v4_distance"] = "200"
        self.ha.states["input_boolean.biosync_maintenance"] = "on"
        self.ha.evaluate_diagnostics()
        messages = self.ha.attributes["sensor.biosync_v4_diagnostic_causes"][
            "meldungen"
        ]
        self.assertGreater(len(" / ".join(messages)), 255)
        self.assertEqual(self.diagnostic("diagnostic_causes"), str(len(messages)))
        self.assertEqual(self.diagnostic("process_warnings"), "4")
        for slug in ("diagnostic_causes", "diagnostic_info", "diagnostic_shorttext"):
            self.assertLess(len(self.diagnostic(slug)), 255)


if __name__ == "__main__":
    unittest.main()
