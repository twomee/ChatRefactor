import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_ELEMENTS = [
  'p', 'strong', 'em', 'del', 'code', 'pre', 'a',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3',
  'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
];

const REMARK_PLUGINS = [remarkGfm];

const MARKDOWN_COMPONENTS = {
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <pre className="code-block">
          <code className={className}>{children}</code>
        </pre>
      );
    }
    return <code className="inline-code">{children}</code>;
  },
  p: ({ children }) => <>{children}</>,
};

export default function MarkdownMessage({ text }) {
  if (!text) return null;

  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={MARKDOWN_COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  );
}

MarkdownMessage.propTypes = {
  text: PropTypes.string,
};
