#!/usr/bin/env python3
"""Offline sanity checks for a Carrier SmartHome custom HACS integration.

Requires only Python's standard library. This validates the source tree, not a
running Home Assistant or HACS instance, and never sends network requests.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

DOMAIN = "carrier_smarthome"
REQUIRED_MANIFEST = {
    "domain", "name", "version", "documentation", "issue_tracker",
    "codeowners", "config_flow", "iot_class", "requirements",
}
REQUIRED_MODULES = {
    "__init__.py", "api.py", "const.py", "config_flow.py", "coordinator.py",
    "entity.py", "climate.py", "sensor.py", "binary_sensor.py", "models.py",
    "diagnostics.py", "strings.json", "translations/en.json",
}


def validate(root: Path) -> list[str]:
    """Return a bounded collection of problems, with no network requests."""
    errors: list[str] = []
    directory = root / "custom_components" / DOMAIN

    def json_file(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.relative_to(root)}: invalid or missing JSON ({type(exc).__name__})")
            return None

    if not (root / "README.md").is_file():
        errors.append("Missing README.md")
    hacs = json_file(root / "hacs.json")
    if isinstance(hacs, dict):
        if not isinstance(hacs.get("name"), str) or not hacs["name"].strip():
            errors.append("hacs.json must contain a nonempty name")
        if hacs.get("content_in_root") is True:
            errors.append("Integration is nested under custom_components, not content_in_root")
    else:
        errors.append("hacs.json must be a JSON object")

    manifest = json_file(directory / "manifest.json")
    if isinstance(manifest, dict):
        for field in sorted(REQUIRED_MANIFEST - manifest.keys()):
            errors.append(f"Missing manifest.json key: {field}")
        if manifest.get("domain") != DOMAIN:
            errors.append("manifest.json domain does not match package directory")
        if manifest.get("config_flow") is not True:
            errors.append("manifest.json must enable config_flow")
        if manifest.get("iot_class") != "cloud_polling":
            errors.append("manifest.json iot_class should be cloud_polling")
        if not isinstance(manifest.get("requirements"), list):
            errors.append("manifest.json requirements must be a list")
        if not isinstance(manifest.get("codeowners"), list):
            errors.append("manifest.json codeowners must be a list")
        if not isinstance(manifest.get("version"), str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?", manifest["version"]):
            errors.append("manifest.json version must be explicit and PEP-440-compatible")
        dependencies = manifest.get("dependencies", [])
        requirements = manifest.get("requirements", [])
        if isinstance(dependencies, list) and isinstance(requirements, list):
            if any("matter" in str(dep).lower() for dep in dependencies + requirements):
                errors.append("Matter dependencies are outside the project's approved scope")
    else:
        errors.append("manifest.json must be a JSON object")

    for relative in sorted(REQUIRED_MODULES):
        if not (directory / relative).is_file():
            errors.append(f"Missing integration module: {relative}")
    string_labels = json_file(directory / "strings.json")
    translations = json_file(directory / "translations" / "en.json")
    if string_labels is not None and translations is not None and string_labels != translations:
        errors.append("strings.json and translations/en.json differ")
    for path in sorted(directory.rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"Invalid Python source: {path.relative_to(root)} ({type(exc).__name__})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    problems = validate(args.root.resolve())
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print("PASS: HACS custom repository layout, metadata, JSON, and Python syntax")
    print("NOTE: This is an offline check, not proof of HACS download or HA runtime success.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
