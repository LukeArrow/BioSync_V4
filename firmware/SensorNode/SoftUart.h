#ifndef BIOSYNC_SOFT_UART_H
#define BIOSYNC_SOFT_UART_H

#include <Arduino.h>

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

inline void sendFrame(uint8_t txPin, uint8_t dePin,
                      unsigned long turnaroundMs, const char *payload) {
  digitalWrite(dePin, HIGH);
  delay(turnaroundMs);
  sendByte(txPin, '<');
  while (*payload) {
    sendByte(txPin, *payload++);
  }
  sendByte(txPin, '>');
  sendByte(txPin, '\r');
  sendByte(txPin, '\n');
  delay(turnaroundMs);
  digitalWrite(dePin, LOW);
}

#endif
