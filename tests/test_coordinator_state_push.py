"""Real coordinator verified-detail push tests (mock HA, no real network)."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'
PKG = 'carrier052_coordinator_tests'


def fake_module(name):
    return types.ModuleType(name)


def load(name):
    full=f'{PKG}.{name}'
    spec=importlib.util.spec_from_file_location(full,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    sys.modules[full]=module
    spec.loader.exec_module(module)
    return module


class DummyHACoordinator:
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, hass, **kwargs):
        self.data={}
        self.last_update_success=True
        self.notifications=0
        self.interval=kwargs['update_interval']
    def async_set_updated_data(self, data):
        self.data=data
        self.notifications += 1


class CoordinatorPushTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stubs={name:fake_module(name) for name in (
            'homeassistant','homeassistant.config_entries','homeassistant.helpers',
            'homeassistant.helpers.update_coordinator',PKG,
        )}
        stubs[PKG].__path__=[str(ROOT)]
        stubs['homeassistant.config_entries'].ConfigEntryAuthFailed=type('ConfigEntryAuthFailed',(Exception,),{})
        update=stubs['homeassistant.helpers.update_coordinator']
        update.DataUpdateCoordinator=DummyHACoordinator
        class UpdateFailed(Exception):
            def __init__(self, message, *, retry_after=None):
                super().__init__(message)
                self.retry_after = retry_after
        update.UpdateFailed=UpdateFailed
        self.patch=patch.dict(sys.modules,stubs)
        self.patch.start()
        for name in ('const','models','api'):
            load(name)
        self.mod=load('coordinator')
        self.coordinator=self.mod.CarrierCoordinator(None,None)
        self.coordinator.data={'serial-test':{
            'serial':'serial-test', 'connection':{'isConnected':True}, 'name':'Keep Name',
            'zones':[{'index':0,'mode':'cool','fan_mode':'auto',
                      'rt':76,'rh':50,'outside_temp':68,
                      'htsp':{'current':67,'max':85},'clsp':{'current':77,'min':60}}]}}
        self.before=self.coordinator.data

    async def asyncTearDown(self):
        self.patch.stop()
        for suffix in ('const','models','api','coordinator'):
            sys.modules.pop(f'{PKG}.{suffix}',None)

    def detail(self, mode='off',serial='serial-test',online=True,index=0):
        return {'serial':serial, 'connection':{'isConnected':online},
                'zones':[{'index':index,'mode':mode,'fan_mode':'on',
                          'htsp':{'current':60}, 'clsp':{'current':74}}]}

    def test_confirmed_off_pushed_to_ha_without_losing_other_sensors(self):
        result=self.coordinator.publish_verified_detail('serial-test',0,self.detail(),{'mode':'off'})
        self.assertTrue(result)
        self.assertEqual(self.coordinator.notifications,1)
        current=self.coordinator.data['serial-test']['zones'][0]
        self.assertEqual(current['mode'],'off')
        self.assertEqual(current['rt'],76)
        self.assertEqual(current['rh'],50)
        self.assertEqual(current['htsp']['current'],67)
        self.assertEqual(current['clsp']['current'],77)
        self.assertEqual(self.before['serial-test']['zones'][0]['mode'],'cool')
        self.assertEqual(self.coordinator.data['serial-test']['name'],'Keep Name')

    def test_wrong_identity_or_offline_never_pushed(self):
        for detail in (self.detail(serial='other'),self.detail(online=False),
                       self.detail(index=1),self.detail(mode='cool')):
            self.assertFalse(self.coordinator.publish_verified_detail('serial-test',0,detail,{'mode':'off'}))
        self.assertEqual(self.coordinator.notifications,0)
        self.assertIs(self.coordinator.data,self.before)

    def test_only_observed_fan_and_setpoints_are_pushed(self):
        desired={'fan_mode':'on','heat_setpoint':60,'cool_setpoint':74}
        self.assertTrue(self.coordinator.publish_verified_detail('serial-test',0,self.detail(),desired))
        z=self.coordinator.data['serial-test']['zones'][0]
        self.assertEqual(z['fan_mode'],'on')
        self.assertEqual(z['htsp']['current'],60)
        self.assertEqual(z['clsp']['current'],74)
        self.assertEqual(z['mode'],'cool')
        self.assertEqual(z['rt'],76)

    def test_unknown_fields_not_pushed(self):
        self.assertFalse(self.coordinator.publish_verified_detail('serial-test',0,self.detail(),{'schedule_enabled':True}))
        self.assertEqual(self.coordinator.notifications,0)

    async def test_transient_failure_short_grace_blocks_writes(self):
        # First a successful online account read, followed by one failed poll.
        from unittest.mock import AsyncMock
        valid = list(self.coordinator.data.values())
        self.coordinator.client = types.SimpleNamespace(async_get_systems=AsyncMock(return_value=valid))
        self.coordinator.data = await self.coordinator._async_update_data()
        self.assertTrue(self.coordinator.telemetry_usable)
        self.assertFalse(self.coordinator.telemetry_in_grace)
        self.coordinator.client.async_get_systems = AsyncMock(side_effect=self.mod.CarrierError('network'))
        with self.assertRaises(self.mod.UpdateFailed):
            await self.coordinator._async_update_data()
        self.coordinator.last_update_success = False  # HA response after failure
        self.assertEqual(self.coordinator.last_error_kind, 'transport_or_graphql')
        self.assertTrue(self.coordinator.telemetry_usable)
        self.assertTrue(self.coordinator.telemetry_in_grace)
        self.assertIsNotNone(self.coordinator.last_poll_utc)
        self.coordinator._last_success_monotonic -= 200
        self.assertFalse(self.coordinator.telemetry_usable)
        self.assertFalse(self.coordinator.telemetry_in_grace)

    async def test_empty_listing_preserves_known_device(self):
        from unittest.mock import AsyncMock
        self.coordinator.client = types.SimpleNamespace(async_get_systems=AsyncMock(return_value=[]))
        with self.assertRaises(self.mod.UpdateFailed):
            await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.last_error_kind, "empty_listing")
        self.assertIn("serial-test", self.coordinator.data)

    async def test_rate_limit_suppresses_repeat_and_recovers(self):
        from unittest.mock import AsyncMock
        self.coordinator.client = types.SimpleNamespace(async_get_systems=AsyncMock(
            side_effect=self.mod.CarrierRateLimitError(120)))
        with self.assertRaises(self.mod.UpdateFailed) as cm:
            await self.coordinator._async_update_data()
        self.assertIn('Retry-After', str(cm.exception))
        self.assertEqual(cm.exception.retry_after, 120)
        self.assertEqual(self.coordinator.last_error_kind, 'rate_limited')
        self.assertGreater(self.coordinator.next_poll_wait_seconds, 0)
        self.assertGreaterEqual(self.coordinator.update_interval.total_seconds(), 120)
        with self.assertRaises(self.mod.UpdateFailed):
            await self.coordinator._async_update_data()
        self.coordinator.client.async_get_systems.assert_awaited_once()
        self.coordinator._next_poll_not_before = 0
        self.coordinator.client.async_get_systems = AsyncMock(return_value=list(self.coordinator.data.values()))
        recovered = await self.coordinator._async_update_data()
        self.assertIn('serial-test', recovered)
        self.assertEqual(self.coordinator.consecutive_errors, 0)
        self.assertIsNone(self.coordinator.last_error_kind)
        self.assertEqual(self.coordinator.update_interval.total_seconds(), 60)

    async def test_cloud_grace_is_not_device_online_override(self):
        from unittest.mock import AsyncMock
        self.coordinator.client = types.SimpleNamespace(async_get_systems=AsyncMock(
            return_value=list(self.coordinator.data.values())))
        await self.coordinator._async_update_data()
        self.coordinator.last_update_success = False
        self.assertTrue(self.coordinator.telemetry_usable)
        # The online flag itself must still govern the live climate entity.
        self.coordinator.data['serial-test']['connection']['isConnected'] = False
        self.assertEqual(self.mod.connectivity_state(
            self.coordinator.data['serial-test']), 'offline')

    def test_fast_but_bounded_background_poll(self):
        self.assertEqual(int(self.coordinator.interval.total_seconds()),60)


if __name__=='__main__':
    unittest.main()
