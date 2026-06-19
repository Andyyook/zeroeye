#!/usr/bin/env python3
"""verify_diagnostics.py — Verify build.py generates full diagnostic artifacts.

Bounty #1: Ensures diagnostics are always produced, even on build failure.
Adds argparse CLI, subprocess error recovery, JSON output, threshold support,
and diagnostic JSON schema validation.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DIR = ROOT / "diagnostic"

REQUIRED_JSON_KEYS = ["generated_at", "commit", "diagnostic_logd",
                      "total_modules", "passed", "failed", "modules"]


def run_build(verbose=False):
    """Run build.py with error recovery. Returns (success, result_or_error)."""
    print("Running python3 build.py...", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "build.py"],
            cwd=str(ROOT),
            capture_output=True, text=True, timeout=300,
        )
        if verbose and result.stdout:
            print(f"  build stdout (tail):\n{result.stdout[-500:]}")
        if verbose and result.stderr:
            print(f"  build stderr (tail):\n{result.stderr[-500:]}")
        return (result.returncode == 0, result)
    except subprocess.TimeoutExpired:
        msg = "build.py timed out after 300s"
        print(f"  ERROR: {msg}")
        return (False, msg)
    except FileNotFoundError:
        msg = "build.py not found in project root"
        print(f"  ERROR: {msg}")
        return (False, msg)
    except PermissionError:
        msg = "permission denied running build.py"
        print(f"  ERROR: {msg}")
        return (False, msg)
    except OSError as e:
        msg = f"OS error running build.py: {e}"
        print(f"  ERROR: {msg}")
        return (False, msg)


def validate_diagnostic_json(path):
    """Validate diagnostic JSON schema. Returns (ok, data_or_error)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return (False, f"cannot parse {path.name}: invalid JSON: {e}")
    except OSError as e:
        return (False, f"cannot read {path.name}: {e}")

    if not isinstance(data, dict):
        return (False, f"{path.name}: root is not an object")

    missing = [k for k in REQUIRED_JSON_KEYS if k not in data]
    if missing:
        return (False, f"{path.name}: missing keys: {missing}")

    if not isinstance(data["modules"], list):
        return (False, f"{path.name}: 'modules' is not a list")

    if not isinstance(data["passed"], int) or not isinstance(data["failed"], int):
        return (False, f"{path.name}: 'passed'/'failed' must be integers")

    return (True, data)


def verify(threshold=0, verbose=False, json_output=False):
    """Main verification logic. Returns (exit_code, report_dict)."""
    report = {
        "build": {"ok": False, "error": None},
        "diagnostics": {"json_found": 0, "logd_found": 0,
                        "schema_valid": False, "schema_error": None,
                        "latest_json": None, "latest_logd": None,
                        "modules": 0, "passed": 0, "failed": 0},
        "threshold": {"required": threshold, "actual_passed": 0, "met": False},
        "overall_ok": False,
    }

    build_ok, build_result = run_build(verbose=verbose)
    report["build"]["ok"] = build_ok
    if not build_ok and isinstance(build_result, str):
        report["build"]["error"] = build_result
    elif not build_ok:
        report["build"]["error"] = f"build exit code {build_result.returncode}"

    if not DIAGNOSTIC_DIR.exists():
        report["diagnostics"]["schema_error"] = "diagnostic/ directory not found"
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            print("  FAIL: diagnostic/ directory not found")
        return (1, report)

    json_files = sorted(DIAGNOSTIC_DIR.glob("build-*.json"))
    logd_files = sorted(DIAGNOSTIC_DIR.glob("build-*.logd"))
    report["diagnostics"]["json_found"] = len(json_files)
    report["diagnostics"]["logd_found"] = len(logd_files)

    if not json_files:
        report["diagnostics"]["schema_error"] = "no build-*.json files found"
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            print("  FAIL: no build-*.json diagnostic files found")
        return (1, report)

    latest_json = json_files[-1]
    latest_logd = logd_files[-1] if logd_files else None
    report["diagnostics"]["latest_json"] = latest_json.name
    report["diagnostics"]["latest_logd"] = latest_logd.name if latest_logd else None

    ok, data_or_err = validate_diagnostic_json(latest_json)
    report["diagnostics"]["schema_valid"] = ok
    if not ok:
        report["diagnostics"]["schema_error"] = data_or_err
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            print(f"  FAIL: {data_or_err}")
        return (1, report)

    report["diagnostics"]["modules"] = len(data_or_err["modules"])
    report["diagnostics"]["passed"] = data_or_err["passed"]
    report["diagnostics"]["failed"] = data_or_err["failed"]

    if latest_logd:
        logd_path = DIAGNOSTIC_DIR / latest_logd.name
        if not logd_path.exists():
            report["diagnostics"]["schema_error"] = f"referenced logd missing: {logd_path}"
            if json_output:
                print(json.dumps(report, indent=2))
            else:
                print(f"  FAIL: referenced logd file missing: {logd_path}")
            return (1, report)

    actual_passed = data_or_err["passed"]
    report["threshold"]["actual_passed"] = actual_passed
    report["threshold"]["met"] = actual_passed >= threshold

    overall = build_ok and ok and (actual_passed >= threshold)
    report["overall_ok"] = overall

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print(f"  JSON valid: {len(data_or_err['modules'])} module(s), "
              f"{data_or_err['passed']} passed, {data_or_err['failed']} failed")
        if latest_logd:
            print(f"  logd size: {latest_logd.stat().st_size:,} bytes")
        status = "PASS" if overall else "FAIL"
        print(f"\n  {status} — diagnostics verified: {latest_json.name}"
              + (f" / {latest_logd.name}" if latest_logd else ""))
        if threshold > 0:
            print(f"  threshold: {actual_passed}/{threshold} modules passed "
                  f"({'met' if actual_passed >= threshold else 'NOT met'})")

    return (0 if overall else 1, report)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify build.py generates full diagnostic artifacts.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show build.py stdout/stderr tails")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output machine-readable JSON report")
    parser.add_argument("--threshold", "-t", type=int, default=0,
                        help="Minimum passing modules required (default: 0)")
    return parser.parse_args()


def main():
    args = parse_args()
    exit_code, _ = verify(
        threshold=args.threshold, verbose=args.verbose, json_output=args.json)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
