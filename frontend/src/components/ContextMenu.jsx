// src/components/ContextMenu.jsx
export default function ContextMenu({ x, y, target, onKick, onMute, onPromote, onClose }) {
  return (
    <div
      style={{
        position: 'fixed', top: y, left: x,
        background: '#fff', border: '1px solid #ccc',
        borderRadius: 4, boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        zIndex: 1000, minWidth: 120,
      }}
      onMouseLeave={onClose}
    >
      <div style={{ padding: '4px 12px', fontWeight: 600, color: '#666', fontSize: 12 }}>{target}</div>
      <hr style={{ margin: '2px 0' }} />
      <div onClick={() => { onKick(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>Kick</div>
      <div onClick={() => { onMute(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>Mute</div>
      <div onClick={() => { onPromote(target); onClose(); }} style={{ padding: '6px 12px', cursor: 'pointer' }}>Make Admin</div>
    </div>
  );
}
