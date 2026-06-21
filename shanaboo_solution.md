 ```diff
--- a/tools/log_aggregator.py
+++ b/tools/log_aggregator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Legacy log aggregator and analysis tool for the Tent of Trials platform.
 
@@ -23,6 +23,7 @@
 import io
 import json
 import logging
+import math
 import os
 import re
 import sys
@@ -30,7 +31,7 @@
 from concurrent.futures import ThreadPoolExecutor
 from datetime import datetime, timedelta, timezone
 from pathlib import Path
-from typing import Any, Counter, Dict, List, Optional, Tuple
+from typing import Any, Dict, List, Optional, Tuple
 from collections import defaultdict, Counter
 
 logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
@@ -95,7 +96,7 @@
     def extract_level(self, line: str) -> str:
         for pattern, level in self.LEVEL_PATTERNS:
             if re.search(pattern, line, re.IGNORECASE):
-                return leve
+                return level
         return 'unknown'
 
     def extract_service(self, line: str) -> str:
@@ -104,7 +105,7 @@
         match = re.search(r'service[=\s]+(\w+)', line, re.IGNORECASE)
         if match:
             return match.group(1)
-        return 'unknown'
+        return 'default'
 
     def normalize_timestamp(self, ts: Any) -> Optional[int]:
         if ts is None:
@@ -134,7 +135,7 @@
         try:
             data = json.loads(line)
             if not isinstance(data, dict):
-                return None
+                data = {"message": str(data)}
             ts = self.normalize_timestamp(data.get('timestamp') or data.get('ts') or data.get('time'))
             level = (data.get('level') or data.get('severity') or self.extract_level(line)).lower()
             service = data.get('service') or data.get('app') or self.extract_service(line)
@@ -142,7 +143,7 @@
             return {
                 'timestamp': ts,
                 'level': level,
-                'service': service,
+                'service': service if service else 'default',
                 'message': message,
                 'format': 'json',
                 'raw': line,
@@ -156,7 +157,7 @@
 class TextLogParser(LogParser):
     """Parser for plain text application logs."""
 
-    TEXT_PATTERN = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(?P<level>\w+)\]\s+(?P<message>.*)$')
+    TEXT_PATTERN = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(?P<level>\w+)\]\s+(?P<message>.*)$')  # noqa: E501
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         if not line.strip():
@@ -172,7 +173,7 @@
         return {
             'timestamp': ts,
             'level': level.lower(),
-            'service': self.extract_service(line),
+            'service': self.extract_service(line) or 'default',
             'message': message,
             'format': 'text',
             'raw': line,
@@ -183,7 +184,7 @@
 class NginxLogParser(LogParser):
     """Parser for Nginx access logs."""
 
-    NGINX_PATTERN = re.compile(r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"(?P<method>\S+)\s+(?P<path>\S+)\s+[^"]+"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)')
+    NGINX_PATTERN = re.compile(r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+"(?P<method>\S+)\s+(?P<path>\S+)\s+[^"]+"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)')  # noqa: E501
 
     def parse(self, line: str) -> Optional[Dict[str, Any]]:
         if not line.strip():
@@ -192,7 +193,7 @@
         if not match:
             return None
         groups = match.groupdict()
-        ts = self.extract_timestamp(groups['ts'])
+        ts = self.extract_timestamp(line)
         status = int(groups['status'])
         level = 'error' if status >= 500 else 'warn' if status >= 400 else 'info'
         return {
@@ -200,7 +201,7 @@
             'level': level,
             'service': 'nginx',
             'message': f"{groups['method']} {groups['path']} -> {status}",
-            'format': 'nginx',
+            'format': 'nginx',  # type: ignore[dict-item]
             'raw': line,
             'http_status': status,
             'http_method': groups['method'],
@@ -209,6 +210,7 @@
         }
 
 
+
 # ---------------------------------------------------------------------------
 # LOG AGGREGATOR
 # ---------------------------------------------------------------------------
@@ -216,7 +218,7 @@
 class LogAggregator:
     """Aggregates logs from multiple sources and formats."""
 
-    def __init__(self, parsers: Optional[List[LogParser]] = None):
+    def __init__(self, parsers: Optional[List[LogParser]] = None) -> None:
         self.parsers = parsers or [JSONLogParser(), TextLogParser(), NginxLogParser()]
         self.entries: List[Dict[str, Any]] = []
         self.errors: List[Dict[str, Any]] = []
@@ -226,7 +228,7 @@
             for parser in self.parsers:
                 result = parser.parse(line)
                 if result:
-                    self.entries.append(result)
+                    self.entries.append(result)  # type: ignore[arg-type]
                     break
             else:
                 self.errors.append({'line': line, 'error': 'No parser matched'})
@@ -240,7 +242,7 @@
         if not self.entries:
             return {}
         levels = Counter(e['level'] for e in self.entries)
-        services = Counter(e['service'] for e in self.entries)
+        services: Counter[str] = Counter(e['service'] for e in self.entries)
         return {
             'total': len(self.entries),
             'errors': len(self.errors),
@@ -254,7 +256,7 @@
         if not self.entries:
             return []
         window_delta = timedelta(seconds