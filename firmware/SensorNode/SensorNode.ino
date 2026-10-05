#include <DallasTemperature.h>
#include <OneWire.h>
#include "SoftUart.h"

// ===== Debug-Konfiguration =====
// Auf 1 setzen fuer Debug-Ausgabe ueber den seriellen Monitor (115200 Baud),
// auf 0 setzen um die Ausgabe komplett zu deaktivieren.
#define DEBUG_ENABLED 0

#if DEBUG_ENABLED
  #define DEBUG_PRINT(x) Serial.print(x)
  #define DEBUG_PRINTLN(x) Serial.println(x)
#else
  #define DEBUG_PRINT(x)
  #define DEBUG_PRINTLN(x)
#endif

const uint8_t TRIG_PIN = 2;
const uint8_t ECHO_PIN = 3;
const uint8_t ONEWIRE_PIN = 4;
const uint8_t RS485_DE_PIN = 5;
const uint8_t RS485_RX_PIN = 7;
const uint8_t RS485_TX_PIN = 6;
const uint8_t TURBIDITY_PIN = A0;
const uint8_t TDS_PIN = A1;
const unsigned long SAMPLE_INTERVAL_MS = 5000;
const unsigned long RS485_DELAY_MS = 10;
const uint8_t DISTANCE_SAMPLES = 5;
const unsigned long DISTANCE_SAMPLE_SPACING_MS = 60;

OneWire oneWire(ONEWIRE_PIN);
DallasTemperature temperatureSensor(&oneWire);
unsigned long lastSample = 0;

float readDistanceSampleCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  const unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (duration == 0) {
    return NAN;
  }
  return duration / 58.0f;
}

float readDistanceCm() {
  float readings[DISTANCE_SAMPLES];
  uint8_t valid = 0;
  for (uint8_t sample = 0; sample < DISTANCE_SAMPLES; ++sample) {
    const float distance = readDistanceSampleCm();
    if (!isnan(distance)) {
      uint8_t index = valid;
      while (index > 0 && readings[index - 1] > distance) {
        readings[index] = readings[index - 1];
        --index;
      }
      readings[index] = distance;
      ++valid;
    }
    if (sample + 1 < DISTANCE_SAMPLES) {
      // JSN-SR04T benoetigt mindestens 60 ms Abstand zwischen Schallimpulsen.
      delay(DISTANCE_SAMPLE_SPACING_MS);
    }
  }
  if (valid < 3) {
    return NAN;
  }
  return valid % 2 ? readings[valid / 2]
                   : (readings[valid / 2 - 1] + readings[valid / 2]) / 2.0f;
}

void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RS485_RX_PIN, INPUT);
  pinMode(RS485_TX_PIN, OUTPUT);
  digitalWrite(RS485_TX_PIN, HIGH);
  pinMode(RS485_DE_PIN, OUTPUT);
  digitalWrite(RS485_DE_PIN, LOW);
  pinMode(TURBIDITY_PIN, INPUT);
  pinMode(TDS_PIN, INPUT);
  temperatureSensor.begin();

  #if DEBUG_ENABLED
    Serial.begin(115200);
    DEBUG_PRINTLN(F("BioSync SensorNode - Debug aktiv"));
  #endif
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSample = now;

  const float distance = readDistanceCm();
  temperatureSensor.requestTemperatures();
  const float temperature = temperatureSensor.getTempCByIndex(0);
  const int turbidity = analogRead(TURBIDITY_PIN);
  const int tds = analogRead(TDS_PIN);

  char frame[112];
  char distanceText[16];
  char temperatureText[16];
  if (isnan(distance)) {
    strcpy(distanceText, "UNKNOWN");
  } else {
    dtostrf(distance, 0, 1, distanceText);
  }
  if (temperature == DEVICE_DISCONNECTED_C || isnan(temperature)) {
    strcpy(temperatureText, "UNKNOWN");
  } else {
    dtostrf(temperature, 0, 1, temperatureText);
  }
  snprintf(
      frame,
      sizeof(frame),
      "SENSOR;DIST=%s;TMP=%s;TUR=%d;TDS=%d",
      distanceText,
      temperatureText,
      turbidity,
      tds);

  DEBUG_PRINT(F("DIST="));
  DEBUG_PRINT(distanceText);
  DEBUG_PRINT(F(" TMP="));
  DEBUG_PRINT(temperatureText);
  DEBUG_PRINT(F(" TUR="));
  DEBUG_PRINT(turbidity);
  DEBUG_PRINT(F(" TDS="));
  DEBUG_PRINT(tds);
  DEBUG_PRINT(F(" -> "));
  DEBUG_PRINTLN(frame);

  sendFrame(RS485_TX_PIN, RS485_DE_PIN, RS485_DELAY_MS, frame);
}
