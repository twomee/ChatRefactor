// src/services/messageApi.js — Message-service API calls
import http from './http';

/**
 * Fetch Open Graph link preview metadata for a URL.
 * Returns { url, title, description, image } on success.
 *
 * @param {string} url - The URL to preview
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function fetchLinkPreview(url) {
  return http.get('/messages/preview', { params: { url } });
}
