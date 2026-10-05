#include "SoftUart.h"

const uint8_t RS485_DE_PIN = 5;
const uint8_t RS485_RX_PIN = 6;
const uint8_t RS485_TX_PIN = 7;
const uint8_t SENSOR_PINS[4] = {A0, A1, A2, A3};
const uint16_t LED_ON_THRESHOLD = 300;
const uint16_t LED_OFF_THRESHOLD = 800;
const uint8_t AVERAGE_SAMPLES = 5;
const unsigned long SAMPLE_INTERVAL_MS = 200;
const unsigned long HEARTBEAT_INTERVAL_MS = 5000;
const unsigned long RS485_DELAY_MS = 10;

const char *stateNames[] = {"IDLE", "ACTIVE", "ERROR"};
uint8_t states[4] = {0, 0, 0, 0};
bool initialized = false;
unsigned long lastSample = 0;
unsigned long lastTransmit = 0;

uint16_t readAverage(uint8_t pin) {
  uint32_t total = 0;
  for (uint8_t sample = 0; sample < AVERAGE_SAMPLES; ++sample) {
    total += analogRead(pin);
  }
  return total / AVERAGE_SAMPLES;
}

uint8_t readLedState(uint8_t pin, uint8_t previous) {
  const uint16_t value = readAverage(pin);
  if (value < LED_ON_THRESHOLD) {
    return 1;
  }
  if (value > LED_OFF_THRESHOLD) {
    return 0;
  }
  return previous;
}

void sendStates() {
  // A0: Pumpe aktiv, A1: Pumpe Fehler, A2: Lüftung aktiv, A3: Lüftung Fehler.
  // Fehlerkanäle A1/A3 liefern nur ERROR/IDLE, nie ACTIVE.
  char frame[112];
  snprintf(
      frame,
      sizeof(frame),
      "RELAY;PUMP_ACTIVE=%s;PUMP_ERROR=%s;VENT_ACTIVE=%s;VENT_ERROR=%s",
      stateNames[states[0]],
      stateNames[states[1] == 1 ? 2 : 0],
      stateNames[states[2]],
      stateNames[states[3] == 1 ? 2 : 0]);
  sendFrame(RS485_TX_PIN, RS485_DE_PIN, RS485_DELAY_MS, frame);
}

void setup() {
  pinMode(RS485_DE_PIN, OUTPUT);
  pinMode(RS485_RX_PIN, INPUT);
  pinMode(RS485_TX_PIN, OUTPUT);
  digitalWrite(RS485_TX_PIN, HIGH);
  digitalWrite(RS485_DE_PIN, LOW);
  for (uint8_t index = 0; index < 4; ++index) {
    pinMode(SENSOR_PINS[index], INPUT);
  }
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSample = now;

  bool changed = !initialized;
  for (uint8_t index = 0; index < 4; ++index) {
    const uint8_t next = readLedState(SENSOR_PINS[index], states[index]);
    if (next != states[index]) {
      states[index] = next;
      changed = true;
    }
  }
  initialized = true;
  if (changed || now - lastTransmit >= HEARTBEAT_INTERVAL_MS) {
    sendStates();
    lastTransmit = now;
  }
}
