package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"

	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- Lobby handler tests ----

func TestLobbyHandlerRejectsWithoutToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

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
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

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
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

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

	// The server registers the connection in a goroutine after the upgrade.
	// Poll briefly to avoid a race between the client dial completing and
	// the server-side ConnectLobby call updating the manager.
	var conns int
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		conns = manager.TotalConnections()
		if conns == 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if conns != 1 {
		t.Errorf("expected 1 connection, got %d", conns)
	}
}

// drainLobby reads and discards up to n messages from a lobby client connection.
// This is needed to skip the user_online broadcasts that fire on ConnectLobby.
func drainLobby(conn *websocket.Conn, n int) {
	conn.SetReadDeadline(time.Now().Add(500 * time.Millisecond))
	for i := 0; i < n; i++ {
		_, _, _ = conn.ReadMessage()
	}
	conn.SetReadDeadline(time.Time{})
}

// TestLobbyTypingPMForwarded verifies that a typing_pm message sent by alice
// is forwarded to bob's lobby connection as { type: "typing_pm", from: "alice" }.
func TestLobbyTypingPMForwarded(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	wsBase := "ws" + strings.TrimPrefix(srv.URL, "http")

	aliceConn, _, err := websocket.DefaultDialer.Dial(wsBase+"/ws/lobby?token="+makeToken(1, "alice"), nil)
	if err != nil {
		t.Fatalf("alice dial: %v", err)
	}
	defer aliceConn.Close()

	bobConn, _, err := websocket.DefaultDialer.Dial(wsBase+"/ws/lobby?token="+makeToken(2, "bob"), nil)
	if err != nil {
		t.Fatalf("bob dial: %v", err)
	}
	defer bobConn.Close()

	// Drain user_online broadcasts:
	// alice receives user_online(alice) on her own connect, then user_online(bob) when bob joins.
	// bob receives user_online(bob) on his own connect.
	drainLobby(aliceConn, 2)
	drainLobby(bobConn, 1)

	if err := aliceConn.WriteJSON(map[string]string{"type": "typing_pm", "to": "bob"}); err != nil {
		t.Fatalf("alice write: %v", err)
	}

	bobConn.SetReadDeadline(time.Now().Add(time.Second))
	var received map[string]string
	if err := bobConn.ReadJSON(&received); err != nil {
		t.Fatalf("bob read: %v", err)
	}
	if received["type"] != "typing_pm" {
		t.Errorf("expected type 'typing_pm', got %q", received["type"])
	}
	if received["from"] != "alice" {
		t.Errorf("expected from 'alice', got %q", received["from"])
	}
}

// TestLobbyTypingPMNotSentToSender verifies that alice does not receive
// the typing_pm she sends (the message goes only to the recipient).
func TestLobbyTypingPMNotSentToSender(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	wsBase := "ws" + strings.TrimPrefix(srv.URL, "http")

	aliceConn, _, err := websocket.DefaultDialer.Dial(wsBase+"/ws/lobby?token="+makeToken(1, "alice"), nil)
	if err != nil {
		t.Fatalf("alice dial: %v", err)
	}
	defer aliceConn.Close()

	bobConn, _, err := websocket.DefaultDialer.Dial(wsBase+"/ws/lobby?token="+makeToken(2, "bob"), nil)
	if err != nil {
		t.Fatalf("bob dial: %v", err)
	}
	defer bobConn.Close()

	drainLobby(aliceConn, 2)
	drainLobby(bobConn, 1)

	if err := aliceConn.WriteJSON(map[string]string{"type": "typing_pm", "to": "bob"}); err != nil {
		t.Fatalf("alice write: %v", err)
	}

	// Bob reads the typing_pm (confirms it was delivered)
	bobConn.SetReadDeadline(time.Now().Add(time.Second))
	var bobMsg map[string]string
	if err := bobConn.ReadJSON(&bobMsg); err != nil {
		t.Fatalf("bob read: %v", err)
	}

	// Alice should NOT receive any message — the typing event is one-way
	aliceConn.SetReadDeadline(time.Now().Add(200 * time.Millisecond))
	_, _, err = aliceConn.ReadMessage()
	if err == nil {
		t.Error("expected alice not to receive a message after sending typing_pm")
	}
}

// TestLobbyTypingPMDroppedForOfflineRecipient verifies that no error occurs
// and no message is sent back when the recipient is not connected to the lobby.
func TestLobbyTypingPMDroppedForOfflineRecipient(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger, nil, false)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	wsBase := "ws" + strings.TrimPrefix(srv.URL, "http")

	aliceConn, _, err := websocket.DefaultDialer.Dial(wsBase+"/ws/lobby?token="+makeToken(1, "alice"), nil)
	if err != nil {
		t.Fatalf("alice dial: %v", err)
	}
	defer aliceConn.Close()

	drainLobby(aliceConn, 1)

	// bob is not connected — typing_pm should silently drop
	if err := aliceConn.WriteJSON(map[string]string{"type": "typing_pm", "to": "bob"}); err != nil {
		t.Fatalf("alice write: %v", err)
	}

	aliceConn.SetReadDeadline(time.Now().Add(200 * time.Millisecond))
	_, raw, err := aliceConn.ReadMessage()
	if err == nil {
		// If any message was received, it must not be a typing_pm echo
		var msg map[string]string
		if jsonErr := json.Unmarshal(raw, &msg); jsonErr == nil {
			if msg["type"] == "typing_pm" {
				t.Error("unexpected typing_pm echo to sender when recipient is offline")
			}
		}
	}
}

