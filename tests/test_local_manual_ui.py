"""v0.5.3+ exact live Omada client alternative, without stale IP fallback."""
from pathlib import Path
import importlib.util
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec = importlib.util.spec_from_file_location('local_manual_probe',ROOT/'tools/Probe-CarrierLocalDeep.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)

class ManualSelectionTest(unittest.TestCase):
    GOOD_IP='172.20.40.25'
    GOOD_MAC='AA:BB:CC:DD:EE:FF'
    def test_owner_confirmation(self):
        ip, record=local.verify_live_ui_selection(self.GOOD_IP,self.GOOD_MAC,'EEFF','I-SEE-IT-CONNECTED')
        self.assertEqual(ip,self.GOOD_IP)
        self.assertFalse(record['independently_verified'])
        self.assertFalse(record['online_verified'])
        self.assertTrue(record['owner_reports_current_connected'])
    def test_no_confirmation(self):
        with self.assertRaises(ValueError):
            local.verify_live_ui_selection(self.GOOD_IP,self.GOOD_MAC,'EEFF','')
    def test_bad_suffix(self):
        with self.assertRaises(ValueError):
            local.verify_live_ui_selection(self.GOOD_IP,self.GOOD_MAC,'FFFF','I-SEE-IT-CONNECTED')
    def test_outside_network(self):
        with self.assertRaises(ValueError):
            local.verify_live_ui_selection('192.168.60.25',self.GOOD_MAC,'EEFF','I-SEE-IT-CONNECTED')
    def test_malformed_mac(self):
        with self.assertRaises(ValueError):
            local.verify_live_ui_selection(self.GOOD_IP,'AA:BB','EEFF','I-SEE-IT-CONNECTED')
    def test_private_identity_not_in_output(self):
        ip, record=local.verify_live_ui_selection(self.GOOD_IP,self.GOOD_MAC,'EEFF','I-SEE-IT-CONNECTED')
        self.assertNotIn(ip,str(record))
        self.assertNotIn(self.GOOD_MAC,str(record))

if __name__=='__main__': unittest.main()
