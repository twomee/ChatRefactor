// src/config/constants.js — Environment-aware configuration
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const wsBaseEnv = import.meta.env.VITE_WS_BASE;
export const WS_BASE = wsBaseEnv || (() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
})();
