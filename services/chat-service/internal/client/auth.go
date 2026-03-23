// Package client provides HTTP clients for calling downstream microservices.
package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"go.uber.org/zap"
)

// UserResponse is the expected shape from the Auth Service user lookup.
type UserResponse struct {
	ID            int    `json:"id"`
	Username      string `json:"username"`
	IsGlobalAdmin bool   `json:"is_global_admin"`
}

// AuthClient calls the Auth Service for user lookups.
type AuthClient struct {
	baseURL    string
	httpClient *http.Client
	logger     *zap.Logger
}

// NewAuthClient creates an HTTP client for the Auth Service with a
// sensible timeout so a slow downstream doesn't block WebSocket handlers.
func NewAuthClient(baseURL string, logger *zap.Logger) *AuthClient {
	return &AuthClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 5 * time.Second,
		},
		logger: logger,
	}
}

// GetUserByUsername looks up a user by username via the Auth Service.
func (c *AuthClient) GetUserByUsername(ctx context.Context, username string) (*UserResponse, error) {
	endpoint := fmt.Sprintf("%s/auth/users/%s", c.baseURL, url.PathEscape(username))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("auth client request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.logger.Warn("auth_service_unreachable", zap.Error(err))
		return nil, fmt.Errorf("auth service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // user not found
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("auth service returned status %d", resp.StatusCode)
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

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.logger.Warn("auth_service_unreachable", zap.Error(err))
		return nil, fmt.Errorf("auth service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("auth service returned status %d", resp.StatusCode)
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
