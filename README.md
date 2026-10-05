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

## Protokoll (zentral dokumentiert)

RS-485-Frames sind ASCII in spitzen Klammern, mit Zeilenende; es gibt keine
Checksumme.

```text
<SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420>
<RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=ERROR>
```

`DIST` ist Zentimeter, `TMP` Grad Celsius, `TUR` und `TDS` sind unveränderte
ADC-Werte. Ein nicht verfügbarer Messwert/Zustand lautet `UNKNOWN`, ein echter
Ruhezustand `IDLE`. SensorNode sendet alle 5 Sekunden, RelayNode bei Änderung
und zusätzlich alle 5 Sekunden.

Der Mega gibt einmal pro Sekunde genau diese USB-Felder aus:

```text
$TELEMETRY;DIST=..;TMP=..;TUR=..;TDS=..;PUMP_ACTIVE=..;PUMP_ERROR=..;VENT_ACTIVE=..;VENT_ERROR=..
```

`SD`, `MAINT` und `ALARM` gehören nicht zum V4-Protokoll. Fehlende oder
veraltete RS-485-Daten werden als `UNKNOWN` übertragen. Empfangene
Nextion-Tastendrücke gehen als Hex-Bytes auf USB:
`$NEXTION;65 00 01 01`; die Bridge veröffentlicht sie auf
`biosync_v4/nextion`.

USB-Kommandos sind zeilenweise:

- `GET` liest den aktuellen EEPROM-Zustand als `$CONFIG;NAME=WERT;...` zurück.
- `SET PARAMETER WERT` speichert einen Parameter im EEPROM; `CAL PARAMETER WERT`
  und `CAL_PARAMETER=WERT` sind kompatible Kurzformen.
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

## Tests und Home Assistant

```sh
PYTHONPATH=ha-bridge python -m unittest discover -s ha-bridge/tests -v
```

Home-Assistant-Pakete sind unter `homeassistant/README.md` beschrieben.
Wartung pausiert den Recorder global und unterdrückt die Beispielalarme.
Schwellenwerte sind MQTT-Discovery-Entitäten und lassen sich ohne Flash ändern.
