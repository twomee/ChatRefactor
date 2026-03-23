# ---- Build stage ----
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git

WORKDIR /app

# Enable automatic toolchain downloads for forward-compatible go.mod.
ENV GOTOOLCHAIN=auto

# Cache dependency downloads.
COPY go.mod go.sum ./
RUN go mod download

# Copy source and build.
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /chat-service ./cmd/server

# ---- Run stage ----
FROM alpine:3.19

# Keep base packages up to date for security.
RUN apk upgrade --no-cache && \
    apk add --no-cache ca-certificates tzdata

# Non-root user.
RUN adduser -D -u 1001 appuser
USER appuser

WORKDIR /app
COPY --from=builder /chat-service .
COPY migrations/ ./migrations/

EXPOSE 8003

ENTRYPOINT ["./chat-service"]
