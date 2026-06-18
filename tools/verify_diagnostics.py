#!/usr/bin/env python3
"""verify_diagnostics.py — Verify build.py generates full diagnostic artifacts.

Bounty #1: Ensures diagnostics are always produced, even on build failure.
"""

import subprocess, sys, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DIR = ROOT / "diagnostic"

def main():
    # Step 1: run the build
    print("Running python3 build.py...", flush=True)
    result = subprocess.run(
        [sys.executable, "build.py"],
        cwd=str(ROOT),
        capture_output=True, text=True, timeout=300,
    )
    build_ok = result.returncode == 0
    if build_ok:
        print("  Build passed.")
    else:
        print(f"  Build FAILED (exit code {result.returncode}).")
        print(f"  stderr: {result.stderr[:500]}")

    # Step 2: check for diagnostic artifacts
    if not DIAGNOSTIC_DIR.exists():
        print("  FAIL: diagnostic/ directory not found")
        sys.exit(1)

    json_files = sorted(DIAGNOSTIC_DIR.glob("build-*.json"))
    logd_files = sorted(DIAGNOSTIC_DIR.glob("build-*.logd"))

    if not json_files:
        print("  FAIL: no build-*.json diagnostic files found")
        sys.exit(1)

    if not logd_files:
        print("  FAIL: no build-*.logd diagnostic files found")
        sys.exit(1)

    latest_json = json_files[-1]
    latest_logd = logd_files[-1]

    print(f"  Found {len(json_files)} JSON diagnostic(s)")
    print(f"  Found {len(logd_files)} logd diagnostic(s)")

    # Step 3: validate latest JSON
    try:
        with open(latest_json) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  FAIL: cannot parse {latest_json}: {e}")
        sys.exit(1)

    required_keys = ["generated_at", "commit", "diagnostic_logd",
                     "total_modules", "passed", "failed", "modules"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"  FAIL: JSON missing keys: {missing}")
        sys.exit(1)

    if not isinstance(data["modules"], list):
        print("  FAIL: JSON 'modules' is not a list")
        sys.exit(1)

    print(f"  JSON valid: {len(data['modules'])} module(s), "
          f"{data['passed']} passed, {data['failed']} failed")

    # Step 4: verify logd exists
    logd_path = DIAGNOSTIC_DIR / Path(data["diagnostic_logd"]).name
    if not logd_path.exists():
        print(f"  FAIL: referenced logd file missing: {logd_path}")
        sys.exit(1)

    logd_size = logd_path.stat().st_size
    print(f"  logd size: {logd_size:,} bytes")

    # Step 5: summary
    print(f"\n  {'PASS' if build_ok else 'BUILD_FAILED_BUT_DIAGNOSTICS_OK'} "
          f"— diagnostics verified: {latest_json.name} / {logd_path.name}")

    return 0 if build_ok else 1

if __name__ == "__main__":
    sys.exit(main())
