package middleware

import (
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

const (
	// HeaderRequestID is the header key for request correlation.
	HeaderRequestID = "X-Request-ID"
	// CtxRequestID is the Gin context key for the correlation ID.
	CtxRequestID = "request_id"
)

// Correlation ensures every request has an X-Request-ID. If the incoming
// request carries one it is reused; otherwise a new UUID is generated. The
// ID is also set in the response header for easy tracing.
func Correlation() gin.HandlerFunc {
	return func(c *gin.Context) {
		reqID := c.GetHeader(HeaderRequestID)
		if reqID == "" {
			reqID = uuid.New().String()
		}
		c.Set(CtxRequestID, reqID)
		c.Header(HeaderRequestID, reqID)
		c.Next()
	}
}
