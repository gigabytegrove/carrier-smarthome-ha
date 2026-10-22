"""Offline checks for HACS distribution metadata and publish safety."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hacs_validation', ROOT/'tools'/'validate_hacs.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class HacsDistributionTests(unittest.TestCase):
    def test_repo_passes_hacs_structure_checks(self):
        self.assertEqual(validator.validate(ROOT), [])

    def test_hacs_instructions_use_custom_repository_not_default_store(self):
        docs = (ROOT/'docs'/'HACS_INSTALLATION.md').read_text(encoding='utf-8')
        self.assertIn('Custom repositories', docs)
        self.assertIn('Integration', docs)
        self.assertIn('github.com/gigabytegrove/carrier-smarthome-ha', docs)
        self.assertIn('experimental', docs.lower())

    def test_published_readme_is_product_focused_and_has_support_badges(self):
        readme = (ROOT/'README.md').read_text(encoding='utf-8')
        self.assertTrue(readme.lstrip().startswith('<div align="center">'))
        self.assertIn('Carrier SmartHome', readme)
        self.assertIn('TSTATCCEWF-01', readme)
        self.assertIn('TSTATCCEEF-01', readme)
        self.assertIn('only thermostat model', readme)
        self.assertIn('my.home-assistant.io/redirect/hacs_repository/', readme)
        self.assertIn('buymeacoffee.com/gigabytegrove', readme)
        self.assertIn('paypal.me/gigabytegrove', readme)
        self.assertIn('No Matter', readme)
        self.assertIn('local-only HVAC control has not yet been established', readme)
        self.assertTrue((ROOT/'.github'/'FUNDING.yml').is_file())
        self.assertTrue((ROOT/'custom_components'/'carrier_smarthome'/'brand'/'icon.png').is_file())

    def test_no_real_thermostat_mac_in_current_test_source(self):
        import re
        files = (ROOT/'tests'/'test_omada_identity.py').read_text(encoding='utf-8')
        self.assertNotRegex(files, r'(?i)40[-:]b3[-:]1e[-:]64')
        self.assertNotIn('Smart Thermostat-144B', files)

    def test_no_hardcoded_thermostat_suffix_in_local_scripts(self):
        for name in ('Review-OmadaExport.ps1', 'Probe-VerifiedCarrierLAN.py'):
            self.assertNotIn('144B', (ROOT/'tools'/name).read_text(encoding='utf-8'))

    def test_manifest_rejects_missing_config_flow(self):
        from tempfile import TemporaryDirectory
        import json
        import shutil
        with TemporaryDirectory() as tmp:
            sample = Path(tmp)
            shutil.copytree(ROOT/'custom_components', sample/'custom_components')
            shutil.copy2(ROOT/'hacs.json', sample/'hacs.json')
            shutil.copy2(ROOT/'README.md', sample/'README.md')
            path = sample/'custom_components'/'carrier_smarthome'/'manifest.json'
            m = json.loads(path.read_text(encoding='utf-8'))
            m.pop('config_flow')
            path.write_text(json.dumps(m), encoding='utf-8')
            self.assertTrue(any('config_flow' in v for v in validator.validate(sample)))


if __name__ == '__main__':
    unittest.main()
