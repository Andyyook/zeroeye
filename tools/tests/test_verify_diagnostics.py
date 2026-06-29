#!/usr/bin/env python3
"""Tests for verify_diagnostics.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.verify_diagnostics import (
    DiagnosticValidationError,
    load_diagnostic_report,
    main,
    validate_diagnostic_payload,
)


def sample_report() -> dict:
    return {
        "generated_at": "2026-06-29T00:00:00+00:00",
        "commit": "abcd1234",
        "diagnostic_logd": "diagnostic/build-abcd1234.logd",
        "total_modules": 1,
        "passed": 1,
        "failed": 0,
        "modules": [
            {
                "name": "compliance",
                "status": "PASS",
                "elapsed_seconds": 1.2,
                "artifact": None,
                "output": "ok",
            }
        ],
    }


class VerifyDiagnosticsTests(unittest.TestCase):
    def test_valid_payload_passes(self) -> None:
        payload = validate_diagnostic_payload(sample_report(), "sample")
        self.assertEqual(payload["passed"], 1)

    def test_missing_keys_reported(self) -> None:
        broken = sample_report()
        del broken["modules"]
        with self.assertRaises(DiagnosticValidationError) as ctx:
            validate_diagnostic_payload(broken, "broken")
        self.assertIn("missing required keys", str(ctx.exception))

    def test_load_diagnostic_report_reads_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "build-test.json"
            path.write_text(json.dumps(sample_report()), encoding="utf-8")
            payload = load_diagnostic_report(path)
            self.assertEqual(payload["commit"], "abcd1234")

    def test_threshold_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = Path(tmp) / "diagnostic"
            diagnostic.mkdir()
            report_path = diagnostic / "build-test.json"
            report_path.write_text(json.dumps(sample_report()), encoding="utf-8")

            with mock.patch("sys.argv", ["verify_diagnostics.py", "--report", str(report_path), "--threshold", "2"]):
                exit_code = main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
