// kafka/logger.ts — Winston logger instance for the file service

import winston from "winston";
import { config } from "../config/env.config.js";

// Keys whose values should be fully redacted in log output.
const REDACT_KEYS = new Set(["password", "token", "secret", "secret_key", "authorization"]);
const BEARER_PATTERN = /Bearer\s+\S+/gi;

/**
 * Winston format that redacts sensitive fields (password, token, etc.)
 * from log metadata to prevent credential leakage in log aggregators.
 */
const redactSensitive = winston.format((info) => {
  for (const key of Object.keys(info)) {
    if (REDACT_KEYS.has(key.toLowerCase())) {
      info[key] = "[REDACTED]";
    } else if (typeof info[key] === "string" && BEARER_PATTERN.test(info[key])) {
      info[key] = info[key].replace(BEARER_PATTERN, "Bearer [REDACTED]");
    }
  }
  return info;
});

export const logger = winston.createLogger({
  level: config.nodeEnv === "production" ? "info" : "debug",
  format: winston.format.combine(
    winston.format.timestamp({ format: "YYYY-MM-DDTHH:mm:ss.SSSZ" }),
    winston.format.errors({ stack: true }),
    redactSensitive(),
    config.nodeEnv === "production"
      ? winston.format.json()
      : winston.format.combine(winston.format.colorize(), winston.format.simple())
  ),
  defaultMeta: { service: "file-service" },
  transports: [new winston.transports.Console()],
});
