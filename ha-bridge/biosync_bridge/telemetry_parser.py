"""Parser für das USB-Protokoll des BioSync-DisplayNode."""

import math

TELEMETRY_FIELDS = (
    "DIST",
    "TMP",
    "TUR",
    "TDS",
    "PUMP_ACTIVE",
    "PUMP_ERROR",
    "VENT_ACTIVE",
    "VENT_ERROR",
)
REQUIRED_FIELDS = frozenset(TELEMETRY_FIELDS)
RELAY_FIELDS = ("PUMP_ACTIVE", "PUMP_ERROR", "VENT_ACTIVE", "VENT_ERROR")
RELAY_STATES = frozenset(("IDLE", "ACTIVE", "ERROR", "UNKNOWN"))


class TelemetryParseError(ValueError):
    """Eine Telemetriezeile entspricht nicht dem USB-Protokoll."""


def _parse_fields(line, prefix):
    text = line.strip()
    if not text.startswith(prefix + ";"):
        raise TelemetryParseError(f"Erwarteter Datensatz {prefix}")

    result = {}
    for item in text[len(prefix) + 1 :].split(";"):
        if not item or "=" not in item:
            raise TelemetryParseError("Ungültiges Feld")
        key, value = item.split("=", 1)
        if not key or not value or key in result:
            raise TelemetryParseError("Leeres oder doppeltes Feld")
        result[key] = value
    return result


def _number_or_unknown(value, key):
    if value == "UNKNOWN":
        return value
    try:
        number = float(value)
    except ValueError as error:
        raise TelemetryParseError(f"{key} muss eine Zahl oder UNKNOWN sein") from error
    if not math.isfinite(number):
        raise TelemetryParseError(f"{key} muss endlich sein")
    return number


def parse_telemetry_line(line):
    """Parst ``$TELEMETRY``; Sensorwerte sind Zahlen oder ``UNKNOWN``."""
    fields = _parse_fields(line, "$TELEMETRY")
    missing = REQUIRED_FIELDS.difference(fields)
    if missing:
        raise TelemetryParseError(f"Fehlende Felder: {', '.join(sorted(missing))}")

    parsed = {
        key: _number_or_unknown(fields[key], key)
        for key in ("DIST", "TMP", "TUR", "TDS")
    }
    for key in TELEMETRY_FIELDS[4:]:
        value = fields[key]
        if value not in RELAY_STATES:
            raise TelemetryParseError(f"Ungültiger Zustand für {key}: {value}")
        parsed[key] = value
    return parsed


def parse_relay_line(line):
    """Parst ``$RELAY`` mit den vier gültigen Relaiszuständen."""
    fields = _parse_fields(line, "$RELAY")
    missing = set(RELAY_FIELDS).difference(fields)
    if missing:
        raise TelemetryParseError(f"Fehlende Felder: {', '.join(sorted(missing))}")

    parsed = {}
    for key in RELAY_FIELDS:
        value = fields[key]
        if value not in RELAY_STATES:
            raise TelemetryParseError(f"Ungültiger Zustand für {key}: {value}")
        parsed[key] = value
    return parsed


def parse_config_line(line):
    """Parst einen ``$CONFIG``-Readback und validiert Zahlenwerte."""
    fields = _parse_fields(line, "$CONFIG")
    parsed = {}
    for key, value in fields.items():
        if not key.replace("_", "").isalnum():
            raise TelemetryParseError(f"Ungültiger Parametername: {key}")
        parsed[key] = _number_or_unknown(value, key)
    return parsed


parse_telemetry = parse_telemetry_line
