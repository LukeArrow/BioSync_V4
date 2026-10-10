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

Die gemeinsame UART- und Prüfsummenlogik liegt in `firmware/common/SoftUart.h`.
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
Messwerte als aktuell gelten. Erst neue gültige `$TELEMETRY` setzt sie wieder
auf `online`; ein MQTT-Reconnect allein reicht dafür nicht.

## Home-Assistant-Add-on

Mit Home Assistant Supervisor lässt sich die Bridge auch als Add-on installieren.
Im Add-on-Store das Repository `https://github.com/LukeArrow/BioSync_V4`
hinzufügen und **BioSync V4 Bridge** installieren. USB-Port und MQTT lassen
sich über die HA-Oberfläche konfigurieren; ein leerer MQTT-Host nutzt automatisch
den Supervisor-MQTT-Service (z. B. Mosquitto).
Installation und Optionen: [`ha-addon/biosync_bridge/`](ha-addon/biosync_bridge/).
Die oben beschriebene Standalone-Nutzung bleibt unverändert.

## Protokoll (zentral dokumentiert)

RS-485-Frames sind ASCII in spitzen Klammern, mit Zeilenende (`\r\n`) und
verpflichtender XOR-Prüfsumme. Das letzte Feld unmittelbar vor `>` ist
`;CK=XX`, mit genau zwei Hex-Ziffern in Großschreibung (`00`–`FF`, ggf. führende
Null). Die Prüfsumme beginnt bei `0` und verknüpft jedes ASCII-Byte des
Nutzinhalts mit XOR: vom ersten Zeichen nach `<` bis einschließlich des letzten
Zeichens vor `;CK=`. Die Feldtrenner innerhalb des Nutzinhalts gehören dazu;
`<`, das Semikolon vor `CK`, `CK=XX`, `>` und das Zeilenende gehören **nicht** dazu.
Beispiel: XOR über `SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420` ergibt `0x7B`.

```text
<SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420;CK=7B>
<RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=ERROR;CK=17>
```

Der DisplayNode verwirft Frames mit fehlender, fehlerhafter oder falsch
formatierter Prüfsumme, ohne Werte oder Empfangszeit zu aktualisieren.
Nach 11 Minuten ohne gültigen Frame werden die jeweiligen Werte `UNKNOWN` und
der jeweilige Node-Status wechselt auf `OFFLINE`. Home Assistant zeigt dafür
die Diagnose-Entities „SensorNode“ und „RelayNode“ als Verbunden/Getrennt an.
Alle drei Firmwares müssen gemeinsam aktualisiert werden; alte Frames ohne
`CK` werden nicht unterstützt. Die vorhandenen USB-Felder bleiben bestehen;
`$TELEMETRY` wird nur um die beiden Node-Statusfelder erweitert. Die Bridge
akzeptiert weiterhin Telemetriezeilen älterer Firmware ohne diese Felder.

`DIST` ist Zentimeter, `TMP` Grad Celsius, `TUR` und `TDS` sind unveränderte
ADC-Werte. Ein nicht verfügbarer Messwert/Zustand lautet `UNKNOWN`, ein echter
Ruhezustand `IDLE`. SensorNode misst sofort nach dem Start und danach alle
5 Minuten. RelayNode sendet bei Änderung sofort und zusätzlich alle 5 Minuten.

Die Distanz ist der Median aus fünf Ultraschallmessungen mit mindestens 60 ms
Abstand zwischen Triggern. Timeouts werden ausgeschlossen; bei weniger als
drei gültigen Messungen wird `UNKNOWN` gesendet. Bei vier gültigen Messungen
wird das Mittel der beiden mittleren Werte verwendet. Die Messserie braucht
einschließlich der maximalen Echo-Timeouts höchstens etwa 390 ms.

Das RelayNode-LED-Mapping ist A0 → `PUMP_ACTIVE`, A1 → `PUMP_ERROR`,
A2 → `VENT_ACTIVE`, A3 → `VENT_ERROR`. Die Error-Kanäle (A1/A3) liefern bei
eingeschalteter Error-LED `ERROR`, sonst `IDLE`, niemals `ACTIVE`;
nicht verfügbare Zustände bleiben `UNKNOWN`.

Der Mega prüft die Werte jede Sekunde auf veraltete RS-485-Daten, sendet diese
Telemetriezeile über USB aber nur, wenn sich ein Wert oder der ONLINE/OFFLINE-
Status geändert hat:

```text
$TELEMETRY;DIST=..;TMP=..;TUR=..;TDS=..;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..
```

Die beiden letzten Felder `SENSOR_NODE` und `RELAY_NODE` melden `ONLINE` oder
`OFFLINE`. Die Bridge macht daraus die Entities
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

Bei einer Änderung eines Relaiszustands sendet der Mega unabhängig vom
Telemetrie-Takt zusätzlich sofort eine eigene USB-Zeile:

```text
$RELAY;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..
```

Die Bridge veröffentlicht diese vier Zustände als JSON auf
`biosync_v4/relay`; Sensor- und kombinierte Heartbeat-Telemetrie bleiben auf
`biosync_v4/state`.

`SD`, `MAINT` und `ALARM` gehören nicht zum V4-Protokoll. Fehlende oder
veraltete RS-485-Daten werden als `UNKNOWN` übertragen. Empfangene
Nextion-Tastendrücke gehen als Hex-Bytes auf USB:
`$NEXTION;65 00 01 01`; die Bridge veröffentlicht sie auf
`biosync_v4/nextion`.

USB-Kommandos sind zeilenweise. `NEX <Nextion-Befehl>` reicht einen Befehl an
Serial2 weiter und fügt die drei Nextion-Endbytes `0xFF` an.
`STATUS_REQUEST` sendet der Mega sofort die aktuelle Telemetrie und Relaiszustände
und bestätigt anschließend die Anfrage mit `$ACK;COMMAND=STATUS_REQUEST`.
Die Bridge fordert den Status nach MQTT-/USB-Reconnect und nach der HA-Birth-Message
`homeassistant/status=online` erneut an, damit Home Assistant den aktuellen Stand
erhält. EEPROM-Konfiguration und Kalibrierkommandos sind nicht Teil des Protokolls. Über
`biosync_v4/command/nextion` kann HA beliebige Nextion-Kommandos senden.
Die Firmware hält keine lokale Fallback-Anzeige aktuell: Bei HA-Ausfall bleibt
das Nextion auf dem zuletzt empfangenen Inhalt stehen.

## Umrechnung und Kalibrierung

Die Bridge publiziert rohe Sensormesswerte; sie verwirft lediglich nicht
endliche Werte und markiert Werte außerhalb plausibler Rohbereiche als
`UNKNOWN`: `DIST` 0–500 cm, `TMP` −20–60 °C sowie `TUR`/`TDS` 0–1023
(Grenzen inklusive). Die Kalibrierung findet im optionalen Home-Assistant-Paket
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

## Tests und Home Assistant

```sh
python -m pip install -r ha-bridge/requirements.txt ruff==0.16.10
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
