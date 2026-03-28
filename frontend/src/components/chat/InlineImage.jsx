// src/components/chat/InlineImage.jsx — Securely renders image previews
// using blob URLs fetched via the authenticated HTTP client.
import useAuthenticatedImage from '../../hooks/useAuthenticatedImage';
import { formatSize } from '../../utils/formatting';

export default function InlineImage({ fileId, filename, fileSize, onDownload }) {
  const { url, error } = useAuthenticatedImage(fileId);

  if (error) {
    return (
      <a
        href="#"
        onClick={(e) => { e.preventDefault(); onDownload(fileId, filename); }}
        className="msg-file-link"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
        </svg>
        {filename}{fileSize ? ` (${formatSize(fileSize)})` : ''}
      </a>
    );
  }

  if (!url) {
    return <div className="msg-image-loading">Loading image...</div>;
  }

  return (
    <div className="msg-image-preview">
      <img
        src={url}
        alt={filename}
        className="msg-inline-image"
        onClick={() => window.open(url, '_blank')}
      />
      <span className="msg-image-filename">
        {filename}{fileSize ? ` (${formatSize(fileSize)})` : ''}
      </span>
    </div>
  );
}
