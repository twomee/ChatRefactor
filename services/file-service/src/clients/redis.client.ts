// clients/redis.client.ts — optional Redis client for token blacklist checks
//
// Returns a connected Redis client if REDIS_URL is configured, or null if not.
// The auth middleware uses this to check whether a token has been revoked by the
// auth-service on logout. If Redis is unavailable, behavior depends on NODE_ENV:
//   - production  → fail closed (reject the request)
//   - development → fail open  (skip the check, log a warning)

import Redis from "ioredis";
import { logger } from "../kafka/logger.js";

let redisClient: Redis | null = null;

export function getRedisClient(): Redis | null {
  return redisClient;
}

export function initRedisClient(redisUrl: string): void {
  if (!redisUrl) return;

  redisClient = new Redis(redisUrl, {
    // Disable auto-reconnect after persistent failure — the app should not
    // hammer a down Redis. The health check will surface the issue.
    maxRetriesPerRequest: 2,
    enableOfflineQueue: false,
    lazyConnect: false,
  });

  redisClient.on("connect", () => {
    logger.info("Redis connected (token blacklist)");
  });

  redisClient.on("error", (err) => {
    logger.warn("Redis connection error", { error: err.message });
  });
}

export async function closeRedisClient(): Promise<void> {
  if (redisClient) {
    await redisClient.quit();
    redisClient = null;
  }
}
