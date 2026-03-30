// src/utils/storage.js — Centralized localStorage helpers for joined-rooms persistence

export function getJoinedRooms(username) {
  const key = `chatbox_joined_rooms_${username ?? 'anonymous'}`;
  try {
    return JSON.parse(localStorage.getItem(key) || '[]');
  } catch {
    localStorage.removeItem(key);
    return [];
  }
}

export function addJoinedRoom(username, roomId) {
  const key = `chatbox_joined_rooms_${username ?? 'anonymous'}`;
  const saved = getJoinedRooms(username);
  if (!saved.includes(roomId)) {
    localStorage.setItem(key, JSON.stringify([...saved, roomId]));
  }
}

export function removeJoinedRoom(username, roomId) {
  const key = `chatbox_joined_rooms_${username ?? 'anonymous'}`;
  const saved = getJoinedRooms(username);
  localStorage.setItem(key, JSON.stringify(saved.filter(id => id !== roomId)));
}

// ── PM thread list helpers ────────────────────────────────────────────────
// Stores only usernames (not message content) to restore the DM sidebar.

function pmThreadKey(username) {
  return `chatbox_pm_threads_${username ?? 'anonymous'}`;
}

export function getPMThreadList(username) {
  try {
    return JSON.parse(localStorage.getItem(pmThreadKey(username)) || '[]');
  } catch {
    return [];
  }
}

export function savePMThreadList(username, usernames) {
  try {
    localStorage.setItem(pmThreadKey(username), JSON.stringify(usernames));
  } catch { /* storage full — ignore */ }
}

export function addPMThread(currentUsername, partnerUsername) {
  const existing = getPMThreadList(currentUsername);
  if (!existing.includes(partnerUsername)) {
    savePMThreadList(currentUsername, [...existing, partnerUsername]);
  }
}
