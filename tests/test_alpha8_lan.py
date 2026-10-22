"""Offline regression tests for current-lease-only proprietary LAN discovery."""
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('alpha8_lan',Path(__file__).resolve().parents[1]/'tools'/'Probe-VerifiedCarrierLAN.py')
local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)

class CurrentLeaseTests(unittest.TestCase):
    def export(self, minutes_ago):
        t=(datetime.now()-timedelta(minutes=minutes_ago)).strftime('%Y-%m-%d-%H-%M')
        self.tmp=tempfile.TemporaryDirectory()
        path=Path(self.tmp.name)/'Client.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr(f'OnlineClient_{t}.csv','MAC ADDRESS,IP ADDRESS,NAME,STATUS\n')
        self.addCleanup(self.tmp.cleanup)
        return path
    def test_refuse_old_client_export(self):
        with self.assertRaisesRegex(ValueError,'too old'):
            local.assert_export_fresh(self.export(90))
    def test_accept_current_export(self):
        local.assert_export_fresh(self.export(2))
    def test_reject_missing_online_snapshot(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        f=Path(self.tmp.name)/'Client.zip'
        with zipfile.ZipFile(f,'w') as z: z.writestr('OfflineClient_2026-10-22-08-14.csv','a,b')
        with self.assertRaisesRegex(ValueError,'cannot be established'):
            local.assert_export_fresh(f)
    def test_probe_target_keeps_private_vlan_restriction(self):
        with self.assertRaises(ValueError):
            local.connected_target({'status':'CONNECTED','current_ip':'8.8.8.8'})
    def test_no_http_unless_optin(self):
        text=(Path(__file__).resolve().parents[1]/'tools'/'Probe-VerifiedCarrierLAN.ps1').read_text()
        self.assertIn('[switch]$HttpFingerprint',text)
        self.assertIn('MaxAgeMinutes',text)
        self.assertIn('--suffix',text)
        self.assertNotIn("$Suffix = '144B'",text)
if __name__=='__main__':unittest.main()
