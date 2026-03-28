// Package main is the entry point for the chat-service.
// It loads config, connects to infrastructure (DB, Redis, Kafka),
// registers Gin routes, and starts the HTTP server.
//
// Database migrations are handled by the init container (see
// docker-compose and the migrate job), not at application startup.
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
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/config"
	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/handler"
	"github.com/twomee/chatbox/chat-service/internal/kafka"
	"github.com/twomee/chatbox/chat-service/internal/metrics"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

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

		// Periodically collect DB pool stats for Prometheus.
		go func() {
			ticker := time.NewTicker(15 * time.Second)
			defer ticker.Stop()
			for {
				select {
				case <-ctx.Done():
					return
				case <-ticker.C:
					stat := dbPool.Stat()
					metrics.DBPoolActiveConns.Set(float64(stat.AcquiredConns()))
					metrics.DBPoolIdleConns.Set(float64(stat.IdleConns()))
					metrics.DBPoolTotalConns.Set(float64(stat.TotalConns()))
				}
			}
		}()
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

	// --- Kafka consumers ---
	// file.events consumer: broadcasts file_shared notifications to lobby.
	var fileEventsConsumer *kafka.Consumer
	if len(brokers) > 0 && brokers[0] != "" {
		fileEventsConsumer = kafka.NewConsumer(brokers, "file.events", "chat-file-events",
			func(_ context.Context, value map[string]interface{}) error {
				// Broadcast file_shared to the room only.
				// (Lobby is not notified to avoid duplicates — room users
				// are connected to both lobby and room WebSockets.)
				msg := map[string]interface{}{
					"type":      "file_shared",
					"file_id":   value["file_id"],
					"filename":  value["filename"],
					"size":      value["size"],
					"from":      value["from"],
					"room_id":   value["room_id"],
					"timestamp": value["timestamp"],
				}
				if roomID, ok := value["room_id"].(float64); ok {
					wsManager.BroadcastRoom(int(roomID), msg)
				}
				return nil
			}, logger)
		fileEventsConsumer.Start(ctx)
		logger.Info("file_events_consumer_started")
	}

	// --- Handlers ---
	healthH := handler.NewHealthHandler(dbPool, rdb, kafkaProducer, brokers)
	roomH := handler.NewRoomHandler(roomStore, wsManager, authClient, logger)
	wsH := handler.NewWSHandler(wsManager, roomStore, deliveryStrategy, authClient, cfg.SecretKey, cfg.MessageServiceURL, logger)
	lobbyH := handler.NewLobbyHandler(wsManager, cfg.SecretKey, logger)
	pmH := handler.NewPMHandler(wsManager, authClient, deliveryStrategy, logger)
	adminH := handler.NewAdminHandler(roomStore, wsManager, authClient, logger)

	// --- Gin router ---
	if cfg.IsProd() {
		gin.SetMode(gin.ReleaseMode)
	}
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.Correlation())
	r.Use(middleware.PrometheusMetrics())

	// Public endpoints.
	r.GET("/health", healthH.Health)
	r.GET("/ready", healthH.Ready)
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

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

		// Admin dashboard endpoints (global admin only — verified per-handler).
		auth.GET("/admin/users", adminH.ListOnlineUsers)
		auth.GET("/admin/rooms", adminH.ListAllRooms)
		auth.POST("/admin/chat/close", adminH.CloseAllRooms)
		auth.POST("/admin/chat/open", adminH.OpenAllRooms)
		auth.POST("/admin/rooms/:id/close", adminH.CloseRoom)
		auth.POST("/admin/rooms/:id/open", adminH.OpenRoom)
		auth.DELETE("/admin/db", adminH.ResetDatabase)
		auth.POST("/admin/promote", adminH.PromoteUserInAllRooms)
	}

	// --- HTTP Server with graceful shutdown ---
	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
		// Note: WriteTimeout applies to REST endpoints only. WebSocket
		// connections are exempt because gorilla/websocket calls Hijack(),
		// which removes the connection from http.Server timeout management.
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

	// Cancel context first so consumer goroutines detect clean shutdown,
	// then stop consumers to close their readers and wait for completion.
	cancel()
	if fileEventsConsumer != nil {
		fileEventsConsumer.Stop()
	}

	// Gracefully close all WebSocket connections with code 1001 (GoingAway).
	wsManager.CloseAll()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("server_shutdown_error", zap.Error(err))
	}
	logger.Info("server_stopped")
}
