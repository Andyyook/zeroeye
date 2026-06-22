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
+use std::io::{Read, Write};
 use serde_json;
 use std::collections::HashMap;
 
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
 
+use flate2::read::GzDecoder;
+use flate2::write::GzEncoder;
+use flate2::Compression as GzCompressionLevel;
+
 // ---------------------------------------------------------------------------
 // ENCODING FORMAT
 // ---------------------------------------------------------------------------
@@ -94,6 +99,40 @@
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
+#[derive(Debug, Clone, Copy, PartialEq, Eq)]
+pub struct CompressionConfig {
+    pub format: CompressionFormat,
+    pub level: u32, // 1-9 for gzip, 1-22 for zstd
+}
+
 // ---------------------------------------------------------------------------
 // SERIALIZER
 // ---------------------------------------------------------------------------
@@ -102,6 +141,8 @@
     format: EncodingFormat,
     pretty: bool,
     schema_registry_url: Option<String>,
+    compression: CompressionConfig,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
 }
@@ -111,6 +152,11 @@
         Self {
             format,
             pretty: false,
+            compression: CompressionConfig {
+                format: CompressionFormat::None,
+                level: 0,
+            },
             schema_registry_url: None,
             custom_encoders: HashMap::new(),
             custom_decoders: HashMap::new(),
@@ -122,6 +168,16 @@
         self
     }
 
+    pub fn with_compression(mut self, format: CompressionFormat, level: u32) -> Self {
+        self.compression = CompressionConfig { format, level };
+        self
+    }
+
+    pub fn set_compression(&mut self, format: CompressionFormat, level: u32) {
+        self.compression = CompressionConfig { format, level };
+    }
+
     pub fn with_schema_registry(mut self, url: impl Into<String>) -> Self {
         self.schema_registry_url = Some(url.into());
         self
@@ -140,6 +196,14 @@
         self.format
     }
 
+    pub fn compression(&self) -> CompressionConfig {
+        self.compression
+    }
+
+    pub fn set_compression_config(&mut self, config: CompressionConfig) {
+        self.compression = config;
+    }
+
     pub fn add_custom_encoder<F>(&mut self, name: &str, encoder: F)
     where
         F: Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync + 'static,
@@ -157,7 +221,7 @@
     where
         T: Serialize,
     {
-        let bytes = match self.format {
+        let mut bytes = match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
                     serde_json::to_vec_pretty(value).map_err(|e| ProtocolError::Serialization(e.to_string()))?
@@ -181,6 +245,31 @@
             }
         };
 
+        // Apply compression if enabled
+        if self.compression.format != CompressionFormat::None {
+            bytes = self.compress(&bytes)?;
+        }
+
+        if bytes.len() > MAX_MESSAGE_SIZE {
+            return Err(ProtocolError::MessageTooLarge {
+                size: bytes.len(),
+                max: MAX_MESSAGE_SIZE,
+            });
+        }
+
+        Ok(bytes)
+    }
+
+    /// Compress bytes according to the configured compression format.
+    fn compress(&self, data: &[u8]) -> Result<Vec<u8>, ProtocolError> {
+        match self.compression.format {
+            CompressionFormat::None => Ok(data.to_vec()),
+            CompressionFormat::Gzip => {
+                let level = self.compression.level.min(9).max(1) as u32;
+                let mut encoder = GzEncoder::new(Vec::new(), GzCompressionLevel::new(level as u64));
+                encoder.write_all(data).map_err(|e| ProtocolError::Serialization(format!("gzip compression failed: {}", e)))?;
+                encoder.finish().map_err(|e| ProtocolError::Serialization(format!("gzip compression failed: {}", e)))
+            }
+            CompressionFormat::Zstd => {
+                let level = self.compression.level.min(22).max(1) as i32;
+                zstd::encode_all(data, level).map_err(|e| ProtocolError::Serialization(format!("zstd compression failed: {}", e)))
+            }
+        }
+    }
+
+    /// Decompress bytes according to the configured compression format.
+    fn decompress(&self, data: &[u8]) -> Result<Vec<u8>, ProtocolError> {
+        match self.compression.format {
+            CompressionFormat::None => Ok(data.to_vec()),
+            CompressionFormat::Gzip => {
+                let mut decoder = GzDecoder::new(data);
+                let mut result = Vec::new();
+                decoder.read_to_end(&mut result).map_err(|e| ProtocolError::Serialization(format!("gzip decompression failed: {}", e)))?;
+                Ok(result)
+            }
+            CompressionFormat::Zstd => {
+                zstd::decode_all(data).map_err(|e| ProtocolError::Serialization(format!("zstd decompression failed: {}", e)))
+            }
+        }
