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
    "distance_samples": ("Füllstand Einzelmessungen", "DIST_RAW", None, None),
    "sensor_age": ("SensorNode Datenalter", "SENSOR_AGE", "duration", "s"),
    "relay_age": ("RelayNode Datenalter", "RELAY_AGE", "duration", "s"),
    "relay_adc_a0": ("RelayNode ADC A0", "A0", None, "ADC"),
    "relay_adc_a1": ("RelayNode ADC A1", "A1", None, "ADC"),
    "relay_adc_a2": ("RelayNode ADC A2", "A2", None, "ADC"),
    "relay_adc_a3": ("RelayNode ADC A3", "A3", None, "ADC"),
}
RELAY_ENTITIES = frozenset(("pump_active", "pump_error", "vent_active", "vent_error"))
DIAGNOSTIC_ENTITIES = frozenset(
    (
        "pump_active",
        "pump_error",
        "vent_active",
        "vent_error",
        "distance_samples",
        "sensor_age",
        "relay_age",
        "relay_adc_a0",
        "relay_adc_a1",
        "relay_adc_a2",
        "relay_adc_a3",
    )
)
# Ungefilterte Rohdaten-Topics; ohne availability_topic, damit sie immer sichtbar
# sind. HA erlaubt höchstens 255 Zeichen pro Zustand.
RAW_TOPICS = {
    "usb_raw": ("USB Rohzeile", "raw"),
    "sensor_frame_raw": ("SensorNode Rohframe", "raw_sensor"),
    "relay_frame_raw": ("RelayNode Rohframe", "raw_relay"),
    "usb_unknown": ("Unbekannte USB-Zeile", "unknown"),
}


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
        "dist_offset",
        "dist_scale",
        "tmp_offset",
        "tmp_scale",
        "tur_x1",
        "tur_y1",
        "tur_x2",
        "tur_y2",
        "tur_x3",
        "tur_y3",
        "tds_a",
        "tds_b",
        "tds_c",
        "tds_d",
        "dist_threshold",
        "tur_threshold",
        "tds_threshold",
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
                "{% set v = value_json.get('"
                + state_key
                + "') %}{{ v if v is number else None }}"
                if unit or device_class
                else "{{ value_json.get('" + state_key + "') }}"
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
        if slug in DIAGNOSTIC_ENTITIES:
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
                        "{% set v = value_json.get('"
                        + state_key
                        + "') %}{{ 'ON' if v == 'ONLINE' else "
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

    for slug, (name, topic) in RAW_TOPICS.items():
        client.publish(
            f"homeassistant/sensor/biosync_v4/{slug}/config",
            _json(
                {
                    "name": name,
                    "unique_id": f"biosync_v4_{slug}",
                    "default_entity_id": f"sensor.biosync_v4_{slug}",
                    "state_topic": f"{root}/{topic}",
                    "value_template": "{{ value[:255] }}",
                    "entity_category": "diagnostic",
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
