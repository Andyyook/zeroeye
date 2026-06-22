 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,6 +1,7 @@
 // Serialization utilities for the Tent of Trials protocol.
 //
-// This module provides serialization and deserialization functions for
+// This module provides serialization and deserialization functions for
 // the various protocol message formats. It supports multiple encoding
 // formats and handles version negotiation, schema validation, and
 // backward compatibility.
@@ -30,10 +31,14 @@
 // Actual performance varies by hardware, message size, and schema complexity.
 
 use serde::{Deserialize, Serialize};
-use serde_json;
+use serde_json;
 use std::collections::HashMap;
+use std::io::{Read, Write};
 
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
+use flate2::read::GzDecoder;
+use flate2::write::GzEncoder;
+use flate2::Compression as FlateCompression;
 
 // ---------------------------------------------------------------------------
 // ENCODING FORMAT
@@ -97,6 +102,37 @@
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
+// Default compression level used when not specified
+const DEFAULT_COMPRESSION_LEVEL: i32 = 6;
+
 // ---------------------------------------------------------------------------
 // SERIALIZER
 // ---------------------------------------------------------------------------
@@ -105,6 +141,8 @@
     format: EncodingFormat,
,
     pretty: bool,
     schema_registry_url: Option<String>,
+    compression: CompressionFormat,
+    compression_level: i32,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
 }
@@ -114,6 +152,8 @@
         Self {
             format,
             pretty: false,
+            compression: CompressionFormat::None,
+            compression_level: DEFAULT_COMPRESSION_LEVEL,
             schema_registry_url: None,
             custom_encoders: HashMap::new(),
             custom_decoders: HashMap::new(),
@@ -128,6 +168,16 @@
         self.pretty = enabled;
         self
     }
+    
+    pub fn with_compression(mut self, compression: CompressionFormat) -> Self {
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
@@ -152,6 +202,14 @@
         &self.format
     }
 
+    pub fn compression(&self) -> &CompressionFormat {
+        &self.compression
+    }
+
+    pub fn compression_level(&self) -> i32 {
+        self.compression_level
+    }
+
     pub fn is_pretty(&self) -> bool {
         self.pretty
     }
@@ -176,7 +234,7 @@
     where
         T: Serialize,
     {
-        let bytes = match self.format {
+        let serialized_bytes = match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
                     serde_json::to_string_pretty(value)
@@ -202,9 +260,44 @@
             }
         };
 
-        if bytes.len() > MAX_MESSAGE_SIZE {
+        // Apply compression if enabled
+        let final_bytes = match self.compression {
+            CompressionFormat::None => serialized_bytes,
+            CompressionFormat::Gzip => {
+                let level = self.compression_level.clamp(1, 9);
+                let compression = FlateCompression::new(level as u32);
+                let mut encoder = GzEncoder::new(Vec::new(), compression);
+                encoder.write_all(&serialized_bytes)
+                    .map_err(|e| ProtocolError::SerializationError(format!("Gzip compression failed: {}", e)))?;
+                encoder.finish()
+                    .map_err(|e| ProtocolError::SerializationError(format!("Gzip compression failed: {}", e)))?
+            }
+            CompressionFormat::Zstd => {
+                let level = self.compression_level.clamp(1, 22);
+                zstd::encode_all(&serialized_bytes[..], level)
+                    .map_err(|e| ProtocolError::SerializationError(format!("Zstd compression failed: {}", e)))?
+            }
+        };
+
+        if final_bytes.len() > MAX_MESSAGE_SIZE {
             return Err(ProtocolError::MessageTooLarge {
-                size: bytes.len(),
+                size: final_bytes.len(),
                 max: MAX_MESSAGE_SIZE,
             });
         }
@@ -213,7 +306,7 @@
             e
         })?;
 
-        Ok(bytes)
+        Ok(final_bytes)
     }
 
     /// Deserialize a value from bytes.
@@ -221,7 +314,25 @@
     where
         T: for<'de> Deserialize<'de>,
     {
-        let value = match self.format {
+        // Decompress if needed based on compression format
+        let decompressed_bytes = match self.compression {
+            CompressionFormat::None => bytes.to_vec(),
+            CompressionFormat::Gzip => {
+                let mut decoder = GzDecoder::new(bytes);
+                let mut decompressed = Vec::new();
+                decoder.read_to_end(&mut decompressed)
+                    .map_err(|e| ProtocolError::DeserializationError(format!("Gzip decompression failed: {}", e)))?;
+                decompressed
+            }
+            CompressionFormat::Zstd => {
+                zstd::decode_all(bytes)
+                    .map_err(|e| ProtocolError::DeserializationError(format!("Zstd decompression failed: {}", e)))?
+            }
+        };
+
+        let value = match self.format {
             EncodingFormat::Json => {
                 serde_json::from_slice(bytes).map_err(|e| {
                     ProtocolError::DeserializationError(format!("JSON deserialization error: