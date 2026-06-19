#!/usr/bin/env python3
"""
verify_diagnostics.py - Diagnostic Verification Tool

Validates diagnostic build artifacts (.logd and .json) produced by build.py.
Checks that JSON diagnostic files are structurally valid, subprocess
operations complete without error, and meets a configurable threshold of
passing modules.

Usage:
    python tools/verify_diagnostics.py
    python tools/verify_diagnostics.py --verbose
    python tools/verify_diagnostics.py --json
    python tools/verify_diagnostics.py --threshold 7
    python tools/verify_diagnostics.py --diagnostic-dir /path/to/diagnostic
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIAGNOSTIC_DIR = ROOT / "diagnostic"

REQUIRED_JSON_KEYS = {"modules", "timestamp", "build_id"}
REQUIRED_MODULE_KEYS = {"name", "status", "duration_seconds"}

VALID_STATUSES = {"PASS", "FAIL", "SKIP", "ERROR"}


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        return None
    except PermissionError:
        print(f"ERROR: Permission denied: {path}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"ERROR: Could not read {path}: {e}", file=sys.stderr)
        return None


def validate_json_schema(data: dict, path: Path, verbose: bool = False) -> list[str]:
    errors = []
    for key in REQUIRED_JSON_KEYS:
        if key not in data:
            errors.append(f"Missing required key '{key}' in {path.name}")

    if "modules" in data:
        if not isinstance(data["modules"], list):
            errors.append(f"'modules' must be a list in {path.name}")
        else:
            for i, mod in enumerate(data["modules"]):
                if not isinstance(mod, dict):
                    errors.append(f"Module {i} in {path.name} is not a dict")
                    continue
                for key in REQUIRED_MODULE_KEYS:
                    if key not in mod:
                        errors.append(f"Module {i} missing '{key}' in {path.name}")
                if "status" in mod and mod["status"] not in VALID_STATUSES:
                    errors.append(f"Module {i} has invalid status '{mod.get('status')}' in {path.name}")

    if "timestamp" in data and not isinstance(data["timestamp"], (str, int, float)):
        errors.append(f"'timestamp' must be string or number in {path.name}")

    if "build_id" in data and not isinstance(data["build_id"], str):
        errors.append(f"'build_id' must be a string in {path.name}")

    return errors


def run_encryptly_check(diagnostic_dir: Path, verbose: bool = False) -> tuple[bool, str]:
    encryptly_path = ROOT / "tools" / "encryptly"
    if not encryptly_path.exists():
        msg = "encryptly binary not found"
        if verbose:
            print(f"  SKIP: {msg}")
        return False, msg

    try:
        result = subprocess.run(
            [str(encryptly_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, "encryptly is functional"
        else:
            msg = f"encryptly returned exit code {result.returncode}"
            if verbose and result.stderr:
                msg += f": {result.stderr.strip()[:200]}"
            return False, msg
    except subprocess.TimeoutExpired:
        return False, "encryptly timed out"
    except FileNotFoundError:
        return False, "encryptly binary not found at expected path"
    except PermissionError:
        return False, "permission denied executing encryptly"
    except OSError as e:
        return False, f"os error running encryptly: {e}"


def verify_diagnostics(
    diagnostic_dir: Path,
    verbose: bool = False,
    output_json: bool = False,
    threshold: int = 0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passed": True,
        "errors": [],
        "warnings": [],
        "json_files_found": 0,
        "logd_files_found": 0,
        "modules_passing": 0,
        "modules_total": 0,
        "threshold": threshold,
        "threshold_met": True,
    }

    if not diagnostic_dir.exists():
        result["errors"].append(f"Diagnostic directory not found: {diagnostic_dir}")
        result["passed"] = False
        return result

    json_files = list(diagnostic_dir.glob("*.json"))
    logd_files = list(diagnostic_dir.glob("*.logd"))
    result["json_files_found"] = len(json_files)
    result["logd_files_found"] = len(logd_files)

    if verbose:
        print(f"Diagnostic directory: {diagnostic_dir}")
        print(f"  JSON files: {len(json_files)}")
        print(f"  LOGD files: {len(logd_files)}")

    if not json_files:
        result["warnings"].append("No .json diagnostic files found")
        if verbose:
            print("  WARNING: No .json diagnostic files found")

    for jf in json_files:
        data = load_json(jf)
        if data is None:
            result["errors"].append(f"Failed to load {jf.name}")
            result["passed"] = False
            continue

        schema_errors = validate_json_schema(data, jf, verbose)
        if schema_errors:
            result["errors"].extend(schema_errors)
            result["passed"] = False
            if verbose:
                for err in schema_errors:
                    print(f"  SCHEMA ERROR: {err}")

        if "modules" in data and isinstance(data["modules"], list):
            result["modules_total"] += len(data["modules"])
            for mod in data["modules"]:
                if isinstance(mod, dict) and mod.get("status") == "PASS":
                    result["modules_passing"] += 1

        if verbose:
            print(f"  {jf.name}: {len(data.get('modules', []))} modules, "
                  f"build_id={data.get('build_id', 'N/A')}")

    encryptly_ok, encryptly_msg = run_encryptly_check(diagnostic_dir, verbose)
    if not encryptly_ok:
        result["warnings"].append(encryptly_msg)
        if verbose:
            print(f"  WARNING: {encryptly_msg}")

    if result["modules_total"] > 0 and result["modules_passing"] < threshold:
        result["threshold_met"] = False
        result["passed"] = False
        msg = (f"Threshold not met: {result['modules_passing']}/{result['modules_total']} "
               f"modules passing (threshold: {threshold})")
        result["errors"].append(msg)
        if verbose:
            print(f"  FAIL: {msg}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify diagnostic build artifacts"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed verification output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON for machine consumption",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Minimum number of passing modules required (default: 0)",
    )
    parser.add_argument(
        "--diagnostic-dir",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_DIR,
        help=f"Path to diagnostic directory (default: {DEFAULT_DIAGNOSTIC_DIR})",
    )
    args = parser.parse_args()

    result = verify_diagnostics(
        diagnostic_dir=args.diagnostic_dir,
        verbose=args.verbose,
        output_json=args.output_json,
        threshold=args.threshold,
    )

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print(f"PASS: Diagnostics verified. "
                  f"{result['modules_passing']}/{result['modules_total']} modules passing.")
        else:
            print(f"FAIL: Diagnostics verification failed with {len(result['errors'])} error(s):")
            for err in result["errors"]:
                print(f"  - {err}")
            for warn in result["warnings"]:
                print(f"  WARNING: {warn}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
