package handler

import (
	"context"
	"encoding/json"
	"fmt"
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
// in ws_helpers.go) so it does not block readLoop from starting.
func (h *WSHandler) handleJoin(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, token string, silent bool) {
	// Check if this is a reconnect (pending leave exists).
	isReconnect := h.cancelPendingLeave(roomID, userID)

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
	h.markLeft(roomID, userID)

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
	h.storePendingLeave(roomID, userID, cancel)

	go func() {
		select {
		case <-leaveCtx.Done():
			return // cancelled — user reconnected or flushed on logout
		case <-time.After(reconnectGrace):
		}

		h.clearPendingLeave(roomID, userID)

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
	h.cancelPendingLeave(roomID, userID)

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
	roomIDs := h.drainPendingLeaves(userID)

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
