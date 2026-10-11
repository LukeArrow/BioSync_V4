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
int analogValue = 512;
int analogRead(uint8_t) { return analogValue; }
char *dtostrf(double value, signed char width, unsigned char precision, char *out) {
  sprintf(out, "%*.*f", width, precision, value);
  return out;
}
struct HardwareSerial {
  std::string output, input;
  size_t inputIndex = 0;
  void begin(unsigned long) {}
  int available() { return static_cast<int>(input.size() - inputIndex); }
  int read() { return static_cast<unsigned char>(input[inputIndex++]); }
  void write(uint8_t value) { output += static_cast<char>(value); }
  void write(const uint8_t *value, size_t length) {
    output.append(reinterpret_cast<const char *>(value), length);
  }
  void print(const char *value) { output += value; }
  void print(char *value) { output += value; }
  void print(char value) { output += value; }
  template <typename T> void print(T) {}
  template <typename T> void print(T, int) {}
  void println() { output += '\n'; }
  void println(const char *value) { output += value; output += '\n'; }
  void println(char *value) { output += value; output += '\n'; }
  template <typename T> void println(T) {}
};
HardwareSerial Serial, Serial1, Serial2, Serial3;
"""


def frame(payload):
    return f"<{payload}>"


def cpp(text):
    return json.dumps(text)


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
                "float stubTemperature = 18.3f;\n"
                "struct DallasTemperature {\n"
                "explicit DallasTemperature(OneWire *) {}\n"
                "void begin() {}\n"
                "void requestTemperatures() { delay(750); }\n"
                "float getTempCByIndex(int) { return stubTemperature; }\n};\n"
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

    def test_uart_byte_framing_interrupts_fresh_clock_without_checksum(self):
        payload = "SENSOR;DIST=123.4;TMP=18.3;TUR=512;TDS=420"
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
  sendFrame(6, 5, 10, {cpp(payload)});
  assert(transmitted == {cpp(frame(payload) + chr(13) + chr(10))});
  assert(transmitted.find("CK=") == std::string::npos);
  assert(irqEnabled && maskedBytes == restoredBytes);
""",
        )

    def test_soft_uart_has_no_checksum_logic(self):
        text = (FIRMWARE / "common" / "SoftUart.h").read_text()
        for name in ("CK=", "Checksum", "checksum"):
            self.assertNotIn(name, text)
        for sketch in ("SensorNode", "RelayNode", "DisplayNode"):
            with self.subTest(sketch=sketch):
                source = (FIRMWARE / sketch / f"{sketch}.ino").read_text()
                self.assertNotIn("validFrameChecksum", source)
                self.assertNotIn("CK=", source.replace('"CK=..', ""))

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

    def test_ultrasound_keeps_all_samples_and_median_without_minimum(self):
        self.run_sketch(
            FIRMWARE / "SensorNode" / "SensorNode.ino",
            r"""
  const std::vector<std::vector<unsigned long>> cases = {
    {5800, 1160, 1740, 29000, 2320},
    {0, 1160, 1740, 0, 2320},
    {5800, 1160, 1740, 0, 2320},
    {0, 1160, 0, 0, 2320},
    {0, 0, 1160, 0, 0},
    {0, 0, 0, 0, 0}
  };
  const float expected[] = {40, 30, 35, 30, 20, 0};
  for (size_t index = 0; index < cases.size(); ++index) {
    pulses = cases[index];
    pulseIndex = 0;
    triggerTimes.clear();
    const uint64_t started = clockUs;
    float samples[DISTANCE_SAMPLES];
    const float result = readDistanceCm(samples);
    assert(!isnan(result));
    assert(fabs(result - expected[index]) < 0.01f);
    for (size_t sample = 0; sample < DISTANCE_SAMPLES; ++sample) {
      assert(fabs(samples[sample] - cases[index][sample] / 58.0f) < 0.01f);
    }
    assert(pulseIndex == 5 && triggerTimes.size() == 5);
    for (size_t sample = 1; sample < triggerTimes.size(); ++sample) {
      assert(triggerTimes[sample] - triggerTimes[sample - 1] >= 60000);
    }
    assert(clockUs - started <= 390060);
  }
""",
        )

    def test_sensor_loop_sends_raw_values_immediately_then_every_five_minutes(self):
        expected = frame(
            "SENSOR;DIST=0.0;TMP=-127.0;TUR=512;TDS=512;DIST_RAW=0.0,0.0,0.0,0.0,0.0"
        )
        self.run_sketch(
            FIRMWARE / "SensorNode" / "SensorNode.ino",
            f"""
  clockUs = 0;
  stubTemperature = DEVICE_DISCONNECTED_C;
  pulses = {{0, 0, 0, 0, 0}};
  loop();
  assert(transmitted == {cpp(expected + chr(13) + chr(10))});
  assert(transmitted.find("UNKNOWN") == std::string::npos);
  const size_t firstLength = transmitted.size();
  loop();
  assert(transmitted.size() == firstLength);
  clockUs = 300000000;
  stubTemperature = 18.3f;
  pulses = {{5800, 1160, 0, 29000, 2320}};
  pulseIndex = 0;
  loop();
  assert(transmitted.find(
      "DIST=70.0;TMP=18.3;TUR=512;TDS=512;"
      "DIST_RAW=100.0,20.0,0.0,500.0,40.0>") != std::string::npos);
  const size_t secondLength = transmitted.size();
  loop();
  assert(transmitted.size() == secondLength);
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

    def test_relay_mapping_error_fields_and_raw_adc_values(self):
        assertions = []
        for mask in range(16):
            states = [(mask >> bit) & 1 for bit in range(4)]
            raw = [100 * index + mask for index in range(4)]
            payload = (
                f"RELAY;PUMP_ACTIVE={'ACTIVE' if states[0] else 'IDLE'};"
                f"PUMP_ERROR={'ERROR' if states[1] else 'IDLE'};"
                f"VENT_ACTIVE={'ACTIVE' if states[2] else 'IDLE'};"
                f"VENT_ERROR={'ERROR' if states[3] else 'IDLE'};"
                + ";".join(f"A{index}={value}" for index, value in enumerate(raw))
            )
            assertions.append(
                "transmitted.clear();\n"
                + "\n".join(f"states[{i}] = {value};" for i, value in enumerate(states))
                + "\n"
                + "\n".join(f"rawValues[{i}] = {value};" for i, value in enumerate(raw))
                + "\nsendStates();\n"
                + f"assert(transmitted == {cpp(frame(payload) + chr(13) + chr(10))});"
            )
        self.run_sketch(FIRMWARE / "RelayNode" / "RelayNode.ino", "\n".join(assertions))

    def test_relay_loop_sends_averaged_adc_values_with_states(self):
        self.run_sketch(
            FIRMWARE / "RelayNode" / "RelayNode.ino",
            r"""
  clockUs = 1000000;
  analogValue = 150;
  loop();
  assert(transmitted.find(
      "<RELAY;PUMP_ACTIVE=IDLE;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;VENT_ERROR=IDLE;"
      "A0=150;A1=150;A2=150;A3=150>") == 0);
  transmitted.clear();
  clockUs += 1000000;
  analogValue = 900;
  loop();
  assert(transmitted ==
         "<RELAY;PUMP_ACTIVE=ACTIVE;PUMP_ERROR=ERROR;VENT_ACTIVE=ACTIVE;"
         "VENT_ERROR=ERROR;A0=900;A1=900;A2=900;A3=900>\r\n");
""",
        )

    def test_display_forwards_raw_frames_and_all_fields_unfiltered(self):
        sensor = frame(
            "SENSOR;DIST=0.0;TMP=-127.0;TUR=abc;TDS=;"
            "DIST_RAW=0.0,20.0,0.0,0.0,0.0;CK=7B"
        )
        relay = frame(
            "RELAY;PUMP_ACTIVE=ON;PUMP_ERROR=IDLE;VENT_ACTIVE=IDLE;"
            "VENT_ERROR=ERROR;A0=900;A1=0;A2=1;A3=2"
        )
        sensor_fields = sensor[len("<SENSOR;") : -1]
        relay_fields = relay[len("<RELAY;") : -1]
        telemetry = (
            f"$TELEMETRY;{sensor_fields};{relay_fields};"
            "SENSOR_NODE=ONLINE;RELAY_NODE=ONLINE;SENSOR_AGE=0;RELAY_AGE=0\n"
        )
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            f"""
  clockUs = 5000000;
  Serial1.input = {cpp("##" + sensor + chr(13) + chr(10))};
  Serial3.input = {cpp(relay + chr(13) + chr(10))};
  loop();
  assert(Serial.output.find({cpp("$RAW_SENSOR;##" + sensor + chr(10))}) !=
         std::string::npos);
  assert(Serial.output.find({cpp("$RAW_RELAY;" + relay + chr(10))}) !=
         std::string::npos);
  assert(Serial.output.find({cpp("$RELAY;" + relay_fields + chr(10))}) !=
         std::string::npos);
  assert(Serial.output.find({cpp(telemetry)}) != std::string::npos);
  assert(Serial.output.find("UNKNOWN") == std::string::npos);
  assert(sensorUpdatedAt == 5000 && relayUpdatedAt == 5000);
  Serial.output.clear();
  Serial1.input = "<GARBAGE>\\r\\n<SENSOR;DIST=1.5>junk\\r\\n";
  Serial1.inputIndex = 0;
  clockUs = 7000000;
  readRs485(Serial1, sensorBuffer, sensorLength, true);
  assert(Serial.output ==
         "$RAW_SENSOR;<GARBAGE>\\n$RAW_SENSOR;<SENSOR;DIST=1.5>junk\\n");
  assert(strcmp(sensorFields, "DIST=1.5") == 0 && sensorUpdatedAt == 7000);
""",
        )

    def test_display_reports_frame_overflow_instead_of_dropping(self):
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            f"""
  Serial3.input = {cpp("X" * 300 + chr(10))};
  readRs485(Serial3, relayBuffer, relayLength, false);
  assert(Serial.output ==
         {cpp("$RAW_RELAY;OVERFLOW;" + "X" * 255 + chr(10) + "$RAW_RELAY;" + "X" * 45 + chr(10))});
  assert(relayLength == 0 && relayUpdatedAt == 0);
""",
        )

    def test_display_stale_status_keeps_last_values_and_reports_age(self):
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            r"""
  assert(SENSOR_STALE_MS == 660000UL && RELAY_STALE_MS == 660000UL);
  sendTelemetry(false);
  assert(Serial.output ==
         "$TELEMETRY;SENSOR_NODE=OFFLINE;RELAY_NODE=OFFLINE;"
         "SENSOR_AGE=NEVER;RELAY_AGE=NEVER\n");
  Serial.output.clear();
  strcpy(sensorFields, "DIST=12.5;TMP=-127.0");
  strcpy(relayFields, "PUMP_ACTIVE=ACTIVE");
  sensorUpdatedAt = 1;
  relayUpdatedAt = 1;
  clockUs = 700000000;
  relayChanged = false;
  loop();
  assert(!relayChanged);
  assert(Serial.output ==
         "$TELEMETRY;DIST=12.5;TMP=-127.0;PUMP_ACTIVE=ACTIVE;"
         "SENSOR_NODE=OFFLINE;RELAY_NODE=OFFLINE;"
         "SENSOR_AGE=699;RELAY_AGE=699\n");
  assert(strcmp(sensorFields, "DIST=12.5;TMP=-127.0") == 0);
  assert(strcmp(relayFields, "PUMP_ACTIVE=ACTIVE") == 0);
  Serial.output.clear();
  clockUs += 5000000;
  loop();
  assert(Serial.output.empty());
  sensorUpdatedAt = millis();
  relayUpdatedAt = millis();
  sendTelemetry(false);
  assert(Serial.output.find(";SENSOR_NODE=ONLINE;RELAY_NODE=ONLINE;") !=
         std::string::npos);
  Serial.output.clear();
  sendTelemetry(false);
  assert(Serial.output.empty());
  char status[] = "STATUS_REQUEST";
  handleUsbCommand(status);
  assert(Serial.output.find("$TELEMETRY;") == 0);
  assert(Serial.output.find("\n$RELAY;PUMP_ACTIVE=ACTIVE\n") != std::string::npos);
  assert(Serial.output.rfind("$ACK;COMMAND=STATUS_REQUEST\n") ==
         Serial.output.size() - strlen("$ACK;COMMAND=STATUS_REQUEST\n"));
""",
        )

    def test_display_reports_unknown_empty_and_truncated_usb_commands(self):
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            f"""
  char get[] = "GET";
  char set[] = "SET DIST_OFFSET 10";
  char empty[] = "NEX ";
  handleUsbCommand(get);
  handleUsbCommand(set);
  handleUsbCommand(empty);
  assert(Serial.output ==
         "$ERR;ERROR=UNKNOWN_COMMAND;COMMAND=GET\\n"
         "$ERR;ERROR=UNKNOWN_COMMAND;COMMAND=SET DIST_OFFSET 10\\n"
         "$ERR;COMMAND=NEX;ERROR=EMPTY\\n");
  assert(Serial2.output.empty());
  Serial.output.clear();
  Serial.input = {cpp("NEX " + "a" * 300 + chr(13) + chr(10) + "NEX page 0" + chr(10))};
  readUsb();
  assert(Serial.output == "$ERR;ERROR=USB_TRUNCATED;DROPPED=49\\n");
  assert(Serial2.output ==
         {cpp("a" * 251)} "\\xff\\xff\\xff" "page 0\\xff\\xff\\xff");
""",
        )

    def test_display_forwards_nextion_input_and_reports_overflow(self):
        self.run_sketch(
            FIRMWARE / "DisplayNode" / "DisplayNode.ino",
            f"""
  Serial2.input = std::string("BTN") + "\\xff\\xff\\xff" +
                  {cpp("A" * 130)} + "\\xff\\xff\\xff";
  forwardNextionInput();
  assert(Serial.output ==
         "$NEXTION;42 54 4E\\n"
         {cpp("$ERR;ERROR=NEXTION_OVERFLOW;DATA=" + " ".join(["41"] * 128) + chr(10))}
         "$NEXTION;41 41\\n");
""",
        )


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
