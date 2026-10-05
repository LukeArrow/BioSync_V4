#ifndef BIOSYNC_SOFT_UART_H
#define BIOSYNC_SOFT_UART_H

#include <Arduino.h>
#include <string.h>

const unsigned long BIT_DURATION_US = 1000000UL / 9600;

inline void waitForBit(unsigned long deadline) {
  while ((int32_t)(micros() - deadline) < 0) {
  }
}

inline void sendByte(uint8_t txPin, uint8_t value) {
  noInterrupts();
  unsigned long deadline = micros();
  digitalWrite(txPin, LOW);
  deadline += BIT_DURATION_US;
  waitForBit(deadline);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    digitalWrite(txPin, (value & (1 << bit)) ? HIGH : LOW);
    deadline += BIT_DURATION_US;
    waitForBit(deadline);
  }
  digitalWrite(txPin, HIGH);
  // Ohne micros()-Aufruf im Stoppbit einen zweiten AVR-Timerüberlauf vermeiden.
  delayMicroseconds(BIT_DURATION_US);
  interrupts();
}

inline uint8_t payloadChecksum(const char *payload, size_t length) {
  uint8_t checksum = 0;
  for (size_t index = 0; index < length; ++index) {
    checksum ^= static_cast<uint8_t>(payload[index]);
  }
  return checksum;
}

inline void sendFrame(uint8_t txPin, uint8_t dePin,
                      unsigned long turnaroundMs, const char *payload) {
  const char hex[] = "0123456789ABCDEF";
  const uint8_t checksum = payloadChecksum(payload, strlen(payload));
  digitalWrite(dePin, HIGH);
  delay(turnaroundMs);
  sendByte(txPin, '<');
  while (*payload) {
    sendByte(txPin, *payload++);
  }
  const char suffix[] = ";CK=";
  for (const char *value = suffix; *value; ++value) {
    sendByte(txPin, *value);
  }
  sendByte(txPin, hex[checksum >> 4]);
  sendByte(txPin, hex[checksum & 0x0F]);
  sendByte(txPin, '>');
  sendByte(txPin, '\r');
  sendByte(txPin, '\n');
  delay(turnaroundMs);
  digitalWrite(dePin, LOW);
}

inline int8_t checksumHex(char value) {
  if (value >= '0' && value <= '9') {
    return value - '0';
  }
  if (value >= 'A' && value <= 'F') {
    return value - 'A' + 10;
  }
  return -1;
}

inline bool validFrameChecksum(const char *frame) {
  const size_t length = strlen(frame);
  if (length < 9 || frame[0] != '<' || frame[length - 1] != '>') {
    return false;
  }
  const char *marker = frame + length - 7;
  if (strncmp(marker, ";CK=", 4) != 0 ||
      strstr(frame, ";CK=") != marker) {
    return false;
  }
  for (const char *value = frame + 1; value < marker; ++value) {
    if (*value == '<' || *value == '>') {
      return false;
    }
  }
  const int8_t high = checksumHex(marker[4]);
  const int8_t low = checksumHex(marker[5]);
  return high >= 0 && low >= 0 &&
         payloadChecksum(frame + 1, marker - frame - 1) ==
             static_cast<uint8_t>((high << 4) | low);
}

#endif
