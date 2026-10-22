#!/usr/bin/env python3
"""Legacy name retained as a compatibility shim; single probe engine is Probe-CarrierLocalDeep.py.

Older invocations: Probe-VerifiedCarrierLAN.py EXPORT.zip [--suffix XXXX]
No alternate probing or stale-lease fallback remains here.
"""
from __future__ import annotations
import runpy
import sys
from pathlib import Path


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omada_export', type=Path)
    parser.add_argument('--suffix', required=True)
    parser.add_argument('--max-age-minutes', type=int, default=30)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--http-fingerprint', action='store_true', help='Compatibility; deep probe already performs HEAD on candidate web ports')
    args = parser.parse_args()
    parent = str(Path(__file__).resolve().parent)
    sys.path.insert(0, parent)
    from importlib.machinery import SourceFileLoader
    from importlib.util import spec_from_loader, module_from_spec
    filename = str(Path(parent) / 'Probe-CarrierLocalDeep.py')
    loader = SourceFileLoader('carrier_local_deep_compat', filename)
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    command = ['--omada', str(args.omada_export), '--suffix', args.suffix,
               '--max-age-minutes', str(args.max_age_minutes)]
    if args.plan:
        command.append('--plan')
    return module.main(command)


if __name__ == '__main__':
    raise SystemExit(main())
