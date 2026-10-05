# Home Assistant

`packages/biosync.yaml` ist ein Beispielpaket für den Wartungsmodus und
Benachrichtigungsalarme. In `configuration.yaml` Packages aktivieren:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Das Paket stellt `input_boolean.biosync_maintenance` bereit. Beim Einschalten
ruft die Automation `recorder.disable` auf, beim Ausschalten `recorder.enable`.
Das pausiert den Recorder global (nicht nur BioSync-Sensoren). Während der
Wartung unterdrücken die Alarmbedingungen Meldungen.

Die Grenzwerte kommen von den MQTT-Discovery-Nummern des Bridges:
`number.biosync_v4_tds_threshold`, `number.biosync_v4_tur_threshold` und
`number.biosync_v4_dist_threshold`. Bei unbekannten Werten werden keine Alarme
ausgelöst. Die Beispielaktionen erzeugen persistente Benachrichtigungen; sie
können in Home Assistant durch Push-, Sirenen- oder andere Aktionen ersetzt
werden.

Der Wartungsmodus startet nach jedem Home-Assistant-Neustart ausgeschaltet;
damit bleibt der Recorder nach einem Neustart aktiviert. Wartung muss danach
bei Bedarf erneut eingeschaltet werden.

Der Mega sendet auch im Wartungsmodus unverändert weiter. Die Bridge berechnet
Messwerte, MQTT Discovery stellt sie bereit und Home Assistant entscheidet über
History, Alarme und Anzeigeinhalte.
