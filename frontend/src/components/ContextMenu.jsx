// src/components/ContextMenu.jsx
export default function ContextMenu({ x, y, target, isMuted, isTargetAdmin, onKick, onMute, onUnmute, onPromote, onClose }) {
  return (
    <div
      style={{
        position: 'fixed', top: y, left: x,
        background: '#fff', border: '1px solid #ccc',
        borderRadius: 4, boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        zIndex: 1000, minWidth: 140,
      }}
      onMouseLeave={onClose}
    >
      <div style={{ padding: '4px 12px', fontWeight: 600, color: '#666', fontSize: 12 }}>{target}</div>
      <hr style={{ margin: '2px 0' }} />

      {/* Kick and mute are not allowed on other admins */}
      {!isTargetAdmin && (
        <>
          <div
            onClick={() => { onKick(target); onClose(); }}
            style={{ padding: '6px 12px', cursor: 'pointer' }}
          >
            🚫 Kick
          </div>
          {isMuted ? (
            <div onClick={() => { onUnmute(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>
              🔊 Unmute
            </div>
          ) : (
            <div onClick={() => { onMute(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>
              🔇 Mute
            </div>
          )}
        </>
      )}

      {/* Promote is always available (even for admins per requirements) */}
      {!isTargetAdmin && (
        <div onClick={() => { onPromote(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>
          ★ Make Admin
        </div>
      )}

      {isTargetAdmin && (
        <div style={{ padding: '6px 12px', color: '#999', fontSize: 12 }}>
          Already an admin
        </div>
      )}
    </div>
  );
}
