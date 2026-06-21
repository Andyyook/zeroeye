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
+ * a localStorage fallback to prevent race conditions when multiple tabs
  * broadcast channel coordination.
  */
 
@@ -163,6 +163,20 @@ let currentTokens: AuthTokens | null = null;
 let currentUser: User | null = null;
 let refreshTimer: number | null = null;
 let authListeners: Array<(user: User | null) => void> = [];
+let inFlightRefresh: Promise<AuthTokens> | null = null;
+
+// Cross-tab coordination
+const BROADCAST_CHANNEL_NAME = 'tot_auth_refresh';
+const STORAGE_EVENT_KEY = 'tot_auth_refresh_event';
+let broadcastChannel: BroadcastChannel | null = null;
+let isRefreshing: boolean = false;
+
+// Initialize broadcast channel for cross-tab coordination
+try {
+  broadcastChannel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
+} catch {
+  // BroadcastChannel not supported, will fall back to localStorage events
+  broadcastChannel = null;
+}
 
 // ---------------------------------------------------------------------------
 // HELPERS
@@ -210,6 +224,16 @@ function storeTokens(tokens: AuthTokens): void {
   }
 }
 
+function storeTokensForBroadcast(tokens: AuthTokens): void {
+  storeTokens(tokens);
+  // Also store in localStorage for cross-tab synchronization
+  try {
+    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
+  } catch {
+    // Ignore storage errors
+  }
+}
+
 function loadTokens(): AuthTokens | null {
   if (currentTokens) return currentTokens;
   try {
@@ -244,6 +268,16 @@ function clearStoredAuth(): void {
   }
 }
 
+function broadcastRefreshResult(tokens: AuthTokens | null, error: boolean = false): void {
+  const message = { type: 'auth_refresh", tokens, error, timestamp: Date.now() };
+  if (broadcastChannel) {
+    broadcastChannel.postMessage(message);
+  }
+  // Also use localStorage as fallback for cross-tab communication
+  try {
+    localStorage.setItem(STORAGE_EVENT_KEY, JSON.stringify(message));
+    // Clean up after a short delay to avoid stale events
+    setTimeout(() => {
+      try {
+        localStorage.removeItem(STORAGE_EVENT_KEY);
+      } catch {
+        // Ignore
+      }
+    }, 5000);
+  } catch {
+    // Ignore storage errors
+  }
+}
+
 // ---------------------------------------------------------------------------
 // TOKEN REFRESH
 // ---------------------------------------------------------------------------
@@ -252,6 +286,7 @@ function clearStoredAuth(): void {
  * Refresh the access token using the refresh token.
  * This is called automatically before the token expires.
  */
+<<<<<<< SEARCH
 export async function refreshTokens(): Promise<AuthTokens> {
   const tokens = loadTokens();
   if (!tokens?.refreshToken) {
@@ -274,6 +309,163 @@ export async function refreshTokens(): Promise<AuthTokens> {
     throw error;
   }
 }
+=======
+export async function refreshTokens(): Promise<AuthTokens> {
+  // If there's already an in-flight refresh, share its result
+  if (inFlightRefresh) {
+    return inFlightRefresh;
+  }
+
+  // Create the in-flight promise so concurrent callers share it
+  inFlightRefresh = performRefresh();
+
+  try {
+    const result = await inFlightRefresh;
+    return result;
+  } finally {
+    inFlightRefresh = null;
+  }
+}
+
+async function performRefresh(): Promise<AuthTokens> {
+  const tokens = loadTokens();
+  if (!tokens?.refreshToken) {
+    throw new Error('No refresh token available');
+  }
+
+  // Check if another tab is already refreshing
+  if (isRefreshing) {
+    // Wait for the other tab's result via broadcast or storage event
+    return waitForRefreshResult();
+  }
+
+  isRefreshing = true;
+
+  try {
+    const response = await post<AuthTokens>('/auth/refresh', {
+      refreshToken: tokens.refreshToken,
+    });
+
+    const newTokens: AuthTokens = {
+      ...response,
+      expiresIn: response.expiresIn || 3600,
+    };
+
+    storeTokensForBroadcast(newTokens);
+    scheduleRefresh(newTokens);
+    broadcastRefreshResult(newTokens, false);
+
+    return newTokens;
+  } catch (error) {
+    // On refresh failure, don't clear tokens immediately - another tab
+    // might have a successful in-flight refresh
+    broadcastRefreshResult(null, true);
+    throw error;
+  } finally {
+    isRefreshing = false;
+  }
+}
+
+function waitForRefreshResult(): Promise<AuthTokens> {
+  return new Promise((resolve, reject) => {
+    const timeout = setTimeout(() => {
+      cleanup();
+      reject(new Error('Timeout waiting for cross-tab refresh'));
+    }, 30000); // 30 second timeout
+
+    function onBroadcast(event: MessageEvent) {
+      if (event.data?.type === 'auth_refresh') {
+        if (event.data.error) {
+          // Another tab failed, but we might still have valid tokens
+          const tokens = loadTokens();
+          if (tokens && !isTokenExpired(tokens.accessToken)) {
+            cleanup();
+            resolve(tokens);
+          }
+          // Otherwise keep waiting or let timeout handle it
+        } else if (event.data.tokens) {
+          cleanup();
+          storeTokens(event.data.tokens);
+          scheduleRefresh(event.data.tokens);
+          resolve(event.data.tokens);
+        }
+      }
+    }
+
+    function onStorage(event: StorageEvent) {
+      if (event.key === TOKEN_KEY && event.newValue) {
+        try {
+          const tokens = JSON.parse(event.newValue) as AuthTokens;
+          cleanup();
+          storeTokens(tokens);
+          scheduleRefresh(tokens);
+          resolve(tokens);
+        } catch {
+          // Ignore parse errors
+        }
+      } else if (event.key === STORAGE_EVENT_KEY && event.newValue) {
+