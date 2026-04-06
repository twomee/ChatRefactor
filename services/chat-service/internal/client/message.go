package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"go.uber.org/zap"
)

// MessageHistory is a single raw message returned by the message service.
type MessageHistory = map[string]interface{}

// MessageClient calls the Message Service for history retrieval.
type MessageClient struct {
	baseURL    string
	httpClient *http.Client
	logger     *zap.Logger
}

// NewMessageClient creates an HTTP client for the Message Service.
func NewMessageClient(baseURL string, logger *zap.Logger) *MessageClient {
	return &MessageClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 3 * time.Second,
		},
		logger: logger,
	}
}

// GetRoomHistory fetches recent messages for a room from the message service.
// Returns nil on any error (the caller falls back to empty history).
func (c *MessageClient) GetRoomHistory(ctx context.Context, roomID int, token string, limit int) []MessageHistory {
	url := fmt.Sprintf("%s/messages/rooms/%d/history?limit=%d", c.baseURL, roomID, limit)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		c.logger.Warn("history_request_build_failed", zap.Error(err))
		return nil
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.logger.Warn("history_fetch_failed", zap.Error(err))
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil
	}

	var messages []MessageHistory
	if err := json.NewDecoder(resp.Body).Decode(&messages); err != nil {
		return nil
	}
	return messages
}
