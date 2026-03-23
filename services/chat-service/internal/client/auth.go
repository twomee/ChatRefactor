// Package client provides HTTP clients for calling downstream microservices.
package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"github.com/sony/gobreaker/v2"
	"go.uber.org/zap"
)

// UserResponse is the expected shape from the Auth Service user lookup.
type UserResponse struct {
	ID            int    `json:"id"`
	Username      string `json:"username"`
	IsGlobalAdmin bool   `json:"is_global_admin"`
}

// AuthClient calls the Auth Service for user lookups.
// Wraps HTTP calls in a circuit breaker to prevent cascading failures
// when the auth service is down.
type AuthClient struct {
	baseURL    string
	httpClient *http.Client
	logger     *zap.Logger
	breaker    *gobreaker.CircuitBreaker[*http.Response]
}

// NewAuthClient creates an HTTP client for the Auth Service with a
// sensible timeout and circuit breaker so a slow/down downstream
// doesn't block WebSocket handlers.
func NewAuthClient(baseURL string, logger *zap.Logger) *AuthClient {
	cb := gobreaker.NewCircuitBreaker[*http.Response](gobreaker.Settings{
		Name:        "auth_service",
		MaxRequests: 3,                // allow 3 probing requests in half-open state
		Interval:    30 * time.Second, // reset failure counts every 30s
		Timeout:     10 * time.Second, // stay open for 10s before probing
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures > 5
		},
		OnStateChange: func(name string, from, to gobreaker.State) {
			logger.Warn("circuit_breaker_state_change",
				zap.String("service", name),
				zap.String("from", from.String()),
				zap.String("to", to.String()),
			)
		},
	})

	return &AuthClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 5 * time.Second,
		},
		logger:  logger,
		breaker: cb,
	}
}

// doRequest executes an HTTP request through the circuit breaker.
func (c *AuthClient) doRequest(req *http.Request) (*http.Response, error) {
	return c.breaker.Execute(func() (*http.Response, error) {
		resp, err := c.httpClient.Do(req)
		if err != nil {
			return nil, err
		}
		// Treat 5xx as failures for the circuit breaker.
		if resp.StatusCode >= 500 {
			resp.Body.Close()
			return nil, fmt.Errorf("auth service returned %d", resp.StatusCode)
		}
		return resp, nil
	})
}

// GetUserByUsername looks up a user by username via the Auth Service.
func (c *AuthClient) GetUserByUsername(ctx context.Context, username string) (*UserResponse, error) {
	endpoint := fmt.Sprintf("%s/auth/users/by-username/%s", c.baseURL, url.PathEscape(username))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("auth client request: %w", err)
	}

	resp, err := c.doRequest(req)
	if err != nil {
		c.logger.Warn("auth_service_unreachable", zap.Error(err))
		return nil, fmt.Errorf("auth service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // user not found
	}

	var user UserResponse
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return nil, fmt.Errorf("auth service decode: %w", err)
	}
	return &user, nil
}

// GetUserByID looks up a user by ID via the Auth Service.
func (c *AuthClient) GetUserByID(ctx context.Context, userID int) (*UserResponse, error) {
	endpoint := fmt.Sprintf("%s/auth/users/%d", c.baseURL, userID)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("auth client request: %w", err)
	}

	resp, err := c.doRequest(req)
	if err != nil {
		c.logger.Warn("auth_service_unreachable", zap.Error(err))
		return nil, fmt.Errorf("auth service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}

	var user UserResponse
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return nil, fmt.Errorf("auth service decode: %w", err)
	}
	return &user, nil
}

// Ping verifies the Auth Service is reachable via its health endpoint.
func (c *AuthClient) Ping(ctx context.Context) error {
	endpoint := fmt.Sprintf("%s/health", c.baseURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("auth service health: status %d", resp.StatusCode)
	}
	return nil
}
