// src/components/UserList.jsx
import { useState } from 'react';
import ContextMenu from './ContextMenu';

export default function UserList({ users, admins, mutedUsers, currentUser, onKick, onMute, onPromote }) {
  const [menu, setMenu] = useState(null); // { x, y, target }

  function handleRightClick(e, username) {
    if (username === currentUser) return; // can't action yourself
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, target: username });
  }

  return (
    <div style={{ width: 140, borderLeft: '1px solid #ccc', padding: 8 }}>
      <h4 style={{ margin: '0 0 8px' }}>Online</h4>
      {(users || []).map(u => (
        <div
          key={u}
          onContextMenu={e => handleRightClick(e, u)}
          style={{ padding: '4px 0', cursor: 'default', userSelect: 'none' }}
        >
          {(admins || []).includes(u) ? '★ ' : ''}
          {u}
          {(mutedUsers || []).includes(u) ? ' 🔇' : ''}
        </div>
      ))}
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y} target={menu.target}
          onKick={onKick} onMute={onMute} onPromote={onPromote}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
