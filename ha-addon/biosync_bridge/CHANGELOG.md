# Changelog
## 1.3.2

- alles kommt nun durch die brdige

## 1.3.1

- Relay- und Nextion-MQTT-Nutzdaten werden bei `log_level: DEBUG` protokolliert.

## 1.3.0

- **Protokolländerung – alle drei Firmwares gemeinsam flashen.** Die
  RS-485-Prüfsumme `CK` entfällt; Frames lauten z. B. `<SENSOR;DIST=..;...>`.
  Ein evtl. noch mitgesendetes `CK=` wird als normales Feld durchgereicht.
- Nichts wird mehr verworfen, ersetzt oder gefiltert: SensorNode sendet
  Rohwerte (z. B. `TMP=-127.0`, `DIST=0.0` bei Timeouts, `DIST_RAW` mit allen
  fünf Einzelmessungen), RelayNode zusätzlich die ADC-Rohwerte `A0`–`A3`.
- DisplayNode gibt jeden Frame roh als `$RAW_SENSOR;`/`$RAW_RELAY;` aus
  (bei Pufferüberlauf mit `OVERFLOW;`), übernimmt alle Felder unverändert in
  `$TELEMETRY`, behält nach 11 Minuten die letzten Werte (`SENSOR_AGE`/
  `RELAY_AGE` in Sekunden) und meldet unbekannte/zu lange Kommandos per `$ERR;`.
- Bridge ohne Bereichsgrenzen, Pflichtfelder und Zustandsprüfung; jede USB-Zeile
  geht nach `biosync_v4/raw`, außerdem `raw_sensor`, `raw_relay`, `ack`,
  `unknown`. Relaisfelder aus `$TELEMETRY` zusätzlich nach `biosync_v4/relay`.
  Jede empfangene Zeile setzt die Verfügbarkeit auf `online`.
- Ausgehende Kommandos werden nicht mehr validiert (nur Zeilenumbrüche entfernt).
- Neue Diagnose-Entitäten für Rohzeilen, Datenalter, Distanz-Einzelmessungen
  und RelayNode-ADC-Werte; Templates robust gegen fehlende Felder.

## 1.2.2

- Optionales HA-Paket `biosync_nextion.yaml`: kalibrierte Nextion-Anzeige,
  persistente Tankhelfer und vollständiges Neuzeichnen bei Start, Reconnect
  sowie `BTN_REFRESH`/`SCR_WAKE`.
- Installation und Feldzuordnung dokumentiert; Bridge und Firmware unverändert.

## 1.2.1

- Telemetrie nur bei Änderungen; Statusabfrage bei HA-Start und Reconnect.
