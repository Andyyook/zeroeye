 ```diff
--- a/frontend/src/services/auth.ts
+++ b/frontend/src/services/auth.ts
@@ -1,4 +1,3 @@
-// @ts-nocheck - TODO: Fix types for v2. See V2-619.
 /**
  * Authentication service for Tent of Trials.
  * Handles login, logout, token management, MFA, and session tracking.
@@ -9,9 +8,9 @@
  * - SSO (SAML, OpenID Connect)
  * - API key authentication for machine-to-machine
  *
- * TODO: The token refresh logic has a race condition when multiple tabs
- * try to refresh simultaneously. The fix involves a shared worker or
- * broadcast channel coordination.
+ * Token refresh is coordinated across tabs using BroadcastChannel with
+ * a localStorage fallback. Concurrent refresh calls in the same tab
+ * share one in-flight request.
  */
 
 import { get, post, del } from './api';
@@ -145,6 +144,12 @@ let currentTokens: AuthTokens | null = null;
 let currentUser: User | null = null;
 let refreshTimer: number | null = null;
 let authListeners: Array<(user: User | null) => void> = [];
+let inFlightRefresh: Promise<AuthTokens> | null = null;
+
+// Cross-tab coordination
+const BROADCAST_CHANNEL_NAME = 'tot_auth_refresh';
+let broadcastChannel: BroadcastChannel | null = null;
+let isBroadcastChannelSupported = typeof BroadcastChannel !== 'undefined';
 
 // ---------------------------------------------------------------------------
 // HELPERS
@@ -180,6 +185,7 @@
 function storeTokens(tokens: AuthTokens): void {
   currentTokens = tokens;
   try {
+    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
   } catch {
     // Ignore storage errors (e.g., private mode)
   }
@@ -188,6 +194,7 @@
 function loadTokens(): AuthTokens | null {
   if (currentTokens) return currentTokens;
   try {
+    const stored = localStorage.getItem(TOKEN_KEY);
     if (stored) {
       return JSON.parse(stored);
     }
@@ -199,6 +206,7 @@
 function clearStoredTokens(): void {
   currentTokens = null;
   try {
+    localStorage.removeItem(TOKEN_KEY);
   } catch {
     // Ignore
   }
@@ -207,6 +215,7 @@
 function storeUser(user: User): void {
   currentUser = user;
   try {
+    localStorage.setItem(USER_KEY, JSON.stringify(user));
   } catch {
     // Ignore
   }
@@ -215,6 +224,7 @@
 function loadUser(): User | null {
   if (currentUser) return currentUser;
   try {
+    const stored = localStorage.getItem(USER_KEY);
     if (stored) {
       return JSON.parse(stored);
     }
@@ -226,6 +236,7 @@
 function clearStoredUser(): void {
   currentUser = null;
   try {
+    localStorage.removeItem(USER_KEY);
   } catch {
     // Ignore
   }
@@ -243,6 +254,155 @@
   }
 }
 
+// ---------------------------------------------------------------------------
+// CROSS-TAB COORDINATION
+// ---------------------------------------------------------------------------
+
+interface RefreshMessage {
+  type: 'refresh-started' | 'refresh-completed' | 'refresh-failed';
+  timestamp: number;
+  tokens?: AuthTokens;
+}
+
+function getBroadcastChannel(): BroadcastChannel | null {
+  if (!isBroadcastChannelSupported) return null;
+  if (!broadcastChannel) {
+    try {
+      broadcastChannel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
+    } catch {
+      isBroadcastChannelSupported = false;
+      return null;
+    }
+  }
+  return broadcastChannel;
+}
+
+function sendRefreshMessage(message: RefreshMessage): void {
+  const channel = getBroadcastChannel();
+  if (channel) {
+    try {
+      channel.postMessage(message);
+      return;
+    } catch {
+      // Fall through to localStorage
+    }
+  }
+
+  // localStorage fallback
+  try {
+    const key = `${BROADCAST_CHANNEL_NAME}_msg`;
+    localStorage.setItem(key, JSON.stringify({ ...message, _ls: true }));
+    // Clean up after a short delay to avoid stale messages
+    setTimeout(() => {
+      try {
+        localStorage.removeItem(key);
+      } catch {
+        // Ignore
+      }
+    }, 100);
+  } catch {
+    // Ignore
+  }
+}
+
+function listenForRefreshMessages(
+  onStarted: () => void,
+  onCompleted: (tokens: AuthTokens) => void,
+  onFailed: () => void
+): () => void {
+  const channel = getBroadcastChannel();
+  const handlers: Array<() => void> = [];
+
+  const handleMessage = (event: MessageEvent) => {
+    const msg = event.data as RefreshMessage;
+    if (!msg || typeof msg !== 'object') return;
+
+    switch (msg.type) {
+      case 'refresh-started":
+        onStarted();
+        break;
+      case 'refresh-completed':
+        if (msg.tokens) {
+          onCompleted(msg.tokens);
+        }
+        break;
+      case 'refresh-failed':
+        onFailed();
+        break;
+    }
+  };
+
+  if (channel) {
+    channel.addEventListener('message', handleMessage);
+    handlers.push(() => channel.removeEventListener('message', handleMessage));
+  }
+
+  // localStorage fallback for cross-tab communication
+  const storageHandler = (event: StorageEvent) => {
+    if (event.key !== `${BROADCAST_CHANNEL_NAME}_msg` || !event.newValue) return;
+    try {
+      const msg = JSON.parse(event.newValue) as RefreshMessage;
+      if (!msg._ls) return;
+      switch (msg.type) {
+        case 'refresh-started':
+          onStarted();
+          break;
+        case 'refresh-completed':
+          if (msg.tokens) {
+            onCompleted(msg.tokens);
+          }
+          break;
+        case 'refresh-failed':
+          onFailed();
+          break;
+      }
+    } catch {
+      // Ignore parse errors
+    }
+  };
+
+  window.addEventListener('storage', storageHandler);
+  handlers.push(() => window.removeEventListener('storage', storageHandler));
+
+  return () => {
+    handlers.forEach((fn) => fn());
+  };
+}
+
 // ---------------------------------------------------------------------------
 // PUBLIC API
 // ---------------------------------------------------------------------------
@@ -251,6 +411,7 @@
   const tokens = loadTokens();
   if (tokens) {
     currentTokens = tokens;
+    scheduleRefresh(tokens);
   }
   const user = loadUser();
   if (user)