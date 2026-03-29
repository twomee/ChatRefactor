package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCheckOriginAllowedInDev(t *testing.T) {
	t.Setenv("APP_ENV", "dev")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "http://evil.com")

	if !checkOrigin(req) {
		t.Error("expected origin to be allowed in dev mode")
	}
}

func TestCheckOriginAllowedInTest(t *testing.T) {
	t.Setenv("APP_ENV", "test")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "http://evil.com")

	if !checkOrigin(req) {
		t.Error("expected origin to be allowed in test mode")
	}
}

func TestCheckOriginAllowedWhenNoEnv(t *testing.T) {
	t.Setenv("APP_ENV", "")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "http://anything.com")

	if !checkOrigin(req) {
		t.Error("expected origin to be allowed when APP_ENV is empty")
	}
}

func TestCheckOriginProdAllowedOrigin(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "https://app.example.com")

	if !checkOrigin(req) {
		t.Error("expected allowed origin to pass in prod mode")
	}
}

func TestCheckOriginProdRejectedOrigin(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("ALLOWED_ORIGINS", "https://app.example.com")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "https://evil.com")

	if checkOrigin(req) {
		t.Error("expected disallowed origin to be rejected in prod mode")
	}
}

func TestCheckOriginProdNoOriginHeader(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("ALLOWED_ORIGINS", "https://app.example.com")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	// No Origin header.

	if checkOrigin(req) {
		t.Error("expected missing origin to be rejected in prod mode")
	}
}

func TestCheckOriginProdNoAllowedOriginsConfig(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("ALLOWED_ORIGINS", "")

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	req.Header.Set("Origin", "http://any.com")

	if checkOrigin(req) {
		t.Error("expected fail-closed (deny all) when ALLOWED_ORIGINS is empty in prod")
	}
}

func TestMaxMessageSizeConstant(t *testing.T) {
	if maxMessageSize != 64*1024 {
		t.Errorf("expected maxMessageSize 64KB, got %d", maxMessageSize)
	}
}

func TestMaxContentLengthConstant(t *testing.T) {
	if maxContentLength != 4096 {
		t.Errorf("expected maxContentLength 4096, got %d", maxContentLength)
	}
}
