package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// reconnectGrace is the time to wait before broadcasting a user_left event.
// If the user reconnects within this window (e.g. page refresh), the leave
// is cancelled silently — no leave/join messages, no state changes.
const reconnectGrace = 10 * time.Second

// handleJoin broadcasts the user_join event and updates room state for the
// newly connected client. Message history is sent separately (see sendHistory
// in websocket.go) so it does not block readLoop from starting.
func (h *WSHandler) handleJoin(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, token string, silent bool) {
	// Check if this is a reconnect (pending leave exists).
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	h.pendingLeaveMu.Lock()
	cancel, isReconnect := h.pendingLeaves[leaveKey]
	if isReconnect {
		cancel() // cancel the pending leave — user came back
		delete(h.pendingLeaves, leaveKey)
	}
	h.pendingLeaveMu.Unlock()

	// Fetch room state.
	usernames := h.manager.GetUsernamesInRoom(roomID)
	adminNames := h.getAdminUsernames(ctx, roomID)
	mutedNames := h.getMutedUsernames(ctx, roomID)

	isSilent := isReconnect || silent
	roomState := map[string]interface{}{
		"type":     "user_join",
		"username": username,
		"users":    usernames,
		"admins":   adminNames,
		"muted":    mutedNames,
		"room_id":  roomID,
		"silent":   isSilent,
	}

	// Always broadcast the updated room state to ALL clients so every
	// user's online list stays in sync.
	h.manager.BroadcastRoom(roomID, roomState)

	// System message ("X joined the room") only for active joins — not for
	// reconnects (page refresh) or silent joins (auto-rejoin on login).
	if !isReconnect && !silent {
		joinMsgID := uuid.New().String()
		joinNow := time.Now().UTC().Format(time.RFC3339)
		joinKafka := map[string]interface{}{
			"type":      "message",
			"room_id":   roomID,
			"sender_id": 0,
			"username":  "system",
			"text":      fmt.Sprintf("%s joined the room", username),
			"msg_id":    joinMsgID,
			"timestamp": joinNow,
		}
		joinPayload, _ := json.Marshal(joinKafka)
		_ = h.delivery.DeliverChat(ctx, roomID, joinPayload)

		h.produceEvent(ctx, "user_joined", roomID, userID, username)
	}
}

// handleLeave processes an intentional room exit (user clicked "Leave Room").
// Disconnects immediately without the reconnect grace period.
// Marks the user as "left" so handleDisconnect (which runs after readLoop
// exits) skips the duplicate leave broadcast.
func (h *WSHandler) handleLeave(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string) {
	// Mark as intentionally left BEFORE disconnect so handleDisconnect skips.
	key := fmt.Sprintf("%d:%d", roomID, userID)
	h.leftMu.Lock()
	h.leftUsers[key] = true
	h.leftMu.Unlock()

	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	if h.manager.IsUserInRoom(roomID, userID) {
		return // multi-tab: user still connected via another tab
	}

	// Active leave: broadcast (non-silent), admin succession, system message.
	h.broadcastLeave(ctx, roomID, userID, username, false)

	leaveMsgID := uuid.New().String()
	leaveNow := time.Now().UTC().Format(time.RFC3339)
	leaveKafka := map[string]interface{}{
		"type":      "message",
		"room_id":   roomID,
		"sender_id": 0,
		"username":  "system",
		"text":      fmt.Sprintf("%s left the room", username),
		"msg_id":    leaveMsgID,
		"timestamp": leaveNow,
	}
	leavePayload, _ := json.Marshal(leaveKafka)
	_ = h.delivery.DeliverChat(ctx, roomID, leavePayload)
}

// wasLeft checks and clears the intentional-leave flag for a room/user pair.
func (h *WSHandler) wasLeft(roomID, userID int) bool {
	key := fmt.Sprintf("%d:%d", roomID, userID)
	h.leftMu.Lock()
	defer h.leftMu.Unlock()
	if h.leftUsers[key] {
		delete(h.leftUsers, key)
		return true
	}
	return false
}

// handleDisconnect cleans up the connection and schedules a delayed leave
// broadcast. If the user reconnects within the grace period (e.g. page
// refresh), the leave is cancelled silently.
// For kicked users, the leave is immediate (no grace period).
func (h *WSHandler) handleDisconnect(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string) {
	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	if h.wasKicked(roomID, userID) || h.wasLeft(roomID, userID) {
		return // already handled by handleKick or handleLeave
	}
	if h.manager.IsUserInRoom(roomID, userID) {
		return // multi-tab: user still connected via another tab
	}

	// No lobby → fully logged out. Leave immediately (no grace period).
	if !h.manager.HasLobbyConnection(userID) {
		h.broadcastLeave(ctx, roomID, userID, username, true)
		return
	}

	// Schedule a delayed leave. If the user reconnects within the grace
	// period (e.g. page refresh), handleJoin cancels this silently.
	h.scheduleGracePeriodLeave(roomID, userID, username)
}

// scheduleGracePeriodLeave waits reconnectGrace before broadcasting a silent
// user_left. If the user reconnects or logs out within the window, the pending
// leave is cancelled by handleJoin or flushPendingLeaves respectively.
func (h *WSHandler) scheduleGracePeriodLeave(roomID, userID int, username string) {
	leaveCtx, cancel := context.WithCancel(context.Background())
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)

	h.pendingLeaveMu.Lock()
	h.pendingLeaves[leaveKey] = cancel
	h.pendingLeaveMu.Unlock()

	go func() {
		select {
		case <-leaveCtx.Done():
			return // cancelled — user reconnected or flushed on logout
		case <-time.After(reconnectGrace):
		}

		h.pendingLeaveMu.Lock()
		delete(h.pendingLeaves, leaveKey)
		h.pendingLeaveMu.Unlock()

		if h.manager.IsUserInRoom(roomID, userID) {
			return
		}

		h.broadcastLeave(context.Background(), roomID, userID, username, true)
	}()
}

// broadcastLeave broadcasts user_left, produces the Kafka event, and handles
// admin succession. When silent=true (passive disconnect), the frontend skips
// the "X left the room" chat message. When silent=false (active leave), the
// frontend shows the message.
func (h *WSHandler) broadcastLeave(ctx context.Context, roomID, userID int, username string, silent bool) {
	// Cancel any existing pending leave for this user/room.
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	h.pendingLeaveMu.Lock()
	if cancel, ok := h.pendingLeaves[leaveKey]; ok {
		cancel()
		delete(h.pendingLeaves, leaveKey)
	}
	h.pendingLeaveMu.Unlock()

	remainingUsers := h.manager.GetUsernamesInRoom(roomID)
	updatedAdmins := h.getAdminUsernames(ctx, roomID)
	updatedMuted := h.getMutedUsernames(ctx, roomID)

	leaveBroadcast := map[string]interface{}{
		"type":     "user_left",
		"username": username,
		"users":    remainingUsers,
		"admins":   updatedAdmins,
		"muted":    updatedMuted,
		"room_id":  roomID,
		"silent":   silent,
	}
	h.manager.BroadcastRoom(roomID, leaveBroadcast)

	h.produceEvent(ctx, "user_left", roomID, userID, username)

	// Admin succession only on active leave — not on logout/disconnect.
	if !silent {
		h.handleAdminSuccession(ctx, roomID, userID, username)
	}
}

// flushPendingLeaves cancels all pending grace-period leave timers for a user
// and broadcasts immediate user_left for each room. Called when a user fully
// logs out (last lobby closes) to avoid the 10s delay when the room socket
// happened to close before the lobby socket.
func (h *WSHandler) flushPendingLeaves(userID int, username string) {
	h.pendingLeaveMu.Lock()
	var roomIDs []int
	for key, cancel := range h.pendingLeaves {
		var rid, uid int
		fmt.Sscanf(key, "%d:%d", &rid, &uid)
		if uid == userID {
			cancel()
			delete(h.pendingLeaves, key)
			roomIDs = append(roomIDs, rid)
		}
	}
	h.pendingLeaveMu.Unlock()

	ctx := context.Background()
	for _, rid := range roomIDs {
		h.broadcastLeave(ctx, rid, userID, username, true)
	}
}

// handleAdminSuccession handles admin departure and succession logic.
// When an admin leaves: remove their admin status, clear all mutes (amnesty),
// and promote the next user in join order.
func (h *WSHandler) handleAdminSuccession(ctx context.Context, roomID, userID int, username string) {
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		return
	}

	// Remove departing admin.
	_ = h.store.RemoveAdmin(ctx, roomID, userID)

	// Amnesty: clear all mutes in the room.
	mutedUsers, _ := h.store.GetMutedUsers(ctx, roomID)
	for _, mu := range mutedUsers {
		_ = h.store.UnmuteUser(ctx, roomID, mu.UserID)
	}

	// Find next user in join order to promote.
	nextUserID, nextUsername, found := h.manager.GetNextUserInRoom(roomID, userID)
	if !found {
		return // room is empty
	}

	// Promote next user.
	_, err := h.store.AddAdmin(ctx, roomID, nextUserID)
	if err != nil {
		h.logger.Error("admin_succession_failed", zap.Error(err))
		return
	}

	// Broadcast new admin.
	promoteMsg := map[string]interface{}{
		"type":     "new_admin",
		"username": nextUsername,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, promoteMsg)

	// Broadcast system message about succession (WS uses "from" for frontend).
	successionNow := time.Now().UTC().Format(time.RFC3339)
	successionMsgID := uuid.New().String()
	systemMsg := map[string]interface{}{
		"type":      "message",
		"from":      "system",
		"text":      fmt.Sprintf("%s left. %s is now admin", username, nextUsername),
		"room_id":   roomID,
		"msg_id":    successionMsgID,
		"timestamp": successionNow,
	}
	h.manager.BroadcastRoom(roomID, systemMsg)

	// Persist system message to Kafka (uses "username" to match consumer).
	successionKafka := map[string]interface{}{
		"type":      "message",
		"room_id":   roomID,
		"sender_id": 0,
		"username":  "system",
		"text":      fmt.Sprintf("%s left. %s is now admin", username, nextUsername),
		"msg_id":    successionMsgID,
		"timestamp": successionNow,
	}
	succPayload, _ := json.Marshal(successionKafka)
	_ = h.delivery.DeliverChat(ctx, roomID, succPayload)
}

// sendReadPosition sends the user's last-read message position for the room.
// Called after sendHistory so the frontend can render the "New messages" divider.
func (h *WSHandler) sendReadPosition(ctx context.Context, conn *websocket.Conn, roomID, userID int) {
	if h.readPositionStore == nil {
		return
	}

	rp, err := h.readPositionStore.Get(ctx, userID, roomID)
	if err != nil {
		// No read position yet (first visit) — nothing to send.
		return
	}

	readPosMsg := map[string]interface{}{
		"type":                 "read_position",
		"room_id":              roomID,
		"last_read_message_id": rp.LastReadMessageID,
	}
	_ = h.manager.SendToConn(conn, readPosMsg)
}

// sendHistory fetches recent messages from the Message Service and sends them
// to the newly connected client.
func (h *WSHandler) sendHistory(conn *websocket.Conn, roomID int, token string) {
	url := fmt.Sprintf("%s/messages/rooms/%d/history?limit=50", h.messageSvcURL, roomID)

	client := &http.Client{Timeout: 3 * time.Second}
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		h.logger.Warn("history_request_build_failed", zap.Error(err))
		return
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := client.Do(req)
	if err != nil {
		h.logger.Warn("history_fetch_failed", zap.Error(err))
		h.sendEmptyHistory(conn, roomID)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		h.sendEmptyHistory(conn, roomID)
		return
	}

	var rawMessages []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&rawMessages); err != nil {
		rawMessages = []map[string]interface{}{}
	}

	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": transformHistoryMessages(rawMessages),
		"room_id":  roomID,
	}
	_ = h.manager.SendToConn(conn, historyMsg)
}

// sendEmptyHistory sends an empty history payload to the client.
// Used when the message service is unavailable or returns a non-OK status.
func (h *WSHandler) sendEmptyHistory(conn *websocket.Conn, roomID int) {
	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": []interface{}{},
		"room_id":  roomID,
	}
	_ = h.manager.SendToConn(conn, historyMsg)
}

// transformHistoryMessages converts raw message-service records (sender_id,
// content) into the frontend wire format (from, text) expected by MessageList.
func transformHistoryMessages(rawMessages []map[string]interface{}) []map[string]interface{} {
	transformed := make([]map[string]interface{}, 0, len(rawMessages))
	for _, m := range rawMessages {
		msg := map[string]interface{}{
			"type": "message",
			"from": m["sender_name"],
			"text": m["content"],
		}
		if ts, ok := m["sent_at"]; ok {
			msg["timestamp"] = ts
		}
		if mid, ok := m["message_id"]; ok {
			msg["msg_id"] = mid
		}
		if editedAt, ok := m["edited_at"]; ok && editedAt != nil {
			msg["edited_at"] = editedAt
		}
		if isDeleted, ok := m["is_deleted"]; ok {
			msg["is_deleted"] = isDeleted
		}
		if reactions, ok := m["reactions"]; ok {
			msg["reactions"] = reactions
		}
		transformed = append(transformed, msg)
	}
	return transformed
}

// getAdminUsernames returns a list of admin usernames for a room by cross-referencing
// the admin records with currently connected users.
func (h *WSHandler) getAdminUsernames(ctx context.Context, roomID int) []string {
	admins, err := h.store.GetAdmins(ctx, roomID)
	if err != nil {
		return []string{}
	}

	// Build a map of userID -> username from connected users.
	usernames := h.manager.GetUsernamesInRoom(roomID)
	userIDToName := make(map[int]string)
	for _, name := range usernames {
		uid, found := h.manager.FindUserIDByUsername(roomID, name)
		if found {
			userIDToName[uid] = name
		}
	}

	names := make([]string, 0)
	for _, a := range admins {
		if name, ok := userIDToName[a.UserID]; ok {
			names = append(names, name)
		}
	}
	return names
}

// produceEvent fires an event to the chat.events Kafka topic (fire-and-forget).
func (h *WSHandler) produceEvent(ctx context.Context, eventType string, roomID, userID int, username string) {
	event := map[string]interface{}{
		"event_type": eventType,
		"room_id":    roomID,
		"user_id":    userID,
		"username":   username,
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}
	payload, _ := json.Marshal(event)
	if err := h.delivery.DeliverEvent(ctx, eventType, payload); err != nil {
		h.logger.Debug("event_deliver_failed", zap.String("event", eventType), zap.Error(err))
	}
}

// getMutedUsernames returns a list of muted usernames for a room.
func (h *WSHandler) getMutedUsernames(ctx context.Context, roomID int) []string {
	mutedUsers, err := h.store.GetMutedUsers(ctx, roomID)
	if err != nil {
		return []string{}
	}

	usernames := h.manager.GetUsernamesInRoom(roomID)
	userIDToName := make(map[int]string)
	for _, name := range usernames {
		uid, found := h.manager.FindUserIDByUsername(roomID, name)
		if found {
			userIDToName[uid] = name
		}
	}

	names := make([]string, 0)
	for _, m := range mutedUsers {
		if name, ok := userIDToName[m.UserID]; ok {
			names = append(names, name)
		}
	}
	return names
}
