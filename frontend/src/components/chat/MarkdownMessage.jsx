import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_ELEMENTS = [
  'p', 'strong', 'em', 'del', 'code', 'pre', 'a',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3',
  'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
];

export default function MarkdownMessage({ text }) {
  if (!text) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={{
        a: ({ children, href, ...props }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
            {children}
          </a>
        ),
        code: ({ children, className, ...props }) => {
          const isBlock = className?.includes('language-');
          if (isBlock) {
            return (
              <pre className="code-block">
                <code className={className} {...props}>{children}</code>
              </pre>
            );
          }
          return <code className="inline-code" {...props}>{children}</code>;
        },
        p: ({ children }) => <>{children}</>,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
