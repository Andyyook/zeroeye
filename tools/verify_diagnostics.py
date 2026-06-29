#!/usr/bin/env python3
"""Validate Tent of Trials diagnostic build JSON reports."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("verify_diagnostics")

REQUIRED_ROOT_KEYS = {
    "generated_at",
    "commit",
    "diagnostic_logd",
    "total_modules",
    "passed",
    "failed",
    "modules",
}
REQUIRED_MODULE_KEYS = {"name", "status", "elapsed_seconds", "output"}


class DiagnosticValidationError(Exception):
    """Raised when a diagnostic JSON report is structurally invalid."""


def validate_diagnostic_payload(payload: Any, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DiagnosticValidationError(f"{source}: root value must be a JSON object")

    missing = sorted(REQUIRED_ROOT_KEYS - payload.keys())
    if missing:
        raise DiagnosticValidationError(f"{source}: missing required keys: {', '.join(missing)}")

    modules = payload["modules"]
    if not isinstance(modules, list):
        raise DiagnosticValidationError(f"{source}: modules must be an array")

    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            raise DiagnosticValidationError(f"{source}: modules[{index}] must be an object")
        module_missing = sorted(REQUIRED_MODULE_KEYS - module.keys())
        if module_missing:
            raise DiagnosticValidationError(
                f"{source}: modules[{index}] missing keys: {', '.join(module_missing)}"
            )
        status = module.get("status")
        if status not in {"PASS", "FAIL"}:
            raise DiagnosticValidationError(
                f"{source}: modules[{index}].status must be PASS or FAIL, got {status!r}"
            )

    if not isinstance(payload["passed"], int) or not isinstance(payload["failed"], int):
        raise DiagnosticValidationError(f"{source}: passed/failed must be integers")

    return payload


def load_diagnostic_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiagnosticValidationError(f"{path}: invalid JSON ({exc.msg})") from exc
    return validate_diagnostic_payload(payload, str(path))


def discover_reports(diagnostic_dir: Path) -> list[Path]:
    reports = [
        path
        for path in sorted(diagnostic_dir.glob("build-*.json"))
        if not path.name.endswith("-metadata.json")
    ]
    if not reports:
        raise DiagnosticValidationError(f"No diagnostic JSON reports found in {diagnostic_dir}")
    return reports


def run_build(repo_root: Path, verbose: bool) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "build.py", "-m", "compliance"]
    try:
        return subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("build.py timed out after 600 seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to execute build.py: {exc}") from exc
    finally:
        if verbose:
            logger.debug("build command: %s", " ".join(cmd))


def build_result(verbose: bool) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    completed = run_build(repo_root, verbose)
    if completed.returncode not in (0, 1):
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"build.py failed: {detail}")

    reports = discover_reports(repo_root / "diagnostic")
    validated = [load_diagnostic_report(path) for path in reports]
    return {
        "build_exit_code": completed.returncode,
        "reports": [
            {
                "path": str(path.relative_to(repo_root)),
                "passed": report["passed"],
                "failed": report["failed"],
                "total_modules": report["total_modules"],
            }
            for path, report in zip(reports, validated)
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify diagnostic build JSON reports")
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Diagnostic JSON report to validate (default: newest under diagnostic/)",
    )
    parser.add_argument(
        "--run-build",
        action="store_true",
        help="Run python build.py -m compliance before validating reports",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Minimum passing modules required (default: 0)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    repo_root = Path(__file__).resolve().parents[1]
    try:
        if args.run_build:
            build_result(args.verbose)

        if args.report:
            report_paths = [Path(value) for value in args.report]
        else:
            report_paths = discover_reports(repo_root / "diagnostic")

        validated_reports = [load_diagnostic_report(path) for path in report_paths]
        total_passed = sum(report["passed"] for report in validated_reports)

        if total_passed < args.threshold:
            raise DiagnosticValidationError(
                f"Passed modules {total_passed} below threshold {args.threshold}"
            )

        payload = {
            "ok": True,
            "reports_checked": len(validated_reports),
            "passed_modules": total_passed,
            "threshold": args.threshold,
            "reports": [str(path) for path in report_paths],
        }

        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"Validated {len(validated_reports)} diagnostic report(s); "
                f"{total_passed} module(s) passed (threshold {args.threshold})"
            )
        return 0
    except (DiagnosticValidationError, RuntimeError) as exc:
        error_payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(error_payload, indent=2))
        else:
            logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
