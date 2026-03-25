package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestCorrelationGeneratesID(t *testing.T) {
	r := gin.New()
	r.Use(Correlation())
	r.GET("/test", func(c *gin.Context) {
		reqID, exists := c.Get(CtxRequestID)
		if !exists {
			t.Error("expected request_id in context")
		}
		if reqID == "" {
			t.Error("expected non-empty request_id")
		}
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Header().Get(HeaderRequestID) == "" {
		t.Error("expected X-Request-ID in response headers")
	}
}

func TestCorrelationPreservesExistingID(t *testing.T) {
	r := gin.New()
	r.Use(Correlation())
	r.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set(HeaderRequestID, "existing-id-12345")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if got := w.Header().Get(HeaderRequestID); got != "existing-id-12345" {
		t.Errorf("expected preserved ID 'existing-id-12345', got %q", got)
	}
}

func TestCorrelationSetsContextValue(t *testing.T) {
	r := gin.New()
	r.Use(Correlation())

	var captured string
	r.GET("/test", func(c *gin.Context) {
		val, _ := c.Get(CtxRequestID)
		captured = val.(string)
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set(HeaderRequestID, "trace-abc")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if captured != "trace-abc" {
		t.Errorf("expected context value 'trace-abc', got %q", captured)
	}
}
