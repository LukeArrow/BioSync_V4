# BioSync V4

BioSync V4 ist ein bewusster, vereinfachter Neustart des Klärgruben-Monitorings.
**Home Assistant ist der Chef.** Die drei Arduinos messen, übertragen und
reichen Anzeige-Kommandos weiter; Umrechnung, Schwellen, Alarmierung,
Langzeit-History und Nextion-Inhalte liegen außerhalb der Firmware.

## Aufbau

```text
SensorNode ─RS-485─┐
                   ├─> DisplayNode (Mega) ─USB 115200─> ha-bridge ─MQTT─> Home Assistant
RelayNode  ─RS-485─┘               └─Serial2 9600─> Nextion
```

- `firmware/SensorNode`: Nano Every, misst Distanz, Temperatur und zwei rohe
  ADC-Werte.
- `firmware/RelayNode`: Nano Every, liest die vier LED-Lichtsensoren und
  übermittelt Zustände ereignisbasiert (mit 5-Minuten-Heartbeat).
- `firmware/DisplayNode`: Mega 2560, RS-485-Gateway, USB-Protokoll und
  generische Nextion-Durchleitung. Kein EEPROM, kein SD, keine lokale Umrechnung,
  Wartungslogik oder Alarmentscheidung.
- `ha-bridge`: Python-USB/MQTT-Bridge mit Discovery und Plausibilitätsprüfung;
  Kalibrierung und Umrechnung liegen im optionalen Home-Assistant-Paket.
- `homeassistant/packages/biosync_v4.yaml`: Beispiel für Wartungsmodus,
  Recorder-Pause und Grenzwertbenachrichtigungen.

## Hardware und Flashen

Die Pinbelegung folgt der V4-Referenzdokumentation:

| Gerät | Pins |
|---|---|
| SensorNode (Nano Every) | JSN-SR04T Trigger D2/Echo D3; DS18B20 D4; RS-485 DE D5, RX D7, TX D6; Trübung A0; TDS A1 |
| RelayNode (Nano Every) | ALS-PT19 A0–A3; RS-485 DE D5, RX D6, TX D7 |
| DisplayNode (Mega 2560) | Sensor RS-485 Serial1 D18/D19, DE D10; Nextion Serial2 D16/D17, 9600 Baud; Relay RS-485 Serial3 D14/D15; USB 115200 Baud |

RS-485 nutzt 9600 Baud, 8N1 und 10 ms Transceiver-Umschaltzeit. Beide Nano
Nodes senden über eine einfache TX-only-Software-UART auf den dokumentierten
TX-Pins; der jeweilige RX-Pin bleibt als Eingang für die vorhandene Verdrahtung
konfiguriert. So ist keine nicht unterstützte `SoftwareSerial`-Implementierung
auf dem Nano Every nötig. SensorNode benötigt außerdem die Arduino Libraries
`OneWire` 2.3.8 und `DallasTemperature` 4.0.6.

Die gemeinsame UART-Logik liegt in `firmware/common/SoftUart.h`.
Für eigenständige `arduino-cli`-Sketch-Builds liegt sie zusätzlich als identische
Datei in allen drei Sketch-Ordnern. Nur die gemeinsame Datei bearbeiten und
anschließend aus dem Repo-Root synchronisieren:

```sh
for node in SensorNode RelayNode DisplayNode; do
  cp firmware/common/SoftUart.h "firmware/$node/SoftUart.h"
done
```

Die Tests prüfen die Byte-Gleichheit. Interrupts sind beim Senden nur pro
UART-Byte (Start-, acht Daten- und Stopbit, etwa 1,04 ms) gesperrt, nicht für
den ganzen Frame. Die Zeitbasis wird für jedes Byte neu gelesen.

Optional mit installiertem `arduino-cli` kompilieren:

```sh
arduino-cli core install arduino:megaavr arduino:avr
arduino-cli lib install OneWire@2.3.8 DallasTemperature@4.0.6
arduino-cli compile -b arduino:megaavr:nona4809 firmware/SensorNode
arduino-cli compile -b arduino:megaavr:nona4809 firmware/RelayNode
arduino-cli compile -b arduino:avr:mega firmware/DisplayNode
```

Die Baudrate des USB-Ports ist 115200. Auf dem Raspberry Pi die Bridge
installieren und starten:

```sh
cd ha-bridge
python -m pip install -r requirements.txt
python -m biosync_bridge.main
```

Standardmäßig nutzt die Bridge `/dev/ttyACM0` und einen lokalen MQTT-Broker
(`localhost:1883`). `BIOSYNC_SERIAL`, `BIOSYNC_MQTT_HOST`,
`BIOSYNC_MQTT_PORT`, `BIOSYNC_MQTT_USER` und `BIOSYNC_MQTT_PASSWORD` können als
Umgebungsvariablen angepasst werden.

Bei einem zunächst unerreichbaren MQTT-Broker oder einem verlorenen USB-Gerät
verbindet sich die Bridge automatisch erneut. Beide verwenden exponentiellen
Backoff von 1 bis maximal 60 Sekunden; die Versuche werden protokolliert.
Nach MQTT-Reconnect werden Discovery und Subscriptions erneut eingerichtet.
Während USB getrennt ist,
werden Kommandos protokolliert und verworfen, nicht später nachgeholt.
Bei USB-Verlust meldet MQTT die Bridge als `offline`, damit keine alten
Messwerte als aktuell gelten. Erst eine neu empfangene USB-Zeile (beliebigen
Inhalts) setzt sie wieder auf `online`; ein MQTT-Reconnect allein reicht dafür nicht.

## Home-Assistant-Add-on

Mit Home Assistant Supervisor lässt sich die Bridge auch als Add-on installieren.
Im Add-on-Store das Repository `https://github.com/LukeArrow/BioSync_V4`
hinzufügen und **BioSync V4 Bridge** installieren. USB-Port und MQTT lassen
sich über die HA-Oberfläche konfigurieren; ein leerer MQTT-Host nutzt automatisch
den Supervisor-MQTT-Service (z. B. Mosquitto).
Installation und Optionen: [`ha-addon/biosync_bridge/`](ha-addon/biosync_bridge/).
Die oben beschriebene Standalone-Nutzung bleibt unverändert.

## Protokoll (zentral dokumentiert)

**Grundsatz: Im gesamten Datenpfad SensorNode/RelayNode → RS-485 → DisplayNode
→ USB → Bridge → MQTT wird nichts verworfen, ersetzt oder gefiltert.** Alle
Werte werden roh durchgereicht; Plausibilitätsprüfung und Aussortieren
übernimmt Home Assistant.

RS-485-Frames sind ASCII in spitzen Klammern mit Zeilenende (`\r\n`), ohne
Prüfsumme:

```text
<SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420;DIST_RAW=123.0,123.4,0.0,124.1,123.6>
<RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=ERROR;A0=812;A1=12;A2=15;A3=640>
```

**Alle drei Firmwares müssen gemeinsam aktualisiert werden.** Ein von älterer
Firmware noch mitgesendetes `;CK=..` wird nicht geprüft, sondern als normales
Feld `CK` durchgereicht. Der DisplayNode übernimmt alle Felder hinter
`SENSOR;` bzw. `RELAY;` bis zum ersten `>` unverändert (auch unbekannte Felder,
nichtnumerische oder leere Werte); Störbytes vor dem Kennzeichen werden
toleriert. Zusätzlich gibt er **jeden** empfangenen RS-485-Frame roh über USB
aus, auch Frames ohne gültiges Kennzeichen:

```text
$RAW_SENSOR;<SENSOR;DIST=...>
$RAW_RELAY;<RELAY;PUMP_ACTIVE=...>
```

Läuft der 256-Byte-Empfangspuffer über, wird der bisherige Inhalt als
`$RAW_SENSOR;OVERFLOW;...` bzw. `$RAW_RELAY;OVERFLOW;...` ausgegeben und der
Rest des Frames als eigene Zeile weitergereicht.

Nach 11 Minuten ohne Frame wechselt der jeweilige Node-Status auf `OFFLINE`;
die zuletzt empfangenen Werte bleiben **unverändert** erhalten. `SENSOR_AGE`
und `RELAY_AGE` geben das Alter der letzten Frames in Sekunden an (`NEVER`,
solange noch kein Frame empfangen wurde). Home Assistant zeigt den Status als
Diagnose-Entities „SensorNode“ und „RelayNode“ (Verbunden/Getrennt) an.

`DIST` ist Zentimeter, `TMP` Grad Celsius, `TUR` und `TDS` sind unveränderte
ADC-Werte. SensorNode misst sofort nach dem Start und danach alle
5 Minuten. RelayNode sendet bei Änderung sofort und zusätzlich alle 5 Minuten.

`TMP` ist der Rohwert des DS18B20; ein nicht angeschlossener Sensor liefert
`-127.0` (`DEVICE_DISCONNECTED_C`), der unverändert gesendet wird.
Die Distanz ergibt sich aus fünf Ultraschallmessungen mit mindestens 60 ms
Abstand zwischen Triggern. `DIST_RAW` enthält alle fünf Einzelmessungen in cm,
kommagetrennt; ein Echo-Timeout erscheint als `0.0`. `DIST` ist der Median der
Messungen ohne Timeout (bei gerader Anzahl das Mittel der beiden mittleren
Werte), ohne Mindestanzahl; sind alle fünf Messungen Timeouts, ist `DIST=0.0`.
Die Messserie braucht einschließlich der maximalen Echo-Timeouts höchstens
etwa 390 ms.

Das RelayNode-LED-Mapping ist A0 → `PUMP_ACTIVE`, A1 → `PUMP_ERROR`,
A2 → `VENT_ACTIVE`, A3 → `VENT_ERROR`. Die Error-Kanäle (A1/A3) liefern bei
eingeschalteter Error-LED `ERROR`, sonst `IDLE`, niemals `ACTIVE`. Die Zustände
entstehen per Hysterese aus den ADC-Werten; zusätzlich sendet der RelayNode die
gemittelten ADC-Rohwerte als `A0`–`A3` (0–1023).

Der Mega prüft jede Sekunde den Node-Status, sendet die Telemetriezeile über
USB aber nur, wenn sich ein Wert oder der ONLINE/OFFLINE-Status geändert hat
(das Alter allein löst keine neue Zeile aus). Sie enthält alle Felder des
letzten Sensor- und Relay-Frames unverändert:

```text
$TELEMETRY;<Felder SensorNode>;<Felder RelayNode>;SENSOR_NODE=..;RELAY_NODE=..;SENSOR_AGE=..;RELAY_AGE=..
$TELEMETRY;DIST=..;TMP=..;TUR=..;TDS=..;DIST_RAW=..;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..;A0=..;A1=..;A2=..;A3=..;SENSOR_NODE=..;RELAY_NODE=..;SENSOR_AGE=..;RELAY_AGE=..
```

Vor dem ersten Frame eines Nodes fehlen dessen Felder. `SENSOR_NODE` und
`RELAY_NODE` melden `ONLINE` oder `OFFLINE`. Die Bridge macht daraus die Entities
`binary_sensor.biosync_v4_sensor_node` („SensorNode“) und
`binary_sensor.biosync_v4_relay_node` („RelayNode“). Eine Automation für beide:

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

Bei jedem empfangenen Relay-Frame sendet der Mega unabhängig vom
Telemetrie-Takt zusätzlich sofort eine eigene USB-Zeile mit allen Feldern:

```text
$RELAY;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..;A0=..;A1=..;A2=..;A3=..
```

`SD`, `MAINT` und `ALARM` gehören nicht zum V4-Protokoll. Empfangene
Nextion-Tastendrücke gehen als Hex-Bytes auf USB:
`$NEXTION;65 00 01 01`. Nextion-Daten über 128 Byte ohne Endbytes werden
abgeschnitten als `$ERR;ERROR=NEXTION_OVERFLOW;DATA=<Hex>` gemeldet.

Die Bridge veröffentlicht jede USB-Zeile unverändert (retained) auf
`biosync_v4/raw` und verteilt sie zusätzlich:

| USB-Zeile | MQTT-Topic |
|---|---|
| `$TELEMETRY;...` | `biosync_v4/state` (JSON, alle Felder), Relaisfelder zusätzlich `biosync_v4/relay` |
| `$RELAY;...` | `biosync_v4/relay` (JSON, alle Felder) |
| `$RAW_SENSOR;...` / `$RAW_RELAY;...` | `biosync_v4/raw_sensor` / `biosync_v4/raw_relay` (Frame ohne Präfix) |
| `$NEXTION;...` | `biosync_v4/nextion` (nicht retained) |
| `$ACK;...` / `$ERR;...` | `biosync_v4/ack` (nicht retained) |
| alles andere | `biosync_v4/unknown` |

Endliche Zahlen werden im JSON zu Zahlen, alle anderen Werte bleiben Text.

USB-Kommandos sind zeilenweise. `NEX <Nextion-Befehl>` reicht einen Befehl an
Serial2 weiter und fügt die drei Nextion-Endbytes `0xFF` an. Unbekannte
Kommandos beantwortet der Mega mit `$ERR;ERROR=UNKNOWN_COMMAND;COMMAND=...`,
ein leeres `NEX ` mit `$ERR;COMMAND=NEX;ERROR=EMPTY`. Zeilen über 255 Zeichen
werden abgeschnitten ausgeführt und mit `$ERR;ERROR=USB_TRUNCATED;DROPPED=<n>`
gemeldet.
`STATUS_REQUEST` sendet der Mega sofort die aktuelle Telemetrie und Relaiszustände
und bestätigt anschließend die Anfrage mit `$ACK;COMMAND=STATUS_REQUEST`.
Die Bridge fordert den Status nach MQTT-/USB-Reconnect und nach der HA-Birth-Message
`homeassistant/status=online` erneut an, damit Home Assistant den aktuellen Stand
erhält. EEPROM-Konfiguration und Kalibrierkommandos sind nicht Teil des Protokolls. Über
`biosync_v4/command/nextion` kann HA beliebige Nextion-Kommandos senden; über
`biosync_v4/command` beliebige USB-Kommandos. Die Bridge validiert diese nicht,
sie entfernt nur Zeilenumbrüche.
Die Firmware hält keine lokale Fallback-Anzeige aktuell: Bei HA-Ausfall bleibt
das Nextion auf dem zuletzt empfangenen Inhalt stehen.

## Umrechnung und Kalibrierung

Die Bridge publiziert rohe Sensormesswerte ohne Bereichsgrenzen oder
Ersetzungen; auch `TMP=-127.0` oder `DIST=0.0` (Timeout) kommen in Home
Assistant an. Numerische Entities zeigen nichtnumerische Werte als „Unbekannt“;
der Originalwert bleibt in `biosync_v4/state` und `biosync_v4/raw` erhalten.
Unplausible Werte bei Bedarf in Home Assistant aussortieren. Die Kalibrierung findet im optionalen Home-Assistant-Paket
[`homeassistant/packages/biosync_v4.yaml`](homeassistant/packages/biosync_v4.yaml)
statt. Es stellt anpassbare `input_number`-Helfer und daraus abgeleitete
kalibrierte Sensoren bereit. Die Kalibrierwerte bleiben in Home Assistant
erhalten und werden nicht im DisplayNode-EEPROM gespeichert.

Trübung wird stückweise linear aus den drei Stützpunkten `TUR_X1/Y1` bis
`TUR_X3/Y3` berechnet. TDS verwendet ein kubisches Polynom
`((a*x+b)*x+c)*x+d` mit den Koeffizienten `TDS_A` bis `TDS_D` und
Temperaturkorrektur:

```text
TDS_25 = TDS(T) / (1 + 0.02 * (Temperatur - 25))
```

Die eingestellten Startwerte sind nur Beispiele. Der TDS-Standard entspricht
dem linearen Beispiel `2.34 * ADC - 622` (A und B sind null). Trübungs-
Stützpunkte und TDS-Polynom sollten anhand realer Sensoren und Referenzlösungen
kalibriert werden. Distanz und Temperatur folgen `(Rohwert + Offset) * Scale`.
Der Rohwert bleibt zusätzlich als eigene Entity verfügbar. Die Kalibrierhelfer
und Grenzwerte funktionieren nur, wenn das HA-Paket eingebunden ist.

## Nextion über Home Assistant befüllen

Die HA-Pakete
[`biosync_v4.yaml`](homeassistant/packages/biosync_v4.yaml) (Kalibrierung) und
[`biosync_nextion.yaml`](homeassistant/packages/biosync_nextion.yaml) (Anzeige)
gemeinsam nach `/config/packages/` kopieren, Packages aktivieren und HA neu
starten. [Installation](homeassistant/README.md).

| Felder | Anzeige |
|---|---|
| `nDist`, `nTemp` | Füllstand in ganzen %, Temperatur in ganzen °C |
| `tTurb`, `tTDS` | Kalibrierte NTU/ppm mit zwei Nachkommastellen, ohne Einheit |
| `tPump`, `tVent` | ERROR > ACTIVE > IDLE |
| `cPumpActive`, `cPumpError`, `cVentActive`, `cVentError` | 0/1 zum priorisierten Gerätestatus |
| `cSystemIdle` | 1 wenn beide Geräte IDLE, sonst 0; HMI-Namen noch prüfen |

`sensor.biosync_v4_fill_percent` verwendet
`clamp((170 - Abstand) / 150 * 100, 0, 100)`. Die Distanzen leer/voll sind als
persistente HA-Helfer `input_number.biosync_v4_distance_empty` (170 cm) und
`input_number.biosync_v4_distance_full` (20 cm) anpassbar.
Bei 20 cm die hardwareseitige Mindestmessdistanz des Ultraschallsensors prüfen.
Die queued-Automation sendet pro Feld einen ASCII-Befehl (≤120 Zeichen,
retain=false) bei Werteänderung, HA-Start, Bridge-Verfügbarkeit `online` und
den ASCII-Hexmeldungen `BTN_REFRESH`/`SCR_WAKE`. Fehlende Messwerte: Text `--`,
Number nicht senden. Kalibrierung ausschließlich über HA-`input_number`-
Entities; `CAL_*`, SD-/RTC-Felder werden nicht vom DisplayNode V4 befüllt.
Farben bleiben unverändert.

**Noch am HMI prüfen:** Das Alt-Repo war nicht zugänglich (404), deshalb ist
`cSystemIdle` nicht quellverifiziert. Systemfelder müssen seitenübergreifend
erreichbar sein; siehe [Feldbefehle und HMI-Voraussetzungen](ha-addon/biosync_bridge/DOCS.md#nextion-über-home-assistant-befüllen).

## Tests und Home Assistant

```sh
python -m pip install -r ha-bridge/requirements.txt -r ha-bridge/requirements-test.txt ruff==0.16.10
ruff check ha-bridge/
ruff format --check ha-bridge/
PYTHONPATH=ha-bridge python -m unittest discover -s ha-bridge/tests -v
```

Die GitHub-Actions-CI führt diese Prüfungen bei Push und Pull Request mit
Python 3.12 aus. Die Laufzeitabhängigkeiten sind exakt auf `paho-mqtt==2.1.0`
(Callback-API VERSION2) und `pyserial==3.5` gepinnt; die Add-on-Kopie bleibt
byte-identisch (Kopierbefehle im Add-on-README).

Home-Assistant-Pakete sind unter `homeassistant/README.md` beschrieben.
Wartung pausiert den Recorder global und unterdrückt die Beispielalarme.
Schwellenwerte sind `input_number`-Helfer im HA-Paket und lassen sich ohne Flash ändern.
