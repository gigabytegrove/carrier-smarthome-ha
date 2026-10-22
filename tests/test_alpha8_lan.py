"""Compatibility and safety regressions for the merged local discovery engine."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LegacyWrapperTests(unittest.TestCase):
    def test_old_powershell_wrapper_uses_only_new_probe(self):
        text = (ROOT/'tools/Probe-VerifiedCarrierLAN.ps1').read_text()
        self.assertIn('Probe-CarrierLocalDeep.ps1', text)
        self.assertNotIn('144B', text)
        self.assertNotIn('172.20.0.51', text)
        self.assertNotIn('HttpFingerprint =', text)

    def test_old_python_wrapper_uses_only_new_probe(self):
        text = (ROOT/'tools/Probe-VerifiedCarrierLAN.py').read_text()
        self.assertIn('Probe-CarrierLocalDeep.py', text)
        self.assertNotIn('asyncio.open_connection(', text)
        self.assertNotIn('172.20.0.51', text)

    def test_deep_script_scans_only_after_identity_verification(self):
        text = (ROOT/'tools/Probe-CarrierLocalDeep.py').read_text()
        self.assertLess(text.index('verify_fresh_export(args.omada'), text.index('asyncio.run(run(ip, args))'))
        self.assertLess(text.index('verify_identity(read_archive(args.omada)'), text.index('asyncio.run(run(ip, args))'))
        self.assertNotIn('172.20.0.51', text)

if __name__=='__main__':
    unittest.main()
