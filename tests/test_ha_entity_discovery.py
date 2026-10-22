"""Stubbed Home Assistant platform lifecycle tests (not full HA runtime tests)."""
from __future__ import annotations

import asyncio
from enum import Enum, IntFlag
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/carrier_smarthome'
PKG = 'ha_alpha3_simulator'


def module(name):
    m = types.ModuleType(name)
    return m


def load(name):
    fullname = f'{PKG}.{name}'
    spec = importlib.util.spec_from_file_location(fullname, ROOT / f'{name}.py')
    m = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = m
    spec.loader.exec_module(m)
    return m


class HVACMode(str, Enum):
    OFF = 'off'
    HEAT = 'heat'
    COOL = 'cool'
    HEAT_COOL = 'heat_cool'
    FAN_ONLY = 'fan_only'


class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    TARGET_TEMPERATURE_RANGE = 2
    TURN_ON = 4
    TURN_OFF = 8


class DummyCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class DummyCoordinator:
    last_update_success = True
    def __init__(self):
        self.data = {'serial-test': {'serial': 'serial-test', 'connection': {'isConnected': True}, 'zones': [{'index': 0}]}}
        self.callbacks = []
        self.client = None
    def async_add_listener(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)
    def update(self):
        for callback in self.callbacks.copy():
            callback()


class DummyEntry:
    entry_id = 'test-entry'
    options = {}
    def __init__(self):
        self.unloads = []
    def async_on_unload(self, callback):
        self.unloads.append(callback)


class EntityDiscoveryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stubs = {}
        for name in ['homeassistant', 'homeassistant.components', 'homeassistant.components.climate',
                     'homeassistant.components.sensor', 'homeassistant.components.binary_sensor',
                     'homeassistant.components.switch',
                     'homeassistant.const', 'homeassistant.exceptions', 'homeassistant.helpers',
                     'homeassistant.helpers.update_coordinator', 'homeassistant.helpers.entity', PKG]:
            stubs[name] = module(name)
        stubs[PKG].__path__ = [str(ROOT)]
        climate = stubs['homeassistant.components.climate']
        climate.ClimateEntity = type('ClimateEntity', (), {})
        climate.ClimateEntityFeature = ClimateEntityFeature
        climate.HVACMode = HVACMode
        stubs['homeassistant.components.switch'].SwitchEntity = type('SwitchEntity', (), {})
        sensor = stubs['homeassistant.components.sensor']
        sensor.SensorEntity = type('SensorEntity', (), {})
        sensor.SensorStateClass = types.SimpleNamespace(MEASUREMENT='measurement')
        sensor.SensorDeviceClass = types.SimpleNamespace(HUMIDITY='humidity', TEMPERATURE='temperature')
        binary = stubs['homeassistant.components.binary_sensor']
        binary.BinarySensorEntity = type('BinarySensorEntity', (), {})
        binary.BinarySensorDeviceClass = types.SimpleNamespace(CONNECTIVITY='connectivity')
        stubs['homeassistant.const'].PERCENTAGE = '%'
        stubs['homeassistant.exceptions'].HomeAssistantError = type('HomeAssistantError', (Exception,), {})
        stubs['homeassistant.helpers.update_coordinator'].CoordinatorEntity = DummyCoordinatorEntity
        stubs['homeassistant.helpers.entity'].EntityCategory = types.SimpleNamespace(DIAGNOSTIC='diagnostic')
        self.patch = patch.dict(sys.modules, stubs)
        self.patch.start()
        for m in ('const', 'models', 'api', 'entity'):
            load(m)
        self.coordinator = DummyCoordinator()
        self.entry = DummyEntry()
        self.hass = types.SimpleNamespace(data={'carrier_smarthome': {self.entry.entry_id: self.coordinator}})

    async def asyncTearDown(self):
        self.patch.stop()
        for suffix in ('const', 'models', 'api', 'entity', 'climate', 'sensor', 'binary_sensor', 'switch', 'control'):
            sys.modules.pop(f'{PKG}.{suffix}', None)

    async def test_entities_added_for_new_device_only_once(self):
        for name, count_per_zone in [('climate', 1), ('sensor', 14), ('binary_sensor', 2), ('switch', 1)]:
            with self.subTest(platform=name):
                platform = load(name)
                self.coordinator = DummyCoordinator()
                self.entry = DummyEntry()
                self.hass.data['carrier_smarthome'][self.entry.entry_id] = self.coordinator
                created = []
                await platform.async_setup_entry(self.hass, self.entry, lambda es: created.extend(es))
                self.assertEqual(len(created), count_per_zone)
                self.coordinator.data['new-device'] = {'serial': 'new-device', 'zones': [{'index': 0}],
                                                        'connection': {'isConnected': False}}
                self.coordinator.update()
                self.assertEqual(len(created), 2*count_per_zone)
                self.coordinator.update()
                self.assertEqual(len(created), 2*count_per_zone)
                for unload in self.entry.unloads:
                    unload()
                self.assertEqual(len(self.coordinator.callbacks), 0)

    async def test_offline_last_reported_diagnostics_do_not_get_temperature_units(self):
        sensor = load('sensor')
        self.hass.config = types.SimpleNamespace(units=types.SimpleNamespace(temperature_unit='°F'))
        self.coordinator.data['serial-test']['temp_unit_format'] = 'F'
        self.coordinator.data['serial-test']['connection']['isConnected'] = False
        zone = self.coordinator.data['serial-test']['zones'][0]
        zone.update({'mode': 'off', 'stage_status': 'idle', 'fan_mode': 'auto',
                     'schedule_enabled': False, 'rt': 73, 'rh': 47,
                     'htsp': {'current': 70, 'max': 90}, 'clsp': {'current': 76, 'min': 62}})
        entities = []
        await sensor.async_setup_entry(self.hass, self.entry, lambda es: entities.extend(es))
        by_key = {obj.key: obj for obj in entities if isinstance(obj, sensor.CarrierLastReportedSensor)}
        self.assertEqual(by_key['mode'].native_value, 'off')
        self.assertEqual(by_key['mode'].native_unit_of_measurement, None)
        self.assertEqual(by_key['fan_mode'].native_unit_of_measurement, None)
        self.assertEqual(by_key['stage_status'].native_unit_of_measurement, None)
        self.assertEqual(by_key['schedule_enabled'].native_value, 'disabled')
        self.assertIsNone(by_key['schedule_enabled'].native_unit_of_measurement)
        self.assertEqual(by_key['temperature'].native_value, 73)
        self.assertEqual(by_key['temperature'].native_unit_of_measurement, '°F')
        self.assertTrue(by_key['temperature'].available)
        self.assertFalse(entities[0].available)  # live humidity remains unavailable

    async def test_offline_climate_unavailable(self):
        cl = load('climate')
        entities = []
        await cl.async_setup_entry(self.hass, self.entry, lambda es: entities.extend(es))
        self.assertTrue(entities[0].available)
        self.coordinator.data['serial-test']['connection']['isConnected'] = False
        self.assertFalse(entities[0].available)
        # A successful cloud poll alone does not re-enable the live climate.
        self.coordinator.data['serial-test']['connection']['isConnected'] = True
        self.assertTrue(entities[0].available)
        self.coordinator.last_update_success = False
        self.assertFalse(entities[0].available)

    async def test_mode_control_off_on_and_feedback(self):
        climate = load('climate')
        switch = load('switch')
        entities = []
        power = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: entities.extend(es))
        await switch.async_setup_entry(self.hass, self.entry, lambda es: power.extend(es))
        self.entry.options = {'enable_control': True, 'power_on_mode': 'cool'}
        state = self.coordinator.data['serial-test']['zones'][0]
        state.update({'mode':'off', 'htsp':{'current':70}, 'clsp':{'current':76}})
        self.coordinator.last_update_success = True
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            if self.coordinator.client.async_update_zone.await_count:
                new_mode = self.coordinator.client.async_update_zone.await_args.kwargs['mode']
                state['mode'] = new_mode
        self.coordinator.async_request_refresh = refresh
        self.assertFalse(power[0].is_on)
        self.assertEqual(power[0].extra_state_attributes['power_on_mode'], 'cool')
        self.assertTrue(entities[0].supported_features & ClimateEntityFeature.TURN_OFF)
        self.assertTrue(entities[0].supported_features & ClimateEntityFeature.TURN_ON)
        self.assertFalse(entities[0].supported_features & ClimateEntityFeature.TARGET_TEMPERATURE)
        await power[0].async_turn_on()
        self.assertEqual(state['mode'],'cool')
        self.assertTrue(power[0].is_on)
        self.assertEqual(self.coordinator.client.async_update_zone.await_count,1)
        await entities[0].async_turn_off()
        self.assertEqual(state['mode'],'off')
        self.assertFalse(power[0].is_on)
        self.assertEqual(self.coordinator.client.async_update_zone.await_count,2)
        await entities[0].async_turn_off()
        self.assertEqual(self.coordinator.client.async_update_zone.await_count,2) # idempotent

    async def test_power_on_requires_explicit_mode_and_online(self):
        switch = load('switch')
        power=[]
        await switch.async_setup_entry(self.hass,self.entry,lambda es: power.extend(es))
        self.entry.options={'enable_control':True, 'power_on_mode':'unset'}
        with self.assertRaisesRegex(Exception, 'Choose Heat'):
            await power[0].async_turn_on()
        self.entry.options={'enable_control':True, 'power_on_mode':'cool'}
        self.coordinator.data['serial-test']['connection']['isConnected']=False
        self.assertFalse(power[0].available)
        self.coordinator.client=types.SimpleNamespace(async_update_zone=AsyncMock())
        with self.assertRaisesRegex(Exception, 'disconnected'):
            await power[0].async_turn_on()
        self.coordinator.client.async_update_zone.assert_not_awaited()

    async def test_preflight_fails_closed_and_never_writes(self):
        switch = load('switch')
        power=[]
        await switch.async_setup_entry(self.hass,self.entry,lambda es: power.extend(es))
        self.entry.options={'enable_control':True,'power_on_mode':'heat'}
        self.coordinator.client=types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            self.coordinator.data['serial-test']['connection']['isConnected']=False
        self.coordinator.async_request_refresh=refresh
        with self.assertRaisesRegex(Exception, 'disconnected'):
            await power[0].async_turn_on()
        self.coordinator.client.async_update_zone.assert_not_awaited()

    async def test_mutation_ack_without_readback_reports_uncertain_and_never_resends(self):
        switch = load('switch')
        control = load('control')
        power=[]
        await switch.async_setup_entry(self.hass,self.entry,lambda es: power.extend(es))
        self.entry.options={'enable_control':True,'power_on_mode':'cool'}
        self.coordinator.data['serial-test']['zones'][0]['mode']='off'
        self.coordinator.client=types.SimpleNamespace(async_update_zone=AsyncMock())
        self.coordinator.async_request_refresh=AsyncMock()  # Carrier keeps reporting Off.
        with patch.object(control.asyncio,'sleep',new_callable=AsyncMock):
            with self.assertRaisesRegex(Exception,'not confirmed'):
                await power[0].async_turn_on()
        self.coordinator.client.async_update_zone.assert_awaited_once()
        self.assertEqual(self.coordinator.async_request_refresh.await_count,4)

    async def test_mode_optin_does_not_automatically_enable_setpoints(self):
        climate=load('climate')
        all_entities=[]
        await climate.async_setup_entry(self.hass,self.entry,lambda es: all_entities.extend(es))
        self.entry.options={'enable_control':True,'enable_setpoint_control':False,
                            'power_on_mode':'cool'}
        self.coordinator.data['serial-test']['zones'][0].update({
            'mode':'cool','htsp':{'current':70},'clsp':{'current':76}})
        self.coordinator.client=types.SimpleNamespace(async_update_zone=AsyncMock())
        self.assertFalse(all_entities[0].supported_features & ClimateEntityFeature.TARGET_TEMPERATURE)
        with self.assertRaisesRegex(Exception,'setpoint writes'):
            await all_entities[0].async_set_temperature(temperature=75)
        self.coordinator.client.async_update_zone.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
