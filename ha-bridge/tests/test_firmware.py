import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"

ARDUINO_STUB = r"""
#pragma once
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using std::isfinite;
using std::isnan;
const uint8_t LOW = 0, HIGH = 1, INPUT = 0, OUTPUT = 1;
const uint8_t A0 = 14, A1 = 15, A2 = 16, A3 = 17, HEX = 16;
uint64_t clockUs = 0;
bool irqEnabled = true;
bool emulatePendingOverflow = false;
uint64_t servicedOverflows = 0;
unsigned maskedBytes = 0, restoredBytes = 0;
std::vector<int> byteBits;
std::vector<unsigned long> byteStarts;
std::string transmitted;
std::vector<unsigned long> pulses, triggerTimes;
size_t pulseIndex = 0;
unsigned long micros() {
  const uint64_t now = clockUs++;
  if (emulatePendingOverflow && !irqEnabled) {
    return static_cast<uint32_t>(
        servicedOverflows * 1024 + now % 1024 +
        (now / 1024 > servicedOverflows ? 1024 : 0));
  }
  return static_cast<uint32_t>(now);
}
unsigned long millis() { return static_cast<uint32_t>(clockUs / 1000); }
void noInterrupts() {
  assert(irqEnabled);
  servicedOverflows = clockUs / 1024;
  irqEnabled = false;
  ++maskedBytes;
  byteBits.clear();
  byteStarts.push_back(static_cast<uint32_t>(clockUs));
}
void interrupts() {
  assert(!irqEnabled && byteBits.size() == 10);
  assert(byteBits.front() == LOW && byteBits.back() == HIGH);
  assert(clockUs - byteStarts.back() >= 10 * 104 || clockUs > UINT32_MAX);
  uint8_t value = 0;
  for (unsigned bit = 0; bit < 8; ++bit) {
    value |= byteBits[bit + 1] << bit;
  }
  transmitted += static_cast<char>(value);
  irqEnabled = true;
  ++restoredBytes;
}
void digitalWrite(uint8_t, uint8_t value) {
  if (!irqEnabled) byteBits.push_back(value);
}
void pinMode(uint8_t, uint8_t) {}
void delay(unsigned long ms) { clockUs += ms * 1000; }
void delayMicroseconds(unsigned int us) { clockUs += us; }
unsigned long pulseIn(uint8_t, uint8_t, unsigned long timeout) {
  assert(pulseIndex < pulses.size() && timeout == 30000UL);
  triggerTimes.push_back(clockUs);
  const unsigned long value = pulses[pulseIndex++];
  clockUs += value ? value : timeout;
  return value;
}
int analogRead(uint8_t) { return 512; }
char *dtostrf(double value, signed char width, unsigned char precision, char *out) {
  sprintf(out, "%*.*f", width, precision, value);
  return out;
}
struct HardwareSerial {
  std::string output;
  void begin(unsigned long) {}
  int available() { return 0; }
  int read() { return 0; }
  void write(uint8_t) {}
  void print(const char *value) { output += value; }
  void print(char *value) { output += value; }
  void print(char value) { output += value; }
  template <typename T> void print(T) {}
  template <typename T> void print(T, int) {}
  void println() {}
  void println(const char *value) { output += value; output += '\n'; }
  void println(char *value) { output += value; output += '\n'; }
  template <typename T> void println(T) {}
};
HardwareSerial Serial, Serial1, Serial2, Serial3;
"""


def checked_frame(payload):
    checksum = 0
    for byte in payload.encode("ascii"):
        checksum ^= byte
    return f"<{payload};CK={checksum:02X}>"


@unittest.skipUnless(shutil.which("g++"), "Firmware-Logiktests benötigen g++")
class FirmwareLogicTests(unittest.TestCase):
    def run_sketch(self, sketch, body):
        # Automatisch entfernte Testdateien in einem erlaubten Verzeichnis ablegen.
        with tempfile.TemporaryDirectory(
            prefix=".firmware-test-", dir=ROOT
        ) as directory:
            work = Path(directory)
            (work / "Arduino.h").write_text(ARDUINO_STUB)
            (work / "OneWire.h").write_text(
                "#pragma once\nstruct OneWire { explicit OneWire(int) {} };\n"
            )
            (work / "DallasTemperature.h").write_text(
                '#pragma once\n#include "OneWire.h"\n'
                "const float DEVICE_DISCONNECTED_C = -127;\n"
                "struct DallasTemperature {\n"
                "explicit DallasTemperature(OneWire *) {}\n"
                "void begin() {}\n"
                "void requestTemperatures() { delay(750); }\n"
                "float getTempCByIndex(int) { return 18.3f; }\n};\n"
            )
            (work / "EEPROM.h").write_text(
                "#pragma once\nstruct EEPROMClass {\n"
                "template <typename T> void put(int, const T &) {}\n"
                "template <typename T> void get(int, T &) {}\n"
                "};\nEEPROMClass EEPROM;\n"
            )
            source = work / "test.cpp"
            source.write_text(
                '#include "Arduino.h"\n'
                f'#include "{sketch}"\n'
                "int main() {\n" + body + "\n}\n"
            )
            binary = work / "firmware-test"
            result = subprocess.run(
                [
                    "g++",
                    "-std=c++11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(work),
                    str(source),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "TMPDIR": str(work)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_uart_byte_framing_interrupts_fresh_clock_and_checksum(self):
        payload = "SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420"
        expected = checked_frame(payload)
        self.run_sketch(
            FIRMWARE / "common" / "SoftUart.h",
            f"""
  sendByte(6, 0xA5);
  delay(7);
  sendByte(6, 0x00);
  assert(transmitted.size() == 2);
  assert(static_cast<uint8_t>(transmitted[0]) == 0xA5);
  assert(transmitted[1] == 0);
  assert(byteStarts[1] - byteStarts[0] >= 8040);
  clockUs = UINT32_MAX - 500;
  sendByte(6, 0xFF);
  assert(static_cast<uint8_t>(transmitted[2]) == 0xFF);
  transmitted.clear();
  clockUs = 10000;
  sendFrame(6, 5, 10, {json.dumps(payload)});
  assert(transmitted == {json.dumps(expected + chr(13) + chr(10))});
  assert(irqEnabled && maskedBytes == restoredBytes);
  assert(validFrameChecksum({json.dumps(expected)}));
""",
        )

    def test_checksum_rejects_missing_malformed_nonfinal_and_duplicate_fields(self):
        valid = checked_frame("SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420")
        invalid = [
            "",
            "<>",
            "<SENSOR;DIST=1>",
            valid[:-4] + "00>",
            valid[:-3] + "GG>",
            valid[:-3] + "aF>",
            valid[:-2] + ">",
            valid[:-1] + "0>",
            valid + "junk",
            "junk" + valid,
            valid[:-1] + ";EXTRA=1>",
            checked_frame("SENSOR;DIST=1;CK=00;TMP=2"),
            checked_frame("SENSOR;DIST=<1"),
            checked_frame("SENSOR;DIST=1>"),
        ]
        checks = "\n".join(
            f"assert(!validFrameChecksum({json.dumps(frame)}));" for frame in invalid
        )
        self.run_sketch(FIRMWARE / "common" / "SoftUart.h", checks)

    def test_uart_pending_timer_overflow_at_every_start_phase(self):
        self.run_sketch(
            FIRMWARE / "common" / "SoftUart.h",
            r"""
  emulatePendingOverflow = true;
  for (unsigned phase = 0; phase < 1024; ++phase) {
    clockUs = phase;
    const uint64_t started = clockUs;
    sendByte(6, 0xA5);
    assert(clockUs - started >= 1040 && clockUs - started < 1060);
    assert(static_cast<uint8_t>(transmitted.back()) == 0xA5);
  }
  assert(irqEnabled && maskedBytes == restoredBytes);
""",
        )

    def test_ultrasound_median_minimum_valid_samples_and_spacing(self):
        self.run_sketch(
            FIRMWARE / "SensorNode" / "SensorNode.ino",
            r"""
  const std::vector<std::vector<unsigned long>> cases = {
    {5800, 1160, 1740, 29000, 2320},
    {0, 1160, 1740, 0, 2320},
    {5800, 1160, 1740, 0, 2320},
    {0, 1160, 0, 0, 2320},
    {0, 0, 0, 0, 0}
  };
  const float expected[] = {40, 30, 35, NAN, NAN};
  for (size_t index = 0; index < cases.size(); ++index) {
    pulses = cases[index];
    pulseIndex = 0;
    triggerTimes.clear();
    const uint64_t started = clockUs;
    const float result = readDistanceCm();
    if (isnan(expected[index])) assert(isnan(result));
    else assert(fabs(result - expected[index]) < 0.01f);
    assert(pulseIndex == 5 && triggerTimes.size() == 5);
    for (size_t sample = 1; sample < triggerTimes.size(); ++sample) {
      assert(triggerTimes[sample] - triggerTimes[sample - 1] >= 60000);
    }
    assert(clockUs - started <= 390060);
  }
""",
        )

    def test_sensor_loop_samples_immediately_then_every_five_minutes(self):
        expected = checked_frame("SENSOR;DIST=UNKNOWN;TMP=18.3;TUR=512;TDS=512")
        self.run_sketch(
            FIRMWARE / "SensorNode" / "SensorNode.ino",
            f"""
  clockUs = 0;
  pulses = {{0, 0, 0, 0, 0}};
  loop();
  assert(transmitted == {json.dumps(expected + chr(13) + chr(10))});
  const size_t firstLength = transmitted.size();
  loop();
  assert(transmitted.size() == firstLength);
  clockUs = 300000000;
  pulses = {{5800, 1160, 1740, 29000, 2320}};
  pulseIndex = 0;
  loop();
  assert(transmitted.find("DIST=40.0") != std::string::npos);
  const size_t secondLength = transmitted.size();
  loop();
  assert(transmitted.size() == secondLength);
""",
        )

    def test_display_reports_node_status_and_publishes_relay_stale_change(self):
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            r"""
  assert(SENSOR_STALE_MS == 660000UL && RELAY_STALE_MS == 660000UL);
  clockUs = 700000000;
  sensorUpdatedAt = 1;
  relayUpdatedAt = 1;
  strcpy(relayStates[0], "ACTIVE");
  relayChanged = false;
  loop();
  assert(relayChanged);
  assert(strcmp(relayStates[0], "UNKNOWN") == 0);
  assert(
      Serial.output.find(";SENSOR_NODE=OFFLINE;RELAY_NODE=OFFLINE") !=
      std::string::npos);
  loop();
  assert(!relayChanged);
  assert(Serial.output.find("$RELAY;PUMP_ACTIVE=UNKNOWN") != std::string::npos);
  Serial.output.clear();
  sensorUpdatedAt = millis();
  relayUpdatedAt = millis();
  sendTelemetry();
  assert(
      Serial.output.find(";SENSOR_NODE=ONLINE;RELAY_NODE=ONLINE") !=
      std::string::npos);
""",
        )

    def test_node_heartbeat_intervals_are_five_minutes(self):
        self.run_sketch(
            FIRMWARE / "RelayNode" / "RelayNode.ino",
            "assert(HEARTBEAT_INTERVAL_MS == 300000UL);",
        )
        self.run_sketch(
            FIRMWARE / "SensorNode" / "SensorNode.ino",
            "assert(SAMPLE_INTERVAL_MS == 300000UL);",
        )

    def test_relay_mapping_and_error_fields_are_only_error_or_idle(self):
        assertions = []
        for mask in range(16):
            states = [(mask >> bit) & 1 for bit in range(4)]
            payload = (
                f"RELAY;PUMP_ACTIVE={'ACTIVE' if states[0] else 'IDLE'};"
                f"PUMP_ERROR={'ERROR' if states[1] else 'IDLE'};"
                f"VENT_ACTIVE={'ACTIVE' if states[2] else 'IDLE'};"
                f"VENT_ERROR={'ERROR' if states[3] else 'IDLE'}"
            )
            assertions.append(
                "transmitted.clear();\n"
                + "\n".join(f"states[{i}] = {value};" for i, value in enumerate(states))
                + "\nsendStates();\n"
                + f"assert(transmitted == {json.dumps(checked_frame(payload) + chr(13) + chr(10))});"
            )
        self.run_sketch(FIRMWARE / "RelayNode" / "RelayNode.ino", "\n".join(assertions))

    def test_display_drops_bad_checksums_without_values_timestamps_or_change_flag(self):
        sensor = checked_frame("SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420")
        relay = checked_frame(
            "RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=ERROR"
        )
        body = f"""
  clockUs = 123000;
  char sensor[] = {json.dumps(sensor)};
  char relay[] = {json.dumps(relay)};
  parseSensorFrame(sensor);
  parseRelayFrame(relay);
  assert(strcmp(distanceValue, "123.4") == 0);
  assert(strcmp(temperatureValue, "18.3") == 0);
  assert(strcmp(turbidityValue, "512") == 0 && strcmp(tdsValue, "420") == 0);
  assert(strcmp(relayStates[0], "ACTIVE") == 0);
  assert(strcmp(relayStates[3], "ERROR") == 0 && relayChanged);
  assert(sensorUpdatedAt == 123 && relayUpdatedAt == 123);
  relayChanged = false;
  clockUs = 456000;
"""
        for parser, payload in [
            ("parseSensorFrame", "SENSOR;DIST=999;TMP=99;TUR=999;TDS=999"),
            (
                "parseRelayFrame",
                "RELAY;PUMP_ACTIVE=IDLE;PUMP_ERROR=ERROR;"
                "VENT_ACTIVE=ACTIVE;VENT_ERROR=IDLE",
            ),
        ]:
            valid = checked_frame(payload)
            invalid = [
                f"<{payload}>",
                valid[:-3] + "GG>",
                valid[:-3] + "a0>",
                valid[:-3] + ("00>" if valid[-3:-1] != "00" else "FF>"),
                valid[:-2] + ">",
                valid[:-1] + ";EXTRA=1>",
                checked_frame(payload + ";CK=00"),
                "junk" + valid,
                valid + "junk",
            ]
            for frame in invalid:
                body += f"""
  {{
    char bad[] = {json.dumps(frame)};
    {parser}(bad);
    assert(strcmp(distanceValue, "123.4") == 0);
    assert(strcmp(temperatureValue, "18.3") == 0);
    assert(strcmp(turbidityValue, "512") == 0 && strcmp(tdsValue, "420") == 0);
    assert(strcmp(relayStates[0], "ACTIVE") == 0);
    assert(strcmp(relayStates[1], "IDLE") == 0);
    assert(strcmp(relayStates[2], "IDLE") == 0);
    assert(strcmp(relayStates[3], "ERROR") == 0);
    assert(sensorUpdatedAt == 123 && relayUpdatedAt == 123 && !relayChanged);
  }}
"""
        self.run_sketch(FIRMWARE / "DisplayNode" / "DisplayNode.ino", body)


class FirmwareCopyTests(unittest.TestCase):
    def test_sketch_local_headers_match_canonical_copy(self):
        canonical = (FIRMWARE / "common" / "SoftUart.h").read_bytes()
        for node in ("SensorNode", "RelayNode", "DisplayNode"):
            with self.subTest(node=node):
                copy = FIRMWARE / node / "SoftUart.h"
                self.assertFalse(copy.is_symlink())
                self.assertEqual(copy.read_bytes(), canonical)


if __name__ == "__main__":
    unittest.main()
