// src/components/chat/SearchModal.jsx — Global message search modal
//
// Opened via Ctrl+K / Cmd+K or the search button in the header.
// Debounces input by 300ms before firing the API call.
// Displays results with sender, content snippet, room name, and timestamp.
// Clicking a result navigates the user to that room.
import { useCallback, useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { searchMessages } from '../../services/searchApi';

/**
 * @param {Object}   props
 * @param {boolean}  props.isOpen      - Whether the modal is visible
 * @param {Function} props.onClose     - Called to close the modal
 * @param {Array}    props.rooms       - Room list [{ id, name }] for name lookups
 * @param {Function} props.onNavigate  - Called with roomId when user clicks a result
 */

// ── Module-scope helpers ──

/**
 * Wraps matching substrings in <mark> for highlighting.
 * Defined at module scope to keep the component's cognitive complexity budget intact.
 */
function highlightMatch(text, q) {
  if (!q || !text) return text;
  const escaped = q.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, i) => {
    const key = `part-${i}`;
    if (part.toLowerCase() === q.toLowerCase()) {
      return (
        <mark key={key} className="search-highlight">
          {part}
        </mark>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

function formatTime(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

export default function SearchModal({ isOpen, onClose, rooms = [], onNavigate }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setError(null);
      // Small delay to let the modal render before focusing
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    globalThis.addEventListener('keydown', handleKeyDown);
    return () => globalThis.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Debounced search — fires after 300 ms of inactivity.
  //
  // Fix (min length): queries shorter than 2 characters are rejected early to
  // avoid triggering full GIN index scans on the backend.
  //
  // Fix (AbortController): each new search cancels the previous in-flight
  // request via AbortController so stale responses from slow network round-trips
  // never overwrite results from a more-recent query.
  //
  // Dependency array is intentionally empty: setResults, setError, and
  // setLoading are stable React dispatcher references that never change between
  // renders, so there is no stale-closure risk here.
  const doSearch = useCallback(
    (q) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);

      const trimmed = q.trim();
      if (!trimmed) {
        setResults([]);
        setError(null);
        setLoading(false);
        return;
      }

      // Guard: require at least 2 characters to prevent full GIN index scans
      if (trimmed.length < 2) {
        setResults([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      debounceRef.current = setTimeout(async () => {
        // Cancel any previous in-flight request before issuing a new one
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        try {
          const res = await searchMessages(trimmed, null, 20, abortControllerRef.current.signal);
          setResults(res.data || []);
          setError(null);
        } catch (err) {
          // AbortError means the request was cancelled by a newer search — ignore it
          if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return;
          setError('Search failed. Please try again.');
          setResults([]);
        } finally {
          setLoading(false);
        }
      }, 300);
    },
    [], // setResults/setError/setLoading are stable React dispatcher refs
  );

  function handleInputChange(e) {
    const val = e.target.value;
    setQuery(val);
    doSearch(val);
  }

  function handleResultClick(result) {
    if (result.room_id && onNavigate) {
      onNavigate(result.room_id);
    }
    onClose();
  }

  function handleOverlayClick(e) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  function getRoomName(roomId) {
    const room = rooms.find((r) => r.id === roomId);
    if (room) return `#${room.name}`;
    if (roomId) return `Room ${roomId}`;
    return 'DM';
  }

  if (!isOpen) return null;

  return (
    <div className="search-modal-overlay" onClick={handleOverlayClick} onKeyDown={e => { if (e.key === 'Escape') onClose(); }} role="dialog" aria-modal="true" aria-label="Search messages">
      <div className="search-modal">
        {/* Search input */}
        <div className="search-modal-input-wrapper">
          <svg className="search-modal-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            className="search-modal-input"
            placeholder="Search messages..."
            value={query}
            onChange={handleInputChange}
            aria-label="Search messages"
          />
          <kbd className="search-modal-kbd">ESC</kbd>
        </div>

        {/* Results */}
        <div className="search-modal-results">
          {loading && (
            <div className="search-modal-status">Searching...</div>
          )}

          {error && (
            <div className="search-modal-status search-modal-error">{error}</div>
          )}

          {!loading && !error && query.trim() && results.length === 0 && (
            <div className="search-modal-status">No messages found</div>
          )}

          {!loading && results.length > 0 && (
            <ul className="search-result-list" role="listbox">
              {results.map((r) => (
                <li
                  key={r.message_id}
                  className="search-result-item"
                  onClick={() => handleResultClick(r)}
                  role="option"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleResultClick(r);
                  }}
                >
                  <div className="search-result-header">
                    <span className="search-result-sender">
                      {r.sender_name || 'Unknown'}
                    </span>
                    <span className="search-result-room">
                      {getRoomName(r.room_id)}
                    </span>
                    <span className="search-result-time">
                      {formatTime(r.sent_at)}
                    </span>
                  </div>
                  <div className="search-result-content">
                    {highlightMatch(r.content, query.trim())}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {!query.trim() && !loading && (
            <div className="search-modal-status search-modal-hint">
              Type to search across all messages
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

SearchModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  rooms: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    name: PropTypes.string,
  })),
  onNavigate: PropTypes.func,
};
