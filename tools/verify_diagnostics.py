#!/usr/bin/env python3
"""Diagnostics verification script with input validation and error handling."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


REQUIRED_FIELDS = ["generated_at", "commit", "total_modules", "passed", "failed", "modules"]
MODULE_FIELDS = ["name", "status"]


def validate_schema(data: dict) -> list[str]:
    """Validate diagnostic JSON schema. Returns list of errors."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if "modules" in data and isinstance(data["modules"], list):
        for i, mod in enumerate(data["modules"]):
            for field in MODULE_FIELDS:
                if field not in mod:
                    errors.append(f"Module {i} missing field: {field}")
    return errors


def load_diagnostic(path: Path, verbose: bool) -> tuple[Optional[dict], list[str]]:
    """Load and validate diagnostic JSON file."""
    errors = []
    if not path.exists():
        return None, [f"File not found: {path}"]
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"Invalid JSON: {e}"]
    schema_errors = validate_schema(data)
    if schema_errors:
        return data, schema_errors
    return data, []
