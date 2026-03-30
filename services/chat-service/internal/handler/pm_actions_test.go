package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- PM Actions handler tests ----

func TestEditPMSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	h := NewPMActionsHandler(manager, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PATCH("/pm/edit/:msg_id", h.EditPM)

	// msg_id format: pm-{senderID}-{recipientID}-{timestamp}
	body := `{"text": "edited text"}`
	req := httptest.NewRequest(http.MethodPatch, "/pm/edit/pm-1-2-1234567890", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestEditPMUnauthorized(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	h := NewPMActionsHandler(manager, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PATCH("/pm/edit/:msg_id", h.EditPM)

	// User 3 trying to edit a message from user 1
	body := `{"text": "edited text"}`
	req := httptest.NewRequest(http.MethodPatch, "/pm/edit/pm-1-2-1234567890", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(3, "charlie"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d: %s", w.Code, w.Body.String())
	}
}

func TestEditPMMissingText(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	h := NewPMActionsHandler(manager, &mockDelivery{}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PATCH("/pm/edit/:msg_id", h.EditPM)

	body := `{}`
	req := httptest.NewRequest(http.MethodPatch, "/pm/edit/pm-1-2-1234567890", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", w.Code, w.Body.String())
	}
}

func TestEditPMInvalidMsgID(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	h := NewPMActionsHandler(manager, &mockDelivery{}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PATCH("/pm/edit/:msg_id", h.EditPM)

	body := `{"text": "hello"}`
	req := httptest.NewRequest(http.MethodPatch, "/pm/edit/bad-id", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", w.Code, w.Body.String())
	}
}

func TestDeletePMSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	h := NewPMActionsHandler(manager, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/pm/delete/:msg_id", h.DeletePM)

	req := httptest.NewRequest(http.MethodDelete, "/pm/delete/pm-1-2-1234567890", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestDeletePMUnauthorized(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	h := NewPMActionsHandler(manager, &mockDelivery{}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/pm/delete/:msg_id", h.DeletePM)

	req := httptest.NewRequest(http.MethodDelete, "/pm/delete/pm-1-2-1234567890", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(3, "charlie"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d: %s", w.Code, w.Body.String())
	}
}

func TestAddPMReactionSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	h := NewPMActionsHandler(manager, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/reaction/:msg_id", h.AddPMReaction)

	body := `{"emoji": "👍"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/reaction/pm-1-2-1234567890", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestAddPMReactionMissingEmoji(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	h := NewPMActionsHandler(manager, &mockDelivery{}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/reaction/:msg_id", h.AddPMReaction)

	body := `{}`
	req := httptest.NewRequest(http.MethodPost, "/pm/reaction/pm-1-2-1234567890", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", w.Code, w.Body.String())
	}
}

func TestRemovePMReactionSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	h := NewPMActionsHandler(manager, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/pm/reaction/:msg_id/:emoji", h.RemovePMReaction)

	req := httptest.NewRequest(http.MethodDelete, "/pm/reaction/pm-1-2-1234567890/%F0%9F%91%8D", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestRemovePMReactionInvalidMsgID(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	h := NewPMActionsHandler(manager, &mockDelivery{}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/pm/reaction/:msg_id/:emoji", h.RemovePMReaction)

	req := httptest.NewRequest(http.MethodDelete, "/pm/reaction/bad-id/emoji", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", w.Code, w.Body.String())
	}
}

func TestParsePMMsgID(t *testing.T) {
	tests := []struct {
		name        string
		msgID       string
		wantSender  int
		wantRecip   int
		expectError bool
	}{
		{"valid", "pm-1-2-1234567890", 1, 2, false},
		{"valid large ids", "pm-100-200-9999999999", 100, 200, false},
		{"missing prefix", "msg-1-2-123", 0, 0, true},
		{"too few parts", "pm-1-2", 0, 0, true},
		{"non-numeric sender", "pm-abc-2-123", 0, 0, true},
		{"non-numeric recipient", "pm-1-abc-123", 0, 0, true},
		{"empty string", "", 0, 0, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sender, recip, err := parsePMMsgID(tt.msgID)
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error for %q", tt.msgID)
				}
				return
			}
			if err != nil {
				t.Errorf("unexpected error: %v", err)
				return
			}
			if sender != tt.wantSender {
				t.Errorf("sender: got %d, want %d", sender, tt.wantSender)
			}
			if recip != tt.wantRecip {
				t.Errorf("recipient: got %d, want %d", recip, tt.wantRecip)
			}
		})
	}
}
