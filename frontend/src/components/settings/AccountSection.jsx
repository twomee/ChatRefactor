// src/components/settings/AccountSection.jsx
import { useState } from 'react';

/**
 * AccountSection -- Account management actions for the Settings page.
 * Contains controls for clearing room and PM history.
 * Actual API integration will be wired when the message service endpoints are ready.
 */
export default function AccountSection() {
  // ── Room history state ──────────────────────────────────────────────
  const [selectedRoom, setSelectedRoom] = useState('');
  const [roomConfirm, setRoomConfirm] = useState(false);
  const [roomSuccess, setRoomSuccess] = useState('');
  const [roomError, setRoomError] = useState('');

  // ── PM history state ────────────────────────────────────────────────
  const [selectedPM, setSelectedPM] = useState('');
  const [pmConfirm, setPmConfirm] = useState(false);
  const [pmSuccess, setPmSuccess] = useState('');
  const [pmError, setPmError] = useState('');

  // ── Room history handler (placeholder) ──────────────────────────────
  function handleClearRoomHistory() {
    if (!roomConfirm) {
      setRoomConfirm(true);
      return;
    }
    // Placeholder — will call clearHistory API when available
    setRoomSuccess('Room history cleared (placeholder).');
    setRoomError('');
    setRoomConfirm(false);
    setSelectedRoom('');
  }

  function handleCancelRoomClear() {
    setRoomConfirm(false);
  }

  // ── PM history handler (placeholder) ────────────────────────────────
  function handleClearPMHistory() {
    if (!pmConfirm) {
      setPmConfirm(true);
      return;
    }
    // Placeholder — will call clearHistory API when available
    setPmSuccess('PM history cleared (placeholder).');
    setPmError('');
    setPmConfirm(false);
    setSelectedPM('');
  }

  function handleCancelPmClear() {
    setPmConfirm(false);
  }

  return (
    <div className="account-section">
      {/* ── Clear Room History ────────────────────────────────────────── */}
      <div className="settings-form">
        <h3 className="settings-form-heading">Clear Room History</h3>
        <p className="settings-form-description">
          Permanently delete all messages in a room. This action cannot be undone.
        </p>

        {roomError && <p className="settings-error">{roomError}</p>}
        {roomSuccess && <p className="settings-success">{roomSuccess}</p>}

        <div className="settings-form-group">
          <label htmlFor="room-select">Select Room</label>
          <input
            id="room-select"
            type="text"
            className="settings-input"
            placeholder="Room name or ID"
            value={selectedRoom}
            onChange={e => {
              setSelectedRoom(e.target.value);
              setRoomConfirm(false);
            }}
          />
        </div>

        {roomConfirm ? (
          <div className="settings-confirm-group">
            <p className="settings-confirm-text">
              Are you sure? This will permanently delete all messages.
            </p>
            <div className="settings-confirm-actions">
              <button
                type="button"
                className="settings-btn btn-danger"
                onClick={handleClearRoomHistory}
                disabled={!selectedRoom.trim()}
              >
                Confirm Delete
              </button>
              <button
                type="button"
                className="settings-btn btn-ghost"
                onClick={handleCancelRoomClear}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="settings-btn btn-danger"
            onClick={handleClearRoomHistory}
            disabled={!selectedRoom.trim()}
          >
            Clear History
          </button>
        )}
      </div>

      {/* ── Clear PM History ──────────────────────────────────────────── */}
      <div className="settings-form">
        <h3 className="settings-form-heading">Clear PM History</h3>
        <p className="settings-form-description">
          Permanently delete all messages in a private conversation. This action cannot be undone.
        </p>

        {pmError && <p className="settings-error">{pmError}</p>}
        {pmSuccess && <p className="settings-success">{pmSuccess}</p>}

        <div className="settings-form-group">
          <label htmlFor="pm-select">Select User</label>
          <input
            id="pm-select"
            type="text"
            className="settings-input"
            placeholder="Username"
            value={selectedPM}
            onChange={e => {
              setSelectedPM(e.target.value);
              setPmConfirm(false);
            }}
          />
        </div>

        {pmConfirm ? (
          <div className="settings-confirm-group">
            <p className="settings-confirm-text">
              Are you sure? This will permanently delete all PM messages.
            </p>
            <div className="settings-confirm-actions">
              <button
                type="button"
                className="settings-btn btn-danger"
                onClick={handleClearPMHistory}
                disabled={!selectedPM.trim()}
              >
                Confirm Delete
              </button>
              <button
                type="button"
                className="settings-btn btn-ghost"
                onClick={handleCancelPmClear}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="settings-btn btn-danger"
            onClick={handleClearPMHistory}
            disabled={!selectedPM.trim()}
          >
            Clear History
          </button>
        )}
      </div>
    </div>
  );
}
