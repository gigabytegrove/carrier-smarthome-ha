"""Regression tests for analysis of real scan JSON without network activity."""
import importlib.util
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

PATH = pathlib.Path(__file__).resolve().parents[1] / 'tools' / 'triage_iot.py'
spec = importlib.util.spec_from_file_location('iot_triage', PATH)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


def fixture():
    return {
        'target': '172.20.0.0/16',
        'addresses_pinged': 65534,
        'icmp_responsive': ['172.20.0.5', '172.20.0.6'],
        'candidate_addresses': ['172.20.0.5', '172.20.0.6', '172.20.0.7'],
        'neighbor_records': [{'IPAddress': '172.20.0.7', 'LinkLayerAddress': 'AA-BB-CC-11-22-33', 'State': 'Reachable'}],
        'tcp_open': [{'ip': '172.20.0.5', 'port': 80}, {'ip': '172.20.0.5', 'port': 443}, {'ip': '172.20.0.6', 'port': 8883}],
        'route': {'destination_prefix': '', 'next_hop': '', 'interface_alias': 'Ethernet 2'},
    }


class TriageTests(unittest.TestCase):
    def test_distinct_devices_not_port_count(self):
        report = triage.analyze(fixture())
        self.assertEqual(report['tcp_port_results'], 3)
        self.assertEqual(report['tcp_devices'], 2)
        self.assertEqual(report['candidate_count'], 3)

    def test_icmp_and_neighbor_separate(self):
        report = triage.analyze(fixture())
        self.assertEqual(report['icmp_count'], 2)
        self.assertEqual(report['neighbor_count'], 1)

    def test_portless_candidates_retained(self):
        report = triage.analyze(fixture())
        self.assertEqual(len(report['devices']), 3)
        self.assertEqual(report['devices'][-1]['ip'], '172.20.0.7')

    def test_results_sorted_for_review(self):
        report = triage.analyze(fixture())
        self.assertEqual(report['devices'][0]['ip'], '172.20.0.5')
        self.assertEqual(report['devices'][0]['ports'], [80, 443])

    def test_out_of_scope_rejected(self):
        test = fixture()
        test['target'] = '192.168.0.0/24'
        with self.assertRaisesRegex(ValueError, 'outside'):
            triage.analyze(test)

    def test_injected_hosts_are_discarded(self):
        test = fixture()
        test['candidate_addresses'].extend(['10.0.0.1', '8.8.8.8', 'not-an-ip'])
        test['tcp_open'].append({'ip': '192.168.0.1', 'port': 443})
        self.assertEqual(triage.analyze(test)['candidate_count'], 3)

    def test_tcp_only_deep_scan_host_is_preserved(self):
        test = fixture()
        test['tcp_open'].append({'ip': '172.20.45.10', 'port': 443})
        result = triage.analyze(test)
        self.assertEqual(result['candidate_count'], 4)
        self.assertEqual(result['by_subnet']['172.20.45.0/24'], 1)

    def test_deduplicate_duplicate_ports(self):
        test = fixture()
        test['tcp_open'].append({'ip': '172.20.0.5', 'port': 80})
        self.assertEqual(triage.analyze(test)['tcp_port_results'], 3)

    def test_no_false_model_claim(self):
        result = triage.format_report(triage.analyze(fixture()))
        self.assertIn('NOT confirmed Carrier', result)
        self.assertIn('reporting defect', result)

    def test_no_network_dependency_cli(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            report = pathlib.Path(d) / 'iot-private.json'
            report.write_text(json.dumps(fixture()), encoding='utf-8')
            output = StringIO()
            with redirect_stdout(output):
                rc = triage.main([str(report)])
            self.assertEqual(rc, 0)
            self.assertIn('172.20.0.5', output.getvalue())

    def test_no_report_is_error(self):
        self.assertEqual(triage.main(['/nonexistent/scan-zzzz.json']), 2)

    def test_malformed_ports_ignored(self):
        test = fixture()
        test['tcp_open'].extend([{'ip':'172.20.0.5','port':'bad'}, {'ip':'172.20.0.6','port':0}])
        self.assertEqual(triage.analyze(test)['tcp_port_results'], 3)


if __name__ == '__main__':
    unittest.main()
