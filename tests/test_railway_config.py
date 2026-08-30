import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAILWAY_CONFIG = ROOT / "railway.json"
PYTHON_VERSION_FILE = ROOT / ".python-version"
ENTRYPOINT = ROOT / "app.py"


class RailwayConfigTests(unittest.TestCase):
    def test_railway_json_is_valid_and_defines_expected_start_command(self) -> None:
        config = json.loads(RAILWAY_CONFIG.read_text(encoding="utf-8"))
        start_command = config["deploy"]["startCommand"]

        self.assertTrue(start_command.startswith("streamlit run app.py "))
        self.assertIn("--server.address=0.0.0.0", start_command)
        self.assertIn("--server.port=$PORT", start_command)
        self.assertIn("--server.headless=true", start_command)

    def test_railway_json_does_not_hardcode_a_port(self) -> None:
        config = json.loads(RAILWAY_CONFIG.read_text(encoding="utf-8"))
        start_command = config["deploy"]["startCommand"]

        self.assertNotRegex(start_command, r"--server\.port=\d")

    def test_streamlit_entrypoint_referenced_by_railway_exists(self) -> None:
        self.assertTrue(ENTRYPOINT.is_file())

    def test_python_version_is_pinned_for_railway(self) -> None:
        pinned_version = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
        self.assertRegex(pinned_version, r"^3\.\d+$")


if __name__ == "__main__":
    unittest.main()
