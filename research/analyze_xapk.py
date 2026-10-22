#!/usr/bin/env python3
"""Offline static API-surface extraction for Carrier SmartHome Hermes HBC v96.

Usage:
    python3 analyze_xapk.py SmartHome_1.2.42_APKPure.xapk -o research

Standard library only. Does not run APK or JS code, access Carrier servers,
query user devices, or extract private credentials from an Android phone.
Outputs metadata, an index, and the GraphQL document strings embedded in APK.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

MAGIC = bytes.fromhex('c61fbc03c103191f')
OP_RE = re.compile(r'\b(query|mutation|subscription|fragment)\s+([A-Za-z_][\w]*)\s*(?:\(|\{|on\s+)', re.MULTILINE)
DOC_RE = re.compile(r'^\s*(query|mutation|subscription|fragment)\s+([A-Za-z_][\w]*)\s*(?:\(|\{|on\s+)', re.MULTILINE)
ENV_RE = re.compile(r'\b(?:REST_API_URL|HASURA_API_URL|WEBSOCKET_API_URL|OKTA_TOKEN_URL|API_URL|ENTRY_TIER_ENV_URL|ENTRA_TENANT_URL|ENTRA_CLIENT_ID|OKTA_CLIENT_ID|SOCIAL_LOGIN_ISSUER)\b')

def extract_strings(bytecode: bytes):
    if bytecode[:8] != MAGIC:
        raise ValueError('The JavaScript bundle does not have a Hermes bytecode header')
    def u32(pos: int) -> int:
        return struct.unpack_from('<I', bytecode, pos)[0]
    if len(bytecode) < 128:
        raise ValueError('Hermes bundle is truncated')
    if u32(8) != 96:
        raise ValueError(f'Unsupported Hermes version {u32(8)}; extractor validated only for v96')
    if u32(32) != len(bytecode):
        raise ValueError('Hermes header file length mismatch')

    function_count, kind_count, identifier_count, string_count, overflow_count, storage_bytes = [u32(i) for i in (40,44,48,52,56,60)]
    # From Hermes v96 BytecodeFileFormat.h; all sections are 4-byte aligned.
    table_at = 128 + function_count * 16 + kind_count * 4 + identifier_count * 4
    over_at = table_at + string_count * 4
    storage_at = over_at + overflow_count * 8
    if not (128 <= table_at <= over_at <= storage_at <= len(bytecode)):
        raise ValueError('Hermes section offsets invalid')
    if storage_at + storage_bytes > len(bytecode):
        raise ValueError('Hermes string storage exceeds bundle length')
    storage = memoryview(bytecode)[storage_at:storage_at + storage_bytes]
    records = []
    actual_overflows = 0
    for idx in range(string_count):
        item = u32(table_at + idx * 4)
        utf16 = item & 1
        off = (item >> 1) & 0x7fffff
        length = (item >> 24) & 0xff
        if length == 0xff:
            if off >= overflow_count:
                raise ValueError(f'Overflow index invalid for string {idx}')
            off, length = struct.unpack_from('<II', bytecode, over_at + off * 8)
            actual_overflows += 1
        byte_len = length * (2 if utf16 else 1)
        if off + byte_len > storage_bytes:
            raise ValueError(f'String storage bounds invalid for string {idx}')
        raw = storage[off:off + byte_len].tobytes()
        value = raw.decode('utf-16le' if utf16 else 'utf-8', errors='replace')
        records.append((idx, value))
    if actual_overflows != overflow_count:
        raise ValueError(f'Overflow entries mismatch: used {actual_overflows}; claimed {overflow_count}')
    return records, {
        'hermes_version':96, 'function_count':function_count,
        'identifier_count': identifier_count, 'string_count':string_count,
        'overflow_string_count':overflow_count, 'string_storage_bytes':storage_bytes,
        'bundle_sha256':hashlib.sha256(bytecode).hexdigest()
    }

def group_for(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ('entrylevel','entry_level','etblesession')):return 'entry_level'
    if 'infinity' in n:return 'infinity'
    if any(k in n for k in ('login','password','token','registeruser','sociallogin','assistedsignin','assistedlogin','emailverification')):return 'authentication'
    if any(k in n for k in ('user','device','location','home','dealer','filter','maintenance','notification','schedule','sendcommand','service')):return 'shared_devices_accounts'
    return 'other'

def run(xapk:Path, destination:Path) -> dict:
    if not xapk.is_file():raise FileNotFoundError(xapk)
    if destination.resolve() == xapk.resolve():raise ValueError('Output cannot overwrite the input file')
    with zipfile.ZipFile(xapk) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('package_name') != 'com.carrier.home':
            raise ValueError(f"Package mismatch: {manifest.get('package_name')}")
        base_name = next((x['file'] for x in manifest.get('split_apks',[]) if x.get('id')=='base'),None)
        if not base_name:raise ValueError('Could not locate base APK in XAPK manifest')
        base_bytes=archive.read(base_name)
    with zipfile.ZipFile(io.BytesIO(base_bytes)) as base:
        bundle = base.read('assets/index.android.bundle')
        expo = json.loads(base.read('assets/app.config'))
    records, byte_meta = extract_strings(bundle)
    # Package integrity and configuration flags. Avoid embedding raw APK contents.
    destination.mkdir(parents=True,exist_ok=True)
    manifest_meta = {
        'package':manifest['package_name'],
        'app_version':manifest.get('version_name'),
        'version_code':manifest.get('version_code'),
        'min_sdk':manifest.get('min_sdk_version'),
        'target_sdk':manifest.get('target_sdk_version'),
        'split_count':len(manifest.get('split_apks',[])),
        'expo_config':{key:expo.get(key) for key in ('name','displayName','slug','version','sdkVersion')},
        'xapk_sha256':hashlib.sha256(xapk.read_bytes()).hexdigest(),
        'base_apk_sha256':hashlib.sha256(base_bytes).hexdigest(),
        **byte_meta,
    }
    (destination/'package-metadata.json').write_text(json.dumps(manifest_meta,indent=2)+'\n',encoding='utf-8')

    operations=[]
    op_base=destination/'graphql'
    op_base.mkdir(parents=True,exist_ok=True)
    for idx,value in records:
        if not (match:=OP_RE.search(value)):
            continue
        kind,name=match.group(1),match.group(2)
        # Includes 3 partial introspection fragments: those must not masquerade as runnable documents.
        complete = bool(DOC_RE.match(value))
        group=group_for(name)
        folder=op_base/group
        folder.mkdir(exist_ok=True)
        ext='.graphql' if complete else '.partial.txt'
        file_name=f'{kind}_{name}_{idx}{ext}'
        relative=Path('graphql')/group/file_name
        (destination/relative).write_text(value.strip()+'\n',encoding='utf-8')
        operations.append({'hermes_string_id':idx,'type':kind,'name':name,'family':group,'standalone_document':complete,'path':relative.as_posix()})
    with (destination/'graphql-index.csv').open('w',newline='',encoding='utf-8') as fd:
        writer=csv.DictWriter(fd,fieldnames=list(operations[0]))
        writer.writeheader();writer.writerows(operations)
    (destination/'graphql-index.json').write_text(json.dumps(operations,indent=2)+'\n',encoding='utf-8')

    # Do not harvest embedded credentials, large images, or all app strings into the deliverable.
    flags=[{'string_id':idx,'value':value} for idx,value in records if ENV_RE.fullmatch(value)]
    flags.sort(key=lambda v:v['value'])
    static_paths=sorted({'/graphql','/graphql-no-auth'}.intersection({v for _,v in records}))
    (destination/'transport-configuration-hints.json').write_text(json.dumps({
        'graphql_path_literals':static_paths,
        'environment_keys':flags,
        'notes':["Configuration key names and paths alone do not establish a production API host.",
                 "Do not assume every GraphQL operation is available for each thermostat model.",
                 "OAuth or token exchanges cannot be confirmed by static strings alone."]
    },indent=2)+'\n',encoding='utf-8')

    from collections import Counter
    summary={'package':manifest_meta,'operations_by_type':dict(Counter(op['type'] for op in operations)),
             'standalone_documents':sum(op['standalone_document'] for op in operations),
             'partial_documents':sum(not op['standalone_document'] for op in operations),
             'operation_count':len(operations)}
    (destination/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('xapk',type=Path)
    parser.add_argument('-o','--output',type=Path,default=Path('smarthome-offline-analysis'))
    args=parser.parse_args()
    try:
        summary=run(args.xapk,args.output)
    except (ValueError,OSError,KeyError,zipfile.BadZipFile,json.JSONDecodeError,struct.error) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1
    print(json.dumps({'output':str(args.output),'operation_count':summary['operation_count'],
                      'by_type':summary['operations_by_type'],'complete':summary['standalone_documents'],
                      'partial':summary['partial_documents']},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
