"""Enforce the cleanup contract; obsolete options must never hide climate."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "carrier_smarthome"


class Alpha10ContractTests(unittest.TestCase):
    def test_only_standard_climate_platforms_no_power_switch(self):
        src = (PKG / "const.py").read_text()
        self.assertIn('PLATFORMS = ["climate", "sensor", "binary_sensor"]', src)
        self.assertFalse((PKG / "switch.py").exists())
        self.assertFalse((PKG / "select.py").exists())

    def test_old_options_cannot_gate_controls(self):
        climate = (PKG / "climate.py").read_text()
        config = (PKG / "config_flow.py").read_text()
        self.assertIn('return _HVAC_MODES', climate)
        for obsolete in ("enable_control", "enable_fan_control", "enable_setpoint_control", "power_on_mode"):
            self.assertNotIn(obsolete, climate)
            self.assertNotIn(obsolete, config)
        self.assertNotIn("OptionsFlow", config)
        self.assertNotIn("_enabled(", (PKG / "control.py").read_text())

    def test_migration_removes_only_prior_owned_power_switch(self):
        integration = (PKG / "__init__.py").read_text()
        self.assertIn("async_migrate_entry", integration)
        self.assertIn("entry.version > 2", integration)
        self.assertIn('options={}', integration)
        self.assertIn('old.domain == "switch"', integration)
        self.assertIn('if old.platform != DOMAIN:', integration)
        self.assertIn('old.unique_id.endswith("_hvac_power")', integration)
        self.assertIn('_last_cloud_reported_stage_status', integration)
        self.assertIn('_last_cloud_reported_current_scene', integration)

    def test_cloud_write_protection_and_version(self):
        src = (PKG / "control.py").read_text()
        self.assertIn("async with coordinator.write_lock", src)
        self.assertIn("await coordinator.async_refresh()", src)
        self.assertIn("Carrier thermostat disconnected", src)
        self.assertIn("math.isfinite", src)
        self.assertNotIn("Enable experimental Carrier", src)
        self.assertEqual(json.loads((PKG / "manifest.json").read_text())["version"], "0.5.8")
        self.assertIn('carrier-smarthome-ha/0.5.8', (PKG / "api.py").read_text())


if __name__ == "__main__":
    unittest.main()
