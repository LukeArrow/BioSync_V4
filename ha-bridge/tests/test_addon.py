import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "ha-addon" / "biosync_bridge"


class AddonTests(unittest.TestCase):
    def test_build_context_contains_unchanged_bridge_sources(self):
        source = ROOT / "ha-bridge"
        copied = ADDON / "rootfs" / "opt" / "biosync"
        originals = {path.name for path in (source / "biosync_bridge").glob("*.py")}
        copies = {path.name for path in (copied / "biosync_bridge").glob("*.py")}
        self.assertEqual(originals, copies)
        for name in originals:
            with self.subTest(file=name):
                self.assertEqual(
                    (source / "biosync_bridge" / name).read_bytes(),
                    (copied / "biosync_bridge" / name).read_bytes(),
                )
        self.assertEqual(
            (source / "requirements.txt").read_bytes(),
            (copied / "requirements.txt").read_bytes(),
        )

    def test_start_script_is_executable_and_valid_bash(self):
        script = ADDON / "run.sh"
        self.assertTrue(script.stat().st_mode & 0o111)
        self.assertEqual(
            script.read_text().splitlines()[0], "#!/usr/bin/with-contenv bashio"
        )
        subprocess.run(["bash", "-n", str(script)], check=True)

    def run_start_script(self, options, service_available=True):
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("BIOSYNC_", "OPTION_", "SERVICE_"))
        }
        environment.update({
            "OPTION_serial_device": "/dev/serial/by-id/mega",
            "OPTION_baud": "115200",
            "OPTION_mqtt_port": "1883",
            "OPTION_mqtt_prefix": "biosync_test",
            "OPTION_log_level": "DEBUG",
            "SERVICE_AVAILABLE": "1" if service_available else "0",
            "SERVICE_host": "core-mosquitto",
            "SERVICE_port": "1884",
            "SERVICE_username": "service-user",
            "SERVICE_password": "test-only-service-value",
        })
        environment.update({f"OPTION_{key}": value for key, value in options.items()})
        mocks = """
bashio::config() {
    local key="OPTION_${1}"
    printf '%s' "${!key-null}"
}
bashio::config.has_value() {
    local key="OPTION_${1}"
    [[ -n "${!key-}" && "${!key-}" != "null" ]]
}
bashio::services.available() {
    [[ "$1" == mqtt && "$SERVICE_AVAILABLE" == 1 ]]
}
bashio::services() {
    [[ "$1" == mqtt ]] || return 1
    local key="SERVICE_${2}"
    printf '%s' "${!key}"
    printf 'service-read\\n' >&2
}
bashio::log.fatal() {
    printf '%s\\n' "$*" >&2
}
source "$1"
"""
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "python3"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "print(json.dumps({'args': sys.argv[1:], 'env': "
                "{k: v for k, v in os.environ.items() if k.startswith('BIOSYNC_')}}))\n"
            )
            executable.chmod(0o755)
            environment["PATH"] = directory + os.pathsep + environment["PATH"]
            return subprocess.run(
                ["bash", "-c", mocks, "addon-test", str(ADDON / "run.sh")],
                env=environment, capture_output=True, text=True,
            )

    def assert_bridge_environment(self, result, host, port, user, password):
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["args"], ["-m", "biosync_bridge.main"])
        self.assertEqual(output["env"], {
            "BIOSYNC_SERIAL": "/dev/serial/by-id/mega",
            "BIOSYNC_BAUD": "115200",
            "BIOSYNC_MQTT_HOST": host,
            "BIOSYNC_MQTT_PORT": port,
            "BIOSYNC_MQTT_USER": user,
            "BIOSYNC_MQTT_PASSWORD": password,
            "BIOSYNC_MQTT_PREFIX": "biosync_test",
            "BIOSYNC_LOG_LEVEL": "DEBUG",
        })

    def test_manual_mqtt_options_are_exported_without_service_lookup(self):
        password = "test-only spaces $literal; 'quoted'"
        result = self.run_start_script({
            "mqtt_host": "broker.example",
            "mqtt_port": "2883",
            "mqtt_user": "manual-user",
            "mqtt_password": password,
        }, service_available=False)
        self.assert_bridge_environment(
            result, "broker.example", "2883", "manual-user", password
        )
        self.assertEqual(result.stderr, "")

    def test_empty_or_omitted_host_uses_all_mqtt_service_values(self):
        for options in ({}, {
            "mqtt_host": "", "mqtt_port": "2883",
            "mqtt_user": "ignored", "mqtt_password": "test-only-ignored",
        }):
            with self.subTest(options=options):
                result = self.run_start_script(options)
                self.assert_bridge_environment(
                    result, "core-mosquitto", "1884",
                    "service-user", "test-only-service-value",
                )
                self.assertNotIn("test-only-service-value", result.stderr)

    def test_manual_host_allows_omitted_credentials(self):
        result = self.run_start_script({"mqtt_host": "broker.example"})
        self.assert_bridge_environment(result, "broker.example", "1883", "", "")
        self.assertEqual(result.stderr, "")

    def test_missing_service_without_manual_host_fails_before_bridge_start(self):
        result = self.run_start_script({}, service_available=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Kein MQTT-Service", result.stderr)


if __name__ == "__main__":
    unittest.main()
