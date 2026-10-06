# Home Assistant

## Pakete installieren und migrieren

Die Pakete ergänzen sich; Berechnungen und Diagnosen sind optional:

| Quelle im Repository | Zweck / Abhängigkeiten |
|---|---|
| `homeassistant/packages/biosync_v4.yaml` | Bestehende Kalibrierhelfer, kalibrierte Sensoren, Grenzwerte, Wartungsmodus und Beispielalarme |
| `homeassistant/packages/biosync_v4_calculations.yaml` | Füllstand und neutrale Trendberechnungen; benötigt `biosync_v4.yaml` |
| `homeassistant/packages/biosync_v4_diagnostics.yaml` | Technische Diagnosen und aggregierte Meldungen; benötigt beide anderen Pakete |

Diese Abhängigkeiten sind logisch: Alle benötigten Entities müssen vorhanden
sein; eine erzwungene alphabetische Ladefolge der Paketdateien ist nicht nötig.

Die gewünschten Dateien aus den **Repository-relativen Quellpfaden** oben nach
`/config/packages/` kopieren, jeweils unter demselben Dateinamen. In
`/config/configuration.yaml` Packages aktivieren:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Existiert bereits ein `homeassistant:`-Block, dessen `packages:`-Schlüssel dort
ergänzen bzw. mit der vorhandenen Package-Einbindung zusammenführen. Weder
`homeassistant:` noch `packages:` doppelt anlegen und jedes Paket nur einmal
einbinden.

Manuelle Migration:

1. Gewünschte Pakete kopieren und bestehende Package-Einbindung zusammenführen.
2. Alte BioSync-Templates entfernen/deaktivieren, um Entity-ID-/`unique_id`-
   Kollisionen und `_2`-Entitäten zu verhindern; Dashboard-, Automations- und
   Nextion-Verweise umstellen.
3. **Home-Assistant-Konfiguration prüfen**, dann Home Assistant neu starten.
4. Registrierte Entity-IDs, Kalibrierung, gemessene Geometrie und Diagnosen prüfen.

Voraussetzung ist eine aktuelle Home-Assistant-Version mit Unterstützung für
`default_entity_id` in Template-Entitäten. Statistik-Sensoren verwenden dagegen
`entity_id` für die Quelle und `unique_id` für die Registrierung;
`default_entity_id` wird dort nicht unterstützt. Bei bestehenden Registry-Einträgen
ggf. die Entity-ID in der Oberfläche an die unten dokumentierten Namen anpassen.

## Bestehende Kalibrierung und Wartung

Das Paket stellt `input_boolean.biosync_maintenance` bereit. Beim Einschalten
ruft die Automation `recorder.disable` auf, beim Ausschalten `recorder.enable`.
Das pausiert den Recorder global (nicht nur BioSync-Sensoren). Während der
Wartung unterdrücken die bestehenden Beispielalarmbedingungen Meldungen.
Die neuen Diagnosen bleiben aktiv; Wartung ist nur ein HA-lokaler Hinweis und
wird nicht an die Firmware übertragen. Die globale Recorder-Automation wird
in den Zusatzpaketen nicht dupliziert.

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

## Füllstand und neutrale Trends

Das Berechnungspaket ergänzt folgende Entities:

| Entity | Bedeutung |
|---|---|
| `input_number.biosync_v4_empty_distance` | Kalibrierter Abstand bei leerem Behälter (cm) |
| `input_number.biosync_v4_full_distance` | Kalibrierter Abstand bei vollem Behälter (cm) |
| `input_boolean.biosync_v4_geometry_initialized` | Eigener, persistenter Erststart-Merker für die Geometrie |
| `sensor.biosync_v4_level_cm` | Füllhöhe: `max(0, empty_distance - distance)` |
| `sensor.biosync_v4_level_percent` | `100 * (empty_distance - distance) / (empty_distance - full_distance)`, auf 0–100 % begrenzt |
| `sensor.biosync_v4_level_mean_14d` | 14-Tage-Mittel der Füllhöhe in cm |
| `sensor.biosync_v4_temperature_mean_14d` | 14-Tage-Mittel der kalibrierten Temperatur |
| `sensor.biosync_v4_turbidity_mean_14d` | 14-Tage-Mittel der kalibrierten Trübung |
| `sensor.biosync_v4_tds_mean_14d` | 14-Tage-Mittel des kalibrierten TDS |
| `sensor.biosync_v4_level_deviation_percent` | Vorzeichenbehaftete Abweichung der Füllhöhe vom Mittel |
| `sensor.biosync_v4_tds_deviation_percent` | Vorzeichenbehaftete TDS-Abweichung vom Mittel |
| `sensor.biosync_v4_turbidity_deviation_percent` | Vorzeichenbehaftete Trübungsabweichung vom Mittel |
| `sensor.biosync_v4_temperature_difference` | Aktuelle Temperatur minus Mittel, vorzeichenbehaftet in °C |
| `sensor.biosync_v4_tds_ntu_ratio` | TDS / Trübung, Einheit ppm/NTU; kein Biologie-Score |

`distance` ist `sensor.biosync_v4_distance`, nicht der Rohabstand. Die Geometrie
muss numerisch sein und `empty_distance > full_distance >= 0` erfüllen.
Bei ungültiger Geometrie sind Füllstandswerte `unavailable`; außerhalb der
Geometrie bleiben die Begrenzungen erhalten und eine separate Diagnose meldet
den Fehler. Die cm-Höhe wird nur unten auf null begrenzt, nicht oben.

Die Geometriehelfer und ihr Merker haben **keine `initial`-Werte**, damit
HA ihre Werte wiederherstellt. Nur der unabhängige erste Geometriestart setzt
die **Beispiele** 170 cm (leer) und 0 cm (voll); die vorhandene
Kalibrierinitialisierung wird dadurch nicht erneut ausgelöst. Beide Abstände
an die reale Anlage anpassen, nicht als universelle Vorgaben übernehmen.
Insbesondere hat der Ultraschallsensor einen Nahbereich/Totbereich:
**0 cm Vollabstand ist nur ein Rechenbeispiel**, kein verlässlicher Messpunkt.
Den tatsächlichen Vollabstand außerhalb dieser Blindzone an der Anlage messen.

Prozentabweichungen sind `100 * (aktuell - Mittel) / Mittel`; ein fehlendes
oder nicht strikt positives Mittel erlaubt keine Division. Auch das Verhältnis
ist nur mit strikt positiver Trübung berechenbar; fehlende, null oder negative
Nenner ergeben `unavailable`. Fehlende Daten werden
nicht durch künstliche Nullen oder einen vermeintlich gesunden Zustand ersetzt.

### Statistik, Recorder und Vergleichbarkeit

Alle vier Statistik-Sensoren verwenden `state_characteristic: average_step`,
`sampling_size: 2000000` und `max_age: {days: 14}`. Quellen sind
`sensor.biosync_v4_level_cm` sowie die drei kalibrierten Sensoren
`sensor.biosync_v4_temperature`, `sensor.biosync_v4_turbidity` und
`sensor.biosync_v4_tds`. `average_step` ist ein zeitgewichtetes Stufenmittel
über die verfügbaren numerischen Zustandsänderungen, kein schlichtes
arithmetisches Mittel und keine Garantie für lückenlose 14 Tage.

Für die Wiederbefüllung nach Neustarts mindestens 14 Tage Recorder-History
vorhalten (`purge_keep_days: 14` oder mehr). Recorder-`include`/`exclude`
müssen die Quellen erfassen. Ausschlüsse, globale Wartungspausen und fehlende
Messwerte können die Basis verkürzen oder unterbrechen. Langzeitstatistiken
ersetzen diese benötigte Zustandshistory nicht.

Bei tatsächlich 1 Hz numerischen Änderungen umfasst ein 14-Tage-Fenster rund
1,21 Millionen Einträge je Quelle; der Puffer erlaubt bis zu **2 Millionen je
Sensor** und kann erheblichen Arbeitsspeicher beanspruchen. Der USB-Takt allein
bedeutet nicht, dass jede Sekunde ein neuer numerischer Zustand gespeichert wird.
Der Speicherverbrauch wächst dynamisch mit den tatsächlich gespeicherten
Einträgen; die Obergrenze reserviert nicht sofort zwei Millionen Einträge.
Bei seltenen Änderungen stabiler Messwerte kann die Statistik unzureichende
Zeitabdeckung haben; alte Einträge können aus dem Fenster auslaufen und das
Mittel kann fehlen, obwohl der zuletzt angezeigte Messwert unverändert bleibt.
Ein nach wenigen Messungen vorhandenes Mittel ist noch keine volle
14-Tage-Abdeckung. Änderungen an Kalibrierung oder Behältergeometrie mischen
unvergleichbare alte und neue Werte in der Basis; Statistik/History bewusst
neu aufbauen oder bis zum Auslaufen der alten Daten nicht als vergleichbar werten.

Offizielle Dokumentation:
[Statistics](https://www.home-assistant.io/integrations/statistics/) und
[Template](https://www.home-assistant.io/integrations/template/).

## Technische Diagnosen und gemeinsame Meldungen

| Entity | Prüfung |
|---|---|
| `binary_sensor.biosync_v4_communication_problem` | Immer verfügbar; Problem bei fehlendem gültigem Node-, Rohwert- oder Relaisstatus |
| `binary_sensor.biosync_v4_pump_fault` | Pumpenfehler: `ERROR` → an, `IDLE` → aus; `UNKNOWN`/fehlend → `unavailable` |
| `binary_sensor.biosync_v4_vent_fault` | Belüfterfehler: `ERROR` → an, `IDLE` → aus; `UNKNOWN`/fehlend → `unavailable` |
| `binary_sensor.biosync_v4_raw_invalid` | Numerische Rohwerte außerhalb der Hardwaregrenzen |
| `binary_sensor.biosync_v4_configuration_problem` | Fehlende kalibrierte Werte, negative kalibrierte Distanz/Trübung/TDS oder ungültige Geometrie |
| `binary_sensor.biosync_v4_out_of_geometry` | Kalibrierter Abstand kleiner als Vollabstand oder größer als Leerabstand, trotz begrenzter Füllstandsanzeige |
| `binary_sensor.biosync_v4_alarm` | Technischer Sammelalarm, sobald eine technische Teildiagnose nicht `off` ist, einschließlich `unknown`/`unavailable` |
| `sensor.biosync_v4_process_messages` | Interne Listenquelle für Prozess-/Datenwarnungen; kurzer fester Zustand und Attribute |
| `sensor.biosync_v4_diagnostic_messages` | Interne Listenquelle für alle Diagnoseursachen; kurzer fester Zustand und Attribute |
| `sensor.biosync_v4_process_warnings` | Anzahl ausschließlich erkannter Prozessbedingungen; Liste im Attribut `meldungen`, fehlende Daten separat im Attribut `daten_fehlend` |
| `sensor.biosync_v4_diagnostic_causes` | Anzahl aller Diagnoseursachen; vollständige Liste im Attribut `meldungen`, einschließlich Wartung und fehlender Baselines |
| `sensor.biosync_v4_diagnostic_level` | Priorität `ALARM` > `WARNUNG` > `INFO` > `OK` |
| `sensor.biosync_v4_diagnostic_info` | Kurzer Text der ersten Ursache |
| `sensor.biosync_v4_diagnostic_shorttext` | Kompakter Text mit Diagnosestufe und Ursachenanzahl |

Die beiden internen Listenquellen berechnen die Meldungsattribute. Die öffentlichen
Sensoren `process_warnings` und `diagnostic_causes` leiten daraus ihre Anzahl und
die Listen ab, statt den Zustand aus eigenen alten Attributen zu berechnen.
`process_warnings` zählt nur erkannte Prozessbedingungen, nicht fehlende Daten.
Sein separates Attribut `daten_fehlend` führt fehlende Vergleichswerte auf;
die Gesamtdiagnose übernimmt diese als „Daten fehlen“ und zählt sie als Ursachen.
So entstehen weder veraltete Selbstzählungen noch zyklische Abhängigkeiten.

Kommunikation ist nur fehlerfrei, wenn beide Node-Entities gültig `on` melden
(`off` bedeutet getrennt), alle vier erforderlichen Rohwerte numerisch sind und
alle vier Relaiszustände gültig sind: Aktivkanäle `ACTIVE`/`IDLE`, Fehlerkanäle
`ERROR`/`IDLE`. Fehlende/ungültige Zustände ergeben ein Kommunikationsproblem,
nicht einen gesunden Ersatzwert. `raw_invalid` prüft unabhängig die inklusiven
Hardwarebereiche: Temperatur −20 bis 60 °C, Abstand 0 bis 500 cm sowie beide
ADC-Werte 0 bis 1023. Die Bridge kann solche Werte bereits als `UNKNOWN`
veröffentlichen; dann meldet die Diagnose fehlende Kommunikation/Daten statt
den verworfenen Zahlenwert nachträglich rekonstruieren zu können.

Kalibrier-/Geometrieprobleme werden getrennt von der Kommunikation ausgewiesen:
Gültige Rohdaten bedeuten nicht automatisch gültige Kalibrierung. Negative
kalibrierte Temperatur ist dagegen nicht allein ein Konfigurationsfehler.
Ein echter `ERROR` ist ein Alarm; `UNKNOWN` ist kein `IDLE`.
Der Sammelalarm ist vorsorglich `on`, sobald mindestens eine technische
Teildiagnose einen anderen Zustand als `off` hat (`on`, `unknown` oder
`unavailable`). Auch während der Initialisierung wird ein unbekannter
Diagnosestatus daher niemals als gesund gewertet. Die Ursachenliste
kennzeichnet dies mit „: Status unbekannt“; das ist **kein Nachweis eines
Hardware-`ERROR`**. Die einzelnen Pumpen-/Belüfterfehler bleiben bei unbekanntem
Fehlerkanal `unavailable` und unterscheiden weiterhin `ERROR` von `IDLE`.

Die gemeinsamen, festen **Beispielschwellen** für Prozesswarnungen lauten überall:

- Betrag der Trübungs- oder TDS-Abweichung **> 25 %**;
- Betrag der Temperaturdifferenz **> 8 °C**;
- Füllstand **< 15 % oder > 95 %**.

Es gibt dafür keine neuen Schwellenhelfer. Die vorhandenen Kalibrierpaket-
Grenzwerte bleiben davon unabhängige Beispielalarme. Fehlende erforderliche
Baselines/Vergleichswerte erzeugen **„Daten fehlen“** als aggregierte Warnung,
niemals allein deshalb `OK`. Diagnose und Anzeige nutzen dieselbe
`process_warnings`-Liste statt unterschiedlicher Schwellenberechnungen.
Technische Ursachen ergeben `ALARM`, Prozess-/Datenwarnungen `WARNUNG`,
Wartung allein `INFO`, nur ohne Ursachen gilt `OK`. Höhere Stufen verdrängen
die niedrigeren in der Stufenanzeige, aber nicht aus der Ursachenliste.
Wartung unterdrückt diese neuen Diagnosen und den Sammelalarm **nicht**.

Node-Liveness nutzt ausschließlich die vorhandenen Node-Status-Entities und
den Firmware-Timeout von etwa 11 Minuten. Es gibt keine Empfangszeitstempel,
keinen erfundenen Staleness-Timer und keine gesicherte Aussage über das Alter
eines unveränderten Zahlenwerts. MQTT-`unavailable` bleibt ein Daten-/Verbindungs-
problem; die Diagnose repariert weder Broker noch Bridge.

### Umfang der automatisierten Prüfung

Die Pakettests rendern die tatsächlichen Jinja-Templates aus den YAML-Dateien
mit Jinja `NativeEnvironment` und minimalen Nachbildungen der HA-Hilfsfunktionen.
Die separaten Testabhängigkeiten PyYAML und Jinja2 stehen in
`homeassistant/requirements-test.txt` und werden von der CI installiert;
die Bridge-Laufzeitabhängigkeiten bleiben unverändert.
Dies ist **kein Live-Home-Assistant-Test**: Entity-Registrierung, Statistik-
Integration, Recorder-Wiederbefüllung und HA-Laufzeitverhalten müssen weiterhin
in der eigenen Installation geprüft werden. Die oben verlinkten offiziellen
Dokumentationsseiten erläutern die Integrationen. Eine Live-HA-Prüfung wurde
hier nicht durchgeführt; die eigene HA-Konfiguration prüfen.

## Zuordnung aus dem Altbestand

Das vollständige Legacy-YAML und seine Formeln liegen für diese Migration nicht
vor; exakte alte Entity-IDs sind deshalb nicht verlässlich bekannt. Die folgende
Zuordnung erfolgt bewusst nach **Legacy-Bezeichnungen**, nicht nach erfundenen IDs:

| Alte Bezeichnung / Funktion | V4-Ersatz |
|---|---|
| Füllhöhe / Füllstand in cm bzw. Prozent | `sensor.biosync_v4_level_cm` bzw. `sensor.biosync_v4_level_percent` |
| 14-Tage-Mittel von Füllstand, Temperatur, Trübung, TDS | Die entsprechenden `sensor.biosync_v4_*_mean_14d` oben; Füllstandsbasis ist cm |
| Relative Abweichung von Füllstand, TDS, Trübung | Die entsprechenden `sensor.biosync_v4_*_deviation_percent` |
| Temperaturabweichung | `sensor.biosync_v4_temperature_difference` in °C, nicht Prozent |
| „NTU TDS Verhältnis“ | Trotz des alten Titels tatsächlich TDS/NTU: `sensor.biosync_v4_tds_ntu_ratio` |
| Pumpen-/Belüfterstörung und Sammelalarm | Technische Binary-Sensoren und `binary_sensor.biosync_v4_alarm` |
| Diagnose, Information, Kurztext | `diagnostic_level`, `diagnostic_info`, `diagnostic_shorttext` mit dem Sensorpräfix `sensor.biosync_v4_` |
| Kläranlagenstatus / Gesundheitsindex / Biologische Aktivität / Biologie Status / Auffälligkeit | Neutrale technische Diagnose, Prozessabweichungen und Ursachenlisten statt alter Score-Formeln |

Ein alter Temperatur-Prozentwert auf einer °C-Skala war irreführend:
Der Nullpunkt ist willkürlich, Prozentwerte nahe 0 °C sind nicht physikalisch
aussagekräftig. Er wird durch die vorzeichenbehaftete Temperaturdifferenz ersetzt,
nicht durch eine andere Biologieformel.

Neutrale Trends, Verhältnis und technische Diagnosen bleiben erhalten; sie
belegen weder biologische Aktivität noch Reinigungsleistung. Ohne vollständige
Altformeln ist keine exakte Score-Reproduktion möglich. Es wird daher auch
**keine experimentelle Heuristik-Datei** angeboten.

### Schnittstellen-Kompatibilität

| Funktion | V4-Schnittstelle / Grenzen |
|---|---|
| Rohmesswerte | MQTT-`sensor`: Abstand in cm, Temperatur in °C, Trübung und TDS in ADC (0–1023), noch nicht NTU/ppm |
| Kalibrierte Messwerte | HA-Template-`sensor`: Abstand in cm, Temperatur in °C, Trübung in NTU, TDS in ppm |
| Pumpen-/Belüfter-Aktiv- und Fehlerkanäle | MQTT-`sensor`, **Textzustände** `ACTIVE`/`IDLE` bzw. `ERROR`/`IDLE`; fehlend `UNKNOWN` oder HA-`unknown`/`unavailable`, keine `on`/`off`-Binary-Sensoren |
| Node-Verbindung | MQTT-`binary_sensor.biosync_v4_sensor_node` / `binary_sensor.biosync_v4_relay_node`, HA-Zustände `on`/`off` |
| Wartung | HA-lokales `input_boolean.biosync_maintenance`; kein Firmware-Wartungsstatus |
| Legacy SD-ready | Nicht unterstützt: SD wurde entfernt; kein künstlicher „gesund/bereit“-Ersatz |
| Legacy Firmware-Alarm | Nicht unterstützt; `binary_sensor.biosync_v4_alarm` wird aus HA-Diagnosen abgeleitet |
| Legacy letzter Telegrammempfang / Last-telegram | Nicht unterstützt: keine Empfangszeitstempel; Node-Status ersetzt keinen Zeitstempel |
