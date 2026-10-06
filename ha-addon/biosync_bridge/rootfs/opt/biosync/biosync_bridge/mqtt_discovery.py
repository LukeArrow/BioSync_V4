"""Home-Assistant-MQTT-Discovery und Geräteparameter."""

PARAMETERS = {
    "DIST_OFFSET": (-100.0, 100.0, 0.1, "cm"),
    "DIST_SCALE": (0.1, 10.0, 0.01, ""),
    "TMP_OFFSET": (-20.0, 20.0, 0.1, "°C"),
    "TMP_SCALE": (0.1, 10.0, 0.01, ""),
    "TUR_X1": (0.0, 1023.0, 1.0, "ADC"),
    "TUR_Y1": (0.0, 10000.0, 1.0, "NTU"),
    "TUR_X2": (0.0, 1023.0, 1.0, "ADC"),
    "TUR_Y2": (0.0, 10000.0, 1.0, "NTU"),
    "TUR_X3": (0.0, 1023.0, 1.0, "ADC"),
    "TUR_Y3": (0.0, 10000.0, 1.0, "NTU"),
    "TDS_A": (-1.0, 1.0, 0.0001, ""),
    "TDS_B": (-100.0, 100.0, 0.001, ""),
    "TDS_C": (-10000.0, 10000.0, 0.01, ""),
    "TDS_D": (-10000.0, 10000.0, 0.1, "ppm"),
    "DIST_THRESHOLD": (0.0, 1000.0, 1.0, "cm"),
    "TUR_THRESHOLD": (0.0, 10000.0, 1.0, "NTU"),
    "TDS_THRESHOLD": (0.0, 10000.0, 1.0, "ppm"),
}

SENSORS = {
    "distance": ("Füllstand Abstand", "DIST", "distance", "cm"),
    "temperature": ("Temperatur", "TMP", "temperature", "°C"),
    "turbidity_raw": ("Trübung Rohwert", "TUR", None, "ADC"),
    "tds_raw": ("TDS Rohwert", "TDS", None, "ADC"),
    "turbidity": ("Trübung", "TUR_NTU", None, "NTU"),
    "tds": ("TDS", "TDS_PPM", None, "ppm"),
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

    for name, (minimum, maximum, step, unit) in PARAMETERS.items():
        slug = name.lower()
        config = {
            "name": f"BioSync V4 {name}",
            "unique_id": f"biosync_v4_{slug}",
            "default_entity_id": f"number.biosync_v4_{slug}",
            "state_topic": f"{root}/config",
            "value_template": "{{ value_json." + name + " }}",
            "command_topic": f"{root}/number/{name}/set",
            "min": minimum,
            "max": maximum,
            "step": step,
            "mode": "box",
            "optimistic": False,
            "availability_topic": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        if unit:
            config["unit_of_measurement"] = unit
        client.publish(
            f"homeassistant/number/biosync_v4/{slug}/config",
            _json(config),
            retain=True,
        )

    for slug, command in (("read_config", "GET"), ("request_status", "STATUS_REQUEST")):
        client.publish(
            f"homeassistant/button/biosync_v4/{slug}/config",
            _json(
                {
                    "name": "BioSync V4 "
                    + (
                        "Konfiguration lesen"
                        if command == "GET"
                        else "Status anfordern"
                    ),
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
