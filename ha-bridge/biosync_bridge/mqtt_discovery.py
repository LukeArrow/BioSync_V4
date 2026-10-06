"""Home-Assistant-MQTT-Discovery für BioSync-Rohwerte."""

SENSORS = {
    "distance_raw": ("Füllstand Abstand Rohwert", "DIST", None, "cm"),
    "temperature_raw": ("Temperatur Rohwert", "TMP", None, "°C"),
    "turbidity_raw": ("Trübung Rohwert", "TUR", None, "ADC"),
    "tds_raw": ("TDS Rohwert", "TDS", None, "ADC"),
    "pump_active": ("Pumpe Aktivität", "PUMP_ACTIVE", None, None),
    "pump_error": ("Pumpe Fehler", "PUMP_ERROR", None, None),
    "vent_active": ("Lüftung Aktivität", "VENT_ACTIVE", None, None),
    "vent_error": ("Lüftung Fehler", "VENT_ERROR", None, None),
}
RELAY_ENTITIES = frozenset(("pump_active", "pump_error", "vent_active", "vent_error"))


def publish_discovery(client, root="biosync_v4"):
    availability = f"{root}/availability"
    device = {
        "identifiers": ["biosync_v4_display_node"],
        "name": "BioSync V4",
        "manufacturer": "BioSync",
        "model": "DisplayNode / HA-Bridge",
    }
    for slug in ("distance", "temperature", "turbidity", "tds"):
        client.publish(
            f"homeassistant/sensor/biosync_v4/{slug}/config", "", retain=True
        )

    for name in (
        "dist_offset", "dist_scale", "tmp_offset", "tmp_scale",
        "tur_x1", "tur_y1", "tur_x2", "tur_y2", "tur_x3", "tur_y3",
        "tds_a", "tds_b", "tds_c", "tds_d",
        "dist_threshold", "tur_threshold", "tds_threshold",
    ):
        client.publish(
            f"homeassistant/number/biosync_v4/{name}/config", "", retain=True
        )
    client.publish(
        "homeassistant/button/biosync_v4/read_config/config", "", retain=True
    )

    for slug, (name, state_key, device_class, unit) in SENSORS.items():
        config = {
            "name": name,
            "unique_id": f"biosync_v4_{slug}",
            "default_entity_id": f"sensor.biosync_v4_{slug}",
            "state_topic": (
                f"{root}/relay" if slug in RELAY_ENTITIES else f"{root}/state"
            ),
            "value_template": (
                "{% set v = value_json."
                + state_key
                + " %}{{ v if v != 'UNKNOWN' else None }}"
                if unit or device_class
                else "{{ value_json." + state_key + " }}"
            ),
            "availability_topic": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        if device_class:
            config["device_class"] = device_class
        if unit:
            config["unit_of_measurement"] = unit
        if slug.endswith(("active", "error")):
            config["entity_category"] = "diagnostic"
        client.publish(
            f"homeassistant/sensor/biosync_v4/{slug}/config",
            _json(config),
            retain=True,
        )

    for slug, name, state_key in (
        ("sensor_node", "SensorNode", "SENSOR_NODE"),
        ("relay_node", "RelayNode", "RELAY_NODE"),
    ):
        client.publish(
            f"homeassistant/binary_sensor/biosync_v4/{slug}/config",
            _json(
                {
                    "name": name,
                    "unique_id": f"biosync_v4_{slug}",
                    "default_entity_id": f"binary_sensor.biosync_v4_{slug}",
                    "state_topic": f"{root}/state",
                    "value_template": (
                        "{% set v = value_json."
                        + state_key
                        + " %}{{ 'ON' if v == 'ONLINE' else "
                        "'OFF' if v == 'OFFLINE' else None }}"
                    ),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "connectivity",
                    "entity_category": "diagnostic",
                    "availability_topic": availability,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device": device,
                }
            ),
            retain=True,
        )

    for slug, command in (("request_status", "STATUS_REQUEST"),):
        client.publish(
            f"homeassistant/button/biosync_v4/{slug}/config",
            _json(
                {
                    "name": "BioSync V4 Status anfordern",
                    "unique_id": f"biosync_v4_{slug}",
                    "command_topic": f"{root}/command",
                    "payload_press": command,
                    "availability_topic": availability,
                    "device": device,
                }
            ),
            retain=True,
        )


def _json(value):
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
