// src/components/ContextMenu.jsx
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const PADDING = 8; // minimum gap from viewport edge (px)

export default function ContextMenu({ x, y, target, isMuted, isTargetAdmin, onKick, onMute, onUnmute, onPromote, onStartPM, onClose }) {
  const menuRef = useRef(null);

  // Start hidden at the raw click position; useLayoutEffect will clamp it to
  // the viewport before the browser paints, so there's no visible flicker.
  const [pos, setPos] = useState({ x, y, visible: false });

  useLayoutEffect(() => {
    if (!menuRef.current) return;
    const { width, height } = menuRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    setPos({
      x: Math.max(PADDING, Math.min(x, vw - width - PADDING)),
      y: Math.max(PADDING, Math.min(y, vh - height - PADDING)),
      visible: true,
    });
  }, [x, y]);

  // Close when clicking anywhere outside the menu.
  useEffect(() => {
    function handleMouseDown(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [onClose]);

  // Render via portal so `position:fixed` is relative to the viewport, not a
  // CSS-transformed ancestor (react-grid-layout positions panels with transforms).
  return createPortal(
    <div
      ref={menuRef}
      className="context-menu"
      style={{ top: pos.y, left: pos.x, visibility: pos.visible ? 'visible' : 'hidden' }}
    >
      <div className="context-menu-header">{target}</div>
      <div className="context-menu-divider" />

      {onStartPM && (
        <div
          className="context-menu-item"
          onClick={() => { onStartPM(target); onClose(); }}
        >
          Send private message
        </div>
      )}

      {!isTargetAdmin && (
        <>
          <div className="context-menu-divider" />
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
    </div>,
    document.body
  );
}
