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
    FAN_MODE = 16


class DummyCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class DummyCoordinator:
    last_update_success = True
    def __init__(self):
        self.data = {'serial-test': {'serial': 'serial-test', 'connection': {'isConnected': True}, 'zones': [{'index': 0}]}}
        self.callbacks = []
        self.client = None
        self.write_lock = asyncio.Lock()
        self.previous = {}
    def last_non_off_mode(self, serial, index):
        return self.previous.get((serial, index))
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
                     'homeassistant.helpers.update_coordinator', 'homeassistant.helpers.entity', PKG]:
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
        for suffix in ('const', 'models', 'api', 'entity', 'climate', 'sensor', 'binary_sensor', 'control'):
            sys.modules.pop(f'{PKG}.{suffix}', None)

    async def test_entities_added_for_new_device_only_once(self):
        for name, count_per_zone in [('climate', 1), ('sensor', 14), ('binary_sensor', 2)]:
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

    async def test_all_modes_visible_even_when_legacy_options_disabled(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        self.assertEqual(len(units), 1)
        self.entry.options = {'enable_control': False, 'enable_fan_control': False,
                              'enable_setpoint_control': False, 'power_on_mode': 'unset'}
        unit = units[0]
        self.assertEqual(unit.hvac_modes, [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL,
                                          HVACMode.HEAT_COOL, HVACMode.FAN_ONLY])
        self.assertEqual(unit.fan_modes, ['auto', 'on'])
        self.assertTrue(unit.supported_features & ClimateEntityFeature.FAN_MODE)
        self.assertTrue(unit.supported_features & ClimateEntityFeature.TURN_OFF)
        self.assertFalse(unit.supported_features & ClimateEntityFeature.TURN_ON)
        self.assertEqual(unit._attr_unique_id, 'serial-test_zone_0_climate')

    async def test_select_cool_off_without_options_one_mutation_each(self):
        climate = load('climate')
        controls = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: controls.extend(es))
        unit = controls[0]
        state = self.coordinator.data['serial-test']['zones'][0]
        state.update({'mode': 'off', 'htsp': {'current': 70}, 'clsp': {'current': 76}})
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            if self.coordinator.client.async_update_zone.await_count:
                state['mode'] = self.coordinator.client.async_update_zone.await_args.kwargs['mode']
        self.coordinator.async_refresh = refresh
        await unit.async_set_hvac_mode(HVACMode.COOL)
        self.assertEqual(unit.hvac_mode, HVACMode.COOL)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='cool')
        await unit.async_set_hvac_mode(HVACMode.COOL)
        self.assertEqual(self.coordinator.client.async_update_zone.await_count, 1)
        await unit.async_turn_off()
        self.assertEqual(unit.hvac_mode, HVACMode.OFF)
        self.assertEqual(self.coordinator.client.async_update_zone.await_count, 2)

    async def test_on_restores_only_observed_mode_not_guessed(self):
        climate = load('climate')
        controls = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: controls.extend(es))
        unit = controls[0]
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'off'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        with self.assertRaisesRegex(Exception, 'Choose Heat'):
            await unit.async_turn_on()
        self.coordinator.client.async_update_zone.assert_not_awaited()
        self.coordinator.previous[('serial-test', 0)] = 'heat'
        self.assertTrue(unit.supported_features & ClimateEntityFeature.TURN_ON)
        async def refresh():
            if self.coordinator.client.async_update_zone.await_count:
                state['mode'] = 'heat'
        self.coordinator.async_refresh = refresh
        await unit.async_turn_on()
        self.assertEqual(unit.hvac_mode, HVACMode.HEAT)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='heat')

    async def test_offline_and_failed_poll_block_all_commands(self):
        climate = load('climate')
        controls = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: controls.extend(es))
        unit = controls[0]
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        self.coordinator.data['serial-test']['connection']['isConnected'] = False
        self.assertFalse(unit.available)
        with self.assertRaisesRegex(Exception, 'disconnected'):
            await unit.async_set_hvac_mode(HVACMode.COOL)
        with self.assertRaisesRegex(Exception, 'disconnected'):
            await unit.async_set_fan_mode('on')
        self.coordinator.data['serial-test']['connection']['isConnected'] = True
        self.coordinator.last_update_success = False
        self.assertFalse(unit.available)
        with self.assertRaisesRegex(Exception, 'unavailable'):
            await unit.async_set_hvac_mode(HVACMode.HEAT)
        self.coordinator.client.async_update_zone.assert_not_awaited()

    async def test_fresh_poll_offline_preflight_fails_closed(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            self.coordinator.data['serial-test']['connection']['isConnected'] = False
        self.coordinator.async_refresh = refresh
        with self.assertRaisesRegex(Exception, 'disconnected'):
            await units[0].async_set_hvac_mode(HVACMode.COOL)
        self.coordinator.client.async_update_zone.assert_not_awaited()

    async def test_mutation_not_repeated_when_cloud_does_not_confirm(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        self.coordinator.data['serial-test']['zones'][0]['mode'] = 'off'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        self.coordinator.async_refresh = AsyncMock()
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(Exception, 'not confirmed'):
                await units[0].async_set_hvac_mode(HVACMode.COOL)
        self.coordinator.client.async_update_zone.assert_awaited_once()
        self.assertEqual(self.coordinator.async_refresh.await_count, 10)

    async def test_fan_auto_on_in_climate_no_extra_select(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state.update({'mode': 'cool', 'fan_mode': 'auto'})
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            if self.coordinator.client.async_update_zone.await_count:
                state['fan_mode'] = self.coordinator.client.async_update_zone.await_args.kwargs['fan']
        self.coordinator.async_refresh = refresh
        await units[0].async_set_fan_mode('on')
        self.assertEqual(units[0].fan_mode, 'on')
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, fan='on')
        with self.assertRaisesRegex(Exception, 'Circulate'):
            await units[0].async_set_fan_mode('circulate')

    async def test_cool_target_without_options_and_fresh_limit(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state.update({'mode': 'cool', 'htsp': {'current': 70, 'max': 85},
                      'clsp': {'current': 76, 'min': 60}})
        self.assertTrue(units[0].supported_features & ClimateEntityFeature.TARGET_TEMPERATURE)
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        async def refresh():
            if self.coordinator.client.async_update_zone.await_count:
                state['clsp']['current'] = self.coordinator.client.async_update_zone.await_args.kwargs['cool']
        self.coordinator.async_refresh = refresh
        await units[0].async_set_temperature(temperature=75)
        self.coordinator.client.async_update_zone.assert_awaited_once_with(
            'serial-test', 0, heat=70, cool=75)
        state['clsp']['min'] = 74
        with self.assertRaisesRegex(Exception, 'current Carrier limit'):
            await units[0].async_set_temperature(temperature=73)
        self.assertEqual(self.coordinator.client.async_update_zone.await_count, 1)

    async def test_nan_setpoint_blocked_at_preflight(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        self.coordinator.data['serial-test']['zones'][0].update({
            'mode': 'heat', 'htsp': {'current': 70}, 'clsp': {'current': 76}})
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        self.coordinator.async_refresh = AsyncMock()
        with self.assertRaisesRegex(Exception, 'Invalid'):
            await units[0].async_set_temperature(temperature=float('nan'))
        self.coordinator.client.async_update_zone.assert_not_awaited()

    async def test_overlapping_mode_writes_are_rejected_not_queued(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'off'
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        writes = []
        async def mutate(serial, index, *, mode):
            writes.append(mode)
            if len(writes) == 1:
                first_started.set()
                await release_first.wait()
            state['mode'] = mode
        self.coordinator.client = types.SimpleNamespace(async_update_zone=mutate)
        self.coordinator.async_refresh = AsyncMock()
        one = asyncio.create_task(units[0].async_set_hvac_mode(HVACMode.COOL))
        await asyncio.wait_for(first_started.wait(), timeout=2)
        two = asyncio.create_task(units[0].async_set_hvac_mode(HVACMode.HEAT))
        await asyncio.sleep(0)
        self.assertEqual(writes, ['cool'])
        with self.assertRaisesRegex(Exception, 'still being verified'):
            await two
        release_first.set()
        await one
        self.assertEqual(writes, ['cool'])
        self.assertEqual(state['mode'], 'cool')


    async def test_delayed_carrier_propagation_confirms_after_multiple_real_polls(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'off'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        seen = []
        async def forced_refresh():
            seen.append(len(seen) + 1)
            # The initial forced read is preflight. The successful mutation
            # arrives only after several subsequent readbacks (cloud latency).
            if len(seen) == 6:
                state['mode'] = 'cool'
        self.coordinator.async_refresh = forced_refresh
        # A stubbed debounced refresh would NOT update state; using it would
        # recreate the previous false-negative HA error.
        self.coordinator.async_request_refresh = AsyncMock(side_effect=AssertionError(
            'Debounced refresh must not be used in command confirmation'))
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            await units[0].async_set_hvac_mode(HVACMode.COOL)
        self.assertEqual(state['mode'], 'cool')
        self.assertEqual(len(seen), 6)
        self.assertEqual(sleep.await_count, 4)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='cool')
        self.coordinator.async_request_refresh.assert_not_awaited()

    async def test_transient_failed_confirmation_recovers_without_second_write(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'off'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        attempts = 0
        async def forced_refresh():
            nonlocal attempts
            attempts += 1
            if attempts == 3:
                raise TimeoutError('transient cloud read timeout')
            if attempts == 5:
                state['mode'] = 'heat'
        self.coordinator.async_refresh = forced_refresh
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            await units[0].async_set_hvac_mode(HVACMode.HEAT)
        self.assertEqual(attempts, 5)
        self.coordinator.client.async_update_zone.assert_awaited_once()

    async def test_confirmation_rate_limit_stops_polling_without_repeating_write(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        self.coordinator.data['serial-test']['zones'][0]['mode'] = 'off'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        attempts = 0
        async def forced_refresh():
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                self.coordinator.last_exception = TimeoutError("Simulated 429")
                self.coordinator.last_exception.retry_after = 120
                raise TimeoutError('simulated rate limit')
        self.coordinator.async_refresh = forced_refresh
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(Exception, 'rate-limited'):
                await units[0].async_set_hvac_mode(HVACMode.COOL)
        self.coordinator.client.async_update_zone.assert_awaited_once()
        self.assertEqual(attempts, 2)


    async def test_cool_to_off_eventually_updates_without_repeating_mutation(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'cool'
        self.coordinator.client = types.SimpleNamespace(async_update_zone=AsyncMock())
        poll_count = 0
        async def refresh():
            nonlocal poll_count
            poll_count += 1
            if poll_count == 7:
                state['mode'] = 'off'
        self.coordinator.async_refresh = refresh
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            await units[0].async_set_hvac_mode(HVACMode.OFF)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='off')
        self.assertEqual(state['mode'], 'off')
        self.assertEqual(poll_count, 7)

    async def test_detail_only_confirmation_publishes_observed_mode_to_ha(self):
        climate = load('climate')
        control = load('control')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'cool'  # Listing has not converged yet.
        self.coordinator.client = types.SimpleNamespace(
            async_update_zone=AsyncMock(),
            async_get_system_detail=AsyncMock(return_value={
                'serial': 'serial-test', 'connection': {'isConnected': True},
                'zones': [{'index': 0, 'mode': 'off'}],
            }),
        )
        self.coordinator.async_refresh = AsyncMock()  # Forced reads still stale.
        # Real CarrierCoordinator is tested separately for its publish logic.
        self.coordinator.publish_verified_detail = lambda serial, index, detail, desired: (
            state.update({'mode': desired['mode']}) or True
        )
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            await units[0].async_set_hvac_mode(HVACMode.OFF)
        self.assertEqual(state['mode'], 'off')
        self.assertEqual(self.coordinator.async_refresh.await_count, 2)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='off')
        self.coordinator.client.async_get_system_detail.assert_awaited_once_with('serial-test')

    async def test_detail_mismatch_prevents_stale_noop_for_explicit_off_request(self):
        climate = load('climate')
        units = []
        await climate.async_setup_entry(self.hass, self.entry, lambda es: units.extend(es))
        state = self.coordinator.data['serial-test']['zones'][0]
        state['mode'] = 'off'  # cloud summary stale but accepted off action requested
        async def detail(serial):
            return {'serial': serial, 'connection': {'isConnected': True},
                    'zones': [{'index': 0, 'mode': 'cool'}]}
        self.coordinator.client = types.SimpleNamespace(
            async_update_zone=AsyncMock(), async_get_system_detail=detail)
        self.coordinator.async_refresh = AsyncMock()
        # The requested action is sent once; delayed summary will not claim it
        # verified, since the test detail always reports Cool.
        control = load('control')
        with patch.object(control.asyncio, 'sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(Exception, 'not confirmed'):
                await units[0].async_set_hvac_mode(HVACMode.OFF)
        self.coordinator.client.async_update_zone.assert_awaited_once_with('serial-test', 0, mode='off')


if __name__ == '__main__':
    unittest.main()
