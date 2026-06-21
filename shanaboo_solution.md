 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -20,6 +20,7 @@
 import argparse
 import collections
 import csv
+import unittest
 import gzip
 import io
 import json
@@ -30,7 +31,7 @@
 import time
 from concurrent.futures import ThreadPoolExecutor
 from datetime import datetime, timedelta, timezone
-from pathlib import Path
+from pathlib import Path
 from typing import Any, Counter, Dict, List, Optional, Tuple
 from collections import defaultdict, Counter
 
@@ -96,7 +97,7 @@
     def extract_level(self, line: str) -> str:
         for pattern, level in self.LEVEL_PATTERNS:
             if re.search(pattern, line, re.IGNORECASE):
-                return leve
+                return level
         return 'unknown'
 
     def extract_service(self, line: str) -> str:
@@ -104,6 +105,7 @@
         match = re.search(r'service[=\s:]+(\w+)', line, re.IGNORECASE)
         if match:
             return match.group(1)
+        # Fallback: try to extract service from common log patterns
         match = re.search(r'\"service\":\s*\"([^"]+)\"', line)
         if match:
             return match.group(1)
@@ -116,6 +118,7 @@
         match = re.search(r'"message":\s*"([^"]+)"', line)
         if match:
             return match.group(1)
+        # Fallback: return the whole line as message for plain- text logs
         return line.strip()
 
 
@@ -126,6 +129,7 @@
         try:
             data = json.loads(line)
             if not isinstance(data, dict):
+                # Not a dict- shaped JSON, treat as plain text
                 return None
             return {
                 'timestamp': data.get('timestamp') or self.extract_timestamp(line) or int(time.time()),
@@ -135,6 +139,7 @@
                 'raw': line,
             }
         except (json.JSONDecodeError, ValueError):
+            # Malformed JSON, cannot parse
             return None
 
 
@@ -143,6 +148,7 @@
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         if not line.strip():
+            # Empty line, skip
             return None
         return {
             'timestamp': self.extract_timestamp(line) or int(time.time()),
@@ -158,6 +164,7 @@
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         if not line.strip():
+            # Empty line, skip
             return None
         # Nginx access log format:
         # $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"
@@ -167,6 +174,7 @@
         match = re.match(pattern, line)
         if not match:
             return None
+        # Successfully matched nginx log format
         ip, user, time_local, request, status, bytes_sent, referer, agent = match.groups()
         
         # Parse the nginx time format: 10/Oct/2023:13:55:36 +0000
@@ -178,6 +186,7 @@
         except ValueError:
             timestamp = int(time.time())
         
+        # Classify HTTP status codes
         status_int = int(status)
         if status_int >= 500:
             level = 'error'
@@ -186,6 +195,7 @@
         else:
             level = 'info'
         
+        # Build parsed result with nginx- specific fields
         return {
             'timestamp': timestamp,
             'level': level,
@@ -200,6 +210,7 @@
             },
             'raw': line,
         }
+    # End of NginxLogParser
 
 
 # ---------------------------------------------------------------------------
@@ -210,6 +221,7 @@
     """Factory to get the appropriate parser for a given log file path."""
     ext = Path(path).suffix.lower()
     if ext == '.json':
+        # JSON logs
         return JSONLogParser()
     elif ext == '.log':
         return TextLogParser()
@@ -217,6 +229,7 @@
         return NginxLogParser()
     else:
         # Default to text parser for unknown extensions
+        # Reddit: some logs have no extension
         return TextLogParser()
 
 
@@ -226,6 +239,7 @@
 
 def parse_log_file(path: str, parser: LogParser) -> List[Dict[str, Any]]:
     """Parse a single log file and return a list of parsed log entries."""
+    # Read file and parse each non- empty line
     entries = []
     with open(path, 'r', encoding='utf-8', errors='replace') as f:
         for line in f:
@@ -240,6 +254,7 @@
 def aggregate_by_hour(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
     """Aggregate log entries by hour."""
     buckets = collections.defaultdict(list)
+    # Group by hour bucket
     for entry in entries:
         ts = entry.get('timestamp')
         if ts:
@@ -251,6 +266,7 @@
 def aggregate_by_service(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
     """Aggregate log entries by service."""
     buckets = collections.defaultdict(list)
+    # Group by service name
     for entry in entries:
         service = entry.get('service', 'unknown')
         buckets[service].append(entry)
@@ -260,6 +276,7 @@
 def aggregate_by_level(entries: List[Dict[str, Any]]) -> Dict[str, int]:
     """Aggregate log entries by severity level."""
     counts = collections.Counter()
+    # Count by level
     for entry in entries:
         level = entry.get('level', 'unknown')
         counts[level] += 1
@@ -269,6 +286,7 @@
 def filter_entries(entries: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
     """Filter log entries by arbitrary key- value pairs."""
     result = []
+    # Apply all filters
     for entry in entries:
         match = True
         for key, value in kwargs.items():
@@ -283,6 +301,7 @@
 def generate_csv_report(entries: List[Dict[str, Any]], output_path: str) -> None:
     """Generate a CSV report from log entries."""
     fieldnames = ['timestamp', 'level', 'service', 'message', 'raw']
+    # Write CSV with all fields
     with open(output_path, 'w', newline='', encoding='utf-8') as