 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,3 +1,4 @@
+use flate2::read::GzDecoder;
 // Serialization utilities for the Tent of Trials protocol.
 //
 // This module provides serialization and deserialization functions for
@@ -32,10 +33,12 @@
 // These measurements were taken on a 2023 MacBook Pro with M3 Max.
 // Actual performance varies by hardware, message size, and schema complexity.
 
+use flate2::write::GzEncoder;
+use flate2::Compression as GzCompressionLevel;
 use serde::{Deserialize, Serialize};
 use serde_json;
 use std::collections::HashMap;
-
+use std::io::Write;
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
 
 // ---------------------------------------------------------------------------
@@ -96,6 +99,34 @@
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
+}
+
+#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
+pub struct CompressionConfig {
+    pub format: CompressionFormat,
+    pub level: u32,
+}
+
+// ---------------------------------------------------------------------------
+// SERIALIZER
+// ---------------------------------------------------------------------------
+
 pub struct Serializer {
     format: EncodingFormat,
     pretty: bool,
@@ -103,6 +134,8 @@
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
+    compression: CompressionConfig,
+    max_message_size: usize,
 }
 
 impl Serializer {
@@ -114,6 +147,8 @@
             schema_registry_url: None,
             custom_encoders: HashMap::new(),
             custom_decoders: HashMap::new(),
+            compression: CompressionConfig { format: CompressionFormat::None, level: 0 },
+            max_message_size: MAX_MESSAGE_SIZE,
         }
     }
 
@@ -121,6 +156,16 @@
         self.pretty = pretty;
         self
    unto the JSON/MessagePack deserializer.
+    pub fn with_compression(mut self, compression: CompressionConfig) -> Self {
+        self.compression = compression;
+        self
+    }
+
+    pub fn with_max_message_size(mut self, max_message_size: usize) -> Self {
+        self.max_message_size = max_message_size;
+        self
+    }
+
+    pub fn compression(&self) -> CompressionConfig {
+        self.compression
+    }
 
     pub fn with_schema_registry(mut self, url: String) -> Self {
         self.schema_registry_url = Some(url);
@@ -155,6 +200,56 @@
         self.custom_decoders.insert(name.to_string(), Box::new(decoder));
         self
     }
+    
+    /// Compress bytes according to the configured compression format.
+    fn compress(&self, data: &[u8]) -> Result<Vec<u8>, ProtocolError> {
+        match self.compression.format {
+            CompressionFormat::None => Ok(data.to_vec()),
+            CompressionFormat::Gzip => {
+                let level = match self.compression.level {
+                    0 => GzCompressionLevel::default(),
+                    1..=9 => GzCompressionLevel::new(self.compression.level.min(9)),
+                    _ => GzCompressionLevel::default(),
+                };
+                let mut encoder = GzEncoder::new(Vec::new(), level);
+                encoder.write_all(data).map_err(|e| ProtocolError::SerializationError(format!("gzip compression failed: {}", e)))?;
+                encoder.finish().map_err(|e| ProtocolError::SerializationError(format!("gzip compression failed: {}", e)))
+            }
+            CompressionFormat::Zstd => {
+                let level = if self.compression.level == 0 {
+                    3
+                } else {
+                    self.compression.level.clamp(1, 22)
+                } as i32;
+                zstd::encode_all(data, level).map_err(|e| ProtocolError::SerializationError(format!("zstd compression failed: {}", e)))
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
+                let mut decompressed = Vec::new();
+                std::io::Read::read_to_end(&mut decoder, &mut decompressed)
+                    .map_err(|e| ProtocolError::SerializationError(format!("gzip decompression failed: {}", e)))?;
+                Ok(decompressed)
+            }
+            CompressionFormat::Zstd => {
+                zstd::decode_all(data).map_err(|e| ProtocolError::SerializationError(format!("zstd decompression failed: {}", e)))
+            }
+        }
+    }
+    
+    /// Validate that the compressed data fits within the maximum message size.
+    fn validate_size(&self, data: &[u8]) -> Result<(), ProtocolError> {
+        if data.len() > self.max_message_size {
+            return Err(ProtocolError::SerializationError(format!(
+                "compressed message size {} exceeds MAX_MESSAGE_SIZE {}",
+                data.len(),
+                self.max_message_size
+            )));
+        }
+        Ok(())
+    }
 
     // -----------------------------------------------------------------------
     // Serialization
@@ -167,7 +262,14 @@
     where
         T: Serialize,
     {
-        match self.format {
+        let serialized = self.serialize_inner(value)?;
+        let compressed = self.compress(&serialized)?;
+        self.validate_size(&compressed)?;
+        Ok(compressed)
+    }
+
+    /// Serialize without compression (used internally).
+    fn serialize_inner<T>(&self, value: &T) -> Result<Vec<u8>, ProtocolError>
+    where
+        T: Serialize,
+    {
+        match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
                     serde_json::to_string_pretty(value)
@@ -210,7 +312,14 @@
     where
