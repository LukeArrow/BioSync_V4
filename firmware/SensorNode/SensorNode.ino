#include <DallasTemperature.h>
#include <OneWire.h>

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

OneWire oneWire(ONEWIRE_PIN);
DallasTemperature temperatureSensor(&oneWire);
unsigned long lastSample = 0;

void waitForBit(unsigned long deadline) {
  while ((int32_t)(micros() - deadline) < 0) {
  }
}

void sendByte(uint8_t value) {
  unsigned long deadline = micros();
  digitalWrite(RS485_TX_PIN, LOW);
  deadline += 104;
  waitForBit(deadline);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    digitalWrite(RS485_TX_PIN, (value & (1 << bit)) ? HIGH : LOW);
    deadline += 104;
    waitForBit(deadline);
  }
  digitalWrite(RS485_TX_PIN, HIGH);
  deadline += 104;
  waitForBit(deadline);
}

float readDistanceCm() {
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

void sendFrame(const char *frame) {
  digitalWrite(RS485_DE_PIN, HIGH);
  delay(RS485_DELAY_MS);
  while (*frame) {
    sendByte(*frame++);
  }
  sendByte('\r');
  sendByte('\n');
  delay(RS485_DELAY_MS);
  digitalWrite(RS485_DE_PIN, LOW);
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
      "<SENSOR;DIST=%s;TMP=%s;TUR=%d;TDS=%d>",
      distanceText,
      temperatureText,
      turbidity,
      tds);
  sendFrame(frame);
}
