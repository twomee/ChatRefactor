// src/utils/fileHelpers.js — File type detection utilities

// Note: .svg excluded because backend serves application/octet-stream
// which prevents inline SVG rendering in <img> tags.
// .bmp excluded — very rare and typically very large files.
const IMAGE_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp',
]);

/**
 * Returns true when `filename` ends with a recognised image extension.
 * Comparison is case-insensitive so "photo.JPG" matches too.
 */
export function isImageFile(filename) {
  if (!filename) return false;
  const dotIndex = filename.lastIndexOf('.');
  if (dotIndex === -1) return false;
  const ext = filename.substring(dotIndex).toLowerCase();
  return IMAGE_EXTENSIONS.has(ext);
}
