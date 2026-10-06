import unittest

from biosync_bridge.telemetry_parser import (
    REQUIRED_FIELDS,
    TelemetryParseError,
    parse_relay_line,
    parse_telemetry_line,
)


class TelemetryParserTests(unittest.TestCase):
    def test_v4_telemetry_does_not_require_removed_fields(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=123.4;TMP=18.3;TUR=512;TDS=420;"
            "PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=UNKNOWN;VENT_ERROR=ERROR"
        )
        self.assertEqual(result["DIST"], 123.4)
        self.assertEqual(result["TUR"], 512.0)
        self.assertEqual(result["VENT_ACTIVE"], "UNKNOWN")
        self.assertEqual(
            REQUIRED_FIELDS,
            {
                "DIST",
                "TMP",
                "TUR",
                "TDS",
                "PUMP_ACTIVE",
                "PUMP_ERROR",
                "VENT_ACTIVE",
                "VENT_ERROR",
            },
        )
        self.assertFalse({"SD", "MAINT", "ALARM"} & REQUIRED_FIELDS)

    def test_unknown_sensor_values_are_preserved(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=UNKNOWN;TMP=UNKNOWN;TUR=UNKNOWN;TDS=UNKNOWN;"
            "PUMP_ACTIVE=UNKNOWN;PUMP_ERROR=UNKNOWN;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
        )
        self.assertEqual(result["DIST"], "UNKNOWN")
        self.assertEqual(result["TDS"], "UNKNOWN")

    def test_optional_node_statuses_are_parsed_and_old_telemetry_remains_valid(self):
        old_telemetry = (
            "$TELEMETRY;DIST=1;TMP=2;TUR=3;TDS=4;PUMP_ACTIVE=IDLE;"
            "PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
        )
        self.assertNotIn("SENSOR_NODE", parse_telemetry_line(old_telemetry))
        result = parse_telemetry_line(
            old_telemetry + ";SENSOR_NODE=ONLINE;RELAY_NODE=OFFLINE"
        )
        self.assertEqual(result["SENSOR_NODE"], "ONLINE")
        self.assertEqual(result["RELAY_NODE"], "OFFLINE")

    def test_invalid_optional_node_status_is_rejected(self):
        telemetry = (
            "$TELEMETRY;DIST=1;TMP=2;TUR=3;TDS=4;PUMP_ACTIVE=IDLE;"
            "PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE;SENSOR_NODE=UNKNOWN"
        )
        with self.assertRaises(TelemetryParseError):
            parse_telemetry_line(telemetry)

    def test_rejects_missing_fields_invalid_states_and_non_finite_values(self):
        with self.assertRaises(TelemetryParseError):
            parse_telemetry_line("$TELEMETRY;DIST=1")
        with self.assertRaises(TelemetryParseError):
            parse_telemetry_line(
                "$TELEMETRY;DIST=1;TMP=2;TUR=3;TDS=4;PUMP_ACTIVE=OFF;"
                "PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
            )
        with self.assertRaises(TelemetryParseError):
            parse_telemetry_line(
                "$TELEMETRY;DIST=nan;TMP=2;TUR=3;TDS=4;PUMP_ACTIVE=IDLE;"
                "PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
            )

    def test_raw_sensor_values_outside_plausible_ranges_become_unknown(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=501;TMP=-21;TUR=1024;TDS=-1;"
            "PUMP_ACTIVE=IDLE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
        )
        self.assertEqual(
            {key: result[key] for key in ("DIST", "TMP", "TUR", "TDS")},
            {key: "UNKNOWN" for key in ("DIST", "TMP", "TUR", "TDS")},
        )

    def test_relay_line_parses_all_four_fields_without_sensor_fields(self):
        self.assertEqual(
            parse_relay_line(
                "$RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;"
                "VENT_ACTIVE=UNKNOWN;VENT_ERROR=ERROR"
            ),
            {
                "PUMP_ACTIVE": "ACTIVE",
                "PUMP_ERROR": "IDLE",
                "VENT_ACTIVE": "UNKNOWN",
                "VENT_ERROR": "ERROR",
            },
        )

    def test_relay_line_rejects_invalid_state_missing_field_and_wrong_prefix(self):
        with self.assertRaises(TelemetryParseError):
            parse_relay_line(
                "$RELAY;PUMP_ACTIVE=OFF;PUMP_ERROR=IDLE;"
                "VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
            )
        with self.assertRaises(TelemetryParseError):
            parse_relay_line(
                "$RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE"
            )
        with self.assertRaises(TelemetryParseError):
            parse_relay_line(
                "$TELEMETRY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;"
                "VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
            )


if __name__ == "__main__":
    unittest.main()
