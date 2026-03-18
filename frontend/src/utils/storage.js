// src/utils/storage.js — Centralized localStorage helpers for joined-rooms persistence

export function getJoinedRooms(username) {
  const key = `chatbox_joined_rooms_${username ?? 'anonymous'}`;
  return JSON.parse(localStorage.getItem(key) || '[]');
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
