#!/usr/bin/env python3
"""Validate build diagnostic metadata before submitting a PR."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_DIAGNOSTIC_GLOB = "diagnostic/build-*.json"


class DiagnosticError(Exception):
    """Raised when a diagnostic file is structurally invalid."""


@dataclass
class VerificationResult:
    path: str
    ok: bool
    passed: int = 0
    failed: int = 0
    total_modules: int = 0
    diagnostics: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "ok": self.ok,
            "passed": self.passed,
            "failed": self.failed,
            "total_modules": self.total_modules,
            "diagnostics": self.diagnostics,
            "errors": self.errors,
        }


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


def run_command(cmd: list[str], cwd: Path | None = None, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DiagnosticError(f"required command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DiagnosticError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
    except OSError as exc:
        raise DiagnosticError(f"could not run command {' '.join(cmd)}: {exc}") from exc


def discover_repo_root() -> tuple[Path, list[str]]:
    warnings: list[str] = []
    try:
        result = run_command(["git", "rev-parse", "--show-toplevel"])
    except DiagnosticError as exc:
        warnings.append(f"{exc}; using current directory")
        return Path.cwd(), warnings

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git did not return a repository root").strip()
        warnings.append(f"could not determine git root: {message}; using current directory")
        return Path.cwd(), warnings

    stdout = (result.stdout or "").strip()
    if not stdout:
        warnings.append("git returned an empty repository root; using current directory")
        return Path.cwd(), warnings

    return Path(stdout).resolve(), warnings


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise DiagnosticError(f"diagnostic metadata not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DiagnosticError(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}") from exc
    except OSError as exc:
        raise DiagnosticError(f"could not read {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise DiagnosticError("diagnostic metadata must be a JSON object")
    return data


def require_type(data: dict[str, Any], key: str, expected: type | tuple[type, ...]) -> Any:
    if key not in data:
        raise DiagnosticError(f"missing required field: {key}")
    value = data[key]
    if not isinstance(value, expected):
        expected_name = (
            " or ".join(t.__name__ for t in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise DiagnosticError(f"field {key!r} must be {expected_name}")
    return value


def validate_modules(data: dict[str, Any]) -> list[str]:
    modules = require_type(data, "modules", list)
    diagnostics: list[str] = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            raise DiagnosticError(f"modules[{index}] must be an object")
        name = module.get("name")
        status = module.get("status")
        if not isinstance(name, str) or not name:
            raise DiagnosticError(f"modules[{index}].name must be a non-empty string")
        if status not in {"PASS", "FAIL"}:
            raise DiagnosticError(f"modules[{index}].status must be PASS or FAIL")
        diagnostics.append(f"{name}: {status}")
    return diagnostics


def diagnostic_log_paths(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise DiagnosticError("field 'diagnostic_logd' must be a string, list of strings, or null")


def verify_diagnostic(path: Path, repo_root: Path, threshold: int, verbose: bool = False) -> VerificationResult:
    errors: list[str] = []
    diagnostics: list[str] = []

    try:
        data = load_json(path)
        commit = require_type(data, "commit", str)
        total_modules = require_type(data, "total_modules", int)
        passed = require_type(data, "passed", int)
        failed = require_type(data, "failed", int)
        logd_value = data.get("diagnostic_logd")
        logd_paths = diagnostic_log_paths(logd_value)
        module_diagnostics = validate_modules(data)

        if total_modules < 0 or passed < 0 or failed < 0:
            raise DiagnosticError("module counts must be non-negative")
        if total_modules != passed + failed:
            errors.append(
                f"module count mismatch: total_modules={total_modules}, passed={passed}, failed={failed}"
            )
        if passed < threshold:
            errors.append(f"passed module count {passed} is below threshold {threshold}")
        if not commit:
            errors.append("commit field is empty")

        for relative in logd_paths:
            logd_path = (repo_root / relative).resolve()
            if not logd_path.exists():
                errors.append(f"referenced diagnostic log not found: {relative}")

        if verbose:
            diagnostics.extend(module_diagnostics)
            diagnostics.extend(f"logd: {relative}" for relative in logd_paths)

        return VerificationResult(
            path=str(path),
            ok=not errors,
            passed=passed,
            failed=failed,
            total_modules=total_modules,
            diagnostics=diagnostics,
            errors=errors,
        )
    except DiagnosticError as exc:
        return VerificationResult(path=str(path), ok=False, errors=[str(exc)])


def discover_diagnostic_files(paths: list[str], repo_root: Path) -> list[Path]:
    if paths:
        return [Path(path).resolve() for path in paths]
    return sorted(repo_root.glob(DEFAULT_DIAGNOSTIC_GLOB))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generated build diagnostic JSON and referenced logd artifacts.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=f"Diagnostic JSON files to inspect. Defaults to {DEFAULT_DIAGNOSTIC_GLOB}.",
    )
    parser.add_argument(
        "--threshold",
        type=non_negative_int,
        default=0,
        help="Minimum number of passed modules required for success. Default: 0.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show module-level details and referenced diagnostic artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root, warnings = discover_repo_root()
    diagnostic_files = discover_diagnostic_files(args.paths, repo_root)

    results: list[VerificationResult]
    if diagnostic_files:
        results = [
            verify_diagnostic(path, repo_root=repo_root, threshold=args.threshold, verbose=args.verbose)
            for path in diagnostic_files
        ]
    else:
        results = [
            VerificationResult(
                path=str(repo_root / DEFAULT_DIAGNOSTIC_GLOB),
                ok=False,
                errors=["no diagnostic JSON files found"],
            )
        ]

    ok = all(result.ok for result in results)
    if args.json:
        payload = {
            "ok": ok,
            "repo_root": str(repo_root),
            "warnings": warnings,
            "results": [result.as_dict() for result in results],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print(f"{status} {result.path}")
            print(
                f"  modules: {result.passed} passed, {result.failed} failed, "
                f"{result.total_modules} total"
            )
            for detail in result.diagnostics:
                print(f"  {detail}")
            for error in result.errors:
                print(f"  error: {error}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
