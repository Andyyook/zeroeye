#!/usr/bin/env python3
"""
Verify build diagnostic artifacts for the Tent of Trials platform.

Reads the latest (or specified) diagnostic JSON report from the diagnostic/
directory, validates its schema, and reports module-level build results.

Usage:
    python3 tools/verify_diagnostics.py                  Verify latest diagnostics
    python3 tools/verify_diagnostics.py --verbose         Show detailed failure output
    python3 tools/verify_diagnostics.py --json            JSON output for machines
    python3 tools/verify_diagnostics.py --threshold 3     Require >=3 passing modules
    python3 tools/verify_diagnostics.py -f diagnostic/build-abc123.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DIR = ROOT / "diagnostic"

REQUIRED_TOP_LEVEL_FIELDS = {
    "generated_at": str,
    "commit": str,
    "total_modules": int,
    "passed": int,
    "failed": int,
    "modules": list,
}

REQUIRED_MODULE_FIELDS = {
    "name": str,
    "status": str,
    "elapsed_seconds": (int, float),
    "artifact": (str, type(None)),
    "output": (str, type(None)),
}

VALID_STATUSES = {"PASS", "FAIL"}


def find_latest_diagnostic() -> Optional[Path]:
    if not DIAGNOSTIC_DIR.exists():
        return None
    json_files = sorted(
        DIAGNOSTIC_DIR.glob("build-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return json_files[0] if json_files else None


def validate_schema(data: dict) -> List[str]:
    errors: List[str] = []

    for field, expected_type in REQUIRED_TOP_LEVEL_FIELDS.items():
        if field not in data:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type: expected {expected_type.__name__}, "
                f"got {type(data[field]).__name__}"
            )

    if "modules" in data and isinstance(data["modules"], list):
        for i, module in enumerate(data["modules"]):
            mod_name = module.get("name", "?") if isinstance(module, dict) else "?"
            if not isinstance(module, dict):
                errors.append(f"Module {i}: not a JSON object")
                continue
            for field, expected_type in REQUIRED_MODULE_FIELDS.items():
                if field not in module:
                    errors.append(f"Module {i} ({mod_name}): missing field '{field}'")
                elif not isinstance(module[field], expected_type):
                    errors.append(
                        f"Module {i} ({mod_name}): field '{field}' has wrong type"
                    )
            if "status" in module and module["status"] not in VALID_STATUSES:
                errors.append(
                    f"Module {i} ({mod_name}): invalid status '{module['status']}'"
                )

    if all(k in data for k in ("total_modules", "passed", "failed")):
        if data["total_modules"] != data["passed"] + data["failed"]:
            errors.append(
                "total_modules does not equal passed + failed "
                f"({data['total_modules']} != {data['passed']} + {data['failed']})"
            )

    if "modules" in data and isinstance(data["modules"], list):
        if "total_modules" in data and data["total_modules"] != len(data["modules"]):
            errors.append(
                "total_modules does not match number of module entries "
                f"({data['total_modules']} != {len(data['modules'])})"
            )

    return errors


def verify_commit_exists(commit_id: str) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", commit_id],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip() or result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "git rev-parse timed out"
    except FileNotFoundError:
        return False, "git executable not found"
    except Exception as e:
        return False, str(e)


def run_verification(
    diagnostic_path: Path,
    threshold: int = 0,
    verbose: bool = False,
    json_output: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    report: Dict[str, Any] = {
        "diagnostic_file": str(diagnostic_path),
        "valid": False,
        "schema_errors": [],
        "modules": [],
        "passed": 0,
        "failed": 0,
        "total": 0,
        "threshold_met": False,
        "commit_verified": False,
        "commit_error": None,
        "error": None,
    }

    try:
        text = diagnostic_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except FileNotFoundError:
        report["error"] = f"Diagnostic file not found: {diagnostic_path}"
        return _format_result(report, json_output, 1)
    except json.JSONDecodeError as exc:
        report["error"] = f"Invalid JSON in {diagnostic_path}: {exc}"
        return _format_result(report, json_output, 1)
    except Exception as exc:
        report["error"] = f"Failed to read {diagnostic_path}: {exc}"
        return _format_result(report, json_output, 1)

    schema_errors = validate_schema(data)
    report["schema_errors"] = schema_errors
    report["valid"] = len(schema_errors) == 0

    if not report["valid"]:
        report["error"] = "Schema validation failed"
        return _format_result(report, json_output, 1)

    commit_id = data.get("commit", "00000000")
    commit_ok, commit_err = verify_commit_exists(commit_id)
    report["commit_verified"] = commit_ok
    report["commit_error"] = commit_err or None

    modules = data.get("modules", [])
    report["modules"] = modules
    report["total"] = len(modules)
    report["passed"] = sum(1 for m in modules if m.get("status") == "PASS")
    report["failed"] = sum(1 for m in modules if m.get("status") == "FAIL")
    report["threshold_met"] = report["passed"] >= threshold

    if json_output:
        return 0 if report["threshold_met"] else 1, report

    try:
        display_path = diagnostic_path.relative_to(ROOT)
    except ValueError:
        display_path = diagnostic_path

    print(f"\nVerifying diagnostic: {display_path}")
    print(f"Commit: {commit_id}")
    print(f"Generated: {data.get('generated_at', 'unknown')}")
    print()
    print(f"Total modules: {report['total']}")
    print(f"Passed: {report['passed']}")
    print(f"Failed: {report['failed']}")
    print()

    for module in modules:
        name = module.get("name", "unknown")
        status = module.get("status", "UNKNOWN")
        elapsed = module.get("elapsed_seconds", 0)
        icon = "\u2713" if status == "PASS" else "\u2717"
        color_pass = "\033[92m"
        color_fail = "\033[91m"
        reset = "\033[0m"
        code = color_pass if status == "PASS" else color_fail
        print(f"  {icon} {name}: {code}{status}{reset} ({elapsed:.2f}s)")
        if status != "PASS" and verbose and module.get("output"):
            lines = module["output"].strip().split("\n")
            print("       last output:")
            for line in lines[-5:]:
                print(f"       {line}")

    print()
    if not commit_ok:
        print(f"  WARNING: commit verification failed: {commit_err}")
    if report["threshold_met"]:
        print(f"  Threshold met: {report['passed']} passed (required: {threshold})")
        return 0, report
    print(f"  Threshold not met: {report['passed']} passed (required: {threshold})")
    return 1, report


def _format_result(report: Dict[str, Any], json_output: bool, code: int) -> Tuple[int, Dict[str, Any]]:
    if json_output:
        return code, report
    print(f"ERROR: {report['error']}")
    for err in report.get("schema_errors", []):
        print(f"  - {err}")
    return code, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify build diagnostic artifacts for Tent of Trials"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including failure logs",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON for machine consumption",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=0,
        help="Minimum number of passing modules required (default: 0)",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Path to diagnostic JSON file (default: latest in diagnostic/)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.file:
        diagnostic_path = Path(args.file)
        if not diagnostic_path.is_absolute():
            diagnostic_path = ROOT / diagnostic_path
    else:
        diagnostic_path = find_latest_diagnostic()
        if diagnostic_path is None:
            msg = "No diagnostic files found in diagnostic/"
            if args.json:
                print(json.dumps({"error": msg}, indent=2))
            else:
                print(f"ERROR: {msg}")
            return 1

    exit_code, report = run_verification(
        diagnostic_path,
        threshold=args.threshold,
        verbose=args.verbose,
        json_output=args.json,
    )

    if args.json:
        print(json.dumps(report, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
