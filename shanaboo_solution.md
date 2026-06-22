 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -10,7 +10,7 @@
 The ELK stack migration was completed in production in Q2 2023. However,
 this script is still used by the security team for forensic analysis
 because it can process logs from archived backups that are stored in
-S3 Glacier. The ELK stack only indexes logs from the last 90 days.
+S3 Glacier. The ELK stack only indexes logs from the last 90 days.
 For logs older than 90 days, this script is the only option.
 
 TODO: The log parser in this script uses regex-based pattern matching
@@ -22,6 +22,7 @@
     python3 log_aggregator.py --input /var/log/app/*.log --output report.json
     python3 log_aggregator.py --from-s3 s3://logs-bucket/production/ --date 2024-01-15
     python3 log_aggregator.py --analyze --window 1h --group-by service
+    python3 log_aggregator.py --input /var/log/app/*.log --output report.json --parse-error-report errors.json
 """
 
 import argparse
@@ -31,6 +32,7 @@
 import io
 import json
 import logging
+import hashlib
 import os
 import re
 import sys
@@ -39,7 +41,7 @@
 from datetime import datetime, timedelta, timezone
 from pathlib import Path
 from typing import Any, Counter, Dict, List, Optional, Tuple
-from collections import defaultdict, Counter
+from collections import defaultdict
 
 logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
 logger = logging.getLogger("log_aggregator")
@@ -91,7 +93,7 @@
     def extract_level(self, line: str) -> str:
         for pattern, level in self.LEVEL_PATTERNS:
             if re.search(pattern, line, re.IGNORECASE):
-                return leve
+                return level
         return "unknown"
 
 
@@ -99,6 +101,7 @@
     """Parser for JSON-formatted log lines."""
 
     def __init__(self):
+        self.parser_type = "json"
         self._required_keys = {'timestamp', 'level', 'message'}
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
@@ -108,7 +111,7 @@
             if not isinstance(record, dict):
                 return None
             # Normalize keys to lowercase
-            record = {k.lower(): v for k, v in record.items()}
+            record = {k.lower() if isinstance(k, str) else k: v for k, v in record.items()}
             # Ensure required keys exist
             for key in self._required_keys:
                 if key not in record:
@@ -124,6 +127,9 @@
 class PlaintextParser(LogParser):
     """Parser for plain text log lines with regex extraction."""
 
+    def __init__(self):
+        self.parser_type = "plaintext"
+
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         # Try to extract timestamp and level from the line
         timestamp = self.extract_timestamp(line)
@@ -140,6 +146,9 @@
 class SyslogParser(LogParser):
     """Parser for syslog-formatted lines."""
 
+    def __init__(self):
+        self.parser_type = "syslog"
+
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         # Simple syslog parsing: PRI, HEADER, MSG
         syslog_pattern = r'^<(\d+)>(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$'
@@ -156,6 +165,9 @@
 class AutoParser(LogParser):
     """Automatically detects log format and delegates to appropriate parser."""
 
+    def __init__(self):
+        self.parser_type = "auto"
+
     def __init__(self):
         self.json_parser = JSONParser()
         self.syslog_parser = SyslogParser()
@@ -178,6 +190,9 @@
 # AGGREGATOR
 # ---------------------------------------------------------------------------
 
+ParseError = Dict[str, Any]
+
+
 class LogAggregator:
     """Aggregates logs from multiple sources and generates reports."""
 
@@ -185,6 +200,7 @@
         self.records: List[Dict[str, Any]] = []
         self.errors: List[str] = []
         self.stats: Dict[str, Any] = {
+            'parse_errors': []  # type: List[ParseError]
             'total_lines': 0,
             'parsed_lines': 0,
             'error_lines': 0,
@@ -193,6 +209,7 @@
         self.parsers = {
             'json': JSONParser(),
             'plaintext': PlaintextParser(),
+            'syslog': SyslogParser(),
             'auto': AutoParser(),
         }
 
@@ -203,6 +220,7 @@
         parser = self.parsers.get(parser_name, self.parsers['auto'])
         file_path = Path(file_path)
 
+        parse_errors = []  # type: List[ParseError]
         try:
             if file_path.suffix == '.gz':
                 f = gzip.open(file_path, 'rt', encoding='utf-8', errors='replace')
@@ -213,14 +231,30 @@
             with f:
                 for line_num, line in enumerate(f, 1):
                     self.stats['total_lines'] += 1
+                    line = line.rstrip('\n\r')
+                    if not line:
+                        continue
                     try:
                         record = parser.parse(line)
                         if record:
                             self.records.append(record)
                             self.stats['parsed_lines'] += 1
                         else:
                             self.stats['error_lines'] += 1
+                            # Record parse error
+                            error_info = {
+                                'parser_type': getattr(parser, 'parser_type', 'unknown'),
+                                'file_path': str(file_path),
+                                'line_number': line_num,
+                                'error_message': 'Failed to parse log line',
+                            }
+                            parse_errors.append(error_info)
                     except Exception as e:
                         self.stats['error_lines'] += 1
                         self.errors.append(f"{file_path}:{line_num}: {e}")
+                        # Record parse error with sanitized message
+                        error_info = {
+                            'parser_type': getattr(parser, 'parser_type', 'unknown'),
+                            'file_path': str(file_path),
+                            'line_number': line_num,
+                            'error_message': _sanitize_error_message(str(e)),
+                        }
+                        parse_errors.append(error_info)
+
+        self.stats['parse_errors'].extend(parse_errors)
         return