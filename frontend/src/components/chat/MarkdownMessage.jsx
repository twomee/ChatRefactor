import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_ELEMENTS = [
  'p', 'strong', 'em', 'del', 'code', 'pre', 'a',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3',
  'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
];

const REMARK_PLUGINS = [remarkGfm];

const COMPONENTS = {
  a: ({ children, href, ...props }) => {
    const safeHref = href?.startsWith('javascript:') ? '#' : href;
    return (
      <a href={safeHref} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
  pre: ({ children }) => <>{children}</>,
  code: ({ children, className, ...props }) => {
    const isBlock = className?.startsWith('language-') || String(children).includes('\n');
    if (isBlock) {
      return (
        <pre className="code-block">
          <code className={className} {...props}>{children}</code>
        </pre>
      );
    }
    return <code className="inline-code" {...props}>{children}</code>;
  },
  p: ({ children }) => <div className="msg-paragraph">{children}</div>,
};

export default React.memo(function MarkdownMessage({ text }) {
  if (!text) return null;

  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  );
});
