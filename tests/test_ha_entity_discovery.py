"""Stubbed Home Assistant platform lifecycle tests (not full HA runtime tests)."""
from __future__ import annotations

import asyncio
from enum import Enum, IntFlag
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

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
                     'homeassistant.const', 'homeassistant.exceptions', 'homeassistant.helpers',
                     'homeassistant.helpers.update_coordinator', PKG]:
            stubs[name] = module(name)
        stubs[PKG].__path__ = [str(ROOT)]
        climate = stubs['homeassistant.components.climate']
        climate.ClimateEntity = type('ClimateEntity', (), {})
        climate.ClimateEntityFeature = ClimateEntityFeature
        climate.HVACMode = HVACMode
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
        self.patch = patch.dict(sys.modules, stubs)
        self.patch.start()
        for m in ('const', 'models', 'api', 'entity'):
            load(m)
        self.coordinator = DummyCoordinator()
        self.entry = DummyEntry()
        self.hass = types.SimpleNamespace(data={'carrier_smarthome': {self.entry.entry_id: self.coordinator}})

    async def asyncTearDown(self):
        self.patch.stop()
        for suffix in ('const', 'models', 'api', 'entity', 'climate', 'sensor', 'binary_sensor'):
            sys.modules.pop(f'{PKG}.{suffix}', None)

    async def test_entities_added_for_new_device_only_once(self):
        for name, count_per_zone in [('climate', 1), ('sensor', 2), ('binary_sensor', 1)]:
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

    async def test_offline_climate_unavailable(self):
        cl = load('climate')
        entities = []
        await cl.async_setup_entry(self.hass, self.entry, lambda es: entities.extend(es))
        self.assertTrue(entities[0].available)
        self.coordinator.data['serial-test']['connection']['isConnected'] = False
        self.assertFalse(entities[0].available)


if __name__ == '__main__':
    unittest.main()
