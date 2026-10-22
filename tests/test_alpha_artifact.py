"""Structural checks for manual HA installation bundle (without running HA)."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'custom_components' / 'carrier_smarthome'

class ArtifactTests(unittest.TestCase):
    def test_manifest(self):
        data = json.loads((PACKAGE/'manifest.json').read_text())
        self.assertEqual(data['domain'], 'carrier_smarthome')
        self.assertTrue(data['config_flow'])
        self.assertEqual(data['requirements'], [])
        self.assertEqual(data['iot_class'], 'cloud_polling')

    def test_strings_and_english_translation_valid(self):
        master = json.loads((PACKAGE/'strings.json').read_text())
        english = json.loads((PACKAGE/'translations/en.json').read_text())
        self.assertEqual(master, english)

    def test_required_modules(self):
        for part in ('__init__.py','api.py','config_flow.py','coordinator.py','const.py',
                     'climate.py','binary_sensor.py','sensor.py','entity.py','models.py'):
            self.assertTrue((PACKAGE / part).is_file(), part)

    def test_no_matter_or_pairing_dependencies(self):
        manifest = json.loads((PACKAGE/'manifest.json').read_text())
        self.assertNotIn('matter', manifest.get('dependencies', []))
        self.assertNotIn('matter', ' '.join(manifest['requirements']).lower())

    def test_operation_source_has_guarded_write(self):
        body = (PACKAGE/'climate.py').read_text()
        self.assertIn('self._require_control()', body)
        self.assertIn('CONF_ENABLE_CONTROL', body)

    def test_research_covers_setup(self):
        self.assertIn('Carrier SmartHome', (ROOT/'research/TEST_TODAY.md').read_text())

class SecurityFlowTests(unittest.TestCase):
    def test_ui_password_field_masked(self):
        code = (PACKAGE / 'config_flow.py').read_text()
        self.assertIn('TextSelectorType.PASSWORD', code)
        self.assertNotIn('vol.Required(CONF_PASSWORD): str', code)

    def test_windows_runner_uses_isolated_environment(self):
        code = (ROOT/'tools/Test-Cloud.ps1').read_text()
        self.assertIn('-m venv', code)
        self.assertIn('Smoke-TestSmartHomeCloud.py', code)
        self.assertNotIn('Write-Host $password', code)
