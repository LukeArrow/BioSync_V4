#include "SoftUart.h"

const uint8_t SENSOR_DE_PIN = 10;
const unsigned long SENSOR_STALE_MS = 660000UL;
const unsigned long RELAY_STALE_MS = 660000UL;
const unsigned long TELEMETRY_INTERVAL_MS = 1000;
const uint8_t FRAME_BUFFER_SIZE = 160;
const uint8_t USB_BUFFER_SIZE = 160;

char sensorBuffer[FRAME_BUFFER_SIZE];
char relayBuffer[FRAME_BUFFER_SIZE];
char usbBuffer[USB_BUFFER_SIZE];
uint8_t sensorLength = 0;
uint8_t relayLength = 0;
uint8_t usbLength = 0;
char distanceValue[16] = "UNKNOWN";
char temperatureValue[16] = "UNKNOWN";
char turbidityValue[16] = "UNKNOWN";
char tdsValue[16] = "UNKNOWN";
char relayStates[4][8] = {"UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"};
unsigned long sensorUpdatedAt = 0;
unsigned long relayUpdatedAt = 0;
unsigned long lastTelemetryAt = 0;
bool relayChanged = false;
char lastTelemetry[192] = "";

void sendTelemetry(bool force);
void sendRelay();

bool validNumber(const char *text) {
  if (text == NULL || *text == '\0') {
    return false;
  }
  char *end = NULL;
  const double value = strtod(text, &end);
  return end != text && *end == '\0' && isfinite(value);
}

void handleUsbCommand(char *command) {
  if (strncmp(command, "NEX ", 4) == 0) {
    const char *nextionCommand = command + 4;
    if (*nextionCommand == '\0') {
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
  }
}

void readUsb() {
  while (Serial.available() > 0) {
    const char value = Serial.read();
    if (value == '\r') {
      continue;
    }
    if (value == '\n') {
      usbBuffer[usbLength] = '\0';
      if (usbLength > 0) {
        handleUsbCommand(usbBuffer);
      }
      usbLength = 0;
    } else if (usbLength < USB_BUFFER_SIZE - 1) {
      usbBuffer[usbLength++] = value;
    } else {
      usbLength = 0;
    }
  }
}

bool readField(char *frame, const char *field, char *destination, size_t capacity) {
  char search[24];
  snprintf(search, sizeof(search), "%s=", field);
  char *start = strstr(frame, search);
  if (start == NULL) {
    return false;
  }
  start += strlen(search);
  char *end = strchr(start, ';');
  if (end == NULL) {
    end = strchr(start, '>');
  }
  if (end == NULL) {
    return false;
  }
  const size_t length = end - start;
  if (length == 0 || length >= capacity) {
    return false;
  }
  memcpy(destination, start, length);
  destination[length] = '\0';
  return true;
}

bool validRelayState(const char *value) {
  return strcmp(value, "IDLE") == 0 || strcmp(value, "ACTIVE") == 0 ||
         strcmp(value, "ERROR") == 0 || strcmp(value, "UNKNOWN") == 0;
}

void parseSensorFrame(char *frame) {
  if (!validFrameChecksum(frame) || strncmp(frame, "<SENSOR;", 8) != 0) {
    return;
  }
  char *start = frame;
  char parsed[16];
  if (readField(start, "DIST", parsed, sizeof(parsed))) {
    if (strcmp(parsed, "UNKNOWN") == 0 || validNumber(parsed)) {
      strcpy(distanceValue, parsed);
    } else {
      strcpy(distanceValue, "UNKNOWN");
    }
  } else {
    strcpy(distanceValue, "UNKNOWN");
  }
  if (readField(start, "TMP", parsed, sizeof(parsed))) {
    if (strcmp(parsed, "UNKNOWN") == 0 || validNumber(parsed)) {
      strcpy(temperatureValue, parsed);
    } else {
      strcpy(temperatureValue, "UNKNOWN");
    }
  } else {
    strcpy(temperatureValue, "UNKNOWN");
  }
  if (readField(start, "TUR", parsed, sizeof(parsed)) && validNumber(parsed)) {
    strcpy(turbidityValue, parsed);
  } else {
    strcpy(turbidityValue, "UNKNOWN");
  }
  if (readField(start, "TDS", parsed, sizeof(parsed)) && validNumber(parsed)) {
    strcpy(tdsValue, parsed);
  } else {
    strcpy(tdsValue, "UNKNOWN");
  }
  sensorUpdatedAt = millis();
}

void parseRelayFrame(char *frame) {
  if (!validFrameChecksum(frame) || strncmp(frame, "<RELAY;", 7) != 0) {
    return;
  }
  char *start = frame;
  const char *fields[4] = {"PUMP_ACTIVE", "PUMP_ERROR", "VENT_ACTIVE", "VENT_ERROR"};
  char parsed[8];
  for (uint8_t index = 0; index < 4; ++index) {
    if (readField(start, fields[index], parsed, sizeof(parsed)) &&
        validRelayState(parsed)) {
      if (strcmp(relayStates[index], parsed) != 0) {
        relayChanged = true;
      }
      strcpy(relayStates[index], parsed);
    } else {
      if (strcmp(relayStates[index], "UNKNOWN") != 0) {
        relayChanged = true;
      }
      strcpy(relayStates[index], "UNKNOWN");
    }
  }
  relayUpdatedAt = millis();
}

void readRs485(HardwareSerial &port, char *buffer, uint8_t &length, bool sensor) {
  while (port.available() > 0) {
    const char value = port.read();
    if (value == '\n') {
      buffer[length] = '\0';
      if (sensor) {
        parseSensorFrame(buffer);
      } else {
        parseRelayFrame(buffer);
      }
      length = 0;
    } else if (value != '\r' && length < FRAME_BUFFER_SIZE - 1) {
      buffer[length++] = value;
    } else if (length >= FRAME_BUFFER_SIZE - 1) {
      length = 0;
    }
  }
}

void buildTelemetry(char *out, size_t size) {
  const unsigned long now = millis();
  if (sensorUpdatedAt == 0 || now - sensorUpdatedAt > SENSOR_STALE_MS) {
    strcpy(distanceValue, "UNKNOWN");
    strcpy(temperatureValue, "UNKNOWN");
    strcpy(turbidityValue, "UNKNOWN");
    strcpy(tdsValue, "UNKNOWN");
  }
  if (relayUpdatedAt == 0 || now - relayUpdatedAt > RELAY_STALE_MS) {
    for (uint8_t index = 0; index < 4; ++index) {
      if (strcmp(relayStates[index], "UNKNOWN") != 0) {
        relayChanged = true;
      }
      strcpy(relayStates[index], "UNKNOWN");
    }
  }
  snprintf(
      out, size,
      "$TELEMETRY;DIST=%s;TMP=%s;TUR=%s;TDS=%s;PUMP_ACTIVE=%s;PUMP_ERROR=%s;"
      "VENT_ACTIVE=%s;VENT_ERROR=%s;SENSOR_NODE=%s;RELAY_NODE=%s",
      distanceValue, temperatureValue, turbidityValue, tdsValue, relayStates[0],
      relayStates[1], relayStates[2], relayStates[3],
      sensorUpdatedAt != 0 && now - sensorUpdatedAt <= SENSOR_STALE_MS ? "ONLINE"
                                                                       : "OFFLINE",
      relayUpdatedAt != 0 && now - relayUpdatedAt <= RELAY_STALE_MS ? "ONLINE"
                                                                    : "OFFLINE");
}

void sendTelemetry(bool force) {
  char line[sizeof(lastTelemetry)];
  buildTelemetry(line, sizeof(line));
  if (force || strcmp(line, lastTelemetry) != 0) {
    strcpy(lastTelemetry, line);
    Serial.println(line);
  }
}

void sendRelay() {
  Serial.print("$RELAY;PUMP_ACTIVE=");
  Serial.print(relayStates[0]);
  Serial.print(";PUMP_ERROR=");
  Serial.print(relayStates[1]);
  Serial.print(";VENT_ACTIVE=");
  Serial.print(relayStates[2]);
  Serial.print(";VENT_ERROR=");
  Serial.println(relayStates[3]);
}

void forwardNextionInput() {
  static uint8_t bytes[48];
  static uint8_t length = 0;
  static uint8_t terminators = 0;
  while (Serial2.available() > 0) {
    const uint8_t value = Serial2.read();
    if (value == 0xFF) {
      if (++terminators == 3) {
        Serial.print("$NEXTION;");
        for (uint8_t index = 0; index < length; ++index) {
          if (bytes[index] < 16) {
            Serial.print('0');
          }
          Serial.print(bytes[index], HEX);
          if (index + 1 < length) {
            Serial.print(' ');
          }
        }
        Serial.println();
        length = 0;
        terminators = 0;
      }
    } else {
      while (terminators > 0 && length < sizeof(bytes)) {
        bytes[length++] = 0xFF;
        --terminators;
      }
      if (length < sizeof(bytes)) {
        bytes[length++] = value;
      } else {
        length = 0;
        terminators = 0;
      }
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
