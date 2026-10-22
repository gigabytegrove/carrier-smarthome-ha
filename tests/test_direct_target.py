"""v0.5.4 direct-IP targeting; offline/loopback only, no IoT network contacted."""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch, AsyncMock

TOOLS=pathlib.Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('carrier_direct_target_tests',TOOLS/'Probe-CarrierLocalDeep.py')
probe=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=probe
spec.loader.exec_module(probe)
ACCEPT='I-ACCEPT-IP-REASSIGNMENT-RISK'

class DirectTargetTests(unittest.TestCase):
    def test_requires_explicit_risk(self):
        for phrase in ('', 'YES', 'I-SEE-IT-CONNECTED'):
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                probe.verify_direct_target('172.20.42.19',phrase)

    def test_known_host_is_authorized_but_not_verified(self):
        host, identity=probe.verify_direct_target('172.20.42.19',ACCEPT)
        self.assertEqual(host,'172.20.42.19')
        self.assertFalse(identity['online_verified'])
        self.assertFalse(identity['independently_verified'])
        self.assertFalse(identity['active_ip_unique'])
        self.assertNotIn(host,str(identity))

    def test_block_other_ip_ranges(self):
        for host in ('0.0.0.0','127.0.0.1','192.168.0.1',
                     '10.1.1.10','172.20.0.0','172.20.255.255',
                     '172.21.0.51','2001:db8::1','not-a-host'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                probe.verify_direct_target(host,ACCEPT)

    def test_direct_plan_exits_before_network(self):
        with patch.object(sys,'argv',['probe','--direct-ip','172.20.42.19',
                   '--accept-direct-risk',ACCEPT,'--plan']), patch.object(probe,'run',new_callable=AsyncMock) as run:
            self.assertEqual(probe.main(),0)
            run.assert_not_called()

    def test_missing_ack_plan_exits_before_network(self):
        with patch.object(sys,'argv',['probe','--direct-ip','172.20.42.19','--plan']), \
             patch.object(probe,'run',new_callable=AsyncMock) as run:
            self.assertEqual(probe.main(),2)
            run.assert_not_called()

    def test_no_manual_args_accepted_for_direct(self):
        with patch.object(sys,'argv',['probe','--direct-ip','172.20.42.19',
                   '--accept-direct-risk',ACCEPT,'--suffix','BEEF','--plan']), \
             patch.object(probe,'run',new_callable=AsyncMock) as run:
            self.assertEqual(probe.main(),2)
            run.assert_not_called()

    def test_manual_ui_still_available(self):
        host,identity=probe.verify_live_ui_selection('172.20.42.19',
            'AA:BB:CC:DD:BE:EF','BEEF','I-SEE-IT-CONNECTED')
        self.assertEqual(host,'172.20.42.19')
        self.assertFalse(identity['independently_verified'])

    def test_power_shell_direct_ip_interface_present(self):
        wrapper=(TOOLS/'Probe-CarrierLocalDeep.ps1').read_text(encoding='utf-8')
        self.assertIn('[string]$DirectIP',wrapper)
        self.assertIn('[switch]$AcknowledgeIpRisk',wrapper)
        self.assertIn("'--direct-ip'",wrapper)
        self.assertNotIn('172.20.42.19',wrapper)

    def test_release_script_has_safe_version_and_commit_checks(self):
        content=(TOOLS/'Publish-CarrierRelease.ps1').read_text(encoding='utf-8')
        for phrase in ('gh release list','gh release create','gh release view',
                       'ExpectedCommit','manifest.version','Main changed'):
            self.assertIn(phrase,content)

    def test_full_scan_only_one_host(self):
        self.assertEqual(len(probe.scan_ports(True)),65535)
        self.assertEqual(probe.scan_ports(True)[-1],65535)
        self.assertLess(len(probe.scan_ports(False)),1200)
