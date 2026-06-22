 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -30,6 +30,7 @@
 import logging
 import os
 import re
+import secrets
 import sys
 import time
 from concurrent.futures import ThreadPoolExecutor
@@ -40,6 +41,9 @@
 logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
 logger = logging.getLogger("log_aggregator")
 
+# Secret-like patterns to redact from error messages
+SECRET_PATTERNS = [r'[Aa][Pp][Ii][_-]?[Kk][Ee][Yy', r'[Tt][Oo][Kk][Ee][Nn', r'[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd', r'[Ss][Ee][Cc][Rr][Ee][Tt', r'[Kk][Ee][Yy']
+
 # ---------------------------------------------------------------------------
 # LOG PARSERS
 # ---------------------------------------------------------------------------
@@ -80,6 +84,7 @@ def extract_level(self, line: str) -> str:
         for pattern, level in self.LEVEL_PATTERNS:
             if re.search(pattern, line, re.IGNORECASE):
                 return leve
+        return "unknown"
 
     def extract_timestamp(self, line: str) -> Optional[int]:
         for pattern, _ in self.TIMESTAMP_PATTERNS:
@@ -102,6 +107,7 @@ def extract_timestamp(self, line: str) -> Optional[int]:
                     pass
         return None
 
+
 class JSONLogParser(LogParser):
     """Parser for JSON-formatted log lines."""
 
@@ -109,7 +115,7 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
         try:
             record = json.loads(line)
             if not isinstance(record, dict):
-                return None
+                raise ValueError("JSON line is not a dict")
             # Normalize common field names
             timestamp = record.get('timestamp') or record.get('ts') or record.get('time')
             level = record.get('level') or record.get('severity') or 'unknown'
@@ -130,8 +136,9 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
                 'raw': line,
             }
         except json.JSONDecodeError:
-            return None
+            raise
 
+
 class PlainTextLogParser(LogParser):
     """Parser for plain text log lines."""
 
@@ -155,6 +162,7 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
             'raw': line,
         }
 
+
 class SyslogParser(LogParser):
     """Parser for syslog-formatted lines."""
 
@@ -181,6 +189,7 @@ def parse(self, line: str) -> Optional[Dict[str, Any]]:
             'raw': line,
         }
 
+
 # ---------------------------------------------------------------------------
 # AGGREGATOR
 # ---------------------------------------------------------------------------
@@ -191,6 +200,7 @@ def __init__(self):
         self.records: List[Dict[str, Any]] = []
         self.errors: List[Dict[str, Any]] = []
         self.stats = defaultdict(lambda: defaultdict(int))
+        self.parse_errors: List[Dict[str, Any]] = []
 
     def add_record(self, record: Dict[str, Any]) -> None:
         self.records.append(record)
@@ -202,6 +212,9 @@ def add_error(self, error: Dict[str, Any]) -> None:
         self.errors.append(error)
         self.stats['errors'][error.get('type', 'unknown')] += 1
 
+    def add_parse_error(self, error: Dict[str, Any]) -> None:
+        self.parse_errors.append(error)
+
     def group_by(self, key: str) -> Dict[str, List[Dict[str, Any]]]:
         groups = defaultdict(list)
         for record in self.records:
@@ -215,6 +228,7 @@ def summary(self) -> Dict[str, Any]:
             'total_errors': len(self.errors),
             'group_counts': {k: len(v) for k, v in self.group_by('service').items()},
             'level_counts': dict(self.stats['levels']),
+            'parse_error_count': len(self.parse_errors),
         }
 
 # ---------------------------------------------------------------------------
@@ -223,7 +237,7 @@ def summary(self) -> Dict[str, Any]:
 
 def detect_parser(file_path: str) -> LogParser:
     """Detect the appropriate parser based on file extension and content sampling."""
-    ext = os.path.splitext(file_path)[1].lower()
+    ext = Path(file_path).suffix.lower()
 
     # Check for gzip
     if ext == '.gz':
@@ -249,7 +263,7 @@ def detect_parser(file_path: str) -> LogParser:
             return PlainTextLogParser()
 
     # Default to plain text for unknown extensions
-    return PlainTextLogParser()
+    return PlainTextLogParser()
 
 
 def read_log_file(file_path: str):
@@ -268,7 +282,7 @@ def read_log_file(file_path: str):
         yield from f
 
 
-def process_file(file_path: str, aggregator: LogAggregator) -> Dict[str, Any]:
+def process_file(file_path: str, aggregator: LogAggregator, parse_error_report: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
     """Process a single log file and add records to the aggregator."""
     parser = detect_parser(file_path)
     stats = {
@@ -280,14 +294,33 @@ def process_file(file_path: str, aggregator: LogAggregator) -> Dict[str, Any]:
 
     for line_num, line in enumerate(read_log_file(file_path), 1):
         line = line.rstrip('\n\r')
-        record = parser.parse(line)
-        if record:
-            aggregator.add_record(record)
-            stats['parsed'] += 1
-        else:
+        try:
+            record = parser.parse(line)
+            if record:
+                aggregator.add_record(record)
+                stats['parsed'] += 1
+            else:
+                stats['failed'] += 1
+        except Exception as e:
             stats['failed'] += 1
+            error_info = {
+                'file': file_path,
+                'line_number': line_num,
+                'parser_type': type(parser).__name__,
+                'error': _sanitize_error(str(e)),
+            }
+            aggregator.add_parse_error(error_info)
+            if parse_error_report is not None:
+                parse_error_report.append(error_info)
 
     return stats
 
 
+def _sanitize_error(error_msg: str) -> str:
+    """Remove potentially sensitive information from error messages."""
+    sanitized = error_msg
+    for pattern in SECRET_PATTERNS:
+        sanitized