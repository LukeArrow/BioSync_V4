import unittest

from biosync_bridge.telemetry_parser import parse_relay_line, parse_telemetry_line


class TelemetryParserTests(unittest.TestCase):
    def test_numbers_become_float_and_text_is_preserved(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=123.4;TMP=18.3;TUR=512;TDS=420;"
            "PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=UNKNOWN;VENT_ERROR=ERROR"
        )
        self.assertEqual(result["DIST"], 123.4)
        self.assertEqual(result["TUR"], 512.0)
        self.assertEqual(result["VENT_ACTIVE"], "UNKNOWN")
        self.assertEqual(result["PUMP_ACTIVE"], "ACTIVE")

    def test_values_outside_old_ranges_are_passed_through_raw(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=0.0;TMP=-127.0;TUR=1024;TDS=-1;"
            "PUMP_ACTIVE=OFF;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE;"
            "SENSOR_NODE=UNKNOWN"
        )
        self.assertEqual(result["DIST"], 0.0)
        self.assertEqual(result["TMP"], -127.0)
        self.assertEqual(result["TUR"], 1024.0)
        self.assertEqual(result["TDS"], -1.0)
        self.assertEqual(result["PUMP_ACTIVE"], "OFF")
        self.assertEqual(result["SENSOR_NODE"], "UNKNOWN")

    def test_missing_fields_and_unknown_fields_do_not_raise(self):
        self.assertEqual(parse_telemetry_line("$TELEMETRY;DIST=1"), {"DIST": 1.0})
        self.assertEqual(parse_telemetry_line("$TELEMETRY"), {})
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=1;DIST_RAW=0.0,20.0;CK=7B;A0=900;"
            "SENSOR_AGE=NEVER;RELAY_AGE=12"
        )
        self.assertEqual(result["DIST_RAW"], "0.0,20.0")
        self.assertEqual(result["CK"], "7B")
        self.assertEqual(result["A0"], 900.0)
        self.assertEqual(result["SENSOR_AGE"], "NEVER")
        self.assertEqual(result["RELAY_AGE"], 12.0)

    def test_malformed_fields_are_kept_instead_of_rejected(self):
        result = parse_telemetry_line(
            "$TELEMETRY;DIST=nan;TMP=inf;TUR=;garbage;=x;CK=7B;CK=1F;;TDS=abc"
        )
        self.assertEqual(result["DIST"], "nan")
        self.assertEqual(result["TMP"], "inf")
        self.assertEqual(result["TUR"], "")
        self.assertEqual(result["FIELD_3"], "garbage")
        self.assertEqual(result["FIELD_4"], "=x")
        self.assertEqual(result["CK"], "7B")
        self.assertEqual(result["CK_6"], "1F")
        self.assertEqual(result["TDS"], "abc")

    def test_relay_line_keeps_all_fields_and_any_state(self):
        self.assertEqual(
            parse_relay_line(
                "$RELAY;PUMP_ACTIVE=OFF;PUMP_ERROR=IDLE;VENT_ACTIVE=UNKNOWN;A3=2"
            ),
            {
                "PUMP_ACTIVE": "OFF",
                "PUMP_ERROR": "IDLE",
                "VENT_ACTIVE": "UNKNOWN",
                "A3": 2.0,
            },
        )
        self.assertEqual(parse_relay_line("$RELAY"), {})


if __name__ == "__main__":
    unittest.main()
