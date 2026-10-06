import unittest

from biosync_bridge.conversions import (
    RAW_VALUE_LIMITS,
    convert_telemetry,
    piecewise_linear,
    tds_ppm,
)


class ConversionTests(unittest.TestCase):
    def test_raw_limits_accept_boundaries_and_reject_outliers(self):
        baseline = {"DIST": 123.4, "TMP": 25, "TUR": 512, "TDS": 420}
        for key, (minimum, maximum) in RAW_VALUE_LIMITS.items():
            for value in (minimum, maximum, (minimum + maximum) / 2):
                with self.subTest(key=key, value=value):
                    converted = convert_telemetry({**baseline, key: value}, {})
                    self.assertEqual(converted[key], value)
            for value in (
                minimum - 0.1,
                maximum + 0.1,
                float("nan"),
                float("inf"),
                float("-inf"),
                "UNKNOWN",
            ):
                with self.subTest(key=key, value=value):
                    converted = convert_telemetry({**baseline, key: value}, {})
                    self.assertEqual(converted[key], "UNKNOWN")
                    if key in ("TMP", "TDS"):
                        self.assertEqual(converted["TDS_PPM"], "UNKNOWN")
                    if key == "TUR":
                        self.assertEqual(converted["TUR_NTU"], "UNKNOWN")
        self.assertEqual(baseline["DIST"], 123.4)

    def test_limits_apply_before_not_after_calibration(self):
        values = {"DIST": 500, "TMP": 60, "TUR": 512, "TDS": 420}
        converted = convert_telemetry(values, {"DIST_OFFSET": 100, "TMP_OFFSET": 10})
        self.assertEqual(converted["DIST"], 600)
        self.assertEqual(converted["TMP"], 70)
        values["DIST"] = 501
        values["TMP"] = 61
        converted = convert_telemetry(values, {"DIST_OFFSET": -100, "TMP_OFFSET": -10})
        self.assertEqual(converted["DIST"], "UNKNOWN")
        self.assertEqual(converted["TMP"], "UNKNOWN")

    def test_piecewise_interpolation_and_end_extrapolation(self):
        points = ((0, 0), (100, 200), (200, 300))
        self.assertEqual(piecewise_linear(50, points), 100)
        self.assertEqual(piecewise_linear(250, points), 350)

    def test_tds_cubic_and_temperature_compensation(self):
        coefficients = (0, 0, 2, 0)
        self.assertEqual(tds_ppm(10, 25, coefficients), 20)
        self.assertAlmostEqual(tds_ppm(10, 30, coefficients), 20 / 1.1)

    def test_invalid_calibration_and_temperature(self):
        with self.assertRaises(ValueError):
            piecewise_linear(10, ((1, 2),))
        with self.assertRaises(ValueError):
            tds_ppm(10, None)

    def test_bridge_applies_eeprom_calibration_and_preserves_unknown(self):
        values = {
            "DIST": 10,
            "TMP": 25,
            "TUR": 512,
            "TDS": 412,
            "PUMP_ACTIVE": "IDLE",
            "PUMP_ERROR": "UNKNOWN",
            "VENT_ACTIVE": "ACTIVE",
            "VENT_ERROR": "IDLE",
            "SENSOR_NODE": "ONLINE",
            "RELAY_NODE": "OFFLINE",
        }
        converted = convert_telemetry(
            values,
            {
                "DIST_OFFSET": 2,
                "DIST_SCALE": 2,
                "TMP_OFFSET": 1,
                "TMP_SCALE": 2,
                "TUR_X1": 0,
                "TUR_Y1": 0,
                "TUR_X2": 512,
                "TUR_Y2": 50,
                "TUR_X3": 1023,
                "TUR_Y3": 100,
                "TDS_A": 0,
                "TDS_B": 0,
                "TDS_C": 2,
                "TDS_D": -100,
            },
        )
        self.assertEqual(converted["DIST"], 24)
        self.assertEqual(converted["SENSOR_NODE"], "ONLINE")
        self.assertEqual(converted["RELAY_NODE"], "OFFLINE")
        self.assertEqual(converted["TMP"], 52)
        self.assertEqual(converted["TUR_NTU"], 50)
        self.assertAlmostEqual(converted["TDS_PPM"], (824 - 100) / 1.54, places=2)
        values["TDS"] = "UNKNOWN"
        self.assertEqual(convert_telemetry(values, {})["TDS_PPM"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
