package handler

import (
	"github.com/gin-gonic/gin"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"github.com/gorilla/websocket"

	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- Lobby handler tests ----

func TestLobbyHandlerRejectsWithoutToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/lobby", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLobbyHandlerRejectsInvalidToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/lobby?token=bad", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLobbyWSUpgrade(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/lobby?token=" + token

	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()

	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Errorf("expected 101, got %d", resp.StatusCode)
	}

	if manager.TotalConnections() != 1 {
		t.Errorf("expected 1 connection, got %d", manager.TotalConnections())
	}
}

