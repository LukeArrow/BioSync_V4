# Konfiguration und Betrieb

## Optionen

| Option | Standard | Bridge-Umgebungsvariable / Bedeutung |
|---|---|---|
| `serial_device` | `/dev/ttyACM0` | `BIOSYNC_SERIAL`: serieller Mega-Port |
| `baud` | `115200` | `BIOSYNC_BAUD`: positive Baudrate; muss zur Firmware passen |
| `mqtt_host` | leer | `BIOSYNC_MQTT_HOST`: leer = Supervisor-MQTT-Service |
| `mqtt_port` | `1883` | `BIOSYNC_MQTT_PORT`: Port für einen manuell gesetzten Host |
| `mqtt_user` | leer | `BIOSYNC_MQTT_USER`: optionaler Benutzer für manuellen Host |
| `mqtt_password` | leer | `BIOSYNC_MQTT_PASSWORD`: optionales Passwort für manuellen Host |
| `mqtt_prefix` | `biosync_v4` | `BIOSYNC_MQTT_PREFIX`: MQTT-Topic-Präfix |
| `log_level` | `INFO` | `BIOSYNC_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING` oder `ERROR` |

Bei leerem `mqtt_host` werden **alle vier** MQTT-Verbindungswerte aus
`services.mqtt` verwendet; manuelle Port-/Benutzer-/Passwortwerte werden dann
ignoriert. Ohne verfügbaren Service bricht der Start mit einer Fehlermeldung ab.
Mit gesetztem `mqtt_host` gelten ausschließlich die konfigurierten Werte
(auch leere Zugangsdaten für einen Broker ohne Authentifizierung).

Das Add-on fordert den Supervisor-Service `mqtt:need` an. Empfohlen ist das
offizielle Mosquitto-Add-on. Für einen anderen Broker dessen erreichbaren
DNS-Namen oder IP-Adresse eintragen. `localhost` bezeichnet den Add-on-Container,
nicht den HA-Host; `host_network` ist bewusst deaktiviert. Die bestehende Bridge
nutzt MQTT ohne TLS; daher nur einen vertrauenswürdigen lokalen Broker verwenden
und den Broker-Port nicht ins Internet freigeben.

Nach Optionsänderungen das Add-on neu starten. Zugangsdaten nur in der
HA-Konfiguration speichern, nicht in Git oder in öffentlich geteilten Logs.

## USB und UART

- Der Mega muss am **Home-Assistant-Host** angeschlossen sein. Bei einer VM
  zuerst das USB-Gerät an die HA-VM durchreichen.
- Unter **Einstellungen → System → Hardware → Gesamte Hardware** den Mega
  suchen. Typische Geräte sind `/dev/ttyACM0` oder `/dev/ttyUSB0`.
- Wenn verfügbar einen stabilen `/dev/serial/by-id/...`-Pfad als
  `serial_device` verwenden; die Nummer von `ttyACM0` kann sich ändern.
- Das Manifest aktiviert `uart: true`, `usb: true` und `udev: true`, damit
  Supervisor die seriellen Geräte, USB-Geräte und udev-Informationen bereitstellt.
  Ein zusätzliches `devices`-Mapping ist normalerweise nicht erforderlich.
  Bei einer angepassten Installation kann ein Maintainer im Manifest z. B.
  `devices: ["/dev/ttyACM0"]` ergänzen; der Pfad muss auf dem Host existieren.
- Nur ein Prozess darf den Port nutzen: Arduino Serial Monitor, andere
  serielle Add-ons und eine parallel laufende Standalone-Bridge beenden.
- Bei „No such file“ den Gerätepfad prüfen, bei „Permission denied“ die
  USB-Durchreichung und Supervisor-Gerätefreigabe prüfen. Zum Flashen das
  Add-on stoppen.

## Home Assistant und MQTT Discovery

Die MQTT-Integration muss mit demselben Broker verbunden sein und Discovery
aktiviert haben. Die Bridge veröffentlicht rohe Messwerte, Node-Status und
einen Button zur Statusabfrage unter dem HA-Discovery-Präfix `homeassistant/`.
Das konfigurierte `mqtt_prefix` betrifft die BioSync-Daten-/Command-Topics.

Das bestehende Paket
[`homeassistant/packages/biosync.yaml`](../../homeassistant/packages/biosync.yaml)
stellt Kalibrierhelfer, kalibrierte Sensoren, Wartungsmodus, Grenzwerte und
Beispielalarme bereit. Es ist nicht für den Bridge-Start erforderlich und wird
nicht automatisch vom Add-on installiert. Ohne das Paket stehen nur die
Rohmesswerte zur Verfügung. Einbindung siehe
[`homeassistant/README.md`](../../homeassistant/README.md).
Bei Änderung von `mqtt_prefix` auch die festen `biosync_v4/...`-Topics im
HA-Paket und eigenen Automationen anpassen.

Die Kalibrierwerte werden in Home Assistant gespeichert und nicht im
DisplayNode-EEPROM. Die Standalone-Nutzung aus `ha-bridge/` bleibt weiterhin
möglich.

SensorNode misst sofort beim Start und anschließend alle fünf Minuten. RelayNode
sendet Änderungen sofort und zusätzlich alle fünf Minuten. Meldet sich ein Node
elf Minuten lang nicht, zeigt Home Assistant die Diagnose-Entity „SensorNode“
oder „RelayNode“ als getrennt an. Eine Beispiel-Automation:

```yaml
alias: BioSync – Gerät meldet sich nicht
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.biosync_v4_sensor_node
      - binary_sensor.biosync_v4_relay_node
    to: "off"
actions:
  - action: notify.notify
    data:
      message: "{{ trigger.to_state.name }} meldet sich seit über 10 Minuten nicht mehr!"
```
