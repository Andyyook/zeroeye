 ```diff
--- a/market/ws/server.go
+++ b/market/ws/server.go
@@ -4,6 +4,7 @@ import (
 	"context"
 	"encoding/json"
 	"fmt"
+	"net"
 	"net/http"
 	"sync"
 	"time"
@@ -15,11 +16,66 @@ import (
 )
 
 var upgrader = websocket.Upgrader{
-	ReadBufferSize:  4096,
-	WriteBufferSize: 4096,
-	CheckOrigin:     func(r *http.Request) bool { return true },
+	ReadBufferSize:  4096,
+	WriteBufferSize: 4096,
+	CheckOrigin:   checkOrigin,
 }
 
+// allowedOrigins holds the explicitly configured origins that are permitted
+// to open WebSocket connections.  It is populated once at start-up from the
+// MARKET_WS_ALLOWED_ORIGINS environment variable (comma-separated list).  An
+// empty list means "allow local development origins only".
+var allowedOrigins []string
+
+// init reads the MARKET_WS_ALLOWED_ORIGINS environment variable once.
+func init() {
+	allowedOrigins = parseAllowedOrigins()
+}
+
+// parseAllowedOrigins splits a comma-separated list of origins and trims
+// whitespace.  If the environment variable is empty, it returns the local
+// development defaults.
+func parseAllowedOrigins() []string {
+	raw := os.Getenv("MARKET_WS_ALLOWED_ORIGINS")
+	if raw == "" {
+		return []string{"http://localhost", "https://localhost", "http://localhost:3000"}
+	}
+	parts := strings.Split(raw, ",")
+	out := make([]string, 0, len(parts))
+	for _, p := range parts {
+		p = strings.TrimSpace(p)
+		if p != "" {
+			out = append(out, p)
+		}
+	}
+	return out
+}
+
+// checkOrigin validates the Origin header of an incoming WebSocket upgrade
+// request.  It allows requests with no Origin header (non-browser clients) and
+// allows any origin when the local development defaults are in use and the
+// request comes from a loopback address.
+func checkOrigin(r *http.Request) bool {
+	origin := r.Header.Get("Origin")
+	if origin == "" {
+		// Non-browser client or same-origin request.
+		return true
+	}
+
+	for _, allowed := range allowedOrigins {
+		if origin == allowed {
+			return true
+		}
+	}
+
+	// Local development fallback: if the defaults are still in place and the
+	// request comes from a loopback address, permit the connection.
+	if len(allowedOrigins) == 3 && allowedOrigins[0] == "http://localhost" {
+		host, _, _ := net.SplitHostPort(r.RemoteAddr)
+		if host == "127.0.0.1" || host == "::1" {
+			return true
+		}
+	}
+
+	return false
+}
+
 type Client struct {
 	hub      *Hub
 	conn     *websocket.Conn
@@ -30,6 +86,8 @@ type Client struct {
 }
 
 type Hub struct {
+	//lint:ignore U1000 unused field kept for future use
+	_          struct{}
 	clients    map[*Client]struct{}
 	register   chan *Client
 	unregister chan *Client
@@ -39,6 +97,8 @@ type Hub struct {
 }
 
 type Server struct {
+	//lint:ignore U1000 unused field kept for future use
+	_      struct{}
 	hub    *Hub
 	engine *matching.MatchingEngine
 	logger *zap.Logger
@@ -46,6 +106,8 @@ type Server struct {
 	srv    *http.Server
 }
 
+// NewHub creates a new Hub.
 func NewHub(logger *zap.Logger) *Hub {
 	return &Hub{
 		clients:    make(map[*Client]struct{}),
@@ -56,6 +118,7 @@ func NewHub(logger *zap.Logger) *Hub {
 	}
 }
 
+// Run starts the hub event loop.
 func (h *Hub) Run() {
 	for {
 		select {
@@ -88,6 +151,7 @@ func (h *Hub) Run() {
 	}
 }
 
+// NewServer creates a new Server.
 func NewServer(hub *Hub, engine *matching.MatchingEngine, logger *zap.Logger, port int) *Server {
 	return &Server{
 		hub:    hub,
@@ -97,6 +161,7 @@ func NewServer(hub *Hub, engine *matching.MatchingEngine, logger *zap.Logger, po
 	}
 }
 
+// Start starts the HTTP server.
 func (s *Server) Start() error {
 	mux := http.NewServeMux()
 	mux.HandleFunc("/ws", s.handleWebSocket)
@@ -114,12 +179,14 @@ func (s *Server) Start() error {
 	return s.srv.ListenAndServe()
 }
 
+// Stop gracefully shuts down the HTTP server.
 func (s *Server) Stop() {
 	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
 	defer cancel()
 	s.srv.Shutdown(ctx)
 }
 
+// handleWebSocket upgrades the HTTP connection to a WebSocket.
 func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
 	conn, err := upgrader.Upgrade(w, r, nil)
 	if err != nil {
@@ -141,6 +208,7 @@ func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
 	go client.readPump()
 }
 
+// handleHealth returns the health status.
 func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
 	w.Header().Set("Content-Type", "application/json")
 	json.NewEncoder(w).Encode(map[string]interface{}{
@@ -150,12 +218,14 @@ func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
 	})
 }
 
+// handleGetTrades returns recent trades.
 func (s *Server) handleGetTrades(w http.ResponseWriter, r *http.Request) {
 	w.Header().Set("Content-Type", "application/json")
 	trades := s.engine.GetRecentTrades(100)
 	json.NewEncoder(w).Encode(trades)
 }
 
+// handleGetDepth returns the depth endpoint message.
 func (s *Server) handleGetDepth(w http.ResponseWriter, r *http.Request) {
 	w.Header().Set("Content-Type", "application/json")
 	json.NewEncoder(w).Encode(map[string]string{"message": "depth endpoint"})
@@ -169,6 +239,7 @@ func (c *Client) readPump() {
 
 	c.conn.Set