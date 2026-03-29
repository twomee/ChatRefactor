// Module-level cache — survives re-renders, lives for the SPA session.
// Exported for testing (cache clearing between tests).
export const previewCache = new Map();
