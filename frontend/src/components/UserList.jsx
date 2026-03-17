// src/components/UserList.jsx
import { useState } from 'react';
import ContextMenu from './ContextMenu';

export default function UserList({ users, admins, mutedUsers, currentUser, isCurrentUserAdmin, onKick, onMute, onUnmute, onPromote }) {
  const [menu, setMenu] = useState(null); // { x, y, target }

  function handleRightClick(e, username) {
    if (username === currentUser) return;
    if (!isCurrentUserAdmin) return; // only admins can perform actions
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, target: username });
  }

  return (
    <div style={{ width: 160, borderLeft: '1px solid #ccc', padding: 8, overflowY: 'auto' }}>
      <h4 style={{ margin: '0 0 8px' }}>Online ({(users || []).length})</h4>
      {(users || []).map(u => (
        <div
          key={u}
          onContextMenu={e => handleRightClick(e, u)}
          style={{
            padding: '4px 0',
            cursor: isCurrentUserAdmin && u !== currentUser ? 'context-menu' : 'default',
            userSelect: 'none',
          }}
          title={isCurrentUserAdmin && u !== currentUser ? 'Right-click for options' : undefined}
        >
          {(admins || []).includes(u) ? '★ ' : ''}
          {u}
          {(mutedUsers || []).includes(u) ? ' 🔇' : ''}
        </div>
      ))}
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y} target={menu.target}
          isMuted={(mutedUsers || []).includes(menu.target)}
          isTargetAdmin={(admins || []).includes(menu.target)}
          onKick={onKick}
          onMute={onMute}
          onUnmute={onUnmute}
          onPromote={onPromote}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
