// src/components/ContextMenu.jsx
export default function ContextMenu({ x, y, target, isMuted, isTargetAdmin, onKick, onMute, onUnmute, onPromote, onClose }) {
  return (
    <div className="context-menu" style={{ top: y, left: x }} onMouseLeave={onClose}>
      <div className="context-menu-header">{target}</div>
      <div className="context-menu-divider" />

      {!isTargetAdmin && (
        <>
          <div
            className="context-menu-item danger"
            onClick={() => { onKick(target); onClose(); }}
          >
            Kick
          </div>
          {isMuted ? (
            <div
              className="context-menu-item"
              onClick={() => { onUnmute(target); onClose(); }}
            >
              Unmute
            </div>
          ) : (
            <div
              className="context-menu-item"
              onClick={() => { onMute(target); onClose(); }}
            >
              Mute
            </div>
          )}
          <div
            className="context-menu-item"
            onClick={() => { onPromote(target); onClose(); }}
          >
            Make Admin
          </div>
        </>
      )}

      {isTargetAdmin && (
        <div className="context-menu-item-disabled">
          Already an admin
        </div>
      )}
    </div>
  );
}
