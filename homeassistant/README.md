# Home Assistant

`packages/biosync.yaml` stellt Kalibrierhelfer, kalibrierte Sensoren,
Grenzwerte, Wartungsmodus und Beispielalarme bereit. In `configuration.yaml`
Packages aktivieren:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Das Paket stellt `input_boolean.biosync_maintenance` bereit. Beim Einschalten
ruft die Automation `recorder.disable` auf, beim Ausschalten `recorder.enable`.
Das pausiert den Recorder global (nicht nur BioSync-Sensoren). Während der
Wartung unterdrücken die Alarmbedingungen Meldungen.

Rohwerte kommen aus den MQTT-Entities mit `_raw` im Entity-Namen. Das Paket
berechnet daraus `sensor.biosync_v4_distance`, `sensor.biosync_v4_temperature`,
`sensor.biosync_v4_turbidity` und `sensor.biosync_v4_tds`. Die dazugehörigen
`input_number`-Helfer erlauben die Anpassung von Distanz-/Temperatur-Offset und
Skalierung, drei Trübungsstützpunkten sowie den vier TDS-Polynomkoeffizienten.
Kalibrierhelfer werden in Home Assistant gespeichert und überleben Neustarts;
eine Kalibrierung im DisplayNode-EEPROM gibt es nicht.
Beim ersten Start initialisiert eine Automation die Helfer mit den im Paket
dokumentierten Beispielwerten; danach bleiben manuelle Anpassungen erhalten.

| Messgröße | Kalibrier-Entities |
|---|---|
| Distanz | `input_number.biosync_v4_dist_offset`, `input_number.biosync_v4_dist_scale` |
| Temperatur | `input_number.biosync_v4_tmp_offset`, `input_number.biosync_v4_tmp_scale` |
| Trübung | `input_number.biosync_v4_tur_x1` bis `_x3` und `input_number.biosync_v4_tur_y1` bis `_y3` |
| TDS | `input_number.biosync_v4_tds_a` bis `_d` |

Die Grenzwerte sind ebenfalls `input_number`-Helfer:
`input_number.biosync_v4_tds_threshold`,
`input_number.biosync_v4_tur_threshold` und
`input_number.biosync_v4_dist_threshold`. Bei unbekannten Messwerten werden
keine Alarme ausgelöst. Die Beispielaktionen erzeugen persistente
Benachrichtigungen; sie können in Home Assistant durch Push-, Sirenen- oder
andere Aktionen ersetzt werden.

Der Wartungsmodus startet nach jedem Home-Assistant-Neustart ausgeschaltet;
damit bleibt der Recorder nach einem Neustart aktiviert. Wartung muss danach
bei Bedarf erneut eingeschaltet werden.

Der Mega sendet rohe Messwerte auch im Wartungsmodus unverändert weiter. Die
Bridge prüft nur Plausibilitätsgrenzen; Home Assistant berechnet kalibrierte
Messwerte und entscheidet über History, Alarme und Anzeigeinhalte.
