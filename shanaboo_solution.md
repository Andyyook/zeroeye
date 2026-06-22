 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -20,6 +20,7 @@
     python3 log_aggregator.py --input /var/log/app/*.log --output report.json
     python3 log_aggregator.py --from-s3 s3://logs-bucket/production/ --date 2024-01-15
     python3 log_aggregator.py --analyze --window 1h --group-by service
+    python3 log_aggregator.py --input /var/log/app/*.log --output report.json --parse-error-report parse_errors.json
     python3 log_aggregator.py --stream --filter 'severity:error'
 """
 
@@ -36,6 +37,7 @@
 from datetime import datetime, timedelta, timezone
 from pathlib import Path
 from typing import Any, Counter, Dict, List, Optional, Tuple
+from dataclasses import dataclass, asdict
 from collections import defaultdict, Counter
 
 logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
@@ -45,6 +47,37 @@
 # LOG PARSERS
 # ---------------------------------------------------------------------------
 
+@dataclass
+class ParseError:
+    """Represents a single parse error with sanitized information."""
+    parser_type: str
+    file_path: str
+    line_number: int
+    error_message: str
+
+    def to_dict(self) -> Dict[str, Any]:
+        return {
+            "parser_type": self.parser_type,
+            "file_path": self.file_path,
+            "line_number": self.line_number,
+            "error_message": self.error_message,
+        }
+
+
+class ParseErrorCollector:
+    """Collects and manages parse errors, with sanitization to prevent data leakage."""
+    
+    def __init__(self):
+        self.errors: List[ParseError] = []
+    
+    def add_error(self, parser_type: str, file_path: str, line_number: int, raw_error: str) -> None:
+        """Add a sanitized parse error. Raw log content is never stored."""
+        sanitized = self._sanitize_error(raw_error)
+        self.errors.append(ParseError(parser_type, file_path, line_number, sanitized))
+    
+    def _sanitize_error(self, raw_error: str) -> str:
+        """Remove potentially sensitive information from error messages."""
+        # Remove anything that looks like a secret (long hex strings, base64, etc.)
+        sanitized = re.sub(r'[a-fA-F0-9]{32,}', '<REDACTED_HASH>', raw_error)
+        # Remove anything that looks like an API key or token
+        sanitized = re.sub(r'(?i)(api[_-]?key|token|secret|password)[\s]*[=:][\s]*\S+', r'\1=<REDACTED>', sanitized)
+        # Remove raw line content indicators
+        sanitized = re.sub(r'line content[:\s]*.*$', 'line content=<REDACTED>', sanitized)
+        return sanitized
+    
+    def to_summary(self) -> Dict[str, Any]:
+        """Return a JSON-serializable summary of all parse errors."""
+        return {
+            "total_errors": len(self.errors),
+            "errors_by_file": self._group_by_file(),
+            "errors": [e.to_dict() for e in self.errors],
+        }
+    
+    def _group_by_file(self) -> Dict[str, int]:
+        counts: Dict[str, int] = {}
+        for error in self.errors:
+            counts[error.file_path] = counts.get(error.file_path, 0) + 1
+        return counts
+    
+    def write_report(self, path: str) -> None:
+        """Write the parse error report to the given path."""
+        with open(path, 'w', encoding='utf-8') as f:
+            json.dump(self.to_summary(), f, indent=2)
+
+
 class LogParser:
     """Base class for log parsers. Subclasses implement format-specific parsing."""
 
@@ -95,6 +128,9 @@ def extract_level(self, line: str) -> str:
         return 'unknown'
 
 
+# Global parse error collector (initialized in main)
+parse_error_collector: Optional[ParseErrorCollector] = None
+
 class JSONLogParser(LogParser):
     """Parser for JSON-formatted log lines."""
 
@@ -102,8 +138,14 @@ def __init__(self):
         self.name = "json"
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
-        # TODO: implement JSON parsing
-        pass
+        try:
+            return json.loads(line)
+        except json.JSONDecodeError as e:
+            # Don't include raw line in error
+            if parse_error_collector is not None:
+                # This will be filled in by the caller with file/line info
+                pass
+            raise
+        except Exception:
+            raise
 
 
 class PlainTextLogParser(LogParser):
@@ -113,8 +155,13 @@ def __init__(self):
         self.name = "plaintext"
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
-        # TODO: implement plain text parsing
-        pass
+        # Simple plaintext parser: extract timestamp and level if possible
+        result: Dict[str, Any] = {
+            "raw_message": line,
+            "timestamp": self.extract_timestamp(line),
+            "level": self.extract_level(line),
+        }
+        return result
+
 
 class SyslogParser(LogParser):
     """Parser for syslog-formatted log lines."""
@@ -123,8 +170,13 @@ def __init__(self):
         self.name = "syslog"
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
-        # TODO: implement syslog parsing
-        pass
+        # Basic syslog parsing
+        result: Dict[str, Any] = {
+            "raw_message": line,
+            "timestamp": self.extract_timestamp(line),
+            "level": self.extract_level(line),
+        }
+        return result
+
 
 # ---------------------------------------------------------------------------
 # LOG AGGREGATOR
@@ -140,6 +192,7 @@ def __init__(self):
         self.parsers = = {
             'json': JSONLogParser(),
             'plaintext': PlainTextLogParser(),
+            'syslog': SyslogParser(),
         }
 
     def detect_format(self, line: str) -> str:
@@ -152,6 +205,7 @@ def detect_format(self, line: str) -> str:
         except:
             return 'plaintext'
 
+
 def main():
     parser = argparse.ArgumentParser