import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_diagnostics


class VerifyDiagnosticsTest(unittest.TestCase):
    def write_metadata(self, root: Path, payload: dict) -> Path:
        diagnostic_dir = root / "diagnostic"
        diagnostic_dir.mkdir()
        logd_path = diagnostic_dir / "build-deadbeef.logd"
        logd_path.write_text("placeholder", encoding="utf-8")
        metadata_path = diagnostic_dir / "build-deadbeef.json"
        metadata_path.write_text(json.dumps(payload), encoding="utf-8")
        return metadata_path

    def valid_payload(self) -> dict:
        return {
            "commit": "deadbeef",
            "diagnostic_logd": "diagnostic/build-deadbeef.logd",
            "total_modules": 1,
            "passed": 1,
            "failed": 0,
            "modules": [
                {
                    "name": "tools",
                    "status": "PASS",
                    "elapsed_seconds": 0.1,
                    "artifact": None,
                    "output": "",
                }
            ],
        }

    def test_valid_metadata_passes_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata = self.write_metadata(root, self.valid_payload())
            result = verify_diagnostics.verify_diagnostic(metadata, root, threshold=1)
            self.assertTrue(result.ok)
            self.assertEqual(result.passed, 1)

    def test_missing_required_field_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = self.valid_payload()
            del payload["modules"]
            metadata = self.write_metadata(root, payload)
            result = verify_diagnostics.verify_diagnostic(metadata, root, threshold=0)
            self.assertFalse(result.ok)
            self.assertIn("missing required field: modules", result.errors[0])

    def test_threshold_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata = self.write_metadata(root, self.valid_payload())
            result = verify_diagnostics.verify_diagnostic(metadata, root, threshold=2)
            self.assertFalse(result.ok)
            self.assertIn("below threshold 2", result.errors[0])

    def test_negative_threshold_is_rejected_by_argparse_type(self):
        with self.assertRaises(Exception):
            verify_diagnostics.non_negative_int("-1")


if __name__ == "__main__":
    unittest.main()
