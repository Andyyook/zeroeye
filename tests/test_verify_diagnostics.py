#!/usr/bin/env python3
"""Tests for tools.verify_diagnostics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import verify_diagnostics


class VerifyDiagnosticsTests(unittest.TestCase):
    def write_report(self, directory: Path, **overrides: object) -> Path:
        logd = directory / "build-test.logd"
        logd.write_bytes(b"logd")
        report = {
            "generated_at": "2026-06-16T15:23:47+00:00",
            "commit": "12345678",
            "diagnostic_logd": str(logd),
            "diagnostic_logd_error": None,
            "chunked": False,
            "chunk_size_bytes": None,
            "password": "redacted-in-test",
            "decrypt_command": "encryptly unpack diagnostic/build-test.logd <outdir> --password redacted-in-test",
            "total_modules": 2,
            "passed": 1,
            "failed": 1,
            "modules": [
                {
                    "name": "backend",
                    "status": "PASS",
                    "elapsed_seconds": 1.2,
                    "artifact": "backend/target/debug/backend",
                    "output": "",
                },
                {
                    "name": "frontend",
                    "status": "FAIL",
                    "elapsed_seconds": 0.5,
                    "artifact": None,
                    "output": "build failed",
                },
            ],
            "pr_note": "test",
        }
        report.update(overrides)
        report_path = directory / "build-test.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report_path

    def test_valid_report_passes_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp))
            result = verify_diagnostics.validate_diagnostic_json(report, check_git=False)
            payload = verify_diagnostics.build_payload([result], threshold=1)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["passed_modules"], 1)

    def test_invalid_json_reports_structural_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "broken.json"
            report.write_text("{not-json", encoding="utf-8")
            result = verify_diagnostics.validate_diagnostic_json(report, check_git=False)
            self.assertFalse(result.ok)
            self.assertIn("invalid JSON", result.errors[0])

    def test_schema_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp), passed=2)
            result = verify_diagnostics.validate_diagnostic_json(report, check_git=False)
            self.assertFalse(result.ok)
            self.assertTrue(any("PASS module count" in error for error in result.errors))

    def test_missing_logd_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp), diagnostic_logd="missing.logd")
            result = verify_diagnostics.validate_diagnostic_json(report, check_git=False)
            self.assertFalse(result.ok)
            self.assertTrue(any("not found" in error for error in result.errors))

    def test_threshold_failure_sets_payload_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp))
            result = verify_diagnostics.validate_diagnostic_json(report, check_git=False)
            payload = verify_diagnostics.build_payload([result], threshold=2)
            self.assertFalse(payload["ok"])

    def test_subprocess_errors_are_meaningful(self) -> None:
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, message = verify_diagnostics.run_subprocess(["missing-tool"])
        self.assertFalse(ok)
        self.assertEqual(message, "command not found: missing-tool")


if __name__ == "__main__":
    unittest.main()
