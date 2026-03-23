package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.uber.org/zap"
)

func TestGetUserByUsernameSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/auth/users/alice" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(UserResponse{ID: 42, Username: "alice"})
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	user, err := c.GetUserByUsername(context.Background(), "alice")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user == nil {
		t.Fatal("expected non-nil user")
	}
	if user.ID != 42 {
		t.Errorf("expected user ID 42, got %d", user.ID)
	}
	if user.Username != "alice" {
		t.Errorf("expected username 'alice', got %q", user.Username)
	}
}

func TestGetUserByUsernameNotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	user, err := c.GetUserByUsername(context.Background(), "unknown")
	if err != nil {
		t.Fatalf("expected nil error for 404, got: %v", err)
	}
	if user != nil {
		t.Errorf("expected nil user for 404, got %+v", user)
	}
}

func TestGetUserByUsernameServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	_, err := c.GetUserByUsername(context.Background(), "alice")
	if err == nil {
		t.Error("expected error for 500 response")
	}
}

func TestGetUserByUsernameUnreachable(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	// Use a URL that cannot connect.
	c := NewAuthClient("http://127.0.0.1:1", logger)

	_, err := c.GetUserByUsername(context.Background(), "alice")
	if err == nil {
		t.Error("expected error for unreachable server")
	}
}

func TestGetUserByUsernameInvalidJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte("not json"))
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	_, err := c.GetUserByUsername(context.Background(), "alice")
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestGetUserByUsernameEscapesPath(t *testing.T) {
	var receivedRawPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedRawPath = r.URL.RawPath
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(UserResponse{ID: 1, Username: "user/slash"})
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	user, err := c.GetUserByUsername(context.Background(), "user/slash")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user == nil {
		t.Fatal("expected non-nil user")
	}
	// Verify the raw path contains the escaped slash.
	if receivedRawPath != "/auth/users/user%2Fslash" {
		t.Errorf("expected escaped raw path, got %q", receivedRawPath)
	}
}

func TestPingSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	err := c.Ping(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestPingUnhealthy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	logger, _ := zap.NewDevelopment()
	c := NewAuthClient(srv.URL, logger)

	err := c.Ping(context.Background())
	if err == nil {
		t.Error("expected error for unhealthy auth service")
	}
}

func TestPingUnreachable(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	c := NewAuthClient("http://127.0.0.1:1", logger)

	err := c.Ping(context.Background())
	if err == nil {
		t.Error("expected error for unreachable server")
	}
}

func TestNewAuthClientSetsTimeout(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	c := NewAuthClient("http://example.com", logger)

	if c.httpClient.Timeout == 0 {
		t.Error("expected non-zero timeout on HTTP client")
	}
	if c.baseURL != "http://example.com" {
		t.Errorf("expected baseURL 'http://example.com', got %q", c.baseURL)
	}
}
