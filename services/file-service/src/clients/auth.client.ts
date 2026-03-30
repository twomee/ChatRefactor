// src/clients/auth.client.ts — Resolves usernames to user IDs via Auth Service.
//
// Used exclusively during PM file uploads to look up the recipient's numeric ID.
// Keeps a simple in-process cache (Map) to avoid repeated lookups for the same
// username within a short window.

import { config } from "../config/env.config.js";

interface AuthUser {
  id: number;
  username: string;
}

const cache = new Map<string, { user: AuthUser | null; expiresAt: number }>();
const CACHE_TTL_MS = 60_000; // 1 minute

/**
 * Look up a user by username via the Auth Service.
 * Returns the user object or null if not found.
 * Throws if the Auth Service is unreachable.
 */
export async function getUserByUsername(username: string): Promise<AuthUser | null> {
  const now = Date.now();
  const cached = cache.get(username);
  if (cached && cached.expiresAt > now) {
    return cached.user;
  }

  const url = `${config.authServiceUrl}/auth/users/by-username/${encodeURIComponent(username)}`;
  const response = await fetch(url, { signal: AbortSignal.timeout(3000) });

  if (response.status === 404) {
    cache.set(username, { user: null, expiresAt: now + CACHE_TTL_MS });
    return null;
  }

  if (!response.ok) {
    throw new Error(`Auth service returned ${response.status} for username lookup`);
  }

  const user: AuthUser = await response.json();
  cache.set(username, { user, expiresAt: now + CACHE_TTL_MS });
  return user;
}

/** Clear the cache — used in tests. */
export function clearAuthCache(): void {
  cache.clear();
}
