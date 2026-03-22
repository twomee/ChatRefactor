// kafka/logger.ts — Winston logger instance for the file service

import winston from "winston";
import { config } from "../config/env.config.js";

export const logger = winston.createLogger({
  level: config.nodeEnv === "production" ? "info" : "debug",
  format: winston.format.combine(
    winston.format.timestamp({ format: "YYYY-MM-DDTHH:mm:ss.SSSZ" }),
    winston.format.errors({ stack: true }),
    config.nodeEnv === "production"
      ? winston.format.json()
      : winston.format.combine(winston.format.colorize(), winston.format.simple())
  ),
  defaultMeta: { service: "file-service" },
  transports: [new winston.transports.Console()],
});
