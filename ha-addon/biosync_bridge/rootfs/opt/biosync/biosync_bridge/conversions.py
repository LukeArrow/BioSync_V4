"""Konfigurierbare Rohwert-Umrechnung für die BioSync-Sensoren."""

from bisect import bisect_left

TDS_TEMPERATURE_COEFFICIENT = 0.02

# Diese Stützpunkte und Polynomkoeffizienten werden an die installierten
# Sensoren angepasst; sie sind keine Firmware-Konstanten.
DEFAULT_TDS_COEFFICIENTS = (0.0, 0.0, 2.34, -622.0)
DEFAULT_TURBIDITY_POINTS = ((0.0, 0.0), (512.0, 500.0), (1023.0, 1000.0))

# Plausibilitätsgrenzen vor der Kalibrierung: cm, °C und 10-Bit-ADC-Rohwerte.
RAW_VALUE_LIMITS = {
    "DIST": (0.0, 500.0),
    "TMP": (-20.0, 60.0),
    "TUR": (0.0, 1023.0),
    "TDS": (0.0, 1023.0),
}


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


def convert_telemetry(values, parameters):
    """Ergänzt Telemetrie um kalibrierte Einheiten und HA-Konvertierungen."""
    result = dict(values)
    for key, (minimum, maximum) in RAW_VALUE_LIMITS.items():
        if result[key] != "UNKNOWN":
            raw = float(result[key])
            result[key] = raw if minimum <= raw <= maximum else "UNKNOWN"

    if result["DIST"] != "UNKNOWN":
        result["DIST"] = round(
            (result["DIST"] + parameters.get("DIST_OFFSET", 0.0))
            * parameters.get("DIST_SCALE", 1.0),
            2,
        )
    if result["TMP"] != "UNKNOWN":
        result["TMP"] = round(
            (result["TMP"] + parameters.get("TMP_OFFSET", 0.0))
            * parameters.get("TMP_SCALE", 1.0),
            2,
        )

    if result["TUR"] == "UNKNOWN":
        result["TUR_NTU"] = "UNKNOWN"
    else:
        points = [
            (
                parameters.get(f"TUR_X{index}", x),
                parameters.get(f"TUR_Y{index}", y),
            )
            for index, (x, y) in enumerate(DEFAULT_TURBIDITY_POINTS, 1)
        ]
        try:
            result["TUR_NTU"] = round(piecewise_linear(result["TUR"], points), 2)
        except ValueError:
            result["TUR_NTU"] = "UNKNOWN"

    if result["TDS"] == "UNKNOWN" or result["TMP"] == "UNKNOWN":
        result["TDS_PPM"] = "UNKNOWN"
    else:
        coefficients = tuple(
            parameters.get(key, default)
            for key, default in zip(
                ("TDS_A", "TDS_B", "TDS_C", "TDS_D"),
                DEFAULT_TDS_COEFFICIENTS,
            )
        )
        try:
            result["TDS_PPM"] = round(
                tds_ppm(result["TDS"], result["TMP"], coefficients), 2
            )
        except ValueError:
            result["TDS_PPM"] = "UNKNOWN"
    return result
