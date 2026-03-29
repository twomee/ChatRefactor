// src/components/chat/TypingIndicator.jsx
import PropTypes from 'prop-types';

/**
 * Displays an animated "X is typing..." indicator below the message list.
 *
 * @param {{ typingUsers: Record<string, number> | undefined }} props
 *   typingUsers — object keyed by username with a timestamp value.
 *   When empty or undefined, nothing is rendered (the container keeps
 *   a min-height so the layout doesn't jump).
 */
export default function TypingIndicator({ typingUsers }) {
  const names = typingUsers ? Object.keys(typingUsers) : [];

  if (names.length === 0) {
    return <div className="typing-indicator" />;
  }

  const label = names.length === 1
    ? `${names[0]} is typing`
    : `${names.join(', ')} are typing`;

  return (
    <div className="typing-indicator">
      {label}
      <span className="typing-dots">
        <span>.</span>
        <span>.</span>
        <span>.</span>
      </span>
    </div>
  );
}

TypingIndicator.propTypes = {
  typingUsers: PropTypes.objectOf(PropTypes.number),
};
