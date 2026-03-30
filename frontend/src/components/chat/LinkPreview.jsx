// src/components/chat/LinkPreview.jsx — Link preview card for URLs in messages
//
// Detects the first URL in message text, fetches OG metadata from the backend,
// and renders a compact card with title, description, image, and domain name.
//
// Caching: fetched previews are stored in a module-level Map to avoid
// re-fetching on re-renders. The cache lives for the duration of the SPA session.
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { fetchLinkPreview } from '../../services/messageApi';
import { previewCache } from '../../utils/linkPreviewUtils';

// Simple URL regex for detecting links in message text.
const URL_REGEX = /https?:\/\/[^\s<>"{}|\\^`[\]]+/;

/**
 * Return true only for http:// or https:// image URLs.
 * Rejects javascript:, data:, and any other scheme to prevent XSS.
 * This is defence-in-depth: the backend already validates scheme,
 * but we double-check on the client before setting src on an <img>.
 */
function isSafeImageUrl(url) {
  return typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'));
}

/**
 * Extract the display domain from a URL string.
 * e.g. "https://www.example.com/path" → "example.com"
 */
function getDomain(url) {
  try {
    const hostname = new URL(url).hostname;
    return hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/**
 * LinkPreview renders a preview card for the first URL found in the text.
 *
 * @param {Object} props
 * @param {string} props.text - The full message text to scan for URLs
 */
export default function LinkPreview({ text }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  // Extract the first URL from the text
  const match = text ? URL_REGEX.exec(text) : null;
  const url = match ? match[0] : null;

  useEffect(() => {
    if (!url) return;

    // Check client-side cache first
    if (previewCache.has(url)) {
      const cached = previewCache.get(url);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (cached) setPreview(cached);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetchLinkPreview(url)
      .then((res) => {
        if (!cancelled) {
          previewCache.set(url, res.data);
          setPreview(res.data);
        }
      })
      .catch(() => {
        // Cache the failure so we don't keep retrying
        if (!cancelled) {
          previewCache.set(url, null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  // Don't render anything if no URL or no preview data
  if (!url || (!preview && !loading)) return null;

  // Show a minimal loading skeleton
  if (loading) {
    return (
      <div className="link-preview-card link-preview-loading" aria-label="Loading link preview">
        <div className="link-preview-info">
          <div className="link-preview-title-skeleton" />
          <div className="link-preview-desc-skeleton" />
          <div className="link-preview-domain">{getDomain(url)}</div>
        </div>
      </div>
    );
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="link-preview-card"
      aria-label={`Link preview: ${preview?.title || url}`}
    >
      <div className="link-preview-info">
        {preview?.title && (
          <div className="link-preview-title">{preview?.title}</div>
        )}
        {preview?.description && (
          <div className="link-preview-desc">{preview?.description}</div>
        )}
        <div className="link-preview-domain">{getDomain(url)}</div>
      </div>
      {preview?.image && isSafeImageUrl(preview?.image) && (
        <img
          src={preview?.image}
          alt=""
          className="link-preview-image"
          loading="lazy"
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      )}
    </a>
  );
}

LinkPreview.propTypes = {
  text: PropTypes.string.isRequired,
};
