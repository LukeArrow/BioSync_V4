"""Parser für das USB-Protokoll des BioSync-DisplayNode.

Der Parser verwirft nichts: Es gibt keine Pflichtfelder, keine Bereichsgrenzen
und keine Zustandsprüfung. Endliche Zahlen werden zu ``float``, alles andere
bleibt unverändert als Text erhalten. Aussortiert wird in Home Assistant.
"""

import math

RELAY_FIELDS = ("PUMP_ACTIVE", "PUMP_ERROR", "VENT_ACTIVE", "VENT_ERROR")


class TelemetryParseError(ValueError):
    """Wird nicht mehr ausgelöst; nur für Rückwärtskompatibilität erhalten."""


def _parse_fields(line, prefix):
    text = line.strip()
    if text == prefix:
        body = ""
    elif text.startswith(prefix + ";"):
        body = text[len(prefix) + 1 :]
    else:
        body = text
    result = {}
    for index, item in enumerate(body.split(";")):
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator or not key:
            key, value = f"FIELD_{index}", item
        if key in result:
            key = f"{key}_{index}"
        result[key] = value
    return result


def _convert(value):
    try:
        number = float(value)
    except ValueError:
        return value
    return number if math.isfinite(number) else value


def parse_telemetry_line(line):
    """Parst ``$TELEMETRY``; alle Felder roh, Zahlen als ``float``."""
    return {
        key: _convert(value) for key, value in _parse_fields(line, "$TELEMETRY").items()
    }


def parse_relay_line(line):
    """Parst ``$RELAY``; alle Felder roh, Zahlen als ``float``."""
    return {
        key: _convert(value) for key, value in _parse_fields(line, "$RELAY").items()
    }


parse_telemetry = parse_telemetry_line
