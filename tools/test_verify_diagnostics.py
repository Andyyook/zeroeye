#!/usr/bin/env python3
"""Tests for tools/verify_diagnostics.py"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from verify_diagnostics import (
    validate_schema,
    find_latest_diagnostic,
    run_verification,
)


@pytest.fixture
def valid_report(tmp_path):
    report = {
        "generated_at": "2026-06-27T00:00:00+00:00",
        "commit": "abc1234",
        "diagnostic_logd": "diagnostic/build-abc1234.logd",
        "diagnostic_logd_error": None,
        "chunked": False,
        "chunk_size_bytes": None,
        "password": None,
        "decrypt_command": None,
        "total_modules": 2,
        "passed": 1,
        "failed": 1,
        "modules": [
            {
                "name": "backend",
                "status": "PASS",
                "elapsed_seconds": 1.23,
                "artifact": "backend/target/debug/backend",
                "output": "Build successful",
            },
            {
                "name": "frontend",
                "status": "FAIL",
                "elapsed_seconds": 0.5,
                "artifact": None,
                "output": "npm install failed",
            },
        ],
        "pr_note": "Include the diagnostic log.",
    }
    p = tmp_path / "build-abc1234.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


@pytest.fixture
def invalid_schema_report(tmp_path):
    report = {
        "generated_at": "2026-06-27T00:00:00+00:00",
        "commit": "abc1234",
        "total_modules": 1,
        "passed": 1,
        "failed": 0,
    }
    p = tmp_path / "build-bad.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def test_validate_schema_valid(valid_report):
    data = json.loads(valid_report.read_text(encoding="utf-8"))
    errors = validate_schema(data)
    assert errors == []


def test_validate_schema_missing_modules(invalid_schema_report):
    data = json.loads(invalid_schema_report.read_text(encoding="utf-8"))
    errors = validate_schema(data)
    assert any("modules" in e for e in errors)


def test_validate_schema_bad_status(tmp_path):
    report = {
        "generated_at": "2026-06-27T00:00:00+00:00",
        "commit": "abc1234",
        "total_modules": 1,
        "passed": 1,
        "failed": 0,
        "modules": [
            {"name": "backend", "status": "UNKNOWN", "elapsed_seconds": 1.0, "artifact": None, "output": None},
        ],
    }
    p = tmp_path / "build-bad-status.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    data = json.loads(p.read_text(encoding="utf-8"))
    errors = validate_schema(data)
    assert any("invalid status" in e for e in errors)


def test_validate_schema_count_mismatch(tmp_path):
    report = {
        "generated_at": "2026-06-27T00:00:00+00:00",
        "commit": "abc1234",
        "total_modules": 2,
        "passed": 1,
        "failed": 1,
        "modules": [
            {"name": "a", "status": "PASS", "elapsed_seconds": 1.0, "artifact": None, "output": None},
        ],
    }
    p = tmp_path / "build-mismatch.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    data = json.loads(p.read_text(encoding="utf-8"))
    errors = validate_schema(data)
    assert any("total_modules does not match number of module entries" in e for e in errors)


def test_run_verification_valid(valid_report):
    code, report = run_verification(valid_report, threshold=0, json_output=True)
    assert code == 0
    assert report["valid"] is True
    assert report["passed"] == 1
    assert report["failed"] == 1


def test_run_verification_threshold_not_met(valid_report):
    code, report = run_verification(valid_report, threshold=2, json_output=True)
    assert code == 1
    assert report["threshold_met"] is False


def test_run_verification_missing_file(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    code, report = run_verification(missing, json_output=True)
    assert code == 1
    assert "not found" in report["error"]


def test_run_verification_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    code, report = run_verification(p, json_output=True)
    assert code == 1
    assert "Invalid JSON" in report["error"]


def test_find_latest_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr("verify_diagnostics.DIAGNOSTIC_DIR", tmp_path)
    (tmp_path / "build-old.json").write_text("{}", encoding="utf-8")
    (tmp_path / "build-new.json").write_text("{}", encoding="utf-8")
    import time
    time.sleep(0.05)
    latest = find_latest_diagnostic()
    assert latest is not None
    assert latest.name == "build-new.json"


def test_find_latest_diagnostic_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("verify_diagnostics.DIAGNOSTIC_DIR", tmp_path)
    assert find_latest_diagnostic() is None
