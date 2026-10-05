"""Konfigurierbare Rohwert-Umrechnung für die BioSync-Sensoren."""

from bisect import bisect_left

TDS_TEMPERATURE_COEFFICIENT = 0.02

# Diese Stützpunkte und Polynomkoeffizienten werden an die installierten
# Sensoren angepasst; sie sind keine Firmware-Konstanten.
DEFAULT_TURBIDITY_POINTS = ((0.0, 0.0), (1023.0, 1000.0))
DEFAULT_TDS_COEFFICIENTS = (0.0, 0.0, 1.0, 0.0)


def piecewise_linear(raw_value, points=DEFAULT_TURBIDITY_POINTS):
    """Interpoliert/extrapoliert zwischen sortierten (ADC, NTU)-Stützpunkten."""
    value = float(raw_value)
    calibration = sorted((float(x), float(y)) for x, y in points)
    if len(calibration) < 2:
        raise ValueError("Mindestens zwei Trübungskalibrierpunkte erforderlich")
    if len({x for x, _ in calibration}) != len(calibration):
        raise ValueError("ADC-Stützpunkte müssen eindeutig sein")

    xs = [point[0] for point in calibration]
    index = bisect_left(xs, value)
    if index == 0:
        left, right = calibration[0], calibration[1]
    elif index == len(calibration):
        left, right = calibration[-2], calibration[-1]
    elif xs[index] == value:
        return calibration[index][1]
    else:
        left, right = calibration[index - 1], calibration[index]
    ratio = (value - left[0]) / (right[0] - left[0])
    return left[1] + ratio * (right[1] - left[1])


def tds_ppm(raw_value, temperature_c, coefficients=DEFAULT_TDS_COEFFICIENTS):
    """Wendet ein kubisches ADC→ppm-Polynom mit Kompensation auf 25 °C an."""
    if temperature_c is None:
        raise ValueError("Temperatur für TDS-Kompensation erforderlich")
    a, b, c, d = (float(value) for value in coefficients)
    raw = float(raw_value)
    uncompensated = ((a * raw + b) * raw + c) * raw + d
    factor = 1.0 + TDS_TEMPERATURE_COEFFICIENT * (float(temperature_c) - 25.0)
    if factor <= 0:
        raise ValueError("Ungültiger Temperaturkompensationsfaktor")
    return uncompensated / factor
