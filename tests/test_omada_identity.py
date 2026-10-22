"""Contract tests for private Omada ZIP correlation. No network access."""
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import omada_identity as omada


def sample():
    return {
        'online': [
            {'NAME': 'Kasa', 'MAC ADDRESS': '00-11-22-33-44-55', 'IP ADDRESS': '172.20.0.31', 'STATUS': 'CONNECTED', 'VLAN': '30'},
        ],
        'offline': [
            {'NAME': 'Smart Thermostat-702B', 'MAC ADDRESS': '40-b3-1e-64-70-2b', 'IP ADDRESS': '-', 'VLAN': '30', 'STATUS': 'DISCONNECTED'},
            {'NAME': 'Smart Thermostat-144B', 'MAC ADDRESS': '40-b3-1e-64-14-4b', 'IP ADDRESS': '172.20.0.51', 'VLAN': '30', 'SSID': 'GG Smart Home', 'AP/PORT': 'Hallway AP', 'STATUS': 'DISCONNECTED'},
            {'NAME': 'Other', 'MAC ADDRESS': 'c0-f8-53-c4-e8-f3', 'IP ADDRESS': '172.20.0.51', 'STATUS': 'DISCONNECTED'},
        ],
        'history': [
            {'USERNAME': 'Smart Thermostat-144B', 'MAC ADDRESS': '40-b3-1e-64-14-4b', 'IP ADDRESS': '172.20.0.51', 'LAST ONLINE TIME': '2026-10-22 08:08:40 AM'},
            {'USERNAME': 'Smart Thermostat-144B', 'MAC ADDRESS': '40-b3-1e-64-14-4b', 'IP ADDRESS': '172.20.0.38', 'LAST ONLINE TIME': '2026-08-22 07:22:13 AM'},
        ],
    }


class OmadaTests(unittest.TestCase):
    def test_canonical_mac(self):
        self.assertEqual(omada.mac('40-b3-1e-64-14-4b'), '40B31E64144B')
        self.assertEqual(omada.mac('bad'), '')
        self.assertEqual(omada.mac('00-00-00-00-00-00'), '')

    def test_multiple_thermostats_need_selection(self):
        with self.assertRaisesRegex(ValueError, 'Multiple thermostat'):
            omada.identify(sample())

    def test_exact_suffix_selects_unit(self):
        result = omada.identify(sample(), suffix='144B')
        self.assertEqual(result['name'], 'Smart Thermostat-144B')
        self.assertEqual(result['status'], 'NOT CONNECTED IN EXPORT')
        self.assertEqual(result['current_ip'], '')
        self.assertEqual(result['last_ip'], '172.20.0.51')
        self.assertEqual(result['same_ip_other_macs'], 1)
        self.assertEqual(result['history_ips'], ['172.20.0.51', '172.20.0.38'])

    def test_connected_has_current_ip(self):
        rows = sample()
        rows['online'].append(dict(rows['offline'][1], STATUS='CONNECTED', **{'IP ADDRESS': '172.20.0.52'}))
        result = omada.identify(rows, suffix='144B')
        self.assertEqual(result['current_ip'], '172.20.0.52')
        self.assertEqual(result['status'], 'CONNECTED')

    def test_wrong_suffix_refuses_to_guess(self):
        with self.assertRaisesRegex(ValueError, 'No named thermostat'):
            omada.identify(sample(), suffix='CCCC')

    def test_invalid_suffix(self):
        with self.assertRaisesRegex(ValueError, 'suffix'):
            omada.identify(sample(), suffix='not-a-mac')

    def test_history_does_not_make_device_online(self):
        result = omada.identify(sample(), suffix='144B')
        output = omada.render(result, {'icmp_responsive': ['172.20.0.51'], 'tcp_open': []})
        self.assertIn('current IP confirmed by ONLINE export: NO'.lower(), output.lower())
        self.assertIn('answered ICMP: yes', output)
        self.assertIn('PREVIOUS SAVED SCAN', output)

    def test_zip_reads_export_names(self):
        with tempfile.TemporaryDirectory() as directory:
            zpath = Path(directory) / 'Client_export.zip'
            with zipfile.ZipFile(zpath, 'w') as z:
                for kind, prefix in omada.ZIP_MEMBERS.items():
                    records = sample()[kind]
                    memory = io.StringIO()
                    writer = csv.DictWriter(memory, fieldnames=sorted({k for r in records for k in r}))
                    writer.writeheader()
                    writer.writerows(records)
                    z.writestr(prefix + '2026.csv', memory.getvalue())
            loaded = omada.read_archive(zpath)
            self.assertEqual(omada.identify(loaded, suffix='144B')['last_ip'], '172.20.0.51')

    def test_zip_missing_csv_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            zpath = Path(directory) / 'Client_export.zip'
            with zipfile.ZipFile(zpath, 'w') as z:
                z.writestr('OnlineClient_test.csv', 'MAC ADDRESS,IP ADDRESS,NAME\n')
            with self.assertRaisesRegex(ValueError, 'Expected exactly one'):
                omada.read_archive(zpath)

    def test_zero_mac_ignored(self):
        rows = sample()
        rows['online'].append({'NAME':'Smart Thermostat-FFFF', 'MAC ADDRESS':'00-00-00-00-00-00', 'IP ADDRESS':'172.20.0.60','STATUS':'CONNECTED'})
        self.assertEqual(omada.identify(rows,suffix='144B')['status'],'NOT CONNECTED IN EXPORT')


if __name__ == '__main__':
    unittest.main()
