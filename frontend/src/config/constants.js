// src/config/constants.js — Environment-aware configuration
// Uses runtime config (K8s) -> Vite env vars (dev) -> sensible defaults
import { config } from '../config';

export const API_BASE = config.apiBase || 'http://localhost:8000';

export const WS_BASE = config.wsBase || (() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
})();
