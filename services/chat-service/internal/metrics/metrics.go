package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// HTTP RED metrics
var (
	HTTPRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "http_requests_total",
			Help: "Total HTTP requests",
		},
		[]string{"method", "path", "status"},
	)
	HTTPRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "http_request_duration_seconds",
			Help:    "HTTP request duration in seconds",
			Buckets: []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10},
		},
		[]string{"method", "path"},
	)
	HTTPRequestsInFlight = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "http_requests_in_flight",
			Help: "Current number of HTTP requests being served",
		},
	)
)

// WebSocket metrics
var (
	WSConnectionsActive = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "ws_connections_active",
			Help: "Active WebSocket connections",
		},
		[]string{"type"},
	)
	WSConnectionsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ws_connections_total",
			Help: "Total WebSocket connections established",
		},
		[]string{"type"},
	)
	WSMessagesTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ws_messages_total",
			Help: "Total WebSocket messages processed",
		},
		[]string{"type", "direction"},
	)
	WSActiveRooms = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "ws_active_rooms",
			Help: "Number of rooms with active connections",
		},
	)
)

// Kafka metrics
var (
	KafkaProduceTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kafka_produce_total",
			Help: "Total Kafka messages produced",
		},
		[]string{"topic", "status"},
	)
	KafkaConsumeTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kafka_consume_total",
			Help: "Total Kafka messages consumed",
		},
		[]string{"topic", "status"},
	)
)

// Database connection pool metrics
var (
	DBPoolActiveConns = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "db_pool_active_conns",
			Help: "Active DB connections",
		},
	)
	DBPoolIdleConns = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "db_pool_idle_conns",
			Help: "Idle DB connections",
		},
	)
	DBPoolTotalConns = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "db_pool_total_conns",
			Help: "Total DB connections",
		},
	)
)

// Business metrics
var (
	RoomsCreatedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "rooms_created_total",
			Help: "Total rooms created",
		},
	)
	PMsSentTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "pms_sent_total",
			Help: "Total private messages sent",
		},
	)
)
