#!/usr/bin/env python3
"""Enforce stricter coverage thresholds for calculation and authorization code."""

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "apps/payroll/services/v1.py": 90.0,
    "apps/taxation/services/engine.py": 85.0,
    "apps/finance/services/calculations.py": 85.0,
    "apps/organizations/services.py": 90.0,
    "apps/organizations/mixins.py": 85.0,
}

report = json.loads(Path("coverage.json").read_text())
failures = []
for filename, threshold in THRESHOLDS.items():
    try:
        actual = report["files"][filename]["summary"]["percent_covered"]
    except KeyError:
        failures.append(f"{filename}: missing from coverage report (required {threshold:.1f}%)")
        continue
    print(f"{filename}: {actual:.1f}% (required {threshold:.1f}%)")
    if actual < threshold:
        failures.append(f"{filename}: {actual:.1f}% is below {threshold:.1f}%")

if failures:
    print("High-risk coverage requirements failed:", file=sys.stderr)
    print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
    raise SystemExit(1)
