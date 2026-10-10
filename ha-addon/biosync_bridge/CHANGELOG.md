# Changelog

## 1.2.3

- MQTT-Verbindung wird auf INFO geloggt; mit `log_level: DEBUG` werden
  empfangene USB-Zeilen, gesendete Kommandos und MQTT-Nutzdaten sichtbar.
- Unbekannte USB-Zeilen werden auf DEBUG als ignoriert protokolliert.

## 1.2.2

- Optionales HA-Paket `biosync_nextion.yaml`: kalibrierte Nextion-Anzeige,
  persistente Tankhelfer und vollständiges Neuzeichnen bei Start, Reconnect
  sowie `BTN_REFRESH`/`SCR_WAKE`.
- Installation und Feldzuordnung dokumentiert; Bridge und Firmware unverändert.

## 1.2.1

- Telemetrie nur bei Änderungen; Statusabfrage bei HA-Start und Reconnect.
