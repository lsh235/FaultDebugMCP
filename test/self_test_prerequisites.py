#!/usr/bin/env python3
"""Verify self-test stops before compilation when the installed setup is absent."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faultdebug.self_test import collect_self_test_report


def main() -> int:
    env = {
        "FAULTDEBUG_REAL_CC": "/nonexistent/faultdebug-self-test-compiler",
        "FAULTDEBUG_RUNTIME_DIR": "/nonexistent/faultdebug-self-test-runtime",
    }
    with patch.dict(os.environ, env):
        report = collect_self_test_report()
    checks = {row["name"]: row for row in report["checks"]}
    assert report["schema_name"] == "faultdebug.self_test"
    assert report["status"] == "NOT RUN", json.dumps(report, indent=2)
    assert checks["compiler"]["status"] in {"FAIL", "NOT RUN"}, checks["compiler"]
    assert checks["runtime_library"]["status"] == "NOT RUN", checks["runtime_library"]
    assert checks["compile"]["status"] == "NOT RUN", checks["compile"]
    assert checks["capture"]["status"] == "NOT RUN", checks["capture"]
    print("self-test prerequisite short-circuit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
