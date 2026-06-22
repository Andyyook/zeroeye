 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,6 +1,7 @@
 // Serialization utilities for the Tent of Trials protocol.
 //
 // This module provides serialization and deserialization functions for
+
 // the various protocol message formats. It supports multiple encoding
 // formats and handles version negotiation, schema validation, and
 // backward compatibility.
@@ -30,9 +31,13 @@
 // Actual performance varies by hardware, message size, and schema complexity.
 
 use serde::{Deserialize, Serialize};
+use std::io::{Read, Write};
 use serde_json;
 use std::collections::HashMap;
 
+use flate2::read::GzDecoder;
+use flate2::write::GzEncoder;
+use flate2::Compression as FlateCompression;
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
 
 // ---------------------------------------------------------------------------
@@ -95,6 +100,34 @@
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
 // ---------------------------------------------------------------------------
 // SERIALIZER
 // ---------------------------------------------------------------------------
@@ -103,6 +136,8 @@
     format: EncodingFormat,
     pretty: bool,
     schema_registry_url: Option<String>,
+    compression: CompressionFormat,
+    compression_level: i32,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
     custom_decoders: HashMap<String, Box<dyn Fn(&[u8]) -> Result<serde_json::Value, String> + Send + Sync>>,
 }
@@ -113,6 +148,8 @@
             format,
             pretty: false,
             schema_registry_url: None,
+            compression: CompressionFormat::None,
+            compression_level: 6,
             custom_encoders: HashMap::new(),
             custom_decoders: HashMap::new(),
         }
@@ -126,6 +163,16 @@
         self.schema_registry_url = Some(url);
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
 
     pub fn format(&self) -> EncodingFormat {
         self.format
@@ -135,6 +182,14 @@
         self.pretty
     }
 
+    pub fn compression(&self) -> CompressionFormat {
+        self.compression
+    }
+
+    pub fn compression_level(&self) -> i32 {
+        self.compression_level
+    }
+
     pub fn add_custom_encoder<F>(&mut self, name: &str, encoder: F)
     where
         F: Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync + 'static,
@@ -155,6 +210,7 @@
     where
         T: Serialize,
     {
+        // First serialize to bytes according to format
         let bytes = match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
@@ -174,7 +230,37 @@
             }
         };
 
-        if bytes.len() > MAX_MESSAGE_SIZE {
+        // Then compress if enabled
+        let compressed = match self.compression {
+            CompressionFormat::None => bytes,
+            CompressionFormat::Gzip => {
+                let level = match self.compression_level {
+                    1..=9 => flate2::Compression::new(self.compression_level as u32),
+                    _ => flate2::Compression::default(),
+                };
+                let mut encoder = GzEncoder::new(Vec::new(), level);
+                encoder.write_all(&bytes).map_err(|e| ProtocolError::SerializationError(e.to_string()))?;
+                encoder.finish().map_err(|e| ProtocolError::SerializationError(e.to_string()))?
+            }
+            CompressionFormat::Zstd => {
+                #[cfg(feature = "zstd")]
+                {
+                    let level = self.compression_level.clamp(1, 22);
+                    zstd::encode_all(&bytes[..], level).map_err(|e| ProtocolError::SerializationError(e.to_string()))?
+                }
+                #[cfg(not(feature = "zstd"))]
+                {
+                    return Err(ProtocolError::SerializationError(
+                        "Zstd compression not available. Enable the 'zstd' feature.".to_string()
+                    ));
+                }
+            }
+        };
+
+        // Add compression format header (1 byte) + original data
+        let mut final_bytes = vec![self.compression as u8];
+        final_bytes.extend_from_slice(&compressed);
+
+        if final_bytes.len() > MAX_MESSAGE_SIZE {
             return Err(ProtocolError::MessageTooLarge {
                 size: bytes.len(),
                 max: MAX_MESSAGE_SIZE,
@@ -182,7 +268,7 @@
         }
 
         // TODO: Add metrics for serialization time and size
-        Ok(bytes)
+        Ok(final_bytes)
     }
 
     /// Deserialize a message from bytes.
@@ -191,6 +277,28 @@
     where
         T: for<'de> Deserialize<'de>,
     {
+        if data.is_empty() {
+            return Err(ProtocolError::SerializationError("Empty data".to_string()));
+        }
+
+        // First byte indicates compression format
+        let compression_format = CompressionFormat::from_u32(data[0] as u32)
+            .unwrap_or(CompressionFormat::None);
+        
+        let payload = &data[1..];
+        
+        // Decompress if needed
+        let decompressed = match compression_format {
+            CompressionFormat::None => payload.to_vec(),
+            CompressionFormat::Gzip => {
+                let mut decoder = GzDecoder::new(payload);
+                let mut result = Vec::new();
+                decoder.read_to_end(&mut result).map_err(|e| ProtocolError::SerializationError(e.to_string()))