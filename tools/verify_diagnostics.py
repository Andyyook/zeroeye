#!/usr/bin/env python3
"""Validate build diagnostic metadata and archive presence, not encryption authenticity."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def run_build(root):
    """Run the repository build explicitly; a failed build is never verification success."""
    try:
        result = subprocess.run([sys.executable, "build.py"], cwd=root,
                                capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Build could not finish: {type(error).__name__}") from error
    if result.returncode:
        raise ValueError(f"Build failed with exit {result.returncode}; inspect build diagnostics")


def check_report(path, root, threshold):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read diagnostic JSON: {type(error).__name__}") from error
    if not isinstance(data, dict):
        raise ValueError("Diagnostic must be a JSON object")
    commit = data.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{8,40}", commit):
        raise ValueError("Invalid diagnostic commit")
    modules = data.get("modules")
    if not isinstance(modules, list):
        raise ValueError("modules must be an array")
    for module in modules:
        if (not isinstance(module, dict) or not isinstance(module.get("name"), str)
                or not module["name"] or module.get("status") not in ("PASS", "FAIL")):
            raise ValueError("Each module requires a name and PASS/FAIL status")
    passed = sum(module["status"] == "PASS" for module in modules)
    for key, count in (("total_modules", len(modules)), ("passed", passed),
                       ("failed", len(modules) - passed)):
        if type(data.get(key)) is not int or data[key] != count:
            raise ValueError(f"Invalid or inconsistent {key}")
    if data.get("diagnostic_logd_error") or data.get("message_blocker"):
        raise ValueError("Diagnostic records archive generation failure")
    refs = data.get("diagnostic_logd")
    refs = [refs] if isinstance(refs, str) else refs
    if not isinstance(refs, list) or not refs:
        raise ValueError("Missing diagnostic_logd archive reference")
    if len(set(ref for ref in refs if isinstance(ref, str))) != len(refs):
        raise ValueError("Invalid or duplicate archive references")
    root = root.resolve()
    for ref in refs:
        if (not isinstance(ref, str) or "\\" in ref or Path(ref).is_absolute()
                or ".." in Path(ref).parts or not ref.startswith("diagnostic/")
                or Path(ref).suffix != ".logd"):
            raise ValueError("Archive path must be repository-relative diagnostic/*.logd")
        archive = (root / ref).resolve()
        if not archive.is_relative_to(root / "diagnostic"):
            raise ValueError("Archive path escapes diagnostic directory")
        if not archive.is_file() or archive.stat().st_size == 0:
            raise ValueError("Referenced diagnostic archive is missing or empty")
        if not Path(ref).name.startswith(f"build-{commit[:8]}"):
            raise ValueError("Archive and diagnostic commit do not match")
    if passed < threshold:
        raise ValueError(f"Passing modules {passed} below threshold {threshold}")
    return {"passed": passed, "failed": len(modules) - passed, "archives": len(refs),
            "commit": commit}


def nonnegative(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("threshold must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("threshold must be nonnegative")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--threshold", type=nonnegative, default=0,
                        help="minimum passing modules per report (default: 0)")
    parser.add_argument("--run-build", action="store_true",
                        help="run build.py first; never implied by ordinary verification")
    args = parser.parse_args(argv)
    results = []
    try:
        if args.run_build:
            run_build(args.root)
        reports = args.reports or sorted((args.root / "diagnostic").glob("build-*.json"))
        if not reports:
            raise ValueError("No diagnostic JSON reports found")
        for path in reports:
            results.append(check_report(path, args.root, args.threshold))
        output = {"ok": True, "reports": results}
    except (ValueError, OSError) as error:
        output = {"ok": False, "error": str(error)}
    if args.as_json:
        print(json.dumps(output))
    elif output["ok"]:
        print(f"Verified {len(results)} diagnostic report(s)")
        if args.verbose:
            for result in results:
                print(json.dumps(result))
    else:
        print(output["error"], file=sys.stderr)
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
