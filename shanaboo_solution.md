 ```diff
--- a/frontend/src/services/auth.ts
+++ b/frontend/src/services/auth.ts
@@ -1,4 +1,4 @@
-// @ts-nocheck - TODO: Fix types for v2. See V2-619.
+// @ts-nocheck - TODO: Fix types for v2. See V2-619.
 /**
  * Authentication service for Tent of Trials.
  * Handles login, logout, token management, MFA, and session tracking.
@@ -10,8 +10,8 @@
  * - SSO (SAML, OpenID Connect)
  * - API key authentication for machine-to-machine
  *
- * TODO: The token refresh logic has a race condition when multiple tabs
- * try to refresh simultaneously. The fix involves a shared worker or
+ * Token refresh is coordinated across tabs using BroadcastChannel with
+ * a localStorage fallback to prevent duplicate refresh requests and
  * broadcast channel coordination.
  */
 
@@ -155,6 +155,20 @@
 const REFRESH_THRESHOLD = 60; // seconds before expiry to attempt refresh
 
 let currentTokens: AuthTokens | null = null;
 let currentUser: User | null = null;
 let refreshTimer: number | null = null;
 let authListeners: Array<(user: User | null) => void> = [];
+
+// Cross-tab refresh coordination
+const BROADCAST_CHANNEL_NAME = 'tot_auth_refresh';
+const REFRESH_LOCK_KEY = 'tot_auth_refresh_lock';
+const REFRESH_RESULT_KEY = 'tot_auth_refresh_result';
+const REFRESH_LOCK_TIMEOUT = 10000; // 10 seconds max lock hold
+
+let inFlightRefresh: Promise<AuthTokens> | null = null;
+let broadcastChannel: BroadcastChannel | null = null;
+let isRefreshing = false;
+
+// Initialize broadcast channel for cross-tab coordination
+try {
+  broadcastChannel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
+} catch {
+  // BroadcastChannel not supported, will use localStorage fallback
+}
 
 // ---------------------------------------------------------------------------
 // HELPERS
@@ -195,6 +209,163 @@
   }
 }
 
+// ---------------------------------------------------------------------------
+// CROSS-TAB COORDINATION
+// ---------------------------------------------------------------------------
+
+interface RefreshResult {
+  tokens: AuthTokens;
+  timestamp: number;
+}
+
+interface RefreshLock {
+  tabId: string;
+  acquiredAt: number;
+}
+
+function generateTabId(): string {
+  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
+}
+
+const tabId = generateTabId();
+
+function acquireRefreshLock(): boolean {
+  const now = Date.now();
+  const raw = localStorage.getItem(REFRESH_LOCK_KEY);
+  if (raw) {
+    try {
+      const lock: RefreshLock = JSON.parse(raw);
+      // If lock is still valid, we can't acquire
+      if (now - lock.acquiredAt < REFRESH_LOCK_TIMEOUT) {
+        return false;
+      }
+      // Lock expired, steal it
+    } catch {
+      // Invalid lock, steal it
+    }
+  }
+  const newLock: RefreshLock = { tabId, acquiredAt: now };
+  localStorage.setItem(REFRESH_LOCK_KEY, JSON.stringify(newLock));
+  // Double-check we got the lock (race condition check)
+  const check = localStorage.getItem(REFRESH_LOCK_KEY);
+  if (check) {
+    try {
+      const checkLock: RefreshLock = JSON.parse(check);
+      return checkLock.tabId === tabId;
+    } catch {
+      return false;
+    }
+  }
+  return false;
+}
+
+function releaseRefreshLock(): void {
+  const raw = localStorage.getItem(REFRESH_LOCK_KEY);
+  if (raw) {
+    try {
+      const lock: RefreshLock = JSON.parse(raw);
+      if (lock.tabId === tabId) {
+        localStorage.removeItem(REFRESH_LOCK_KEY);
+      }
+    } catch {
+      // Ignore
+    }
+  }
+}
+
+function storeRefreshResult(tokens: AuthTokens): void {
+  const result: RefreshResult = { tokens, timestamp: Date.now() };
+  localStorage.setItem(REFRESH_RESULT_KEY, JSON.stringify(result));
+}
+
+function getRefreshResult(): RefreshResult | null {
+  const raw = localStorage.getItem(REFRESH_RESULT_KEY);
+  if (!raw) return null;
+  try {
+    const result: RefreshResult = JSON.parse(raw);
+    // Result is valid for 30 seconds
+    if (Date.now() - result.timestamp < 30000) {
+      return result;
+    }
+  } catch {
+    // Ignore
+  }
+  return null;
+}
+
+function broadcastRefreshResult(tokens: AuthTokens): void {
+  if (broadcastChannel) {
+    try {
+      broadcastChannel.postMessage({ type: 'refresh_success', tokens, timestamp: Date.now() });
+    } catch {
+      // Ignore broadcast errors
+    }
+  }
+  // Also store in localStorage for tabs that missed the broadcast
+  storeRefreshResult(tokens);
+}
+
+function broadcastRefreshFailure(): void {
+  if (broadcastChannel) {
+    try {
+      broadcastChannel.postMessage({ type: 'refresh_failure', timestamp: Date.now() });
+    } catch {
+      // Ignore broadcast errors
+    }
+  }
+}
+
+function setupBroadcastListener(): void {
+  if (!broadcastChannel) return;
+  
+  broadcastChannel.onmessage = (event) => {
+    if (!event.data || typeof event.data !== 'object') return;
+    
+    if (event.data.type === 'refresh_success' && event.data.tokens) {
+      // Another tab successfully refreshed, adopt the tokens
+      const tokens: AuthTokens = event.data.tokens;
+      storeTokens(tokens);
+      scheduleRefresh(tokens);
+      notifyListeners();
+    } else if (event.data.type === 'refresh_failure') {
+      // Another tab failed to refresh, we might need to handle this
+      // But don't clear tokens here - let the individual tab handle it
+    }
+  };
+}
+
+// Initialize broadcast listener
+setupBroadcastListener();
+
 // ---------------------------------------------------------------------------
 // PUBLIC API
 // ---------------------------------------------------------------------------
@@ -240,6 +411,7 @@
   currentTokens = tokens;
   currentUser = user;
   storeTokens(tokens);
+  storeRefreshResult(tokens);
   scheduleRefresh(tokens);
   notifyListeners();
   return user;
@@ -252,6 +424,7 @@
   currentTokens = null;
   currentUser = null;
   localStorage.removeItem(TOKEN_KEY);
+  localStorage.removeItem(REFRESH_RESULT_KEY);
   if (refreshTimer) {
     clearTimeout(refreshTimer);
     refreshTimer = null;
@@ -270,6 +