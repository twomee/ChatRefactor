package handler

import (
	"github.com/gin-gonic/gin"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// ---- Health handler tests ----

func TestHealthEndpoint(t *testing.T) {
	h := NewHealthHandler(nil, nil, nil, nil)
	r := gin.New()
	r.GET("/health", h.Health)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "ok" {
		t.Errorf("expected 'ok', got %v", body["status"])
	}
}

func TestReadyEndpointNoInfra(t *testing.T) {
	h := NewHealthHandler(nil, nil, nil, nil)
	r := gin.New()
	r.GET("/ready", h.Ready)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

