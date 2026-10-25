"""Documentation contract: keep cloud setup independent of optional Matter pairing."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "carrier_smarthome"

class MatterPreparationDocsTest(unittest.TestCase):
    def test_cloud_sign_in_does_not_require_matter_code(self):
        flow = (COMPONENT / "config_flow.py").read_text()
        self.assertNotIn('CONF_MATTER_CODE', flow)
        self.assertIn("CONF_USERNAME", flow)
        self.assertIn("CONF_PASSWORD", flow)

    def test_localized_onboarding_texts_match(self):
        strings = json.loads((COMPONENT / "strings.json").read_text())
        en = json.loads((COMPONENT / "translations" / "en.json").read_text())
        self.assertEqual(strings, en)
        desc = strings["config"]["step"]["user"]["description"]
        for phrase in ("cloud", "Smart Home", "Mobile Onboarding", "does NOT commission", "manual"):
            self.assertIn(phrase, desc)

    def test_beginner_preparation_is_documented(self):
        readme = (ROOT / "README.md").read_text()
        doc = (ROOT / "docs" / "MATTER_PAIRING_PREP.md").read_text()
        for phrase in ("before", "Smart Home", "Mobile Onboarding", "11-digit", "powered", "commissioning window"):
            self.assertIn(phrase, doc)
        self.assertIn("not Matter", readme)
        self.assertIn("MATTER_PAIRING_PREP.md", readme)
        self.assertIn("Matter", doc)

if __name__ == "__main__":
    unittest.main()
