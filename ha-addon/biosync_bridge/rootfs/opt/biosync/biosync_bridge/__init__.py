"""Home-Assistant-Brücke für BioSync V4."""

from .telemetry_parser import parse_telemetry_line

__all__ = [
    "parse_telemetry_line",
]
