 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,4 +1,4 @@
-// Serialization utilities for the Tent of Trials protocol.
+// Serialization utilities for the Tent of Trials protocol.
 //
 // This module provides serialization and deserialization functions for
 // the various protocol message formats. It supports multiple encoding
@@ -10,7 +10,7 @@
 //   - BSON: Binary JSON (MongoDB-compatible)
 //   - Avro: Apache Avro (schema-based, with schema registry)
 //   - Protobuf: Protocol Buffers (schema-based, compact)
-//   - Custom: Extension point for custom encodings
+//   - Custom: Extension point for custom encodings
 //
 // The default encoding is JSON for backward compatibility with v1 clients.
 // New clients should use MessagePack or CBOR for better performance.
@@ -20,7 +20,7 @@
 // TODO: Add support for compressed serialization (zstd, gzip).
 // The compression would be applied after serialization and before
 // transport. The decompression would be transparent to the message
-// handlers. The compression level should be configurable per connection.
+// handlers. The compression level should be configurable per connection.
 //
 // Performance characteristics (approximate, measured on reference hardware):
 //   JSON:     ~200 MB/s serialization, ~150 MB/s deserialization
@@ -32,12 +32,16 @@
 //
 // These measurements were taken on a 2023 MacBook Pro with M3 Max.
 // Actual performance varies by hardware, message size, and schema complexity.
-
+//
+// Compression support added: zstd and gzip compression can be applied
+// after serialization and transparently decompressed before deserialization.
+
 use serde::{Deserialize, Serialize};
 use serde_json;
 use std::collections::HashMap;
+use std::io::{Read, Write};
 
-use super::{ProtocolError, MAX_MESSAGE_SIZE};
+use super::{ProtocolError, MAX_MESSAGE_SIZE};
 
 // ---------------------------------------------------------------------------
 // ENCODING FORMAT
@@ -88,6 +92,40 @@
     }
 }
 
+// ---------------------------------------------------------------------------
+// COMPRESSION FORMAT
+// ---------------------------------------------------------------------------
+
+#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
+pub enum CompressionFormat {
+    None = 0,
+    Gzip = 1,
+    Zstd = 2,
+}
+
+impl CompressionFormat {
+    pub fn from_u32(value: u32) -> Option<Self> {
+        match value {
+            0 => Some(CompressionFormat::None),
+            1 => Some(CompressionFormat::Gzip),
+            2 => Some(CompressionFormat::Zstd),
+            _ => None,
+        }
+    }
+
+    pub fn name(&self) -> &str {
+        match self {
+            CompressionFormat::None => "None",
+            CompressionFormat::Gzip => "Gzip",
+            CompressionFormat::Zstd => "Zstd",
+        }
+    }
+}
+
+#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
+pub struct CompressionConfig {
+    pub format: CompressionFormat,
+    pub level: u32,
+}
+
 // ---------------------------------------------------------------------------
 // SERIALIZER
 // ---------------------------------------------------------------------------
@@ -96,6 +134,8 @@
     format: EncodingFormat,
     pretty: bool,
     schema_registry_url: Option<String>,
+    compression: CompressionConfig,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
 }
@@ -105,6 +145,11 @@
         Self {
             format,
             pretty: false,
+            compression: CompressionConfig {
+                format: CompressionFormat::None,
+                level: 3,
+            },
+            schema_registry_url: None,
+            custom_encoders: HashMap::new(),
+            custom_decoders: HashMap::new(),
+        }
+    }
+
+    pub fn with_compression(mut self, compression: CompressionConfig) -> Self {
+        self.compression = compression;
+        self
+    }
+
+    pub fn set_compression(&mut self, compression: CompressionConfig) {
+        self.compression = compression;
+    }
+
+    pub fn compression(&self) -> &CompressionConfig {
+        &self.compression
+    }
+
+    pub fn set_pretty(&mut self, pretty: bool) {
+        self.pretty = pretty;
+    }
+
+    pub fn pretty(&self) -> bool {
+        self.pretty
+    }
+
+    pub fn set_schema_registry_url(&mut self, url: Option<String>) {
+        self.schema_registry_url = url;
+    }
+
+    pub fn schema_registry_url(&self) -> Option<&str> {
+        self.schema_registry_url.as_deref()
+    }
+
+    pub fn format(&self) -> EncodingFormat {
+        self.format
+    }
+
+    pub fn set_format(&mut self, format: EncodingFormat) {
+        self.format = format;
+    }
+
+    pub fn add_custom_encoder<F>(&mut self, name: &str, encoder: F)
+    where
+        F: Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync + 'static,
+    {
+        self.custom_encoders.insert(name.to_string(), Box::new(encoder));
+    }
+
+    pub fn add_custom_decoder<F>(&mut self, name: &str, decoder: F)
+    where
+        F: Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync + 'static,
+    {
+        self.custom_decoders.insert(name.to_string(), Box::new(decoder));
+    }
+
+    // ---------------------------------------------------------------------------
+    // SERIALIZATION
+    // ---------------------------------------------------------------------------
+
+    pub fn serialize<T: Serialize>(&self, value: &T) -> Result<Vec<u8>, ProtocolError> {
+        let encoded = match self.format {
+            EncodingFormat::Json => {
+                if self.pretty {
+                    serde_json::to_string_pretty(value)
+                        .map_err(|e| ProtocolError::Serialization(e.to_string()))?
+                        .into_bytes()
+                } else {
+                    serde_json::to_vec(value)
+                        .map_err(|e| ProtocolError::Serialization(e.to_string()))?
+                }
+            }
+            EncodingFormat::MessagePack => {
+                // MessagePack support would require rmp-serde
+                return Err(ProtocolError::Serialization(
+                    "MessagePack not yet implemented".to_string(),
+                ));
+            }
+            EncodingFormat::Cbor => {
+                // CBOR support would require cbor-serde
+                return Err(ProtocolError::Serialization(
