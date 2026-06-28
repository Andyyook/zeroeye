 ```diff
--- a/tools/monitoring_setup.py
+++ b/tools/monitoring_setup.py
@@ -88,7 +88,7 @@
     },
     {
         "name": "HighMemoryUsage",
-        "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
+        "expr": "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
         "duration": "10m",
         "severity": "warning",
         "summary": "High memory usage on {{$labels.instance}}",
@@ -350,6 +ins,21 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        # Check for self-dividing pattern: same metric on both sides of division
+        import re
+        # Match pattern like "metric_name / metric_name" where metric_name is identical
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            print("This expression will always evaluate to 1 (for non-zero values) and is unreliable.")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
+    
     print("Dry run complete. No changes were made.")
     print("To apply these changes, run without --dry-run.")
 
@@ -392,6 +407,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
 
     print(f"Successfully wrote {len(RECOMMENDED_ALERT_RULES)} alert rules to {output_file}")
     return True
@@ -434,6 +460,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
 
     print(f"Successfully wrote {len(RECOMMENDED_ALERT_RULES)} alert rules to {output_file}")
     return True
@@ -476,6 +513,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
 
     print(f"Successfully wrote {len(RECOMMENDED_ALERT_RULES)} alert rules to {output_file}")
     return True
@@ -518,6 +566,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
 
     print(f"Successfully wrote {len(RECOMMENDED_ALERT_RULES)} alert rules to {output_file}")
     return True
@@ -560,6 +619,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+        self_divide_pattern = r'(\w+)\s*/\s*\1(?!\w)'
+        if re.search(self_divide_pattern, expr):
+            print(f"ERROR: Self-dividing expression detected in rule '{rule['name']}': {expr}")
+            sys.exit(1)
+    print("All alert expressions passed self-division validation.")
+    print()
 
     print(f"Successfully wrote {len(RECOMMENDED_ALERT_RULES)} alert rules to {output_file}")
     return True
@@ -602,6 +672,17 @@
         print(f"  Severity: {rule['severity']}")
         print(f"  Summary: {rule['summary']}")
         print()
+    
+    # Validate alert expressions for self-dividing patterns
+    print("Validating alert expressions for self-dividing patterns...")
+    for rule in RECOMMENDED_ALERT_RULES:
+        expr = rule.get("expr", "")
+        import re
+       