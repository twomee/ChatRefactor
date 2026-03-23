// Package main is the entry point for the chat-service.
// It loads config, connects to infrastructure (DB, Redis, Kafka),
// registers Gin routes, and starts the HTTP server.
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/config"
	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/handler"
	"github.com/twomee/chatbox/chat-service/internal/kafka"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// runMigrations reads the SQL migration file and executes it against the
// database. It tries two paths: first "migrations/" (Docker working dir),
// then "services/chat-service/migrations/" (local dev from repo root).
// After applying the schema, it seeds the default rooms if they don't exist.
func runMigrations(ctx context.Context, pool *pgxpool.Pool, logger *zap.Logger) error {
	migrationPaths := []string{
		"migrations/001_create_rooms.up.sql",
		"services/chat-service/migrations/001_create_rooms.up.sql",
	}

	var sqlBytes []byte
	var usedPath string
	for _, p := range migrationPaths {
		data, err := os.ReadFile(p)
		if err == nil {
			sqlBytes = data
			usedPath = p
			break
		}
	}
	if sqlBytes == nil {
		return fmt.Errorf("migration file not found in any of %v", migrationPaths)
	}
	logger.Info("migration_file_found", zap.String("path", usedPath))

	if _, err := pool.Exec(ctx, string(sqlBytes)); err != nil {
		return fmt.Errorf("migration exec failed: %w", err)
	}
	logger.Info("migration_applied")

	// Seed default rooms if they don't already exist.
	defaultRooms := []string{"politics", "sports", "movies"}
	for _, name := range defaultRooms {
		_, err := pool.Exec(ctx,
			"INSERT INTO rooms (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
			name,
		)
		if err != nil {
			return fmt.Errorf("seed room %q failed: %w", name, err)
		}
	}
	logger.Info("default_rooms_seeded", zap.Strings("rooms", defaultRooms))

	return nil
}

func main() {
	// --- Logger ---
	logger, _ := zap.NewProduction()
	if os.Getenv("APP_ENV") == "dev" || os.Getenv("APP_ENV") == "" {
		logger, _ = zap.NewDevelopment()
	}
	defer func() { _ = logger.Sync() }()

	// --- Config ---
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("config_load_failed", zap.Error(err))
	}
	logger.Info("config_loaded",
		zap.String("env", cfg.AppEnv),
		zap.Int("port", cfg.Port),
	)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// --- PostgreSQL ---
	var dbPool *pgxpool.Pool
	if cfg.DatabaseURL != "" {
		dbPool, err = pgxpool.New(ctx, cfg.DatabaseURL)
		if err != nil {
			logger.Fatal("db_connect_failed", zap.Error(err))
		}
		defer dbPool.Close()
		if err := dbPool.Ping(ctx); err != nil {
			logger.Fatal("db_ping_failed", zap.Error(err))
		}
		logger.Info("database_connected")

		// Run SQL migrations and seed default rooms.
		if err := runMigrations(ctx, dbPool, logger); err != nil {
			logger.Fatal("migration_failed", zap.Error(err))
		}
	} else {
		logger.Warn("database_not_configured")
	}

	// --- Redis ---
	var rdb *redis.Client
	if cfg.RedisURL != "" {
		opts, err := redis.ParseURL(cfg.RedisURL)
		if err != nil {
			logger.Fatal("redis_url_parse_failed", zap.Error(err))
		}
		rdb = redis.NewClient(opts)
		if err := rdb.Ping(ctx).Err(); err != nil {
			logger.Warn("redis_ping_failed", zap.Error(err))
		} else {
			logger.Info("redis_connected")
		}
		defer func() { _ = rdb.Close() }()
	}

	// --- Kafka ---
	brokers := cfg.KafkaBrokerList()
	var kafkaProducer *kafka.Producer
	var deliveryStrategy delivery.Strategy
	if len(brokers) > 0 && brokers[0] != "" {
		kafkaProducer = kafka.NewProducer(brokers, logger)
		deliveryStrategy = delivery.NewKafkaDelivery(kafkaProducer)
		defer func() { _ = kafkaProducer.Close() }()
		logger.Info("kafka_producer_initialized", zap.Strings("brokers", brokers))
	} else {
		deliveryStrategy = delivery.NewSyncDelivery(logger)
		logger.Warn("kafka_not_configured_using_sync_delivery")
	}

	// --- Domain components ---
	roomStore := store.NewRoomStore(dbPool)
	wsManager := ws.NewManager(logger)
	authClient := client.NewAuthClient(cfg.AuthServiceURL, logger)

	// --- Handlers ---
	healthH := handler.NewHealthHandler(dbPool, rdb, kafkaProducer, brokers)
	roomH := handler.NewRoomHandler(roomStore, wsManager, authClient, logger)
	wsH := handler.NewWSHandler(wsManager, roomStore, deliveryStrategy, cfg.SecretKey, logger)
	lobbyH := handler.NewLobbyHandler(wsManager, cfg.SecretKey, logger)
	pmH := handler.NewPMHandler(wsManager, authClient, deliveryStrategy, logger)

	// --- Gin router ---
	if cfg.IsProd() {
		gin.SetMode(gin.ReleaseMode)
	}
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.Correlation())

	// Public endpoints.
	r.GET("/health", healthH.Health)
	r.GET("/ready", healthH.Ready)

	// WebSocket endpoints (auth via query param, not middleware).
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	// Authenticated REST endpoints.
	auth := r.Group("/")
	auth.Use(middleware.JWTAuth(cfg.SecretKey))
	{
		auth.GET("/rooms", roomH.ListRooms)
		auth.POST("/rooms", roomH.CreateRoom)
		auth.GET("/rooms/:id/users", roomH.GetRoomUsers)
		auth.PUT("/rooms/:id/active", roomH.SetActive)
		auth.POST("/rooms/:id/admins", roomH.AddAdmin)
		auth.DELETE("/rooms/:id/admins/:userId", roomH.RemoveAdmin)
		auth.POST("/rooms/:id/mutes", roomH.MuteUser)
		auth.DELETE("/rooms/:id/mutes/:userId", roomH.UnmuteUser)
		auth.POST("/pm/send", pmH.SendPM)
	}

	// --- HTTP Server with graceful shutdown ---
	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		logger.Info("server_starting", zap.String("addr", srv.Addr))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("server_failed", zap.Error(err))
		}
	}()

	// Wait for interrupt signal.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Info("shutting_down")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("server_shutdown_error", zap.Error(err))
	}
	logger.Info("server_stopped")
}
