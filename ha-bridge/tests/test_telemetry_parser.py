import unittest

from biosync_bridge.telemetry_parser import (
    REQUIRED_FIELDS,
    TelemetryParseError,
    parse_config_line,
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
        self.assertEqual(REQUIRED_FIELDS, {
            "DIST", "TMP", "TUR", "TDS", "PUMP_ACTIVE", "PUMP_ERROR",
            "VENT_ACTIVE", "VENT_ERROR",
        })
        self.assertFalse({"SD", "MAINT", "ALARM"} & REQUIRED_FIELDS)

    def test_unknown_sensor_values_are_preserved(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=UNKNOWN;TMP=UNKNOWN;TUR=UNKNOWN;TDS=UNKNOWN;"
            "PUMP_ACTIVE=UNKNOWN;PUMP_ERROR=UNKNOWN;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE"
        )
        self.assertEqual(result["DIST"], "UNKNOWN")
        self.assertEqual(result["TDS"], "UNKNOWN")

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

    def test_config_readback(self):
        self.assertEqual(parse_config_line("$CONFIG;DIST_OFFSET=1.5;TDS_A=0"), {
            "DIST_OFFSET": 1.5, "TDS_A": 0.0,
        })


if __name__ == "__main__":
    unittest.main()
