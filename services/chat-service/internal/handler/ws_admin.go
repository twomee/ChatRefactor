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

// handleKick processes an admin kick command.
func (h *WSHandler) handleKick(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot kick yourself.
	if target == username {
		h.sendError(conn, "Cannot kick yourself")
		return
	}

	// Find target user in room.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot kick another admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "Cannot kick an admin")
		return
	}

	// Send kicked message to target before closing their connections.
	kickedMsg := map[string]interface{}{
		"type":    "kicked",
		"room_id": roomID,
	}
	h.manager.SendToUserInRoom(roomID, targetID, kickedMsg)

	// Mark user as kicked so handleDisconnect skips the duplicate "user_left" broadcast.
	h.markKicked(roomID, targetID)

	// Small delay so the kicked message is delivered before close.
	time.Sleep(50 * time.Millisecond)

	// Close target's connections.
	h.manager.CloseUserConnsInRoom(roomID, targetID)

	// Broadcast system message about the kick.
	msgID := uuid.New().String()
	now := time.Now().UTC().Format(time.RFC3339)
	systemMsg := map[string]interface{}{
		"type":      "message",
		"from":      "system",
		"text":      fmt.Sprintf("%s was kicked by %s", target, username),
		"room_id":   roomID,
		"msg_id":    msgID,
		"timestamp": now,
	}
	h.manager.BroadcastRoom(roomID, systemMsg)

	// Persist system message to Kafka.
	kafkaMsg := map[string]interface{}{
		"type":      "message",
		"room_id":   roomID,
		"sender_id": 0,
		"username":  "system",
		"text":      fmt.Sprintf("%s was kicked by %s", target, username),
		"msg_id":    msgID,
		"timestamp": now,
	}
	payload, _ := json.Marshal(kafkaMsg)
	_ = h.delivery.DeliverChat(ctx, roomID, payload)

	// Broadcast updated user list.
	updatedUsers := h.manager.GetUsernamesInRoom(roomID)
	adminNames := h.getAdminUsernames(ctx, roomID)
	mutedNames := h.getMutedUsernames(ctx, roomID)
	updateMsg := map[string]interface{}{
		"type":     "user_left",
		"username": target,
		"users":    updatedUsers,
		"admins":   adminNames,
		"muted":    mutedNames,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, updateMsg)

	// Produce kicked event to Kafka.
	h.produceEvent(ctx, "user_kicked", roomID, targetID, target)
}

// handleMute processes an admin mute command.
func (h *WSHandler) handleMute(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot mute yourself.
	if target == username {
		h.sendError(conn, "Cannot mute yourself")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot mute another admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "Cannot mute an admin")
		return
	}

	// Check not already muted.
	alreadyMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if alreadyMuted {
		h.sendError(conn, "User is already muted")
		return
	}

	// Mute in database.
	_, err := h.store.MuteUser(ctx, roomID, targetID)
	if err != nil {
		h.logger.Error("mute_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to mute user")
		return
	}

	// Broadcast muted event.
	mutedMsg := map[string]interface{}{
		"type":     "muted",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, mutedMsg)

	// Produce muted event to Kafka.
	h.produceEvent(ctx, "user_muted", roomID, targetID, target)
}

// handleUnmute processes an admin unmute command.
func (h *WSHandler) handleUnmute(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Check currently muted.
	isMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if !isMuted {
		h.sendError(conn, "User is not muted")
		return
	}

	// Unmute in database.
	if err := h.store.UnmuteUser(ctx, roomID, targetID); err != nil {
		h.logger.Error("unmute_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to unmute user")
		return
	}

	// Broadcast unmuted event.
	unmutedMsg := map[string]interface{}{
		"type":     "unmuted",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, unmutedMsg)

	// Produce unmuted event to Kafka.
	h.produceEvent(ctx, "user_unmuted", roomID, targetID, target)
}

// handlePromote processes an admin promote command.
func (h *WSHandler) handlePromote(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot promote yourself.
	if target == username {
		h.sendError(conn, "Cannot promote yourself")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot promote already-admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "User is already an admin")
		return
	}

	// Cannot promote muted user.
	isMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if isMuted {
		h.sendError(conn, "Cannot promote a muted user")
		return
	}

	// Add admin in database.
	_, err := h.store.AddAdmin(ctx, roomID, targetID)
	if err != nil {
		h.logger.Error("promote_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to promote user")
		return
	}

	// Broadcast new_admin event.
	promoteMsg := map[string]interface{}{
		"type":     "new_admin",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, promoteMsg)

	// Produce promoted event to Kafka.
	h.produceEvent(ctx, "user_promoted", roomID, targetID, target)
}
