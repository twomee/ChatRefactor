package handler

import (
	"sync"
	"time"
)

const (
	// rateLimitWindow is the sliding window for rate limiting.
	rateLimitWindow = 10 * time.Second

	// rateLimitMax is the maximum messages per window per user.
	rateLimitMax = 30
)

// rateLimiter provides a per-user sliding window rate limiter.
type rateLimiter struct {
	mu      sync.Mutex
	windows map[string][]time.Time
}

func newRateLimiter() *rateLimiter {
	return &rateLimiter{
		windows: make(map[string][]time.Time),
	}
}

// allow checks whether a user (identified by key) is within the rate limit.
// Returns true if the message is allowed.
func (rl *rateLimiter) allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	cutoff := now.Add(-rateLimitWindow)

	// Prune expired timestamps.
	timestamps := rl.windows[key]
	start := 0
	for start < len(timestamps) && timestamps[start].Before(cutoff) {
		start++
	}
	timestamps = timestamps[start:]

	if len(timestamps) >= rateLimitMax {
		rl.windows[key] = timestamps
		return false
	}

	rl.windows[key] = append(timestamps, now)
	return true
}
