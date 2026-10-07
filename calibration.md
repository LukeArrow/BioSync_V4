# BioSync V4 Kalibrierungsanleitung

## Dokumentinformationen

**Projekt:** BioSync V4  
**Version:** Home Assistant Paket V4  
**Anwender:** Lukas Pfeiler  
**Erstellt am:** Oktober 2026

---

# Inhaltsverzeichnis

1. Einleitung
2. Vorbereitungen
3. Kalibrierung des JSN-SR04T Abstandssensors
4. Kalibrierung des DS18B20 Temperatursensors
5. Kalibrierung des TSW-20M Trübungssensors
6. Kalibrierung des CQRSENTDS01 TDS-Sensors
7. Einstellung der Alarm-Grenzwerte
8. Wartungsmodus
9. Empfohlene Praxiswerte
10. Fehlersuche
11. Wartungsprotokoll

---

# 1. Einleitung

Das BioSync-V4-System verarbeitet die Messdaten der Sensoren direkt in Home Assistant. Die Sensoren liefern Rohwerte, welche mithilfe von Kalibrierparametern auf reale Messwerte umgerechnet werden.

Eine sorgfältige Kalibrierung erhöht die Genauigkeit und verbessert die Aussagekraft der Messdaten für:

- Wasserstand
- Temperatur
- Trübung
- TDS (Total Dissolved Solids)

Alle Einstellungen werden über die in Home Assistant angelegten Helfer (`input_number`) vorgenommen.

---

# 2. Vorbereitungen

Vor Beginn der Kalibrierung werden folgende Hilfsmittel empfohlen:

## Für den Abstandssensor

- Maßband
- Zollstock

## Für den Temperatursensor

- Kalibriertes Thermometer
- Eiswasser (ca. 0 °C)
- Warmwasser (ca. 40–50 °C)

## Für den Trübungssensor

- Klares Wasser
- Leicht eingetrübtes Wasser
- Stark eingetrübtes Wasser

Alternativ:

- Professionelle NTU-Referenzlösungen

## Für den TDS-Sensor

Empfohlen:

- TDS-Referenzlösung 342 ppm
- TDS-Referenzlösung 1413 ppm

---

# 3. Kalibrierung des JSN-SR04T Abstandssensors

## Sensorbeschreibung

Der JSN-SR04T misst den Abstand zwischen Sensor und Wasseroberfläche.

Berechnungsformel:

```text
Abstand = (Rohwert + Offset) × Scale
```

---

## Verwendete Helfer

```text
input_number.biosync_v4_dist_offset
input_number.biosync_v4_dist_scale
```

---

## Einfache Kalibrierung (empfohlen)

### Schritt 1

Tatsächlichen Abstand messen.

Beispiel:

```text
Abstand gemessen: 50 cm
```

### Schritt 2

Rohwert auslesen:

```text
sensor.biosync_v4_distance_raw
```

Beispiel:

```text
47 cm
```

### Schritt 3

Offset berechnen:

```text
Offset = Referenzwert - Rohwert

Offset = 50 - 47
Offset = 3
```

### Schritt 4

Eintragen:

```text
BioSync Distanz Offset = 3
BioSync Distanz Skalierung = 1
```

---

## Erweiterte Zweipunkt-Kalibrierung

Falls Messfehler mit zunehmender Entfernung größer werden:

Messpunkt 1:

```text
Real: 20 cm
Roh: 18 cm
```

Messpunkt 2:

```text
Real: 100 cm
Roh: 92 cm
```

Berechnung:

```text
Scale = (100 - 20) / (92 - 18)

Scale = 1,0811
```

Offset:

```text
Offset = 20 / 1,0811 - 18

Offset ≈ 0,5
```

Eintragen:

```text
Offset = 0,5
Scale = 1,08
```

---

# 4. Kalibrierung des DS18B20 Temperatursensors

## Sensorbeschreibung

Der DS18B20 misst die Wassertemperatur.

Berechnungsformel:

```text
Temperatur = (Rohwert + Offset) × Scale
```

---

## Verwendete Helfer

```text
input_number.biosync_v4_tmp_offset
input_number.biosync_v4_tmp_scale
```

---

## Einpunkt-Kalibrierung

Sensor neben ein Referenzthermometer legen.

Beispiel:

```text
DS18B20: 22,1 °C
Referenz: 22,8 °C
```

Berechnung:

```text
Offset = 22,8 - 22,1

Offset = 0,7
```

Eintragen:

```text
BioSync Temperatur Offset = 0,7
BioSync Temperatur Skalierung = 1
```

---

## Zweipunkt-Kalibrierung

### Eiswasser-Test

```text
Referenz: 0 °C
Sensor: 1 °C
```

### Warmwasser-Test

```text
Referenz: 50 °C
Sensor: 48 °C
```

Berechnung:

```text
Scale = (50 - 0) / (48 - 1)

Scale = 1,0638
```

Offset:

```text
Offset = 0 / 1,0638 - 1

Offset = -1
```

Eintragen:

```text
Offset = -1
Scale = 1,064
```

---

# 5. Kalibrierung des TSW-20M Trübungssensors

## Sensorbeschreibung

Der TSW-20M liefert ADC-Rohwerte zwischen:

```text
0 bis 1023
```

Diese werden über drei Referenzpunkte in NTU umgerechnet.

---

## Verwendete Helfer

```text
biosync_v4_tur_x1
biosync_v4_tur_y1

biosync_v4_tur_x2
biosync_v4_tur_y2

biosync_v4_tur_x3
biosync_v4_tur_y3
```

---

## Bedeutung

```text
x = ADC-Rohwert
y = NTU-Wert
```

---

## Praktische Kalibrierung

### Punkt 1 – klares Wasser

Messung:

```text
ADC = 220
```

Eintragen:

```text
x1 = 220
y1 = 0
```

---

### Punkt 2 – leicht trübes Wasser

Messung:

```text
ADC = 450
```

Eintragen:

```text
x2 = 450
y2 = 500
```

---

### Punkt 3 – stark trübes Wasser

Messung:

```text
ADC = 800
```

Eintragen:

```text
x3 = 800
y3 = 1000
```

---

## Wichtige Regel

Die ADC-Werte müssen immer aufsteigend sein:

```text
x1 < x2 < x3
```

Korrekt:

```text
220 < 450 < 800
```

Falsch:

```text
450 < 220 < 800
```

---

## Hinweis

Ohne professionelle NTU-Referenzlösungen sind die resultierenden NTU-Werte als Näherungswerte zu betrachten.

Der Sensor eignet sich hervorragend zur Erkennung von Veränderungen:

```text
klar
↓
leicht trüb
↓
stark trüb
```

---

# 6. Kalibrierung des CQRSENTDS01 TDS-Sensors

## Sensorbeschreibung

Der Sensor misst die Konzentration gelöster Stoffe im Wasser.

Einheit:

```text
ppm
```

---

## Verwendete Helfer

```text
biosync_v4_tds_a
biosync_v4_tds_b
biosync_v4_tds_c
biosync_v4_tds_d
```

---

## Berechnungsformel

```text
TDS = a × x³ + b × x² + c × x + d
```

mit:

```text
x = ADC-Rohwert
```

---

## Empfohlene lineare Kalibrierung

Für die meisten Anwendungen ausreichend:

```text
a = 0
b = 0
```

Es werden nur:

```text
c
d
```

bestimmt.

---

## Kalibrierung mit Referenzlösungen

### Referenzlösung 1

```text
342 ppm
ADC = 410
```

### Referenzlösung 2

```text
1413 ppm
ADC = 870
```

---

## Berechnung von c

```text
c = (1413 - 342) / (870 - 410)

c = 2,328
```

---

## Berechnung von d

```text
d = 342 - (410 × 2,328)

d = -612,5
```

---

## Eintragen

```text
BioSync TDS Koeffizient A = 0
BioSync TDS Koeffizient B = 0
BioSync TDS Koeffizient C = 2,328
BioSync TDS Koeffizient D = -612,5
```

---

# 7. Einstellung der Alarm-Grenzwerte

Die Grenzwerte dienen ausschließlich der Alarmierung.

---

## Abstand

```text
input_number.biosync_v4_dist_threshold
```

Beispiel:

```text
200 cm
```

---

## Trübung

```text
input_number.biosync_v4_tur_threshold
```

Beispiel:

```text
1000 NTU
```

---

## TDS

```text
input_number.biosync_v4_tds_threshold
```

Beispiel:

```text
1000 ppm
```

---

# 8. Wartungsmodus

Der Wartungsmodus verhindert die Erzeugung neuer BioSync-Alarme.

Aktivierung:

```text
input_boolean.biosync_maintenance
```

Status:

```text
ON  = Wartung aktiv
OFF = Normalbetrieb
```

---

# 9. Empfohlene Praxiswerte

## Distanz

```text
Offset = individuell
Scale = 1
```

---

## Temperatur

```text
Offset = individuell
Scale = 1
```

---

## Trübung

```text
x1 = 220  y1 = 0
x2 = 450  y2 = 500
x3 = 800  y3 = 1000
```

---

## TDS

```text
a = 0
b = 0
c = 2,34
d = -622
```

Diese Werte können als Ausgangspunkt verwendet werden.

---

# 10. Fehlersuche

## Sensor zeigt "unknown"

Prüfen:

- MQTT-Verbindung aktiv
- Sensor liefert Rohwert
- Kalibrierwerte vorhanden
- Home Assistant Template zeigt keine Fehler

---

## Negative Trübungswerte

Mögliche Ursache:

```text
Messung außerhalb des kalibrierten Bereiches
```

Trübung neu kalibrieren.

---

## Unplausible TDS-Werte

Prüfen:

- Temperaturwert plausibel
- Referenzlösung korrekt
- TDS-Koeffizienten richtig eingegeben

---

## Abstand springt stark

Mögliche Ursachen:

- Schräger Einbau
- Reflexionen an Behälterwänden
- Bewegte Wasseroberfläche
- Kondenswasser auf dem Sensor

---

# 11. Wartungs- und Kalibrierprotokoll

## Distanzsensor

```text
Datum:
Referenz:
Rohwert:
Offset:
Scale:
Bemerkung:
```

---

## Temperatursensor

```text
Datum:
Referenz:
Rohwert:
Offset:
Scale:
Bemerkung:
```

---

## Trübungssensor

```text
Datum:
x1:
y1:

x2:
y2:

x3:
y3:

Bemerkung:
```

---

## TDS-Sensor

```text
Datum:

Referenz 1:
ADC:

Referenz 2:
ADC:

a:
b:
c:
d:

Bemerkung:
```

---

# Zusammenfassung

Für höchste Messgenauigkeit sollten zunächst der DS18B20-Temperatursensor, der CQRSENTDS01-TDS-Sensor und anschließend der JSN-SR04T-Abstandssensor kalibriert werden. Der TSW-20M-Trübungssensor liefert auch ohne professionelle NTU-Referenzlösungen wertvolle Trendinformationen und eignet sich hervorragend zur frühzeitigen Erkennung von Veränderungen der Wasserqualität.
