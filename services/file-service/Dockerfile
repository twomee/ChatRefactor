# Multi-stage build for File Service
# Stage 1: Build TypeScript + generate Prisma client
# Stage 2: Production runtime with minimal image

# ── Build stage ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Copy dependency manifests first (Docker layer caching)
COPY package.json package-lock.json* ./
COPY prisma ./prisma/

# Install all dependencies (including devDependencies for tsc)
RUN npm ci

# Generate Prisma client
RUN npx prisma generate

# Copy source code and compile TypeScript
COPY tsconfig.json ./
COPY src ./src/
RUN npm run build

# ── Production stage ────────────────────────────────────────────────────────
FROM node:22-alpine AS runner

# Keep base image up to date (security)
# Patch picomatch CVE-2026-33671 in npm's bundled copy (node-gyp → tinyglobby → picomatch).
# node:22-alpine ships npm 10.9.7 which bundles picomatch 4.0.3; fixed in 4.0.4.
# Remove this once the base image ships npm with picomatch ≥4.0.4.
RUN apk upgrade --no-cache && \
    cd /usr/local/lib/node_modules/npm/node_modules/picomatch && \
    npm pack picomatch@4.0.4 --pack-destination /tmp && \
    tar xzf /tmp/picomatch-4.0.4.tgz --strip-components=1 && \
    rm /tmp/picomatch-4.0.4.tgz

WORKDIR /app

# Copy dependency manifests and install production-only deps
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# Copy Prisma schema + generated client from builder.
# Schema is needed for `prisma migrate deploy` in the K8s init container.
# Generated client avoids installing the prisma CLI (devDep) in prod.
COPY --from=builder /app/prisma ./prisma/
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/prisma ./node_modules/prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma

# Copy compiled JavaScript from build stage
COPY --from=builder /app/dist ./dist/

# Create upload directory with correct permissions
RUN mkdir -p /app/uploads

# Create non-root user for security
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Give appuser ownership of the app directory (needed for uploads)
RUN chown -R appuser:appgroup /app

USER appuser

# Expose the service port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8005/health || exit 1

# Start the service (db schema created by db-init container, not here)
CMD ["node", "dist/index.js"]
