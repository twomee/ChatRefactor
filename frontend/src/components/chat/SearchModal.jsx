// src/components/chat/SearchModal.jsx — Global message search (command palette)
//
// Opened via Ctrl+K / Cmd+K or the search button in the header.
// Debounces input by 300ms before firing the API call.
// Displays results with sender avatar, content snippet, room name, and timestamp.
// Supports full keyboard navigation (ArrowUp/Down + Enter).
// Clicking or pressing Enter on a result navigates to that room AND message.
import { useCallback, useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { searchMessages } from '../../services/searchApi';

// ── Module-scope helpers ──

/**
 * Wraps matching substrings in <mark> for highlighting.
 * Defined at module scope to keep the component's cognitive complexity budget intact.
 */
function highlightMatch(text, q) {
  if (!q || !text) return text;
  const escaped = q.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
  const parts = text.split(new RegExp(`(${escaped})`, 'gi')); // NOSONAR - input is sanitized on the line above
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

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

function searchPMThreads(query, pmThreads) {
  if (!pmThreads) return [];
  const q = query.toLowerCase();
  const results = [];
  for (const [username, messages] of Object.entries(pmThreads)) {
    for (const msg of messages) {
      if (!msg.is_deleted && msg.text?.toLowerCase().includes(q)) {
        results.push({
          message_id: msg.msg_id || `pm-local-${username}-${results.length}`,
          sender_name: msg.from,
          content: msg.text,
          sent_at: msg.timestamp || null,
          pm_username: username,
          room_id: null,
        });
      }
    }
  }
  return results;
}

/**
 * @param {Object}   props
 * @param {boolean}  props.isOpen      - Whether the modal is visible
 * @param {Function} props.onClose     - Called to close the modal
 * @param {Array}    props.rooms       - Room list [{ id, name }] for name lookups
 * @param {Object}   props.pmThreads   - PM threads for local search { username: [messages] }
 * @param {Function} props.onNavigate  - Called with (roomId, messageId, pmUsername) when user clicks a result
 */
export default function SearchModal({ isOpen, onClose, rooms = [], pmThreads = {}, onNavigate }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const abortControllerRef = useRef(null);
  const resultsListRef = useRef(null);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setError(null);
      setSelectedIndex(-1);
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

  // Scroll active item into view when selectedIndex changes
  useEffect(() => {
    if (selectedIndex < 0) return;
    const listEl = resultsListRef.current;
    if (!listEl) return;
    const activeItem = listEl.querySelector('.search-result-item.active');
    if (activeItem) {
      activeItem.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  // Debounced search — fires after 300 ms of inactivity.
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

        // Search PM threads locally (instant)
        const pmResults = searchPMThreads(trimmed, pmThreads);

        try {
          const res = await searchMessages(trimmed, null, 20, abortControllerRef.current.signal);
          // Combine room results with PM results; PM results first for immediacy
          setResults([...pmResults, ...(res.data || [])]);
          setError(null);
        } catch (err) {
          // AbortError means the request was cancelled by a newer search — ignore it
          if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return;
          // Still show PM results even if room search failed
          setResults(pmResults);
          setError(pmResults.length === 0 ? 'Search failed. Please try again.' : null);
        } finally {
          setLoading(false);
        }
      }, 300);
    },
    [pmThreads], // pmThreads changes when new PMs arrive
  );

  function handleInputChange(e) {
    const val = e.target.value;
    setQuery(val);
    setSelectedIndex(-1);
    doSearch(val);
  }

  function handleResultClick(result) {
    if (onNavigate) {
      onNavigate(result.room_id, result.message_id, result.pm_username);
    }
    onClose();
  }

  function handleInputKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < results.length) {
        handleResultClick(results[selectedIndex]);
      }
    }
  }

  function handleOverlayClick(e) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  function handleOverlayKeyDown(e) {
    if (e.key === 'Escape') onClose();
  }

  function getResultContext(result) {
    if (result.pm_username) return `DM · ${result.pm_username}`;
    const room = rooms.find((r) => r.id === result.room_id);
    if (room) return room.name;
    if (result.room_id) return `Room ${result.room_id}`;
    return '';
  }

  if (!isOpen) return null;

  const activeDescendant = selectedIndex >= 0 ? `search-result-${selectedIndex}` : undefined;

  return (
    <div className="search-modal-overlay" onClick={handleOverlayClick} onKeyDown={handleOverlayKeyDown}>
      <div className="search-modal" role="dialog" aria-modal="true" aria-label="Search messages">
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
            onKeyDown={handleInputKeyDown}
            aria-label="Search messages"
            aria-activedescendant={activeDescendant}
            role="combobox"
            aria-expanded={results.length > 0}
            aria-controls="search-results-list"
            aria-autocomplete="list"
          />
          <kbd className="search-modal-kbd">ESC</kbd>
        </div>

        {/* Results */}
        <div className="search-modal-results">
          {loading && (
            <div className="search-modal-status">Searching...</div>
          )}

          {Boolean(error) && (
            <div className="search-modal-status search-modal-error">{error}</div>
          )}

          {!loading && !error && query.trim().length > 0 && results.length === 0 && (
            <div className="search-modal-status">No messages found</div>
          )}

          {!loading && results.length > 0 && (
            <div className="search-result-list" id="search-results-list" ref={resultsListRef} role="listbox"> {/* NOSONAR — ARIA combobox pattern; native select cannot render rich content */}
              {results.map((r, idx) => (
                <div key={r.message_id} role="option" aria-selected={idx === selectedIndex} id={`search-result-${idx}`}>
                  <button
                    type="button"
                    className={`search-result-item${idx === selectedIndex ? ' active' : ''}`}
                    onClick={() => handleResultClick(r)}
                  >
                    <div className="search-result-header">
                      <span className="search-result-avatar">
                        {getInitials(r.sender_name)}
                      </span>
                      <span className="search-result-sender">
                        {r.sender_name || 'Unknown'}
                      </span>
                      <span className="search-result-room">
                        {getResultContext(r)}
                      </span>
                      <span className="search-result-time">
                        {formatTime(r.sent_at)}
                      </span>
                    </div>
                    <div className="search-result-content">
                      {highlightMatch(r.content, query.trim())}
                    </div>
                  </button>
                </div>
              ))}
            </div>
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
  pmThreads: PropTypes.object,
  onNavigate: PropTypes.func,
};
