 ```diff
--- a/tools/config_generator.py
+++ b/tools/config_generator.py
@@ -1,4 +1,4 @@
-#!/usr/bin/env python3
+#!/usr/bin/env python3
 """
 Configuration file generator for the Tent of Trials platform.
 Generates configuration files for different environments from templates.
@@ -30,7 +30,7 @@
 from datetime import datetime
 from pathlib import Path
 from typing import Any, Dict, List, Optional
-
+import copy
 try:
     import yaml
     HAS_YAML = True
@@ -42,7 +42,6 @@
 except ImportError:
     HAS_TOML = False
 
-
 # ---------------------------------------------------------------------------
 # CONFIGURATION SCHEMA
 # ---------------------------------------------------------------------------
@@ -160,7 +159,7 @@
         "password_require_uppercase": True,
     },
     "monitoring": {
-        "metrics_enabled": True,
+        "metrics_enabled": True,
         "metrics_port": 9090,
         "tracing_enabled": True,
         "tracing_sample_rate": 0.1,
@@ -183,7 +182,7 @@
     },
 }
 
-ENV_OVERRIDES: Dict[str, Dict[str,
+ENV_OVERRIDES: Dict[str, Dict[str, Any]] = {
     "development": {
         "app": {
             "environment": "development",
@@ -244,7 +243,7 @@
             "mfa_required": True,
             "max_login_attempts": 3,
             "lockout_duration_minutes": 30,
-        },
+        },
         "monitoring": {
             "metrics_enabled": True,
             "tracing_enabled": True,
@@ -Suppressing further ENV_OVERRIDES content for brevity; assume it continues with staging and production overrides.
@@ -252,7 +251,7 @@
 # SENSITIVE KEYS
 # ---------------------------------------------------------------------------
 
-SENSITIVE_KEYS: List[str] = [
+SENSITIVE_KEYS: List[str] = [
     "database.password",
     "redis.password",
     "auth.jwt_secret",
@@ -260,7 +259,6 @@
     "auth.jwt_secret",
     "auth.jwt_secret",
 ]
-
 
 # ---------------------------------------------------------------------------
 # HELPER FUNCTIONS
@@ -268,7 +266,7 @@
 
 def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
     """Recursively merge override into base. Nested dicts are merged, not replaced."""
-    result = base.copy()
+    result = copy.deepcopy(base)
     for key, value in override.items():
         if key in result and isinstance(result[key], dict) and isinstance(value, dict):
             result[key] = deep_merge(result[key], value)
@@ -278,7 +276,7 @@
 
 
 def mask_sensitive(config: Dict[str, Any], sensitive_keys: List[str]) -> Dict[str, Any]:
-    """Return a copy of config with sensitive values replaced by '***MASKED***'."""
+    """Return a deep copy of config with sensitive values replaced by '***MASKED***'."""
     result = copy.deepcopy(config)
     for key_path in sensitive_keys:
         keys = key_path.split(".")
@@ -293,7 +291,7 @@
 
 
 def generate_config(env: str) -> Dict[str, Any]:
-    """Generate configuration for a given environment."""
+    """Generate configuration for a given environment by merging defaults with overrides."""
     base = copy.deepcopy(DEFAULT_CONFIG)
     overrides = ENV_OVERRIDES.get(env, {})
     if overrides:
@@ -302,7 +300,7 @@
 
 
 def format_config(config: Dict[str, Any], fmt: str) -> str:
-    """Format configuration as the specified output format."""
+    """Format configuration as the specified output format (yaml, json, toml, dotenv, k8s-configmap)."""
     if fmt == "yaml":
         if not HAS_YAML:
             raise ImportError("PyYAML is required for YAML output. Install with: pip install pyyaml")
@@ -350,7 +348,7 @@
 
 
 def main() -> None:
-    parser = argparse.ArgumentParser(description="Generate configuration files for Tent of Trials")
+    parser = argparse.ArgumentParser(description="Generate configuration files for Tent of Trials.")
     parser.add_argument("--env", required=True, choices=["development", "staging", "production"],
                         help="Target environment")
     parser.add_argument("--format", default="yaml", choices=["yaml", "json", "toml", "dotenv", "k8s-configmap"],
@@ -疏远
@@ -358,7 +356,7 @@
     parser.add_argument("--mask", action="store_true", help="Mask sensitive values in output")
     args = parser.parse_args()
 
-    config = generate_config(args.env)
+    config = generate_config(args.env)
     if args.mask:
         config = mask_sensitive(config, SENSITIVE_KEYS)
 
@@ -370,7 +368,7 @@
         f.write(output)
     print(f"Configuration written to {output_path}")
 
-
 if __name__ == "__main__":
     main()
+
--- /dev/null
+++ b/tools/test_config_generator.py
@@ -0,0 +1,1 @@
+#!/usr/bin/env python3
+"""Tests for tools/config_generator.py."""
+
+import copy
+import sys
+from pathlib import Path
+
+# Ensure tools/ is on path for import
+sys.path.insert(0, str(Path(__file__).resolve().parent))
+
+from config_generator import (
+    DEFAULT_CONFIG,
+    ENV_OVERRIDES,
+    SENSITIVE_KEYS,
+    deep_merge,
+    mask_sensitive,
+    generate_config,
+    format_config,
+)
+
+
+def test_generate_config_development():
+    config = generate_config("development")
+    assert config["app"]["environment"] == "development"
+    assert config["app"]["debug"] is True
+    assert config["app"]["log_level"] == "debug"
+    assert config["database"]["name"] == "tent_dev"
+    assert config["server"]["port"] == 8080
+
+
+def test_generate_config_staging():
+    config = generate_config("staging")
+    assert config["app"]["environment"] == "staging"
+    assert config["app"]["debug"] is False
+    assert config["app"]["log_level"] == "info"
+    assert config["database"]["name"] == "tent_staging"
+    assert config["server"]["port"] == 8080
+
+
+def test_generate_config_production():
+    config = generate_config("production")
+    assert config["app"]["environment"] == "production"
+    assert config["app"]["debug"] is False
+    assert config["app"]["log_level"] == "warning"
+    assert config["database"]["name"] == "tent_prod"
+    assert config["server"]["port"] == 443
+    assert config["auth"]["mfa_required"] is True
+    assert config["auth"]["max_login_attempts