#!/usr/bin/env python3
"""Trace safe Carrier network-config string literals to Android DEX methods.

Pure stdlib. Records method ownership of a const-string/const-string-jumbo
opcode; it does not pretend to decompile call flows or prove a
runtime environment selection. No secrets, user identifiers, or raw bytecode
are exported. Operates on a user-authorized APK without modifying it.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import struct
import zipfile

# Reuse independently verified DEX string-id parsing.
from analyze_native_apk import uleb

SAFE_KEYS = {'API_URL', 'REST_API_URL', 'HASURA_API_URL', 'WEBSOCKET_API_URL',
             'ENTRY_TIER_ENV_URL', 'OKTA_TOKEN_URL', 'OKTA_CLIENT_ID',
             'ENTRA_CLIENT_ID', 'ENTRA_TENANT_URL', 'SOCIAL_LOGIN_ISSUER'}
SAFE_BUILD_CONFIG_FIELDS = {'API_URL', 'REST_API_URL', 'OKTA_TOKEN_URL', 'WEBSOCKET_API_URL',
                            'SOCIAL_LOGIN_ISSUER', 'ENTRY_TIER_ENV_URL', 'ENV', 'FLAVOR',
                            'MOBILE_APP_BRAND', 'REDIRECT_URI', 'APPLICATION_ID', 'VERSION_NAME'}
SAFE_AWS_ENDPOINT = re.compile(r'^[a-z0-9-]+-ats\.iot\.us-east-1\.amazonaws\.com$', re.I)
SAFE_CARRIER_HOST = re.compile(r'^(?:https|wss)://(?:[a-z0-9-]+\.)*carrier\.com(?:/[-a-z0-9/_.]+)?$', re.I)


def read_strids(dex: bytes) -> list[str]:
    # Preserve EVERY string ID including the valid empty string; omitting one
    # shifts all type/method lookup indices and creates false class attributions.
    count, offset = struct.unpack_from('<II', dex, 56)
    if count > 5_000_000 or offset < 112 or offset + count * 4 > len(dex):
        raise ValueError('Invalid DEX string table')
    result = []
    for idx in range(count):
        position = struct.unpack_from('<I', dex, offset + 4*idx)[0]
        try:
            _, position = uleb(dex, position)
            end = dex.find(b'\0', position, min(len(dex), position+30000))
            result.append(dex[position:end].decode('utf-8', 'replace') if end >= position else '')
        except (ValueError, IndexError):
            result.append('')
    return result


def class_methods(dex: bytes, classes: list[str]):
    """Yield (class descriptor, method id, code offset) from class_data_items."""
    if len(dex) < 112 or not dex.startswith(b'dex\n'):
        raise ValueError('Not a DEX file')
    type_count, type_offset = struct.unpack_from('<II', dex, 64)
    method_count, method_offset = struct.unpack_from('<II', dex, 88)
    class_count, class_offset = struct.unpack_from('<II', dex, 96)
    if (class_count > 200_000 or type_count > 500_000 or method_count > 1_000_000 or
            type_offset + type_count * 4 > len(dex) or
            method_offset + method_count * 8 > len(dex) or
            class_offset + class_count * 32 > len(dex)):
        raise ValueError('Bad DEX index tables')
    types = [struct.unpack_from('<I', dex, type_offset + 4*i)[0] for i in range(type_count)]
    method_ids = [struct.unpack_from('<HHI', dex, method_offset + 8*i) for i in range(method_count)]
    for c in range(class_count):
        class_idx, _, _, _, _, _, data_off, _ = struct.unpack_from('<IIIIIIII', dex, class_offset + c*32)
        if not data_off or class_idx >= len(types):
            continue
        class_string_idx = types[class_idx]
        descriptor = classes[class_string_idx] if class_string_idx < len(classes) else 'unknown'
        pos = data_off
        try:
            field_static, pos = uleb(dex, pos)
            field_instance, pos = uleb(dex, pos)
            method_direct, pos = uleb(dex, pos)
            method_virtual, pos = uleb(dex, pos)
            # skip field table (index delta and access flags)
            for _ in range(field_static + field_instance):
                _, pos = uleb(dex, pos)
                _, pos = uleb(dex, pos)
            for quantity in (method_direct, method_virtual):
                method_idx = 0
                for _ in range(quantity):
                    delta, pos = uleb(dex, pos)
                    method_idx += delta
                    _, pos = uleb(dex, pos)
                    code_off, pos = uleb(dex, pos)
                    if method_idx < len(method_ids) and code_off:
                        defining_class, _proto, name_idx = method_ids[method_idx]
                        name = classes[name_idx] if name_idx < len(classes) else 'unknown'
                        yield descriptor, name, code_off
        except (ValueError, IndexError, struct.error):
            continue


def opcode_width(opcode: int) -> int:
    """Dalvik standard opcode widths in 16-bit code units (DEX 035-041)."""
    if opcode in (0x03, 0x06, 0x09, 0x14, 0x17, 0x1b, 0x24, 0x25, 0x26,
                  0x2a, 0x2b, 0x2c, 0x6e, 0x6f, 0x70, 0x71, 0x72,
                  0x74, 0x75, 0x76, 0x77, 0x78, 0xfc, 0xfd):
        return 3
    if opcode in (0x18,):
        return 5
    if opcode in (0xfa, 0xfb):
        return 4
    if opcode in (0x02, 0x05, 0x08, 0x13, 0x15, 0x16, 0x19, 0x1a,
                  0x1c, 0x1f, 0x20, 0x22, 0x23, 0x29, 0xfe, 0xff):
        return 2
    if (0x2d <= opcode <= 0x3d or 0x44 <= opcode <= 0x6d or
            0x90 <= opcode <= 0xaf or 0xd0 <= opcode <= 0xe2):
        return 2
    return 1


def method_constants(dex: bytes, code_offset: int, interesting: set[int]) -> set[int]:
    """Decode opcode boundaries and identify real const-string references."""
    if code_offset + 16 > len(dex):
        return set()
    count = struct.unpack_from('<I', dex, code_offset + 12)[0]
    if count > 250_000 or code_offset + 16 + count * 2 > len(dex):
        return set()
    raw = memoryview(dex)[code_offset + 16:code_offset + 16 + count * 2]
    found, i = set(), 0
    while i < count:
        unit = struct.unpack_from('<H', raw, i*2)[0]
        opcode = unit & 0xff
        if opcode == 0 and unit != 0:  # pseudo-instruction payload (unaligned skipped data)
            fmt = unit >> 8
            if i + 2 > count: break
            if fmt == 1:  # packed switch payload
                size = struct.unpack_from('<H', raw, (i+1)*2)[0]
                width = 4 + size * 2
            elif fmt == 2:  # sparse switch payload
                size = struct.unpack_from('<H', raw, (i+1)*2)[0]
                width = 2 + size * 4
            elif fmt == 3 and i + 4 <= count:  # fill array payload
                byte_width = struct.unpack_from('<H', raw, (i+1)*2)[0]
                length = struct.unpack_from('<I', raw, (i+2)*2)[0]
                width = 4 + (length * byte_width + 1) // 2
            else:
                break
        else:
            width = opcode_width(opcode)
        if i + width > count:
            break
        if opcode == 0x1a and width == 2:
            idx = struct.unpack_from('<H', raw, (i+1)*2)[0]
            if idx in interesting: found.add(idx)
        elif opcode == 0x1b and width == 3:
            idx = struct.unpack_from('<I', raw, (i+1)*2)[0]
            if idx in interesting: found.add(idx)
        i += width
    return found


def parse_encoded_value(data: bytes, offset: int, depth=0):
    """Read static encoded_value and return primitive string-index marker when present."""
    if depth > 8 or offset >= len(data): raise ValueError('Invalid encoded DEX value')
    header = data[offset]
    kind, size = header & 0x1f, (header >> 5) + 1
    offset += 1
    if kind in (0x1c, 0x1d):
        if kind == 0x1d:
            _, offset = uleb(data, offset)
        count, offset = uleb(data, offset)
        if count > 100_000: raise ValueError('Oversized encoded value')
        values = []
        for _ in range(count):
            if kind == 0x1d: _, offset = uleb(data, offset)
            value, offset = parse_encoded_value(data, offset, depth+1)
            values.extend(value)
        return values, offset
    if kind in (0x1e, 0x1f):
        return [], offset
    if offset + size > len(data): raise ValueError('Truncated value')
    if kind == 0x17:
        return [int.from_bytes(data[offset:offset+size], 'little')], offset+size
    return [], offset+size


def static_string_crossrefs(dex: bytes, strings: list[str], interesting: set[int]):
    """Map encoded static class values onto static field names with full index preservation."""
    type_count, type_offset = struct.unpack_from('<II', dex, 64)
    field_count, field_offset = struct.unpack_from('<II', dex, 80)
    class_count, class_offset = struct.unpack_from('<II', dex, 96)
    types = [struct.unpack_from('<I', dex, type_offset + 4*i)[0] for i in range(type_count)]
    fields = [struct.unpack_from('<HHI', dex, field_offset + 8*i) for i in range(field_count)]
    result = []
    for c in range(class_count):
        class_idx, _, _, _, _, _, data_off, values_off = struct.unpack_from('<IIIIIIII', dex, class_offset + c*32)
        if not data_off or not values_off: continue
        try:
            static_count, p = uleb(dex, data_off)
            _instance_count, p = uleb(dex, p)
            _direct_count, p = uleb(dex, p)
            _virtual_count, p = uleb(dex, p)
            field_ids, idx = [], 0
            for _ in range(static_count):
                delta, p = uleb(dex, p)
                idx += delta
                _, p = uleb(dex, p)
                field_ids.append(idx)
            length, p = uleb(dex, values_off)
            if length > static_count: continue
            owner = strings[types[class_idx]]
            for i in range(length):
                values, p = parse_encoded_value(dex, p)
                for value in values:
                    if value in interesting and field_ids[i] < len(fields):
                        field = fields[field_ids[i]]
                        result.append((owner, strings[field[2]], strings[value]))
        except (ValueError, IndexError, struct.error):
            continue
    return result


def trace(apk: Path):
    result = {'source': 'DEX bytecode instruction references, not runtime proof',
              'dex_files': [], 'references': [], 'static_fields': [], 'build_config': {}}
    with zipfile.ZipFile(apk) as archive:
        for filename in sorted(n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)):
            data = archive.read(filename)
            strings = read_strids(data)
            wanted = {idx for idx, value in enumerate(strings) if value in SAFE_KEYS or SAFE_CARRIER_HOST.fullmatch(value)}
            refs = defaultdict(set)
            static_values = static_string_crossrefs(data, strings, wanted)
            # BuildConfig contains API keys and device-level cryptographic roots.
            # Whitelist only public connectivity metadata; never export raw keys.
            all_static_strings = static_string_crossrefs(data, strings, set(range(len(strings))))
            for owner, field, value in all_static_strings:
                if owner != 'Lcom/carrier/home/BuildConfig;' or field not in SAFE_BUILD_CONFIG_FIELDS:
                    continue
                if field == 'ENTRY_TIER_ENV_URL' and not SAFE_AWS_ENDPOINT.fullmatch(value):
                    continue
                if field in {'API_URL', 'REST_API_URL', 'OKTA_TOKEN_URL',
                             'WEBSOCKET_API_URL', 'SOCIAL_LOGIN_ISSUER'} and not SAFE_CARRIER_HOST.fullmatch(value):
                    continue
                if field in {'REDIRECT_URI', 'ENV', 'FLAVOR', 'MOBILE_APP_BRAND',
                             'APPLICATION_ID', 'VERSION_NAME'} and (len(value) > 80 or '\n' in value):
                    continue
                result['build_config'][field] = {'value': value,
                                                 'source': f'{filename}:com.carrier.home.BuildConfig static field',
                                                 'interpretation': 'compiled config value, runtime usage not proven'}
            for owner, field, value in static_values:
                result['static_fields'].append({'dex': filename, 'class_descriptor': owner, 'field': field, 'literal': value})
            examined = 0
            for owner, method, code_offset in class_methods(data, strings):
                examined += 1
                found = method_constants(data, code_offset, wanted)
                for idx in found:
                    refs[strings[idx]].add((owner, method))
            result['dex_files'].append({'file': filename, 'strings': len(strings),
                                        'code_methods_examined': examined, 'target_literals': len(wanted),
                                        'cross_references': sum(len(v) for v in refs.values()), 'static_value_matches': len(static_values)})
            for value, origins in sorted(refs.items()):
                result['references'].append({'dex': filename, 'literal': value,
                                             'candidate_methods': [{'class_descriptor': c, 'method': m}
                                                                   for c, m in sorted(origins)[:40]]})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = trace(args.apk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.is_symlink():
        parser.error('Refusing symlink output')
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('DEX files:', len(result['dex_files']))
    print('Methods examined:', sum(e['code_methods_examined'] for e in result['dex_files']))
    print('Method-reference literals:', len(result['references']))
    print('Static-value literals:', len(result['static_fields']))
    print('Sanitized app BuildConfig fields:', len(result['build_config']))

if __name__ == '__main__':
    main()
