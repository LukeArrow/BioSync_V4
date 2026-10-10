import itertools
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml
from biosync_bridge.main import ROOT, BioSyncBridge
from jinja2 import Environment, StrictUndefined

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "homeassistant" / "packages" / "biosync_nextion.yaml"


def is_number(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


class NextionPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = yaml.safe_load(PACKAGE.read_text())

    def setUp(self):
        self.states = {
            "input_number.biosync_v4_distance_empty": "170",
            "input_number.biosync_v4_distance_full": "20",
            "sensor.biosync_v4_distance": "95",
            "sensor.biosync_v4_fill_percent": "50",
            "sensor.biosync_v4_temperature": "23.6",
            "sensor.biosync_v4_turbidity": "123.45",
            "sensor.biosync_v4_tds": "456.78",
        }
        self.env = Environment(undefined=StrictUndefined)
        self.env.globals.update(
            states=lambda entity: self.states.get(entity, "unknown"),
            is_number=is_number,
        )

    def render(self, template, **variables):
        return self.env.from_string(template).render(**variables).strip()

    def redraw(self):
        sequence = self.package["script"]["biosync_nextion_redraw"]["sequence"]
        variables = {
            key: self.render(value) for key, value in sequence[0]["variables"].items()
        }
        payloads = []
        for action in sequence[1:]:
            if "if" in action:
                if self.render(action["if"], **variables) != "True":
                    continue
                publishes = action["then"]
                contexts = [variables]
            else:
                repeat = action["repeat"]
                publishes = repeat["sequence"]
                contexts = [
                    {
                        **variables,
                        "repeat": SimpleNamespace(item=self.render(item, **variables)),
                    }
                    for item in repeat["for_each"]
                ]
            for context in contexts:
                for publish in publishes:
                    self.assertEqual(publish["service"], "mqtt.publish")
                    data = publish["data"]
                    self.assertEqual(data["topic"], "biosync_v4/command/nextion")
                    self.assertIs(data["retain"], False)
                    payload = self.render(data["payload"], **context)
                    self.assertTrue(all(0x20 <= ord(char) < 0x7F for char in payload))
                    self.assertLessEqual(len(payload), 120)
                    payloads.append(payload)
        return payloads

    def test_fill_formula_limits_helpers_and_invalid_values(self):
        template = self.package["template"][0]["sensor"][0]["state"]
        for distance, expected in [
            ("170", 0),
            ("20", 100),
            ("95", 50),
            ("0", 100),
            ("500", 0),
        ]:
            with self.subTest(distance=distance):
                self.states["sensor.biosync_v4_distance"] = distance
                self.assertEqual(float(self.render(template)), expected)
        self.states.update(
            {
                "input_number.biosync_v4_distance_empty": "200",
                "input_number.biosync_v4_distance_full": "50",
                "sensor.biosync_v4_distance": "125",
            }
        )
        self.assertEqual(float(self.render(template)), 50)
        for empty, full, distance in [
            ("20", "20", "20"),
            ("10", "20", "20"),
            ("unknown", "20", "20"),
            ("170", "unavailable", "20"),
            ("170", "20", "unknown"),
            ("170", "20", "nan"),
        ]:
            self.states.update(
                {
                    "input_number.biosync_v4_distance_empty": empty,
                    "input_number.biosync_v4_distance_full": full,
                    "sensor.biosync_v4_distance": distance,
                }
            )
            self.assertEqual(self.render(template), "None")

    def test_all_fields_and_number_rounding(self):
        payloads = self.redraw()
        self.assertEqual(len(payloads), 11)
        self.assertIn("nDist.val=50", payloads)
        self.assertIn("nTemp.val=24", payloads)
        self.assertIn('tTurb.txt="123.45"', payloads)
        self.assertIn('tTDS.txt="456.78"', payloads)
        self.assertIn("cSystemIdle.val=1", payloads)
        self.assertEqual(len({p.split("=")[0] for p in payloads}), 11)

    def test_missing_unsafe_and_extreme_sensor_values(self):
        for value in (
            "unknown",
            "unavailable",
            "nan",
            "inf",
            '1"\nÿ',
            "1e300",
            "-1e300",
        ):
            with self.subTest(value=value):
                for slug in ("fill_percent", "temperature", "turbidity", "tds"):
                    self.states[f"sensor.biosync_v4_{slug}"] = value
                payloads = self.redraw()
                if not is_number(value):
                    self.assertEqual(len(payloads), 9)
                    self.assertIn('tTurb.txt="--"', payloads)
                    self.assertIn('tTDS.txt="--"', payloads)
                else:
                    self.assertFalse(any(p.startswith("nTemp.") for p in payloads))

    def test_relay_priority_for_all_entity_states(self):
        options = ("IDLE", "ACTIVE", "ERROR", "UNKNOWN", "unknown", "unavailable")
        for values in itertools.product(options, repeat=2):
            for device in ("pump", "vent"):
                for suffix, value in zip(("active", "error"), values):
                    self.states[f"sensor.biosync_v4_{device}_{suffix}"] = value
            status = (
                "ERROR"
                if "ERROR" in values
                else "ACTIVE"
                if "ACTIVE" in values
                else "IDLE"
            )
            payloads = self.redraw()
            for device in ("Pump", "Vent"):
                self.assertIn(f't{device}.txt="{status}"', payloads)
                for suffix in ("Active", "Error"):
                    self.assertIn(
                        f"c{device}{suffix}.val={int(status == suffix.upper())}",
                        payloads,
                    )
            self.assertIn(f"cSystemIdle.val={int(status == 'IDLE')}", payloads)

    def test_triggers_hex_and_bridge_passthrough(self):
        automation = self.package["automation"][1]
        self.assertEqual(automation["mode"], "queued")
        self.assertEqual(
            automation["action"], [{"service": "script.biosync_nextion_redraw"}]
        )
        triggers = automation["trigger"]
        self.assertIn({"platform": "homeassistant", "event": "start"}, triggers)
        self.assertIn(
            {
                "platform": "mqtt",
                "topic": "biosync_v4/availability",
                "payload": "online",
            },
            triggers,
        )
        entities = triggers[1]["entity_id"]
        for entity in self.states:
            self.assertIn(entity, entities)
        for device in ("pump", "vent"):
            for suffix in ("active", "error"):
                self.assertIn(f"sensor.biosync_v4_{device}_{suffix}", entities)
        with patch("biosync_bridge.main.mqtt.Client"):
            bridge = BioSyncBridge("/dev/test", 115200, "broker.example", 1883)
        for text in ("BTN_REFRESH", "SCR_WAKE"):
            encoded = " ".join(f"{byte:02X}" for byte in text.encode("ascii"))
            trigger = next(
                t for t in triggers[3:] if t["payload"] == encoded.replace(" ", "")
            )
            self.assertEqual(trigger["topic"], "biosync_v4/nextion")
            for value in (encoded, encoded.lower(), encoded.replace(" ", "")):
                self.assertEqual(
                    self.render(trigger["value_template"], value=value),
                    trigger["payload"],
                )
            self.assertNotEqual(
                self.render(trigger["value_template"], value="65 00 01 01"),
                trigger["payload"],
            )
            bridge._handle_line("$NEXTION;" + encoded)
            bridge.client.publish.assert_called_with(
                f"{ROOT}/nextion", encoded, retain=False
            )
        with patch.object(bridge, "send_command") as send:
            for payload in self.redraw():
                bridge._on_message(
                    bridge.client,
                    None,
                    MagicMock(
                        topic=f"{ROOT}/command/nextion", payload=payload.encode("ascii")
                    ),
                )
                send.assert_called_with("NEX " + payload)

    def test_helpers_restore_and_do_not_reset_calibration(self):
        for helper in self.package["input_number"].values():
            self.assertNotIn("initial", helper)
        initialization = self.package["automation"][0]
        self.assertEqual(
            initialization["condition"][0]["entity_id"],
            "input_boolean.biosync_nextion_initialized",
        )
        self.assertEqual(
            [a["data"]["value"] for a in initialization["action"][:2]], [170, 20]
        )
        self.assertNotIn("biosync_calibration_initialized", PACKAGE.read_text())
