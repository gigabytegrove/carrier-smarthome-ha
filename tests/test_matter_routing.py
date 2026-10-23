"""Offline policy tests: never cause duplicate Matter/Carrier writes."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"
PKG = "carrier_matter_router_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(BASE)]
sys.modules[PKG] = package
for name in ("matter_protocol", "matter_routing"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", BASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
p = sys.modules[PKG + ".matter_protocol"]
r = sys.modules[PKG + ".matter_routing"]


class FakeMatter:
    def __init__(self, healthy=True):
        self.healthy = healthy

    async def get_state(self):
        if not self.healthy:
            raise p.MatterNotReady("offline")
        return object()


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, policy, healthy=True, cloud=True, matter_outcome=None):
        calls = []
        m = FakeMatter(healthy)

        async def cloud_write():
            calls.append("cloud")

        async def matter_write(_):
            calls.append("matter")
            if matter_outcome is not None:
                raise matter_outcome
            return {"confirmed": True}

        router = r.DualTransportRouter(m, lambda: cloud)
        try:
            result = await router.execute(policy, cloud_write=cloud_write,
                                          matter_write=matter_write)
        except Exception as exc:
            return calls, exc
        return calls, result

    async def test_cloud_only(self):
        calls, result = await self.call(p.CLOUD_ONLY)
        self.assertEqual(calls, ["cloud"])
        self.assertEqual(result.transport, p.CLOUD_ONLY)

    async def test_matter_only(self):
        calls, result = await self.call(p.MATTER_ONLY)
        self.assertEqual(calls, ["matter"])
        self.assertEqual(result.transport, p.MATTER_ONLY)

    async def test_auto_prefers_matter(self):
        calls, result = await self.call(p.MATTER_PREFERRED)
        self.assertEqual(calls, ["matter"])
        self.assertFalse(result.cloud_fallback)

    async def test_auto_fallback_when_matter_preflight_fails(self):
        calls, result = await self.call(p.MATTER_PREFERRED, healthy=False)
        self.assertEqual(calls, ["cloud"])
        self.assertTrue(result.cloud_fallback)

    async def test_matter_only_blocks_cloud_when_unavailable(self):
        calls, error = await self.call(p.MATTER_ONLY, healthy=False)
        self.assertEqual(calls, [])
        self.assertIsInstance(error, p.MatterNotReady)

    async def test_uncertain_matter_write_never_cloud_retries(self):
        calls, error = await self.call(
            p.MATTER_PREFERRED, matter_outcome=p.MatterWriteUncertain("ACK lost"))
        self.assertEqual(calls, ["matter"])
        self.assertIsInstance(error, p.MatterWriteUncertain)

    async def test_auto_fallback_before_any_local_write(self):
        calls, result = await self.call(
            p.MATTER_PREFERRED, matter_outcome=p.MatterNotReady("prewrite"))
        self.assertEqual(calls, ["matter", "cloud"])
        self.assertTrue(result.cloud_fallback)

    async def test_no_cloud_fallback_if_cloud_also_offline(self):
        calls, error = await self.call(p.MATTER_PREFERRED, healthy=False, cloud=False)
        self.assertEqual(calls, [])
        self.assertIsInstance(error, p.MatterNotReady)

    async def test_no_fabricated_success_accepted(self):
        calls = []

        async def cloud_write():
            calls.append("cloud")

        async def matter_write(_):
            calls.append("matter")
            return {"confirmed": False}

        router = r.DualTransportRouter(FakeMatter(), lambda: True)
        with self.assertRaises(p.MatterWriteUncertain):
            await router.execute(p.MATTER_PREFERRED, cloud_write=cloud_write,
                                 matter_write=matter_write)
        self.assertEqual(calls, ["matter"])
