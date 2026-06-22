 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -15,6 +15,7 @@
 because it can process logs from archived backups that are stored in
 S3 Glacier. The ELK stack only indexes logs from the last 90 days.
 For logs older than 90 days, this script is the only option.
+This script now supports parse-error reporting for malformed logs.
 
 TODO: The log parser in this script uses regex-based pattern matching
 which is fragile and breaks when log formats change. There's a test
@@ -26,6 +27,7 @@
     python3 log_aggregator.py --input /var/log/app/*.log --output report.json
     python3 log_aggregator.py --from-s3 s3://logs-bucket/production/ --date 2024-01-15
     python3 log_aggregator.py --analyze --window 1h --group-by service
+    python3 log_aggregator.py --input /var/log/app/*.log --parse-error-report errors.json
     python3 log_aggregator.py --stream --filter 'severity:error'
 """
 
@@ -40,6 +42,7 @@
 import sys
 import time
 from concurrent.futures import ThreadPoolExecutor
+from dataclasses import dataclass, field
 from datetime import datetime, timedelta, timezone
 from pathlib import Path
 from typing import Any, Counter, Dict, List, Optional, Tuple
@@ -48,6 +51,32 @@
 logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
 logger = logging.getLogger("log_aggregator")
 
+
+# ---------------------------------------------------------------------------
+# PARSE ERROR REPORTING
+# ---------------------------------------------------------------------------
+
+@dataclass
+class ParseErrorReport:
+    """Collects sanitized parse errors for reporting without leaking sensitive data."""
+    errors: List[Dict[str, Any]] = field(default_factory=list)
+
+    def add_error(self, parser_type: str, file_path: str, line_number: int, error_message: str) -> None:
+        """Add a sanitized parse error to the report."""
+        sanitized_message = self._sanitize_error_message(error_message)
+        self.errors.append({
+            "parser_type": parser_type,
+            "file_path": file_path,
+            "line_number": line_number,
+            "error_message": sanitized_message,
+        })
+
+    def _sanitize_error_message(self, message: str) -> str:
+        """Remove potential secrets and raw log content from error messages."""
+        # Remove anything that looks like a secret (key=, token=, password=, secret=)
+        sanitized = re.sub(r'(?i)(key|token|password|secret|auth|credential)[\s]*[=:][\s]*[^\s]+', r'\1=<REDACTED>', message)
+        # Truncate very long messages
+        if len(sanitized) > 500:
+            sanitized = sanitized[:500] + "...[truncated]"
+        return sanitized
+
 # ---------------------------------------------------------------------------
 # LOG PARSERS
 # ---------------------------------------------------------------------------
@@ -72,7 +101,7 @@
         (r'\b(DEBUG|TRACE)\b', 'debug'),
     ]
 
-    def parse(self, line: str) -> Optional[Dict[str, Any]]:
+    def parse(self, line: str, file_path: str = "", line_number: int = 0, error_report: Optional[ParseErrorReport] = None) -> Optional[Dict[str, Any]]:
         raise NotImplementedError
 
     def extract_timestamp(self, line: str) -> Optional[int]:
@@ -108,6 +137,9 @@ def extract_level(self, line: str) -> str:
         return 'unknown'
 
 
+_global_parse_error_report: Optional[ParseErrorReport] = None
+
+
 class JSONLogParser(LogParser):
     """Parser for JSON-formatted log lines."""
 
@@ -117,13 +149,22 @@ def __init__(self):
         self.malformed_count = 0
         self.total_count = 0
 
-    def parse(self, line: str) -> Optional[Dict[str, Any]]:
+    def parse(self, line: str, file_path: str = "", line_number: int = 0, error_report: Optional[ParseErrorReport] = None) -> Optional[Dict[str, Any]]:
         self.total_count += 1
         try:
             record = json.loads(line)
             self.parsed_count += 1
             return record
-        except json.JSONDecodeError:
+        except json.JSONDecodeError as e:
+            self.malformed_count += 1
+            if error_report is not None:
+                error_report.add_error(
+                    parser_type="json",
+                    file_path=file_path,
+                    line_number=line_number,
+                    error_message=f"JSON decode error: {str(e)}",
+                )
+            return None
+        except Exception as e:
             self.malformed_count += 1
             return None
 
@@ -131,7 +172,7 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
 class PlainTextLogParser(LogParser):
     """Parser for plain text log lines."""
 
-    def parse(self, line: str) -> Optional[Dict[str, Any]]:
+    def parse(self, line: str, file_path: str = "", line_number: int = 0, error_report: Optional[ParseErrorReport] = None) -> Optional[Dict[str, Any]]:
         # Try to extract timestamp and level from plain text
         timestamp = self.extract_timestamp(line)
         level = self.extract_level(line)
@@ -141,6 +182,15 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
             'timestamp': timestamp,
             'level': level,
         }
+        # If the line is empty or doesn't look like a log, record as potential parse issue
+        if not line.strip():
+            if error_report is not None:
+                error_report.add_error(
+                    parser_type="plaintext",
+                    file_path=file_path,
+                    line_number=line_number,
+                    error_message="Empty line in plaintext log",
+                )
         return result
 
 
@@ -148,7 +198,7 @@ class SyslogParser(LogParser):
     """Parser for syslog-formatted lines."""
 
     # Simple syslog regex: <priority>timestamp host process[pid]: message
-    SYSLOG_RE = re.compile(r'^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$')
+    SYSLOG_RE = re.compile(r'^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{