#!/usr/bin/env python3
"""diagnostic_diff.py — Compare two diagnostic metadata JSON files and print a human-readable diff.

Bounty #172: Helps reviewers understand what changed between PR submissions.
"""

import argparse, json, sys
from pathlib import Path


def color(text, color_name):
    codes = {"red": 31, "green": 32, "yellow": 33, "cyan": 36, "bold": 1}
    c = codes.get(color_name, 0)
    return f"\033[{c}m{text}\033[0m" if sys.stdout.isatty() else text


def load_json(path):
    with open(path) as f:
        return json.load(f)


def diff_module_statuses(old_mods, new_mods):
    old_map = {m["name"]: m for m in old_mods}
    new_map = {m["name"]: m for m in new_mods}
    lines = []

    all_names = sorted(set(old_map.keys()) | set(new_map.keys()))
    for name in all_names:
        om = old_map.get(name)
        nm = new_map.get(name)
        old_status = om["status"] if om else "—"
        new_status = nm["status"] if nm else "—"

        if old_status != new_status:
            if new_status == "PASS":
                lines.append(color(f"  ✓ {name}: {old_status} → {new_status}", "green"))
            elif new_status == "FAIL":
                lines.append(color(f"  ✗ {name}: {old_status} → {new_status}", "red"))
            else:
                lines.append(color(f"  ~ {name}: {old_status} → {new_status}", "yellow"))
        else:
            old_sec = om.get("elapsed_seconds", 0) if om else 0
            new_sec = nm.get("elapsed_seconds", 0) if nm else 0
            delta = new_sec - old_sec
            if abs(delta) > 0.5:
                icon = "🐌" if delta > 0 else "⚡"
                lines.append(f"  {icon} {name}: {old_sec:.1f}s → {new_sec:.1f}s ({delta:+.1f}s)")
    return lines


def diff_summary(old, new):
    lines = []
    for key in ["total_modules", "passed", "failed"]:
        ov = old.get(key, 0)
        nv = new.get(key, 0)
        if ov != nv:
            lines.append(f"  {key}: {ov} → {nv}")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="Compare two diagnostic metadata JSON files")
    parser.add_argument("old", type=str, help="Path to older diagnostic JSON")
    parser.add_argument("new", type=str, help="Path to newer diagnostic JSON")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of human-readable")
    args = parser.parse_args()

    old_path = Path(args.old)
    new_path = Path(args.new)

    if not old_path.exists():
        print(f"Error: {args.old} not found", file=sys.stderr)
        sys.exit(1)
    if not new_path.exists():
        print(f"Error: {args.new} not found", file=sys.stderr)
        sys.exit(1)

    old = load_json(old_path)
    new = load_json(new_path)

    if args.json:
        result = {
            "old_commit": old.get("commit"),
            "new_commit": new.get("commit"),
            "old_generated_at": old.get("generated_at"),
            "new_generated_at": new.get("generated_at"),
            "summary_diff": {
                "total_modules": [old.get("total_modules"), new.get("total_modules")],
                "passed": [old.get("passed"), new.get("passed")],
                "failed": [old.get("failed"), new.get("failed")],
            },
            "module_status_changes": [],
            "elapsed_deltas": {},
        }
        old_map = {m["name"]: m for m in old.get("modules", [])}
        new_map = {m["name"]: m for m in new.get("modules", [])}
        for name in sorted(set(old_map.keys()) | set(new_map.keys())):
            om = old_map.get(name)
            nm = new_map.get(name)
            if om and nm:
                if om["status"] != nm["status"]:
                    result["module_status_changes"].append({
                        "name": name, "from": om["status"], "to": nm["status"]
                    })
                delta = nm.get("elapsed_seconds", 0) - om.get("elapsed_seconds", 0)
                if abs(delta) > 0.5:
                    result["elapsed_deltas"][name] = round(delta, 2)
            elif nm and not om:
                result["module_status_changes"].append({
                    "name": name, "from": None, "to": nm["status"]
                })
        print(json.dumps(result, indent=2))
        return

    # Human-readable output
    print(f"\n{color('=== Diagnostic Diff ===', 'bold')}")
    print(f"  Old: {old_path.name} ({old.get('generated_at', '?')})")
    print(f"  New: {new_path.name} ({new.get('generated_at', '?')})")
    print(f"  Commit: {old.get('commit', '?')} → {new.get('commit', '?')}")

    summary_diff = diff_summary(old, new)
    if summary_diff:
        print(f"\n{color('Summary Changes:', 'bold')}")
        print("\n".join(summary_diff))

    old_mods = old.get("modules", [])
    new_mods = new.get("modules", [])
    if old_mods or new_mods:
        print(f"\n{color('Module Status:', 'bold')}")
        module_lines = diff_module_statuses(old_mods, new_mods)
        if module_lines:
            print("\n".join(module_lines))
        else:
            print("  (no significant changes)")


if __name__ == "__main__":
    main()
