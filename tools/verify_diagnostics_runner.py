#!/usr/bin/env python3
"""Main entry point for diagnostics verification."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from verify_diagnostics import load_diagnostic


def run_subprocess(cmd: list[str], verbose: bool) -> tuple[int, str, str]:
    """Run subprocess with error handling."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out: {' '.join(cmd)}"
    except OSError as e:
        return -1, "", f"OS error: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify diagnostic build results")
    parser.add_argument("diagnostic_file", type=Path, help="Path to diagnostic JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--threshold", type=int, default=0, help="Min passing modules")
    args = parser.parse_args()

    data, errors = load_diagnostic(args.diagnostic_file, args.verbose)
    result = {"success": False, "errors": errors, "passed": 0, "threshold": args.threshold}

    if data and not errors:
        result["passed"] = data.get("passed", 0)
        result["success"] = result["passed"] >= args.threshold
        if args.verbose:
            for mod in data.get("modules", []):
                print(f"{mod['name']}: {mod['status']}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if errors:
            for e in errors:
                print(f"Error: {e}", file=sys.stderr)
        print(f"Passed: {result['passed']}/{args.threshold} threshold")

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
