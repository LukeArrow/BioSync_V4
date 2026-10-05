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
  übermittelt Zustände ereignisbasiert (mit 5-s-Heartbeat).
- `firmware/DisplayNode`: Mega 2560, RS-485-Gateway, USB-Protokoll, EEPROM und
  generische Nextion-Durchleitung. Kein SD, keine lokale Umrechnung,
  Wartungslogik oder Alarmentscheidung.
- `ha-bridge`: Python-USB/MQTT-Bridge mit Discovery und Rohwertumrechnung.
- `homeassistant/packages/biosync.yaml`: Beispiel für Wartungsmodus,
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
Nach MQTT-Reconnect werden Discovery, Subscriptions und `GET` erneut ausgeführt,
nach USB-Reconnect wird ebenfalls `GET` gesendet. Während USB getrennt ist,
werden Kommandos protokolliert und verworfen, nicht später nachgeholt.

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
Nach 15 Sekunden ohne gültigen Frame werden die jeweiligen Werte `UNKNOWN`.
Alle drei Firmwares müssen gemeinsam aktualisiert werden; alte Frames ohne
`CK` werden nicht unterstützt. Das USB-Protokoll bleibt unverändert.

`DIST` ist Zentimeter, `TMP` Grad Celsius, `TUR` und `TDS` sind unveränderte
ADC-Werte. Ein nicht verfügbarer Messwert/Zustand lautet `UNKNOWN`, ein echter
Ruhezustand `IDLE`. SensorNode sendet alle 5 Sekunden, RelayNode bei Änderung
und zusätzlich alle 5 Sekunden.

Die Distanz ist der Median aus fünf Ultraschallmessungen mit mindestens 60 ms
Abstand zwischen Triggern. Timeouts werden ausgeschlossen; bei weniger als
drei gültigen Messungen wird `UNKNOWN` gesendet. Bei vier gültigen Messungen
wird das Mittel der beiden mittleren Werte verwendet. Die Messserie braucht
einschließlich der maximalen Echo-Timeouts höchstens etwa 390 ms und bleibt
mit der Temperaturmessung innerhalb des 5-s-Takts.

Das RelayNode-LED-Mapping ist A0 → `PUMP_ACTIVE`, A1 → `PUMP_ERROR`,
A2 → `VENT_ACTIVE`, A3 → `VENT_ERROR`. Die Error-Kanäle (A1/A3) liefern bei
eingeschalteter Error-LED `ERROR`, sonst `IDLE`, niemals `ACTIVE`;
nicht verfügbare Zustände bleiben `UNKNOWN`.

Der Mega gibt einmal pro Sekunde genau diese USB-Felder aus:

```text
$TELEMETRY;DIST=..;TMP=..;TUR=..;TDS=..;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..
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

USB-Kommandos sind zeilenweise:

- `GET` liest den aktuellen EEPROM-Zustand als `$CONFIG;NAME=WERT;...` zurück.
- `SET PARAMETER WERT` speichert einen Parameter im EEPROM; `CAL PARAMETER WERT`
  und `CAL_PARAMETER=WERT` sind kompatible Kurzformen.
- `CAL_SAVE` speichert die aktuelle Konfiguration erneut im EEPROM und bestätigt
  mit `$ACK;COMMAND=CAL_SAVE`. `SET`/`CAL` speichern bereits unmittelbar.
- `NEX <Nextion-Befehl>` reicht den Befehl an Serial2 weiter und fügt die drei
  Nextion-Endbytes `0xFF` an.
- `STATUS_REQUEST` bestätigt die Verbindung. Es werden keine SD-Befehle
  unterstützt.

Home Assistant lädt beim Start mit `GET` die Werte aus dem EEPROM und stellt
sie über MQTT-Discovery als `number`-Entities bereit. Änderungen werden mit
`SET` direkt im EEPROM gespeichert; ein Firmware-Flash ist dafür nicht nötig.
Über `biosync_v4/command/nextion` kann HA beliebige Nextion-Kommandos senden.
Die Firmware hält keine lokale Fallback-Anzeige aktuell: Bei HA-Ausfall bleibt
das Nextion auf dem zuletzt empfangenen Inhalt stehen.

## Umrechnung und Kalibrierung

Die SensorNode-ADC-Rohwerte werden erst in der Bridge interpretiert. Trübung
wird stückweise linear aus den drei EEPROM-Stützpunkten `TUR_X1/Y1` bis
`TUR_X3/Y3` berechnet. TDS verwendet ein kubisches Polynom
`((a*x+b)*x+c)*x+d` mit den EEPROM-Koeffizienten `TDS_A` bis `TDS_D` und
Temperaturkorrektur:

```text
TDS_25 = TDS(T) / (1 + 0.02 * (Temperatur - 25))
```

Die Startwerte sind Beispielwerte und keine Sensor-Kalibrierung. Die
Referenzdokumentation nennt als lineares TDS-Beispiel `2.34 * ADC - 622`,
veröffentlicht aber keine Koeffizienten des dort ebenfalls beschriebenen
kubischen Fits. Daher wird dieses bekannte lineare Beispiel als kubisches
Polynom mit den höheren Koeffizienten null initialisiert; die vier
`TDS_A`–`TDS_D`-Werte können in HA auf einen kubischen Fit umgestellt werden.
Trübungsstützpunkte und TDS-Polynom müssen anhand der realen Sensoren und
Referenzmessungen eingestellt werden. Distanz und Temperatur folgen
`(Rohwert + Offset) * Scale`; die Rohwert-Entitäten für TUR und TDS bleiben
zusätzlich verfügbar.

Vor jeder Umrechnung prüft die Bridge die **Rohwerte** auf Plausibilität:
`DIST` 0–500 cm, `TMP` −20–60 °C sowie `TUR`/`TDS` 0–1023 (Grenzen inklusive).
Ausreißer und nicht endliche Werte werden `UNKNOWN`, ebenso ihre abgeleiteten
Werte. Ungültige Temperatur verhindert die TDS-Kompensation, lässt aber den
gültigen TDS-Rohwert erhalten. Die benannten Grenzen in `conversions.py` sind
Defaults; Offset/Scale ändern diese Rohwertprüfung nicht.

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
Schwellenwerte sind MQTT-Discovery-Entitäten und lassen sich ohne Flash ändern.
