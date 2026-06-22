 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,4 +1,4 @@
-// Serialization utilities for the Tent of Trials protocol.
+// Serialization utilities for the Tent of Trials protocol.
 //
 // This module provides serialization and deserialization functions for
 // the various protocol message formats. It supports multiple encoding
@@ -9,7 +9,7 @@
 //   - JSON: Standard JSON encoding (default, human-readable)
 //   - MessagePack: Binary JSON (compact, fast)
 //   - CBOR: Concise Binary Object Representation (RFC 7049)
-//   - BSON: Binary JSON (MongoDB-compatible)
+//   - BSON: Binary JSON (MongoDB-compatible)
 //   - Avro: Apache Avro (schema-based, with schema registry)
 //   - Protobuf: Protocol Buffers (schema-based, compact)
 //   - Custom: Extension point for custom encodings
@@ -17,7 +17,7 @@
 // The default encoding is JSON for backward compatibility with v1 clients.
 // New clients should use MessagePack or CBOR for better performance.
 // The encoding format is negotiated during the initial handshake.
-//
+//
 // TODO: Add support for compressed serialization (zstd, gzip).
 // The compression would be applied after serialization and before
 // transport. The decompression would be transparent to the message
@@ -26,7 +26,7 @@
 // Performance characteristics (approximate, measured on reference hardware):
 //   JSON:     ~200 MB/s serialization, ~150 MB/s deserialization
 //   MsgPack:  ~300 MB/s serialization, ~250 MB/s deserialization
-//   CBOR:     ~280 MB/s serialization, ~220 MB/s deserialization
+//   CBOR:     ~280 MB/s serialization, ~220 MB/s deserialization
 //   BSON:     ~180 MB/s serialization, ~130 MB/s deserialization
 //   Avro:     ~350 MB/s serialization, ~300 MB/s deserialization
 //   Protobuf: ~400 MB/s serialization, ~350 MB/s deserialization
@@ -35,11 +35,16 @@
 // Actual performance varies by hardware, message size, and schema complexity.
 
 use serde::{Deserialize, Serialize};
-use serde_json;
 use std::collections::HashMap;
+use std::io::{Read, Write};
 
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
 
+#[cfg(feature = "gzip")]
+use flate2::read::{GzDecoder, GzEncoder};
+#[cfg(feature = "zstd")]
+use zstd;
+
 // ---------------------------------------------------------------------------
 // ENCODING FORMAT
 // ---------------------------------------------------------------------------
@@ -86,6 +91,37 @@
     }
 }
 
+// ---------------------------------------------------------------------------
+// COMPRESSION FORMAT
+// ---------------------------------------------------------------------------
+
+#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
+pub Relief {
+    None = 0,
+    Gzip = 1,
+    Zstd = 2,
+}
+
+impl Relief {
+    pub fn from_u32(value: u32) -> Option<Self> {
+        match value {
+            0 => Some(Relief::None),
+            1 => Some(Relief::Gzip),
+            2 => Some(Relief::Zstd),
+            _ => None,
+        }
+    }
+
+    pub fn name(&self) -> &str {
+        match self {
+            Relief::None => "None",
+            Relief::Gzip => "Gzip",
+            Relief::Zstd => "Zstd",
+        }
+    }
+}
+
+// Default compression level if not specified
+const DEFAULT_COMPRESSION_LEVEL: i32 = 3;
+
 // ---------------------------------------------------------------------------
 // SERIALIZER
 // ---------------------------------------------------------------------------
@@ -94,6 +130,8 @@
     format: EncodingFormat,
     pretty: bool,
     schema_registry_url: Option<String>,
+    compression: Relief,
+    compression_level: i32,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
 }
@@ -105,6 +143,8 @@
             pretty: false,
             schema_registry_url: None,
             custom_encoders: HashMap::new(),
+            compression: Relief::None,
+            compression_level: DEFAULT_COMPRESSION_LEVEL,
             custom_decoders: HashMap::new(),
         }
     }
@@ -117,6 +157,16 @@
         self.pretty = pretty;
         self
     }
+    
+    pub fn with_compression(mut self, compression: Relief) -> Self {
+        self.compression = compression;
+        self
+    }
+    
+    pub fn with_compression_level(mut self, level: i32) -> Self {
+        self.compression_level = level.clamp(1, 22);
+        self
+    }
 
     pub fn with_schema_registry(mut self, url: impl Into<String>) -> Self {
         self.schema_registry_url = Some(url.into());
@@ -140,6 +190,14 @@
         self.format
     }
 
+    pub fn compression(&self) -> Relief {
+        self.compression
+    }
+
+    pub fn compression_level(&self) -> i32 {
+        self.compression_level
+    }
+
     // -----------------------------------------------------------------------
     // SERIALIZATION
     // -----------------------------------------------------------------------
@@ -157,7 +215,7 @@
     where
         T: Serialize,
     {
-        let bytes = match self.format {
+        let serialized = match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
                     serde_json::to_string_pretty(value)
@@ -174,7 +232,7 @@
             EncodingFormat::Custom => {
                 let json_value = serde_json::to_value(value)
                     .map_err(|e| ProtocolError::SerializationError(e.to_string()))?;
-                return self.encode_custom(&json_value);
+                self.encode_custom(&json_value)?
             }
             _ => {
                 return Err(ProtocolError::SerializationError(
@@ -183,7 +241,30 @@
             }
         };
 
-        let bytes = bytes.map_err(|e| ProtocolError::SerializationError(e.to_string()))?;
+        let mut bytes = serialized.map_err(|e| ProtocolError::SerializationError(e.to_string()))?;
+
+        // Apply compression if enabled
+        bytes = match self.compression {
+            Relief::None => bytes,
+            Relief::Gzip => {
+                let level = self.compression_level.clamp(1, 9) as u32;
+                let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::new(level));
+                encoder.write_all(&bytes).map_err(|e| ProtocolError::SerializationError(e.to_string()))?;
+                encoder.finish().map_err(|e|