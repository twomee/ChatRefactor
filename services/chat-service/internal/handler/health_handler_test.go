package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
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

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	status := body["status"].(map[string]interface{})
	if status["database"] != "not configured" {
		t.Errorf("expected database 'not configured', got %v", status["database"])
	}
	if status["redis"] != "not configured" {
		t.Errorf("expected redis 'not configured', got %v", status["redis"])
	}
	if status["kafka"] != "not configured" {
		t.Errorf("expected kafka 'not configured', got %v", status["kafka"])
	}
}

func TestReadyEndpointRedisUnhealthy(t *testing.T) {
	// Create a Redis client pointing at an unreachable address.
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:1", // port 1 is not a Redis server
	})
	defer rdb.Close()

	h := NewHealthHandler(nil, rdb, nil, nil)
	r := gin.New()
	r.GET("/ready", h.Ready)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", w.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	status := body["status"].(map[string]interface{})
	if status["redis"] != "unhealthy" {
		t.Errorf("expected redis 'unhealthy', got %v", status["redis"])
	}
	// Database and Kafka should be "not configured" since they are nil.
	if status["database"] != "not configured" {
		t.Errorf("expected database 'not configured', got %v", status["database"])
	}
	if status["kafka"] != "not configured" {
		t.Errorf("expected kafka 'not configured', got %v", status["kafka"])
	}
}

func TestReadyEndpointPartialDegradation(t *testing.T) {
	// Only Redis configured (and unhealthy), others nil.
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:1",
	})
	defer rdb.Close()

	h := NewHealthHandler(nil, rdb, nil, nil)
	r := gin.New()
	r.GET("/ready", h.Ready)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Even one unhealthy component should make the overall status 503.
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 for partial degradation, got %d", w.Code)
	}
}

