// src/hooks/useAuthenticatedImage.js — Fetches images via authenticated
// HTTP client and exposes them as blob URLs, avoiding JWT leakage in
// <img src> query strings, browser history, Referer headers, and logs.

import { useState, useEffect } from 'react';
import http from '../services/http';

export default function useAuthenticatedImage(fileId) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!fileId) return;
    let revoked = false;

    http.get(`/files/download/${fileId}`, { responseType: 'blob' })
      .then(res => {
        if (!revoked) {
          setUrl(URL.createObjectURL(res.data));
        }
      })
      .catch(() => {
        if (!revoked) setError(true);
      });

    return () => {
      revoked = true;
    };
  }, [fileId]);

  // Cleanup blob URL on unmount or when url changes
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  return { url, error };
}
