package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
	"github.com/twomee/chatbox/chat-service/internal/metrics"
)

// collectCounterValue reads the current value from a Prometheus Counter.
func collectCounterValue(c prometheus.Collector) float64 {
	ch := make(chan prometheus.Metric, 1)
	c.Collect(ch)
	m := <-ch
	var d dto.Metric
	_ = m.Write(&d)
	return d.GetCounter().GetValue()
}

// collectGaugeValue reads the current value from a Prometheus Gauge.
func collectGaugeValue(g prometheus.Gauge) float64 {
	ch := make(chan prometheus.Metric, 1)
	g.Collect(ch)
	m := <-ch
	var d dto.Metric
	_ = m.Write(&d)
	return d.GetGauge().GetValue()
}

// collectHistogramCount reads the observation count from a Prometheus Histogram.
func collectHistogramCount(c prometheus.Collector) uint64 {
	ch := make(chan prometheus.Metric, 1)
	c.Collect(ch)
	m := <-ch
	var d dto.Metric
	_ = m.Write(&d)
	return d.GetHistogram().GetSampleCount()
}

func setupMetricsRouter() *gin.Engine {
	r := gin.New()
	r.Use(PrometheusMetrics())
	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})
	r.POST("/api/data", func(c *gin.Context) {
		c.String(http.StatusCreated, "created")
	})
	r.GET("/health", func(c *gin.Context) {
		c.String(http.StatusOK, "healthy")
	})
	r.GET("/ready", func(c *gin.Context) {
		c.String(http.StatusOK, "ready")
	})
	r.GET("/metrics", func(c *gin.Context) {
		c.String(http.StatusOK, "metrics")
	})
	return r
}

func TestPrometheusMetricsRecordsRequestTotal(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "/test", "200")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before+1 {
		t.Errorf("expected HTTPRequestsTotal to increment by 1, got before=%f after=%f", before, after)
	}
}

func TestPrometheusMetricsRecordsDuration(t *testing.T) {
	r := setupMetricsRouter()

	observer := metrics.HTTPRequestDuration.WithLabelValues("GET", "/test")
	h := observer.(prometheus.Histogram)
	beforeCount := collectHistogramCount(h)

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	afterCount := collectHistogramCount(h)
	if afterCount != beforeCount+1 {
		t.Errorf("expected duration observation count to increment by 1, got before=%d after=%d", beforeCount, afterCount)
	}
}

func TestPrometheusMetricsInFlightReturnsToBaseline(t *testing.T) {
	r := setupMetricsRouter()

	before := collectGaugeValue(metrics.HTTPRequestsInFlight)

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// After the request completes, in-flight should return to baseline.
	after := collectGaugeValue(metrics.HTTPRequestsInFlight)
	if after != before {
		t.Errorf("expected HTTPRequestsInFlight to return to %f after request, got %f", before, after)
	}
}

func TestPrometheusMetricsRecordsCorrectStatus(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("POST", "/api/data", "201")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodPost, "/api/data", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before+1 {
		t.Errorf("expected counter for 201 to increment, got before=%f after=%f", before, after)
	}
}

func TestPrometheusMetricsSkipsHealth(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "/health", "200")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before {
		t.Errorf("expected /health to be skipped, but counter changed from %f to %f", before, after)
	}
}

func TestPrometheusMetricsSkipsReady(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "/ready", "200")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before {
		t.Errorf("expected /ready to be skipped, but counter changed from %f to %f", before, after)
	}
}

func TestPrometheusMetricsSkipsMetricsEndpoint(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "/metrics", "200")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before {
		t.Errorf("expected /metrics to be skipped, but counter changed from %f to %f", before, after)
	}
}

func TestPrometheusMetricsUnknownPathFallback(t *testing.T) {
	r := setupMetricsRouter()

	// A path that has no registered route will result in FullPath() == "".
	// The middleware should fall back to "unknown".
	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "unknown", "404")
	before := collectCounterValue(counter)

	req := httptest.NewRequest(http.MethodGet, "/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}

	after := collectCounterValue(counter)
	if after != before+1 {
		t.Errorf("expected unknown path counter to increment, got before=%f after=%f", before, after)
	}
}

func TestPrometheusMetricsMultipleRequestsAccumulate(t *testing.T) {
	r := setupMetricsRouter()

	counter := metrics.HTTPRequestsTotal.WithLabelValues("GET", "/test", "200")
	before := collectCounterValue(counter)

	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
	}

	after := collectCounterValue(counter)
	if after != before+5 {
		t.Errorf("expected counter to increment by 5, got before=%f after=%f", before, after)
	}
}
