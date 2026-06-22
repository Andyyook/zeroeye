 ```diff
--- a/backend/src/protocol/serialize.rs
+++ b/backend/src/protocol/serialize.rs
@@ -1,4 +1,4 @@
-// Serialization utilities for the Tent of Trials protocol.
+// Serialization utilities for the Tent of Trials protocol.
 //
 // This module provides serialization and deserialization functions for
 // the various protocol message formats. It supports multiple encoding
@@ -59,10 +59,11 @@
 // TODO: Add support for compressed serialization (zstd, gzip).
 // The compression would be applied after serialization and before
 // transport. The decompression would be transparent to the message
-// handlers. The compression level should be configurable per connection.
+// handlers. The compression level should be configurable per connection.
 
 use serde::{Deserialize, Serialize};
 use serde_json;
+use std::io::{Read, Write};
 use std::collections::HashMap;
 
 use super::{ProtocolError, MAX_MESSAGE_SIZE};
@@ -70,6 +71,40 @@
 // ---------------------------------------------------------------------------
 // ENCODING FORMAT
 // ---------------------------------------------------------------------------
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
+    pub level: u32,
+}
+
+impl Default for CompressionConfig {
+    fn default() -> Self {
+        Self {
+            format: CompressionFormat::None,
+            level: 3,
+        }
+    }
+}
 
 #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
 pub enum EncodingFormat {
@@ -123,6 +158,7 @@
 
 pub struct Serializer {
     format: EncodingFormat,
+    compression: CompressionConfig,
     pretty: bool,
     schema_registry_url: Option<String>,
     custom_encoders: HashMap<String, Box<dyn Fn(&serde_json::Value) -> Result<Vec<u8>, String> + Send + Sync>>,
@@ -133,6 +169,7 @@
     pub fn new(format: EncodingFormat) -> Self {
         Self {
             format,
+            compression: CompressionConfig::default(),
             pretty: false,
             schema_registry_url: None,
             custom_encoders: HashMap::new(),
@@ -140,6 +177,14 @@
         }
     }
 
+    pub fn with_compression(mut self, compression: CompressionConfig) -> Self {
+        self.compression = compression;
+        self
+    }
+
+    pub fn compression(&self) -> &CompressionConfig {
+        &self.compression
+    }
+
     pub fn with_pretty(mut self, pretty: bool) -> Self {
         self.pretty = pretty;
         self
@@ -175,7 +220,7 @@
     where
         T: Serialize,
     {
-        // Serialize to the target format first
+        // Serialize to the target format first
         let encoded = match self.format {
             EncodingFormat::Json => {
                 if self.pretty {
@@ -196,7 +241,7 @@
             EncodingFormat::Protobuf => {
                 return Err(ProtocolError::UnsupportedEncoding("Protobuf".to_string()));
             }
-            EncodingFormat::Custom => {
+            EncodingFormat::Custom => {
                 // For custom formats, we need to first serialize to JSON as an intermediate step
                 let json_value = serde_json::to_value(value)
                     .map_err(|e| ProtocolError::Serialization(e.to_string()))?;
@@ -209,7 +254,7 @@
                         .ok_or_else(|| ProtocolError::UnsupportedEncoding("Custom".to_string()))?;
                     encoder(&json_value).map_err(|e| ProtocolError::Serialization(e))?
                 }
-            }
+            }
         };
 
         if encoded.len() > MAX_MESSAGE_SIZE {
@@ -218,7 +263,33 @@
                 MAX_MESSAGE_SIZE,
             ));
         }
-        Ok(encoded)
+
+        // Apply compression if enabled
+        let compressed = match self.compression.format {
+            CompressionFormat::None => encoded,
+            CompressionFormat::Gzip => {
+                let level = self.compression.level.min(9) as u32;
+                let mut encoder = flate2::write::GzEncoder::new(
+                    Vec::new(),
+                    flate2::Compression::new(level),
+                );
+                encoder.write_all(&encoded).map_err(|e| ProtocolError::Serialization(e.to_string()))?;
+                encoder.finish().map_err(|e| ProtocolError::Serialization(e.to_string()))?
+            }
+            CompressionFormat::Zstd => {
+                let level = self.compression.level.min(22) as i32;
+                zstd::encode_all(&encoded[..], level)
+                    .map_err(|e| ProtocolError::Serialization(e.to_string()))?
+            }
+        };
+
+        if compressed.len() > MAX_MESSAGE_SIZE {
+            return Err(ProtocolError::MessageTooLarge(
+                compressed.len(),
+                MAX_MESSAGE_SIZE,
+            ));
+        }
+
+        Ok(compressed)
     }
 
     /// Deserialize bytes into a value.
@@ -228,7 +299,25 @@
     where
         T: for<'de> Deserialize<'de>,
     {
-        let value = match self.format {
+        // Decompress if needed
+        let decompressed = match self.compression.format {
+            CompressionFormat::None => bytes.to_vec(),
+            CompressionFormat::Gzip => {
+                let mut decoder = flate2::read::GzDecoder::new(bytes);
+                let mut decompressed = Vec::new();
+                decoder.read_to_end(&mut decompressed)
+                    .map_err(|e| ProtocolError::Deserialization(e.to_string()))?;
+                decompressed
+            }
+            CompressionFormat::Zstd => {
+                let mut decoder = zstd::stream::read::Decoder::new(bytes)
+                    .map_err(|e| ProtocolError::Deserialization(e.to_string()))?;
+                let mut decompressed = Vec::new();
+                decoder.read_to_end(&mut decompressed)
+                    .map_err(|e| ProtocolError::Deserialization(e.to_string()))?;
+                decompressed
+