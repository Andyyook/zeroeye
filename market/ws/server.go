package ws

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/tent-of-trials/market/matching"
	"github.com/tent-of-trials/market/types"
	"go.uber.org/zap"
)

// Default allowed origins for local development.
var defaultAllowedOrigins = []string{"http://localhost", "http://localhost:3000", "http://127.0.0.1", "http://127.0.0.1:3000"}

type Client struct {
	hub      *Hub
	conn     *websocket.Conn
	send     chan []byte
	subs     map[types.Symbol]struct{}
	remote   string
	mu       sync.Mutex
}

type Hub struct {
	clients    map[*Client]struct{}
	register   chan *Client
	unregister chan *Client
	broadcast  chan []byte
	logger     *zap.Logger
	mu         sync.RWMutex
}

type Server struct {
	hub    *Hub
	engine *matching.MatchingEngine
	logger *zap.Logger
	port   int
	srv    *http.Server
}

func NewHub(logger *zap.Logger) *Hub {
	return &Hub{
	logger     *zap.Logger
	port       int
	srv        *http.Server
	allowedOrigins []string
}

func NewHub(logger *zap.Logger) *Hub {
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = struct{}{}
			h.mu.Unlock()
			h.logger.Info("client connected",
				zap.String("remote", client.remote),
				zap.Int("total", len(h.clients)),
			)

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
			}
			h.mu.Unlock()
			h.logger.Info("client disconnected",
				zap.String("remote", client.remote),
				zap.Int("total", len(h.clients)),
			)

		case message := <-h.broadcast:
			h.mu.RLock()
}

func NewServer(hub *Hub, engine *matching.MatchingEngine, logger *zap.Logger, port int) *Server {
	// Read allowed origins from environment; falls back to safe local defaults.
	return &Server{
		hub:    hub,
		engine: engine,
		logger: logger,
		port:   port,
			h.mu.RUnlock()
}

func (s *Server) Start() error {
	// Determine allowed origins: env var overrides defaults.
	allowed := defaultAllowedOrigins
	if envOrigins := os.Getenv("MARKET_ALLOWED_ORIGINS"); envOrigins != "" {
		allowed = strings.Split(envOrigins, ",")
		for i := range allowed {
			allowed[i] = strings.TrimSpace(allowed[i])
		}
	}
	s.allowedOrigins = allowed

	upgrader := websocket.Upgrader{
		ReadBufferSize:  4096,
		WriteBufferSize: 4096,
		CheckOrigin: func(r *http.Request) bool {
			origin := r.Header.Get("Origin")
			if origin == "" {
				// No origin header: allow for non-browser clients.
				return true
			}
			for _, o := range s.allowedOrigins {
				if subtle.ConstantTimeCompare([]byte(origin), []byte(o)) == 1 {
					return true
				}
			}
			return false
		},
	}
	s.upgrader = upgrader

	mux := http.NewServeMux()
	mux.HandleFunc("/ws", s.handleWebSocket)
	mux.HandleFunc("/health", s.handleHealth)
		hub:    hub,
		engine: engine,
		logger: logger,
		port:   port,
	}
}

func (s *Server) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", s.handleWebSocket)
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/api/v1/trades", s.handleGetTrades)
	mux.HandleFunc("/api/v1/depth", s.handleGetDepth)

	s.srv = &http.Server{
		Addr:         fmt.Sprintf(":%d", s.port),
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	return s.srv.ListenAndServe()
}

func (s *Server) Stop() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := s.upgrader.Upgrade(w, r, nil)
	if err != nil {
		s.logger.Error("websocket upgrade failed", zap.Error(err))
		return
		s.logger.Error("websocket upgrade failed", zap.Error(err))
		return
	}

	client := &Client{
		hub:    s.hub,
		conn:   conn,
		send:   make(chan []byte, 256),
		subs:   make(map[types.Symbol]struct{}),
		remote: r.RemoteAddr,
	}

	s.hub.register <- client

	go client.writePump()
	go client.readPump()
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"service": "tent-market",
		"time":    time.Now().Unix(),
	})
}

func (s *Server) handleGetTrades(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	trades := s.engine.GetRecentTrades(100)
	json.NewEncoder(w).Encode(trades)
}

func (s *Server) handleGetDepth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"message": "depth endpoint"})
}

func (c *Client) readPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()

	c.conn.SetReadLimit(65536)
	c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			break
		}

		var event map[string]interface{}
		if err := json.Unmarshal(message, &event); err != nil {
			continue
		}

		c.mu.Lock()

		c.mu.Unlock()
	}
}

func (c *Client) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, message); err != nil {
				return
			}

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
