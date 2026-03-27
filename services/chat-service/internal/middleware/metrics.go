package middleware

import (
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/twomee/chatbox/chat-service/internal/metrics"
)

// PrometheusMetrics returns a Gin middleware that records HTTP request metrics.
func PrometheusMetrics() gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.FullPath()
		if path == "" {
			path = "unknown"
		}

		// Skip metrics/health endpoints to avoid noise
		if path == "/metrics" || path == "/health" || path == "/ready" {
			c.Next()
			return
		}

		metrics.HTTPRequestsInFlight.Inc()
		start := time.Now()

		c.Next()

		metrics.HTTPRequestsInFlight.Dec()
		duration := time.Since(start).Seconds()
		status := strconv.Itoa(c.Writer.Status())

		metrics.HTTPRequestsTotal.WithLabelValues(c.Request.Method, path, status).Inc()
		metrics.HTTPRequestDuration.WithLabelValues(c.Request.Method, path).Observe(duration)
	}
}
