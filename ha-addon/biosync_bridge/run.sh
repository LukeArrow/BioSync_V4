#!/usr/bin/with-contenv bashio
set -euo pipefail

BIOSYNC_SERIAL="$(bashio::config 'serial_device')"
BIOSYNC_BAUD="$(bashio::config 'baud')"
BIOSYNC_MQTT_HOST=""
BIOSYNC_MQTT_PORT="$(bashio::config 'mqtt_port')"
BIOSYNC_MQTT_USER=""
BIOSYNC_MQTT_PASSWORD=""
BIOSYNC_MQTT_PREFIX="$(bashio::config 'mqtt_prefix')"
BIOSYNC_LOG_LEVEL="$(bashio::config 'log_level')"

if bashio::config.has_value 'mqtt_host'; then
    BIOSYNC_MQTT_HOST="$(bashio::config 'mqtt_host')"
fi
if bashio::config.has_value 'mqtt_user'; then
    BIOSYNC_MQTT_USER="$(bashio::config 'mqtt_user')"
fi
if bashio::config.has_value 'mqtt_password'; then
    BIOSYNC_MQTT_PASSWORD="$(bashio::config 'mqtt_password')"
fi

if [[ -z "${BIOSYNC_MQTT_HOST}" ]]; then
    if ! bashio::services.available 'mqtt'; then
        bashio::log.fatal 'Kein MQTT-Service verfügbar. Mosquitto starten oder mqtt_host konfigurieren.'
        exit 1
    fi
    BIOSYNC_MQTT_HOST="$(bashio::services 'mqtt' 'host')"
    BIOSYNC_MQTT_PORT="$(bashio::services 'mqtt' 'port')"
    BIOSYNC_MQTT_USER="$(bashio::services 'mqtt' 'username')"
    BIOSYNC_MQTT_PASSWORD="$(bashio::services 'mqtt' 'password')"
    if [[ "${BIOSYNC_MQTT_USER}" == "null" ]]; then
        BIOSYNC_MQTT_USER=""
    fi
    if [[ "${BIOSYNC_MQTT_PASSWORD}" == "null" ]]; then
        BIOSYNC_MQTT_PASSWORD=""
    fi
fi

export BIOSYNC_SERIAL BIOSYNC_BAUD BIOSYNC_MQTT_HOST BIOSYNC_MQTT_PORT
export BIOSYNC_MQTT_USER BIOSYNC_MQTT_PASSWORD BIOSYNC_MQTT_PREFIX BIOSYNC_LOG_LEVEL

exec python3 -m biosync_bridge.main
