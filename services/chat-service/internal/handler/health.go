package handler

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/twomee/chatbox/chat-service/internal/kafka"
)

// HealthHandler provides liveness and readiness probes.
type HealthHandler struct {
	db            *pgxpool.Pool
	redis         *redis.Client
	kafkaProducer *kafka.Producer
	kafkaBrokers  []string
}

// NewHealthHandler creates a HealthHandler with the infrastructure deps.
func NewHealthHandler(db *pgxpool.Pool, rdb *redis.Client, kp *kafka.Producer, brokers []string) *HealthHandler {
	return &HealthHandler{
		db:            db,
		redis:         rdb,
		kafkaProducer: kp,
		kafkaBrokers:  brokers,
	}
}

// Health is the liveness probe — always returns 200 if the process is up.
func (h *HealthHandler) Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"service": "chat-service",
	})
}

// Ready is the readiness probe — checks DB, Redis, Kafka connectivity.
// Error details are intentionally omitted from the response to avoid
// leaking internal infrastructure information (CWE-209).
func (h *HealthHandler) Ready(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
	defer cancel()

	checks := make(map[string]string)
	healthy := true

	// PostgreSQL
	if h.db != nil {
		if err := h.db.Ping(ctx); err != nil {
			checks["database"] = "unhealthy"
			healthy = false
		} else {
			checks["database"] = "ok"
		}
	} else {
		checks["database"] = "not configured"
	}

	// Redis
	if h.redis != nil {
		if err := h.redis.Ping(ctx).Err(); err != nil {
			checks["redis"] = "unhealthy"
			healthy = false
		} else {
			checks["redis"] = "ok"
		}
	} else {
		checks["redis"] = "not configured"
	}

	// Kafka
	if h.kafkaProducer != nil {
		if err := h.kafkaProducer.Ping(ctx, h.kafkaBrokers); err != nil {
			checks["kafka"] = "unhealthy"
			healthy = false
		} else {
			checks["kafka"] = "ok"
		}
	} else {
		checks["kafka"] = "not configured"
	}

	status := http.StatusOK
	if !healthy {
		status = http.StatusServiceUnavailable
	}

	c.JSON(status, gin.H{
		"status": checks,
	})
}
