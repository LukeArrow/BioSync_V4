# BioSync V4 Bridge – Home-Assistant-Add-on

Die Python-Bridge verbindet den per USB angeschlossenen DisplayNode (Mega)
mit einem MQTT-Broker und veröffentlicht Home-Assistant-MQTT-Discovery.
Benötigt wird Home Assistant mit Supervisor (z. B. Home Assistant OS);
Home Assistant Container/Core allein kann keine Supervisor-Add-ons installieren.

## Installation

1. Unter **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositorys**
   `https://github.com/LukeArrow/BioSync_V4` hinzufügen.
2. **BioSync V4 Bridge** auswählen und installieren. Das Image wird lokal
   gebaut; dafür ist Internetzugriff auf GHCR, Alpine und PyPI erforderlich.
3. Mega per USB an den Home-Assistant-Host anschließen und `serial_device`
   unter **Konfiguration** einstellen.
4. Mosquitto-Add-on installieren und starten. Bei leerem `mqtt_host` werden
   Host, Port und Zugangsdaten automatisch vom Supervisor übernommen.
5. Add-on starten, Protokoll prüfen und die MQTT-Integration in Home Assistant
   einrichten. Nicht gleichzeitig die Standalone-Bridge für denselben Mega starten.

Alternativ den vollständigen Ordner `ha-addon/biosync_bridge/` nach
`/addons/biosync_bridge/` auf dem HA-Host kopieren und im Add-on-Store nach
Updates suchen; er erscheint dann unter **Lokale Add-ons**.

Alle Optionen, USB-Voraussetzungen und das optionale HA-Paket sind in
[DOCS.md](DOCS.md) beschrieben.

## Quellen und Build

`rootfs/opt/biosync/biosync_bridge/` und die dortige `requirements.txt` sind
unveränderte Kopien aus `ha-bridge/`. Die maßgeblichen Quellen bleiben in
`ha-bridge/`; nach jeder Bridge-Änderung muss die Kopie synchronisiert werden.
Aus dem Repo-Root:

```sh
cp ha-bridge/biosync_bridge/*.py ha-addon/biosync_bridge/rootfs/opt/biosync/biosync_bridge/
cp ha-bridge/requirements.txt ha-addon/biosync_bridge/rootfs/opt/biosync/requirements.txt
```

Entfernte/umbenannte Python-Dateien auch in der Kopie entfernen. Die
`unittest`-Tests unter `ha-bridge/tests/` prüfen die Übereinstimmung.
Der Build braucht ausschließlich den Add-on-Ordner als Kontext:

```sh
docker build \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.21 \
  --build-arg BUILD_ARCH=amd64 --build-arg BUILD_VERSION=1.0.0 \
  -t biosync-bridge:local ha-addon/biosync_bridge/
```

`build.yaml` verwendet offizielle HA-Alpine-3.21-Base-Images für alle fünf
angegebenen Architekturen; neuere HA-Versionen unterstützen nicht mehr alle
32-Bit-Plattformen. Python-Abhängigkeiten werden in einer virtuellen Umgebung
installiert, ohne das Alpine-System-Python zu verändern.

## Changelog

### 1.0.0

- Erstes Supervisor-Add-on mit USB/UART, bashio-Optionen und MQTT-Service-Erkennung.
- Unveränderte BioSync-Bridge inklusive MQTT Discovery im eigenständigen Build-Kontext.
