"""Privacy and shape regression checks for v0.5.1 read-only mode observer."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tools" / "Read-CarrierMode.py"

class ModeObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("carrier_mode_observer", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_format_only_known_fields(self):
        sample = {"connection": "online", "list": dict.fromkeys(self.module.FIELDS, "off"),
                  "detail": dict.fromkeys(self.module.FIELDS, "off")}
        string = self.module.format_sample(1, sample)
        self.assertIn("mode=off", string)
        self.assertNotIn("serial", string)
        self.assertNotIn("mac", string.lower())
        self.assertNotIn("DISAGREEMENT", string)

    def test_source_disagreement_visible(self):
        left = dict.fromkeys(self.module.FIELDS, "off")
        right = dict(left)
        right["mode"] = "cool"
        string = self.module.format_sample(1, {"connection": "online", "list": left, "detail": right})
        self.assertIn("DISAGREEMENT", string)

    def test_missing_detail_is_explicit(self):
        left = dict.fromkeys(self.module.FIELDS, "off")
        string = self.module.format_sample(1, {"connection": "offline", "list": left, "detail": None})
        self.assertIn("detail unavailable", string)

    def test_no_write_api_called(self):
        raw = path.read_text()
        self.assertNotIn("client.async_update_zone(", raw)
        self.assertNotIn("Mutation", raw)
