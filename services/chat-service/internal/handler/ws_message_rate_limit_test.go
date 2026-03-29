package handler

import (
	"testing"
	"time"
)

// TestWSMessageRateLimitExceeded verifies that when a user sends more messages
// than the rate limit allows within the window, an error is returned.
func TestWSMessageRateLimitExceeded(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, 1, "alice")
	defer c.Close()

	// rateLimitMax = 30 messages per 10s window.
	// Send exactly rateLimitMax + 1 messages to trigger the rate limit.
	var lastErrMsg map[string]interface{}
	hitLimit := false

	for i := 0; i <= rateLimitMax; i++ {
		c.SetWriteDeadline(time.Now().Add(time.Second))
		c.WriteJSON(map[string]string{"type": "message", "text": "hello"})

		c.SetReadDeadline(time.Now().Add(2 * time.Second))
		var m map[string]interface{}
		if err := c.ReadJSON(&m); err != nil {
			break
		}
		if m["type"] == "error" {
			lastErrMsg = m
			hitLimit = true
			break
		}
	}

	if !hitLimit || lastErrMsg == nil {
		t.Error("expected rate limit to be hit within rateLimitMax+1 messages")
		return
	}

	detail, _ := lastErrMsg["detail"].(string)
	if detail != "Rate limit exceeded" {
		t.Errorf("expected 'Rate limit exceeded', got %q", detail)
	}
}
