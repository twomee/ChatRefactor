package handler

import (
	"github.com/gin-gonic/gin"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- PM handler tests ----

func TestSendPMSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	authClient := &mockAuthClient{
		user: &client.UserResponse{ID: 2, Username: "bob"},
	}
	del := &mockDelivery{}
	pmH := NewPMHandler(manager, authClient, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "bob", "text": "hello bob"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestSendPMBadBody(t *testing.T) {
	logger := newLogger()
	pmH := NewPMHandler(ws.NewManager(logger), nil, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader("bad"))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSendPMRecipientNotFound(t *testing.T) {
	logger := newLogger()
	authClient := &mockAuthClient{user: nil, err: nil}
	pmH := NewPMHandler(ws.NewManager(logger), authClient, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "unknown", "text": "hello"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestSendPMAuthServiceError(t *testing.T) {
	logger := newLogger()
	authClient := &mockAuthClient{err: fmt.Errorf("auth service down")}
	pmH := NewPMHandler(ws.NewManager(logger), authClient, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "bob", "text": "hello"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", w.Code)
	}
}

