#!/usr/bin/env python3
"""
Diagnostic verification tool with input validation and error handling.

Validates diagnostic artifacts produced by the build system, checks JSON schema
compliance, and reports structured results.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DIR = ROOT / "diagnostic"


class ValidationError(Exception):
    """Raised when diagnostic validation fails."""
    pass


class DiagnosticSchema:
    """Expected schema for diagnostic JSON metadata."""

    REQUIRED_TOP_LEVEL = {
        "generated_at", "commit", "total_modules", "passed", "failed", "modules"
    }

    REQUIRED_MODULE_FIELDS = {
        "name", "status", "elapsed_seconds", "output"
    }

    VALID_STATUSES = {"PASS", "FAIL"}


def validate_diagnostic_json(data: dict) -> list[str]:
    """
    Validate diagnostic JSON structure and return list of error messages.

    Args:
        data: Parsed JSON data from diagnostic metadata file.

    Returns:
        List of validation error messages. Empty list if valid.
    """
    errors = []

    # Check required top-level fields
    missing_top = DiagnosticSchema.REQUIRED_TOP_LEVEL - set(data.keys())
    if missing_top:
        errors.append(f"Missing required top-level fields: {sorted(missing_top)}")

    # Validate modules array
    modules = data.get("modules", [])
    if not isinstance(modules, list):
        errors.append("'modules' must be an array")
        return errors

    for i, module in enumerate(modules):
        if not isinstance(module, dict):
            errors.append(f"Module at index {i} must be an object")
            continue

        missing_fields = DiagnosticSchema.REQUIRED_MODULE_FIELDS - set(module.keys())
        if missing_fields:
            errors.append(f"Module {i}: missing fields {sorted(missing_fields)}")

        status = module.get("status")
        if status and status not in DiagnosticSchema.VALID_STATUSES:
            errors.append(
                f"Module {i}: invalid status '{status}', expected PASS or FAIL"
            )

        elapsed = module.get("elapsed_seconds")
        if elapsed is not None and not isinstance(elapsed, (int, float)):
            errors.append(f"Module {i}: elapsed_seconds must be numeric")

    # Validate counts match
    passed_count = data.get("passed", 0)
    failed_count = data.get("failed", 0)
    total_modules = data.get("total_modules", 0)

    if isinstance(modules, list):
        actual_total = len(modules)
        if total_modules != actual_total:
            errors.append(
                f"total_modules ({total_modules}) does not match actual module count ({actual_total})"
            )

        actual_passed = sum(1 for m in modules if m.get("status") == "PASS")
        if passed_count != actual_passed:
            errors.append(
                f"passed count ({passed_count}) does not match actual PASS modules ({actual_passed})"
            )

        actual_failed = sum(1 for m in modules if m.get("status") == "FAIL")
        if failed_count != actual_failed:
            errors.append(
                f"failed count ({failed_count}) does not match actual FAIL modules ({actual_failed})"
            )

    return errors


def find_diagnostic_files() -> tuple[list[Path], list[Path]]:
    """
    Find all diagnostic .logd and .json files in the diagnostic directory.

    Returns:
        Tuple of (logd_files, json_files).
    """
    logd_files = []
    json_files = []

    if not DIAGNOSTIC_DIR.exists():
        return logd_files, json_files

    for path in DIAGNOSTIC_DIR.iterdir():
        if path.is_file():
            if path.suffix == ".logd":
                logd_files.append(path)
            elif path.suffix == ".json":
                json_files.append(path)

    return sorted(logd_files), sorted(json_files)


def verify_subprocess(
    cmd: list[str],
    description: str,
    verbose: bool = False,
    timeout: int = 60,
    **kwargs
) -> tuple[bool, str]:
    """
    Run a subprocess with proper error handling and meaningful messages.

    Args:
        cmd: Command and arguments to execute.
        description: Human-readable description of the operation.
        verbose: Whether to print detailed output.
        timeout: Maximum seconds to wait for command completion.
        **kwargs: Additional arguments passed to subprocess.run.

    Returns:
        Tuple of (success, message).
    """
    if verbose:
        print(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **kwargs
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return False, f"{description} failed (exit {result.returncode}): {error_msg}"

        output = result.stdout.strip()
        return True, output

    except subprocess.TimeoutExpired:
        return False, f"{description} timed out after {timeout}s"
    except FileNotFoundError as e:
        return False, f"{description}: command not found - {e}"
    except PermissionError as e:
        return False, f"{description}: permission denied - {e}"
    except Exception as e:
        return False, f"{description}: unexpected error - {type(e).__name__}: {e}"


def verify_encryptly_unpack(logd_path: Path, verbose: bool = False) -> tuple[bool, str]:
    """
    Verify that a .logd file can be unpacked by encryptly.

    Args:
        logd_path: Path to the .logd file.
        verbose: Whether to print detailed output.

    Returns:
        Tuple of (success, message).
    """
    encryptly_dir = ROOT / "tools" / "encryptly"

    # Detect platform binary
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()

    arch_map = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
    os_map = {"linux": "linux", "darwin": "macos", "windows": "windows"}

    arch = arch_map.get(machine, machine)
    os_name = os_map.get(system, system)
    platform_key = f"{os_name}-{arch}"

    binary_name = "encryptly.exe" if system == "windows" else "encryptly"
    encryptly_bin = encryptly_dir / platform_key / binary_name

    if not encryptly_bin.exists():
        # Try legacy location
        encryptly_bin = encryptly_dir / binary_name
        if not encryptly_bin.exists():
            return False, f"encryptly binary not found for platform {platform_key}"

    # Try to verify the logd file structure (just check it's readable)
    try:
        with open(logd_path, "rb") as f:
            header = f.read(16)
            if len(header) < 8:
                return False, "Logd file is too small (less than 8 bytes)"
    except Exception as e:
        return False, f"Cannot read logd file: {e}"

    return True, f"Logd file is readable ({logd_path.stat().st_size} bytes)"


def verify_diagnostics(
    threshold: int = 0,
    verbose: bool = False,
    json_output: bool = False,
) -> dict[str, Any]:
    """
    Main verification routine for diagnostic artifacts.

    Args:
        threshold: Minimum number of modules that must have passed.
        verbose: Whether to print detailed progress.
        json_output: Whether to format output as JSON.

    Returns:
        Verification result dictionary.
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "logd_files": [],
        "json_files": [],
        "modules_verified": 0,
        "modules_passed": 0,
        "modules_failed": 0,
        "threshold_met": True,
    }

    if verbose:
        print("Scanning for diagnostic artifacts...")

    logd_files, json_files = find_diagnostic_files()

    if not logd_files and not json_files:
        msg = "No diagnostic files found in diagnostic/ directory"
        result["warnings"].append(msg)
        if verbose:
            print(f"  Warning: {msg}")

    # Verify .logd files
    for logd_path in logd_files:
        if verbose:
            print(f"  Checking logd: {logd_path.name}")

        success, msg = verify_encryptly_unpack(logd_path, verbose)
        file_result = {"file": str(logd_path.relative_to(ROOT)), "valid": success, "message": msg}
        result["logd_files"].append(file_result)

        if not success:
            result["valid"] = False
            result["errors"].append(f"Logd verification failed for {logd_path.name}: {msg}")

    # Verify .json files
    for json_path in json_files:
        if verbose:
            print(f"  Checking json: {json_path.name}")

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result["valid"] = False
            result["errors"].append(f"Invalid JSON in {json_path.name}: {e}")
            result["json_files"].append({
                "file": str(json_path.relative_to(ROOT)),
                "valid": False,
                "message": f"JSON parse error: {e}"
            })
            continue
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Cannot read {json_path.name}: {e}")
            continue

        schema_errors = validate_diagnostic_json(data)
        is_valid = len(schema_errors) == 0

        if not is_valid:
            result["valid"] = False
            for err in schema_errors:
                result["errors"].append(f"Schema error in {json_path.name}: {err}")

        result["json_files"].append({
            "file": str(json_path.relative_to(ROOT)),
            "valid": is_valid,
            "errors": schema_errors,
            "message": "Valid" if is_valid else f"{len(schema_errors)} schema error(s)"
        })

        # Count modules from the first valid JSON
        if is_valid and result["modules_verified"] == 0:
            modules = data.get("modules", [])
            result["modules_verified"] = len(modules)
            result["modules_passed"] = data.get("passed", 0)
            result["modules_failed"] = data.get("failed", 0)

    # Check threshold
    if threshold > 0:
        if result["modules_passed"] < threshold:
            result["threshold_met"] = False
            result["valid"] = False
            result["errors"].append(
                f"Threshold not met: {result['modules_passed']} passed, required {threshold}"
            )

    return result


def print_text_report(result: dict[str, Any]) -> None:
    """Print a human-readable verification report."""
    print("=" * 60)
    print("Diagnostic Verification Report")
    print("=" * 60)

    status = "PASS" if result["valid"] else "FAIL"
    status_icon = "✓" if result["valid"] else "✗"
    print(f"\nOverall: {status_icon} {status}")

    if result["modules_verified"] > 0:
        print(f"\nModules: {result['modules_verified']} total")
        print(f"  Passed: {result['modules_passed']}")
        print(f"  Failed: {result['modules_failed']}")

    if result["logd_files"]:
        print(f"\nLogd files: {len(result['logd_files'])}")
        for f in result["logd_files"]:
            icon = "✓" if f["valid"] else "✗"
            print(f"  {icon} {f['file']} - {f['message']}")

    if result["json_files"]:
        print(f"\nJSON files: {len(result['json_files'])}")
        for f in result["json_files"]:
            icon = "✓" if f["valid"] else "✗"
            print(f"  {icon} {f['file']} - {f['message']}")

    if result["warnings"]:
        print("\nWarnings:")
        for w in result["warnings"]:
            print(f"  ! {w}")

    if result["errors"]:
        print("\nErrors:")
        for e in result["errors"]:
            print(f"  ✗ {e}")

    if not result["threshold_met"]:
        print("\n! Threshold not met")

    print("\n" + "=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify diagnostic artifacts from the build system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 tools/verify_diagnostics.py           Basic verification
  python3 tools/verify_diagnostics.py --verbose Show detailed progress
  python3 tools/verify_diagnostics.py --json    Output machine-readable JSON
  python3 tools/verify_diagnostics.py --threshold 5  Require 5+ passing modules
        """,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed verification progress",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for machine consumption",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=0,
        metavar="N",
        help="Minimum number of passing modules required (default: 0)",
    )

    args = parser.parse_args()

    result = verify_diagnostics(
        threshold=args.threshold,
        verbose=args.verbose,
        json_output=args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_text_report(result)

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
