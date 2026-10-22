"""v0.5.0 single-target LAN scan contract; no user's device contacted."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('carrier_local_deep_test', ROOT / 'tools/Probe-CarrierLocalDeep.py')
local = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = local
spec.loader.exec_module(local)


class IdentityAndFreshness(unittest.TestCase):
    def setUp(self):
        self.online = {'MAC ADDRESS': 'A1:B2:C3:D4:BE:EF', 'NAME': 'Smart Thermostat-BEEF',
                       'STATUS': 'CONNECTED', 'IP ADDRESS': '172.20.0.52',
                       'VLAN': '30', 'SSID': 'Synthetic', 'AP/PORT': 'Test'}
        self.rows = {'online': [self.online], 'offline': [], 'history': []}

    def test_connected_unique_identity(self):
        ip, proof = local.verify_identity(self.rows, 'BEEF')
        self.assertEqual(ip, '172.20.0.52')
        self.assertTrue(proof['active_ip_unique'])
        self.assertNotIn('172.20.', str(proof))

    def test_missing_or_wrong_suffix_refused(self):
        for x in ('', 'AB', 'BB22', 'nothex'):
            with self.subTest(suffix=x), self.assertRaises(ValueError):
                local.verify_identity(self.rows, x)

    def test_offline_refused(self):
        self.rows['online'] = []
        self.rows['offline'] = [dict(self.online, STATUS='DISCONNECTED')]
        with self.assertRaisesRegex(ValueError, 'not CONNECTED'):
            local.verify_identity(self.rows, 'BEEF')

    def test_other_active_device_same_ip_refused(self):
        self.rows['online'].append(dict(self.online, **{'MAC ADDRESS': 'A1:B2:C3:D4:BE:EE', 'NAME': 'Other'}))
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            local.verify_identity(self.rows, 'BEEF')

    def test_historical_reuse_is_not_active_conflict(self):
        self.rows['offline'] = [dict(self.online, **{'MAC ADDRESS': 'A1:B2:C3:D4:BE:EE', 'STATUS': 'DISCONNECTED'})]
        self.assertEqual(local.verify_identity(self.rows, 'BEEF')[0], '172.20.0.52')

    def test_outside_vlan_refused(self):
        for ip in ('192.168.0.1', '172.20.255.255', '172.20.0.0', '127.0.0.1', '1.1.1.1'):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                local.verify_identity({'online': [dict(self.online, **{'IP ADDRESS': ip})],
                                       'offline': [], 'history': []}, 'BEEF')

    def test_embedded_timestamp_and_mtime_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            for age, permitted in ((0, True), (20, True), (90, False), (-15, False)):
                with self.subTest(age=age):
                    stamp = (now - timedelta(minutes=age)).strftime('%Y-%m-%d-%H-%M')
                    path = Path(tmp) / f'Client_{stamp}.zip'
                    with zipfile.ZipFile(path, 'w') as z:
                        z.writestr(f'OnlineClient_{stamp}.csv', 'empty,fixture\n')
                    os.utime(path, (now.timestamp(), now.timestamp()))
                    if permitted:
                        self.assertTrue(local.verify_fresh_export(path, 30, now=now))
                    else:
                        with self.assertRaises(ValueError):
                            local.verify_fresh_export(path, 30, now=now)

    def test_old_zip_mtime_also_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            stamp = now.strftime('%Y-%m-%d-%H-%M')
            path = Path(tmp) / 'Client_fixture.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('OnlineClient_'+stamp+'.csv', '')
            then = (now - timedelta(hours=4)).timestamp()
            os.utime(path, (then, then))
            with self.assertRaisesRegex(ValueError, 'filesystem'):
                local.verify_fresh_export(path, 30, now=now)

    def test_utc_offset_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            stamp = (now - timedelta(hours=4)).strftime('%Y-%m-%d-%H-%M')
            path = Path(tmp) / 'Client_fixture.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('OnlineClient_'+stamp+'.csv', '')
            os.utime(path, (now.timestamp(), now.timestamp()))
            proof = local.verify_fresh_export(path, 30, now=now, clock_offset_hours=-4)
            self.assertEqual(proof['controller_clock'], 'explicit-controller-offset')


class ProtocolPayloads(unittest.TestCase):
    def test_only_expected_udp_queries(self):
        found = local.udp_discoveries()
        self.assertEqual(set(found), {'mdns_unicast','ssdp_unicast','coap_well_known_core'})
        self.assertEqual(found['coap_well_known_core'][1][1], 1)  # GET
        self.assertIn(b'.well-known', found['coap_well_known_core'][1])
        self.assertIn(b'_dns-sd', found['mdns_unicast'][1])
        self.assertIn(b'M-SEARCH', found['ssdp_unicast'][1])

    def test_mqtt_is_anonymous_connect_only(self):
        data = local.mqtt_connect()
        self.assertTrue(data.startswith(b'\x10'))
        self.assertIn(b'MQTT\x04\x02\x00\x00', data)
        self.assertNotIn(b'\x30\x00', data)  # No empty PUBLISH frame

    def test_full_tcp_range(self):
        allports = local.scan_ports(True)
        self.assertEqual(len(allports), 65535)
        self.assertEqual(allports[0], 1)
        self.assertEqual(allports[-1], 65535)
        self.assertEqual(len(allports), len(set(allports)))

    def test_quick_scope(self):
        quick = local.scan_ports(False)
        self.assertTrue(all(x in quick for x in (80, 443, 1883, 8883, 8443, 5683)))
        self.assertLess(len(quick), 1200)

    def test_inconclusive_no_ports(self):
        lines = local.conclusions({'tcp': {'open_ports': []}, 'tls': {}, 'http': {}, 'mqtt': {}, 'udp': {}})
        self.assertTrue(any('does NOT exclude' in x for x in lines))


class IsolatedTCPNetworkTest(unittest.IsolatedAsyncioTestCase):
    async def test_loopback_listener_detected(self):
        server = await asyncio.start_server(lambda rd, wr: wr.close(), '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            result = await local.tcp_sweep('127.0.0.1', [port], 2, .6, show_progress=False)
            self.assertEqual(result['open_ports'], [port])
            self.assertEqual(result['count'], 1)
        finally:
            server.close()
            await server.wait_closed()

    async def test_closed_loopback_port_not_reported_open(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        outcome = await local.check_tcp('127.0.0.1', port, .5)
        self.assertIn(outcome, ('closed', 'filtered_or_no_reply'))

    async def test_safe_mqtt_connack_handshake(self):
        seen = []
        async def broker(rd, wr):
            try:
                packet = await asyncio.wait_for(rd.read(256), .5)
                seen.append(packet)
                wr.write(b'\x20\x02\x00\x00')
                await wr.drain()
                await asyncio.wait_for(rd.read(2), 1)
            finally:
                wr.close()
        server = await asyncio.start_server(broker, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            result = await local.mqtt_handshake('127.0.0.1', port)
            self.assertTrue(result['mqtt_connack'])
            self.assertEqual(result['return_code'], 0)
            self.assertEqual(seen[0][0], 0x10)
        finally:
            server.close()
            await server.wait_closed()


if __name__ == '__main__':
    unittest.main()
