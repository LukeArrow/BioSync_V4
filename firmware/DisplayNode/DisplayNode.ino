#include "SoftUart.h"

// Der DisplayNode verwirft keine Daten: Jeder RS-485-Frame wird roh als
// $RAW_SENSOR/$RAW_RELAY über USB ausgegeben und alle Felder werden
// unverändert in $TELEMETRY bzw. $RELAY übernommen. Aussortiert wird in HA.

const uint8_t SENSOR_DE_PIN = 10;
const unsigned long SENSOR_STALE_MS = 660000UL;
const unsigned long RELAY_STALE_MS = 660000UL;
const unsigned long TELEMETRY_INTERVAL_MS = 1000;
const uint16_t FRAME_BUFFER_SIZE = 256;
const uint16_t USB_BUFFER_SIZE = 256;
const uint16_t NEXTION_BUFFER_SIZE = 128;
// "$TELEMETRY" + zwei vollständige Frame-Inhalte + Node-Status.
const uint16_t TELEMETRY_BUFFER_SIZE = 600;

char sensorBuffer[FRAME_BUFFER_SIZE];
char relayBuffer[FRAME_BUFFER_SIZE];
char usbBuffer[USB_BUFFER_SIZE];
uint16_t sensorLength = 0;
uint16_t relayLength = 0;
uint16_t usbLength = 0;
uint16_t usbDropped = 0;
// Unveränderte Feldliste des letzten Frames (ohne "<SENSOR;"/"<RELAY;" und ">").
char sensorFields[FRAME_BUFFER_SIZE] = "";
char relayFields[FRAME_BUFFER_SIZE] = "";
unsigned long sensorUpdatedAt = 0;
unsigned long relayUpdatedAt = 0;
unsigned long lastTelemetryAt = 0;
bool relayChanged = false;
char lastTelemetry[TELEMETRY_BUFFER_SIZE] = "";

void sendTelemetry(bool force);
void sendRelay();

void handleUsbCommand(char *command) {
  if (strncmp(command, "NEX ", 4) == 0) {
    const char *nextionCommand = command + 4;
    if (*nextionCommand == '\0') {
      Serial.println("$ERR;COMMAND=NEX;ERROR=EMPTY");
      return;
    }
    Serial2.print(nextionCommand);
    Serial2.write(0xFF);
    Serial2.write(0xFF);
    Serial2.write(0xFF);
    return;
  }
  if (strcmp(command, "STATUS_REQUEST") == 0) {
    sendTelemetry(true);
    sendRelay();
    Serial.println("$ACK;COMMAND=STATUS_REQUEST");
    return;
  }
  Serial.print("$ERR;ERROR=UNKNOWN_COMMAND;COMMAND=");
  Serial.println(command);
}

void readUsb() {
  while (Serial.available() > 0) {
    const char value = Serial.read();
    if (value == '\r') {
      continue;
    }
    if (value == '\n') {
      usbBuffer[usbLength] = '\0';
      if (usbDropped > 0) {
        // Zu lange Zeile: abgeschnitten ausführen und Kürzung melden.
        char message[64];
        snprintf(message, sizeof(message),
                 "$ERR;ERROR=USB_TRUNCATED;DROPPED=%u",
                 static_cast<unsigned>(usbDropped));
        Serial.println(message);
      }
      if (usbLength > 0) {
        handleUsbCommand(usbBuffer);
      }
      usbLength = 0;
      usbDropped = 0;
    } else if (usbLength < USB_BUFFER_SIZE - 1) {
      usbBuffer[usbLength++] = value;
    } else if (usbDropped < UINT16_MAX) {
      ++usbDropped;
    }
  }
}

// Übernimmt die Felder hinter dem Kennzeichen (z. B. "SENSOR;") bis zum ersten
// '>' unverändert. Führende Störbytes vor dem Kennzeichen werden toleriert;
// ein evtl. noch mitgesendetes "CK=.." ist ein normales Feld.
bool copyFrameFields(const char *frame, const char *tag, char *destination,
                     size_t capacity) {
  const char *start = strstr(frame, tag);
  if (start == NULL) {
    return false;
  }
  start += strlen(tag);
  const char *end = strchr(start, '>');
  size_t length = end == NULL ? strlen(start) : static_cast<size_t>(end - start);
  if (length >= capacity) {
    length = capacity - 1;
  }
  memcpy(destination, start, length);
  destination[length] = '\0';
  return true;
}

void parseSensorFrame(const char *frame) {
  if (copyFrameFields(frame, "SENSOR;", sensorFields, sizeof(sensorFields))) {
    sensorUpdatedAt = millis();
  }
}

void parseRelayFrame(const char *frame) {
  if (copyFrameFields(frame, "RELAY;", relayFields, sizeof(relayFields))) {
    relayUpdatedAt = millis();
    relayChanged = true;
  }
}

void printRawFrame(const char *prefix, const char *buffer, uint16_t length) {
  Serial.print(prefix);
  Serial.write(reinterpret_cast<const uint8_t *>(buffer), length);
  Serial.println();
}

void readRs485(HardwareSerial &port, char *buffer, uint16_t &length, bool sensor) {
  while (port.available() > 0) {
    const char value = port.read();
    if (value == '\n') {
      buffer[length] = '\0';
      if (length > 0) {
        printRawFrame(sensor ? "$RAW_SENSOR;" : "$RAW_RELAY;", buffer, length);
        if (sensor) {
          parseSensorFrame(buffer);
        } else {
          parseRelayFrame(buffer);
        }
      }
      length = 0;
    } else if (value != '\r') {
      if (length >= FRAME_BUFFER_SIZE - 1) {
        printRawFrame(sensor ? "$RAW_SENSOR;OVERFLOW;" : "$RAW_RELAY;OVERFLOW;",
                      buffer, length);
        length = 0;
      }
      buffer[length++] = value;
    }
  }
}

void appendText(char *out, size_t size, size_t &used, const char *text) {
  while (*text != '\0' && used + 1 < size) {
    out[used++] = *text++;
  }
  out[used] = '\0';
}

void appendField(char *out, size_t size, size_t &used, const char *field) {
  if (*field != '\0') {
    appendText(out, size, used, ";");
    appendText(out, size, used, field);
  }
}

bool nodeOnline(unsigned long updatedAt, unsigned long staleMs, unsigned long now) {
  return updatedAt != 0 && now - updatedAt <= staleMs;
}

// Veraltete Werte werden nicht überschrieben; nur der Node-Status wechselt.
void buildTelemetry(char *out, size_t size) {
  const unsigned long now = millis();
  size_t used = 0;
  out[0] = '\0';
  appendText(out, size, used, "$TELEMETRY");
  appendField(out, size, used, sensorFields);
  appendField(out, size, used, relayFields);
  appendField(out, size, used,
              nodeOnline(sensorUpdatedAt, SENSOR_STALE_MS, now)
                  ? "SENSOR_NODE=ONLINE"
                  : "SENSOR_NODE=OFFLINE");
  appendField(out, size, used,
              nodeOnline(relayUpdatedAt, RELAY_STALE_MS, now)
                  ? "RELAY_NODE=ONLINE"
                  : "RELAY_NODE=OFFLINE");
}

void formatAge(char *out, size_t size, const char *name, unsigned long updatedAt) {
  if (updatedAt == 0) {
    snprintf(out, size, ";%s=NEVER", name);
  } else {
    snprintf(out, size, ";%s=%lu", name, (millis() - updatedAt) / 1000UL);
  }
}

void sendTelemetry(bool force) {
  char line[sizeof(lastTelemetry)];
  buildTelemetry(line, sizeof(line));
  // Das Alter allein löst keine neue Zeile aus, wird aber immer mitgesendet.
  if (force || strcmp(line, lastTelemetry) != 0) {
    strcpy(lastTelemetry, line);
    char age[32];
    Serial.print(line);
    formatAge(age, sizeof(age), "SENSOR_AGE", sensorUpdatedAt);
    Serial.print(age);
    formatAge(age, sizeof(age), "RELAY_AGE", relayUpdatedAt);
    Serial.println(age);
  }
}

void sendRelay() {
  Serial.print("$RELAY");
  if (relayFields[0] != '\0') {
    Serial.print(";");
    Serial.print(relayFields);
  }
  Serial.println();
}

void printNextionBytes(const char *prefix, const uint8_t *bytes, uint16_t length) {
  Serial.print(prefix);
  for (uint16_t index = 0; index < length; ++index) {
    char hex[4];
    snprintf(hex, sizeof(hex), index + 1 < length ? "%02X " : "%02X", bytes[index]);
    Serial.print(hex);
  }
  Serial.println();
}

void forwardNextionInput() {
  static uint8_t bytes[NEXTION_BUFFER_SIZE];
  static uint16_t length = 0;
  static uint8_t terminators = 0;
  while (Serial2.available() > 0) {
    const uint8_t value = Serial2.read();
    if (value == 0xFF) {
      if (++terminators == 3) {
        printNextionBytes("$NEXTION;", bytes, length);
        length = 0;
        terminators = 0;
      }
    } else {
      while (terminators > 0) {
        if (length >= sizeof(bytes)) {
          printNextionBytes("$ERR;ERROR=NEXTION_OVERFLOW;DATA=", bytes, length);
          length = 0;
        }
        bytes[length++] = 0xFF;
        --terminators;
      }
      if (length >= sizeof(bytes)) {
        // Zu lange Nextion-Daten abgeschnitten melden, nicht still verwerfen.
        printNextionBytes("$ERR;ERROR=NEXTION_OVERFLOW;DATA=", bytes, length);
        length = 0;
      }
      bytes[length++] = value;
    }
  }
}

void setup() {
  pinMode(SENSOR_DE_PIN, OUTPUT);
  digitalWrite(SENSOR_DE_PIN, LOW);
  Serial.begin(115200);
  Serial1.begin(9600);
  Serial2.begin(9600);
  Serial3.begin(9600);
}

void loop() {
  readUsb();
  readRs485(Serial1, sensorBuffer, sensorLength, true);
  readRs485(Serial3, relayBuffer, relayLength, false);
  forwardNextionInput();
  if (relayChanged) {
    relayChanged = false;
    sendRelay();
  }
  if (millis() - lastTelemetryAt >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAt = millis();
    sendTelemetry(false);
  }
}
