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
Der Mega prüft veraltete RS-485-Daten jede Sekunde, sendet Telemetrie über USB
aber nur bei einer Änderung einschließlich `UNKNOWN`- und ONLINE/OFFLINE-Wechseln.
Bei MQTT-Verbindung, USB-Reconnect und der HA-Birth-Message
`homeassistant/status=online` fordert die Bridge den aktuellen Status mit
`STATUS_REQUEST` erneut an.

Das bestehende Paket
[`homeassistant/packages/biosync_v4.yaml`](../../homeassistant/packages/biosync_v4.yaml)
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

## Nextion über Home Assistant befüllen

Zusätzlich zum Kalibrierpaket
[`homeassistant/packages/biosync_nextion.yaml`](../../homeassistant/packages/biosync_nextion.yaml)
nach `/config/packages/biosync_nextion.yaml` kopieren. Packages gemäß
[`homeassistant/README.md`](../../homeassistant/README.md) aktivieren, die
HA-Konfiguration prüfen und HA neu starten. Beide Pakete sind erforderlich;
das Add-on installiert sie nicht automatisch. Bereits angepasste
Kalibrierhelfer bleiben erhalten: Den Merker `biosync_calibration_initialized`
nicht ausschalten.

Kalibrierung erfolgt ausschließlich in HA über die vorhandenen
`input_number.biosync_v4_*`-Entities (HA-number-Helfer für Offset/Scale,
Trübungsstützpunkte und TDS-Koeffizienten). Die alten MQTT-`number`-Entities
werden von Discovery entfernt. Bridge und Mega liefern nur Rohwerte.
Die Anzeige nutzt die daraus berechneten kalibrierten Sensoren.

| Nextion-Objekt | Inhalt / Befehl |
|---|---|
| `nDist` | Füllstand 0–100 %, `nDist.val=<int>` |
| `nTemp` | Temperatur, gerundete ganze °C, `nTemp.val=<int>` |
| `tTurb` | Trübung NTU, zwei Nachkommastellen, `tTurb.txt="<wert>"` |
| `tTDS` | TDS ppm, zwei Nachkommastellen, `tTDS.txt="<wert>"` |
| `tPump`, `tVent` | `IDLE` / `ACTIVE` / `ERROR`, `<obj>.txt="<status>"` |
| `cPumpActive`, `cPumpError`, `cVentActive`, `cVentError` | `<obj>.val=<0|1>` |
| `cSystemIdle` | 1, wenn beide Geräte IDLE sind, sonst 0 |

**HMI-Abgleich erforderlich:** `LukeArrow/BioSync` war beim Implementieren
nicht zugänglich (404). `cSystemIdle` ist deshalb der angenommene, nicht
quellverifizierte Objektname. Im HMI prüfen und nötigenfalls die eine
Payload-Zeile im Script anpassen. Die Befehle verwenden unqualifizierte
Objektnamen; insbesondere die c*-Felder auf `pgSystem` müssen auch beim
Seitenwechsel erreichbar sein (HMI-`vscope=global` bzw. passende
seitenqualifizierte Namen verwenden). Ohne passenden HMI-Namen kann dieses
Feld nicht befüllt werden.

`input_number.biosync_v4_distance_empty` startet einmalig mit **170 cm**,
`input_number.biosync_v4_distance_full` mit **20 cm**. Danach werden beide
Werte bei Neustarts wiederhergestellt. Den eigenen Merker
`input_boolean.biosync_nextion_initialized` nicht ausschalten, sonst werden
diese beiden Tankhelfer beim nächsten Start zurückgesetzt.
`sensor.biosync_v4_fill_percent` berechnet aus dem kalibrierten Abstand:

```text
Füllstand % = clamp((Distanz leer - Distanz) / (Distanz leer - Distanz voll) * 100, 0, 100)
Standard:   = clamp((170 - Distanz) / 150 * 100, 0, 100)
```

Leer muss größer als voll sein; sonst ist der Sensor `unknown`. Die bestehenden
Distanzalarme vergleichen weiterhin Abstand in cm, nicht Prozent.
20 cm liegen bei manchen Ultraschallsensoren nahe an der hardwareseitigen
Mindestmessdistanz: Zuverlässigkeit am Überlauf prüfen.

Die queued-Automation ruft ein gemeinsames Script auf und zeichnet alle elf
Felder bei Sensor-/Relais-/Tankhelferänderungen, HA-Start und
`biosync_v4/availability=online` neu. Zusätzlich reagiert sie auf
`BTN_REFRESH` (`42 54 4E 5F 52 45 46 52 45 53 48`) und
`SCR_WAKE` (`53 43 52 5F 57 41 4B 45`) auf `biosync_v4/nextion`.
Das HMI muss diese ASCII-Bytes mit drei `FF`-Endbytes senden; Mega entfernt
die Terminatoren, Bridge leitet die Hexdarstellung ohne Retain weiter.
Normale Touchpakete (`65 ...`) lösen kein Neuzeichnen aus. Ein reiner
Nextion-Neustart ohne solche HMI-Meldung ist nicht automatisch erkennbar.
Manuell lässt sich `script.biosync_nextion_redraw` in HA ausführen.

Jedes Feld erhält eine eigene nicht-retainierte MQTT-Nachricht auf
`biosync_v4/command/nextion`: nur druckbares ASCII, maximal 120 Zeichen.
Bei geändertem `mqtt_prefix`/`BIOSYNC_MQTT_PREFIX` die drei Topic-Arten
im Nextion-Paket anpassen; Entity-IDs bleiben gleich. Fehlende Zahlen
(`unknown`/`unavailable`) werden nicht an Number-Felder gesendet; Text zeigt
`--`. Textzahlen werden für eine feste maximale Befehlslänge auf ±10¹²
begrenzt, Temperatur außerhalb des vorzeichenbehafteten 32-Bit-Bereichs
nicht gesendet. Einheiten stehen ausschließlich im HMI.
Relaispriorität pro Gerät: ERROR vor ACTIVE vor IDLE, unbekannte Zustände
zählen als IDLE; c*-Felder entsprechen dem priorisierten Zustand.

Keine `bco`-Farben. `CAL_*`, SD- und RTC-Felder des Alt-Projekts werden in V4
nicht mehr vom DisplayNode verarbeitet/befüllt; es gibt dort kein EEPROM,
SD oder RTC. Kalibrierung erfolgt in HA, nicht über die alten HMI-Buttons.

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
