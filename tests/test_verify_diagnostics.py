import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools/verify_diagnostics.py"
spec = importlib.util.spec_from_file_location("verify_diagnostics", SCRIPT)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "diagnostic").mkdir()
        (self.root / "diagnostic/build-12345678.logd").write_bytes(b"synthetic fixture")
        self.path = self.root / "diagnostic/build-12345678.json"
        self.data = dict(commit="12345678", diagnostic_logd="diagnostic/build-12345678.logd",
                         total_modules=2, passed=1, failed=1,
                         modules=[dict(name="a", status="PASS"), dict(name="b", status="FAIL")])

    def report(self):
        self.path.write_text(json.dumps(self.data))
        return verify.check_report(self.path, self.root, 0)

    def test_valid_report_and_threshold(self):
        self.assertEqual(self.report()["passed"], 1)
        self.path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "threshold"):
            verify.check_report(self.path, self.root, 2)

    def test_missing_and_malformed_json(self):
        with self.assertRaises(ValueError):
            verify.check_report(self.path, self.root, 0)
        self.path.write_text("{")
        with self.assertRaises(ValueError):
            verify.check_report(self.path, self.root, 0)

    def test_invalid_schema_and_counts(self):
        for key, value in [("modules", {}), ("total_modules", True), ("passed", -1),
                           ("failed", 0), ("commit", "bad"), ("modules", [None])]:
            with self.subTest(key=key, value=value):
                old = self.data[key]
                self.data[key] = value
                with self.assertRaises(ValueError):
                    self.report()
                self.data[key] = old

    def test_missing_archive_and_path_escape(self):
        for ref in ["diagnostic/missing.logd", "../outside.logd", "/etc/passwd"]:
            self.data["diagnostic_logd"] = ref
            with self.assertRaises(ValueError):
                self.report()

    def test_chunked_archive_and_errors(self):
        self.data["diagnostic_logd"] = ["diagnostic/build-12345678.logd"]
        self.assertEqual(self.report()["passed"], 1)
        self.data["diagnostic_logd"] = []
        with self.assertRaises(ValueError):
            self.report()

    def test_build_failures_are_explained(self):
        for error in [FileNotFoundError("missing"), PermissionError("denied"),
                      subprocess.TimeoutExpired("build", 300)]:
            with self.subTest(error=type(error).__name__), patch.object(
                    verify.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "Build"):
                    verify.run_build(self.root)
        with patch.object(verify.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "failure", "")):
            with self.assertRaisesRegex(ValueError, "exit 1"):
                verify.run_build(self.root)

    def test_cli_json_success_and_failure(self):
        self.path.write_text(json.dumps(self.data))
        for threshold, expected in [(0, 0), (2, 1)]:
            q = subprocess.run([sys.executable, str(SCRIPT), str(self.path),
                                "--root", str(self.root), "--json", "--threshold", str(threshold)],
                               capture_output=True, text=True)
            self.assertEqual(q.returncode, expected)
            self.assertEqual(json.loads(q.stdout)["ok"], expected == 0)
            self.assertEqual(q.stderr, "")

    def test_mismatched_archive_commit(self):
        self.data["commit"] = "abcdef12"
        with self.assertRaises(ValueError):
            self.report()

    def test_archive_generation_error(self):
        self.data["diagnostic_logd_error"] = "pack failed"
        with self.assertRaises(ValueError):
            self.report()

    def test_duplicate_chunks(self):
        ref = self.data["diagnostic_logd"]
        self.data["diagnostic_logd"] = [ref, ref]
        with self.assertRaises(ValueError):
            self.report()

    def test_symlink_escape(self):
        outside = self.root / "outside.logd"
        outside.write_bytes(b"outside")
        archive = self.root / self.data["diagnostic_logd"]
        archive.unlink()
        archive.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.report()

    def test_negative_threshold_rejected(self):
        q = subprocess.run([sys.executable, str(SCRIPT), "--threshold", "-1"],
                           capture_output=True, text=True)
        self.assertEqual(q.returncode, 2)


if __name__ == "__main__":
    unittest.main()
