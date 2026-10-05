import unittest

from biosync_bridge.conversions import piecewise_linear, tds_ppm


class ConversionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
