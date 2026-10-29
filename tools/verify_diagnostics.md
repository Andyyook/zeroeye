# Diagnostic verification

Run from the repository root:

    python3 tools/verify_diagnostics.py --verbose
    python3 tools/verify_diagnostics.py diagnostic/build-00000000.json --json
    python3 tools/verify_diagnostics.py --threshold 1

The default checks all diagnostic JSON reports. Positional paths select reports.
--threshold is the minimum passing modules per report, default zero.
Verification success at zero does not assert a successful application build:
failed module counts are retained in the result.

Checks cover JSON structure, module counts/statuses, commit pairing, and
nonempty repository-contained archive references. They do not decrypt archives,
authenticate their author, or attest to compilation. Synthetic test fixtures
are not real encryption evidence.

--run-build explicitly runs the unmodified repository build first, with a
five-minute subprocess timeout. Build failure, missing tools, permissions and
timeouts return nonzero with an explanation. A failed build never passes as
successful verification. Normal verification does not execute subprocesses.

Tests (standard library only):

    python3 -m unittest discover -s tests -p 'test_verify_diagnostics.py' -v
