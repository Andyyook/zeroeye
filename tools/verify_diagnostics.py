#!/usr/bin/env python3
"""Validate zeroeye diagnostic metadata and referenced .logd artifacts."""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERN = "diagnostic/*.json"
VALID_STATUSES = {"PASS", "FAIL"}


@dataclass
class DiagnosticResult:
    path: str
    ok: bool = True
    passed: int = 0
    total_modules: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    logd_files: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def run_subprocess(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 10) -> tuple[bool, str]:
    """Run a command with useful, non-secret error messages."""
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"command timed out after {timeout}s: {cmd[0]}"
    except OSError as exc:
        return False, f"could not run {cmd[0]}: {exc}"

    output = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode != 0:
        return False, output or f"{cmd[0]} exited with status {completed.returncode}"
    return True, output


def is_tracked(path: Path) -> tuple[bool, str]:
    relpath = _display_path(path)
    return run_subprocess(["git", "ls-files", "--error-unmatch", "--", relpath])


def require_type(result: DiagnosticResult, data: dict[str, Any], key: str, expected: type | tuple[type, ...]) -> Any:
    if key not in data:
        result.fail(f"missing required field: {key}")
        return None
    value = data[key]
    if not isinstance(value, expected):
        if isinstance(expected, tuple):
            expected_name = " or ".join(t.__name__ for t in expected)
        else:
            expected_name = expected.__name__
        result.fail(f"field {key} must be {expected_name}")
        return None
    return value


def normalize_logd_entries(value: Any, result: DiagnosticResult) -> list[str]:
    if value is None:
        result.warn("diagnostic_logd is null; no .logd artifact was recorded")
        return []
    if isinstance(value, str):
        entries = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        entries = value
    else:
        result.fail("field diagnostic_logd must be a string, list of strings, or null")
        return []

    for entry in entries:
        if not entry.endswith(".logd"):
            result.fail(f"diagnostic_logd entry is not a .logd file: {entry}")
    return entries


def resolve_artifact(path_text: str, base_dir: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    root_candidate = ROOT / candidate
    if root_candidate.exists():
        return root_candidate
    return base_dir / candidate


def validate_modules(data: dict[str, Any], result: DiagnosticResult) -> None:
    total = require_type(result, data, "total_modules", int)
    passed = require_type(result, data, "passed", int)
    failed = require_type(result, data, "failed", int)
    modules = require_type(result, data, "modules", list)

    if total is None or passed is None or failed is None or modules is None:
        return
    result.total_modules = total
    result.passed = passed

    for key, value in (("total_modules", total), ("passed", passed), ("failed", failed)):
        if value < 0:
            result.fail(f"field {key} must be non-negative")

    if len(modules) != total:
        result.fail(f"modules length ({len(modules)}) does not match total_modules ({total})")

    counted_passed = 0
    counted_failed = 0
    for index, module in enumerate(modules):
        prefix = f"modules[{index}]"
        if not isinstance(module, dict):
            result.fail(f"{prefix} must be an object")
            continue
        name = module.get("name")
        if not isinstance(name, str) or not name.strip():
            result.fail(f"{prefix}.name must be a non-empty string")
        status = module.get("status")
        if status not in VALID_STATUSES:
            result.fail(f"{prefix}.status must be PASS or FAIL")
        elif status == "PASS":
            counted_passed += 1
        else:
            counted_failed += 1
        elapsed = module.get("elapsed_seconds")
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or elapsed < 0:
            result.fail(f"{prefix}.elapsed_seconds must be a non-negative number")
        artifact = module.get("artifact")
        if artifact is not None and not isinstance(artifact, str):
            result.fail(f"{prefix}.artifact must be a string or null")
        output = module.get("output")
        if not isinstance(output, str):
            result.fail(f"{prefix}.output must be a string")

    if counted_passed != passed:
        result.fail(f"passed ({passed}) does not match PASS module count ({counted_passed})")
    if counted_failed != failed:
        result.fail(f"failed ({failed}) does not match FAIL module count ({counted_failed})")
    if passed + failed != total:
        result.fail(f"passed + failed ({passed + failed}) does not match total_modules ({total})")


def validate_diagnostic_json(path: Path, *, check_git: bool) -> DiagnosticResult:
    result = DiagnosticResult(path=_display_path(path))
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        result.fail(f"could not read file: {exc}")
        return result

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        result.fail(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        return result

    if not isinstance(data, dict):
        result.fail("diagnostic JSON root must be an object")
        return result

    require_type(result, data, "generated_at", str)
    commit = require_type(result, data, "commit", str)
    if isinstance(commit, str) and not commit:
        result.fail("field commit must not be empty")

    validate_modules(data, result)

    logd_entries = normalize_logd_entries(data.get("diagnostic_logd"), result)
    for entry in logd_entries:
        artifact = resolve_artifact(entry, path.parent)
        result.logd_files.append(_display_path(artifact))
        if not artifact.exists():
            result.fail(f"referenced diagnostic log not found: {entry}")
        elif artifact.suffix != ".logd":
            result.fail(f"referenced diagnostic log must end with .logd: {entry}")
        elif artifact.stat().st_size == 0:
            result.fail(f"referenced diagnostic log is empty: {entry}")

        if check_git and artifact.exists():
            tracked, message = is_tracked(artifact)
            if not tracked:
                result.fail(f"referenced diagnostic log is not tracked by git: {entry} ({message})")

    if check_git:
        tracked, message = is_tracked(path)
        if not tracked:
            result.fail(f"diagnostic JSON is not tracked by git: {message}")

    return result


def discover_paths(inputs: list[str]) -> list[Path]:
    patterns = inputs or [DEFAULT_PATTERN]
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern, root_dir=ROOT)
        if matches:
            paths.extend(ROOT / match for match in matches)
        else:
            paths.append((ROOT / pattern).resolve() if not Path(pattern).is_absolute() else Path(pattern))
    return sorted(dict.fromkeys(paths))


def build_payload(results: list[DiagnosticResult], threshold: int) -> dict[str, Any]:
    total_passed = sum(result.passed for result in results if result.ok)
    valid_reports = sum(1 for result in results if result.ok)
    errors = sum(len(result.errors) for result in results)
    threshold_met = total_passed >= threshold
    return {
        "ok": errors == 0 and threshold_met,
        "threshold": threshold,
        "passed_modules": total_passed,
        "valid_reports": valid_reports,
        "errors": errors,
        "reports": [
            {
                "path": result.path,
                "ok": result.ok,
                "passed": result.passed,
                "total_modules": result.total_modules,
                "logd_files": result.logd_files,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }


def print_human(payload: dict[str, Any], *, verbose: bool) -> None:
    print("Diagnostic verification")
    print(f"  threshold: {payload['threshold']}")
    print(f"  passed modules in valid reports: {payload['passed_modules']}")
    print(f"  valid reports: {payload['valid_reports']}")
    for report in payload["reports"]:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"\n  {status} {report['path']}")
        print(f"    modules passed: {report['passed']}/{report['total_modules']}")
        if verbose and report["logd_files"]:
            print("    logd files:")
            for logd in report["logd_files"]:
                print(f"      - {logd}")
        for warning in report["warnings"]:
            print(f"    warning: {warning}")
        for error in report["errors"]:
            print(f"    error: {error}")
    if not payload["ok"] and payload["passed_modules"] < payload["threshold"]:
        print(f"\n  error: threshold not met ({payload['passed_modules']} < {payload['threshold']})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate diagnostic JSON metadata and .logd artifacts")
    parser.add_argument("paths", nargs="*", help="diagnostic JSON file(s) or glob(s); defaults to diagnostic/*.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="show referenced .logd files and extra details")
    parser.add_argument("--json", action="store_true", help="write machine-readable JSON output")
    parser.add_argument("--threshold", type=int, default=0, help="minimum passing modules required across valid reports (default: 0)")
    parser.add_argument("--no-git-check", action="store_true", help="skip git tracked-file validation")
    args = parser.parse_args(argv)
    if args.threshold < 0:
        parser.error("--threshold must be non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    paths = discover_paths(args.paths)
    results = [validate_diagnostic_json(path, check_git=not args.no_git_check) for path in paths]
    if not results:
        missing = DiagnosticResult(path=DEFAULT_PATTERN, ok=False)
        missing.fail("no diagnostic JSON files found")
        results = [missing]
    payload = build_payload(results, args.threshold)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload, verbose=args.verbose)

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
