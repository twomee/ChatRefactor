# Monitoring — Prometheus & Grafana

## Architecture Overview

```
                    ┌─────────────┐
                    │   Grafana   │ ← Dashboards (7 provisioned)
                    │  :3001 (DC) │
                    │ :30030 (K8s)│
                    └──────┬──────┘
                           │ queries
                    ┌──────▼──────┐
                    │ Prometheus  │ ← Scrapes /metrics every 15s
                    │    :9090    │
                    └──────┬──────┘
                           │ scrapes
        ┌──────────────────┼──────────────────────┐
        │                  │                      │
   ┌────▼────┐       ┌────▼────┐           ┌─────▼─────┐
   │ Services │       │  Kong   │           │   Infra   │
   │ /metrics │       │  :8100  │           │ Exporters │
   └─────────┘       └─────────┘           └───────────┘
   auth    :8001      prometheus             postgres-exporter
   chat    :8003      plugin                 redis-exporter
   message :8004                             kafka-exporter
   file    :8005
```

Every backend service exposes a `/metrics` endpoint in Prometheus text format. Prometheus scrapes these endpoints and stores the time-series data. Grafana reads from Prometheus and renders dashboards.

## Metrics Exposed

### Per-Service (RED Method)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, path/handler, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, path/handler | Request latency (use `histogram_quantile` for percentiles) |
| `http_requests_in_flight` | Gauge | — | Currently active requests |

### Auth Service
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `auth_registrations_total` | Counter | status | User registrations (success/duplicate/error) |
| `auth_logins_total` | Counter | status | Login attempts (success/invalid_credentials/error) |
| `auth_logouts_total` | Counter | status | Logout operations |
| `kafka_events_produced_total` | Counter | topic, status | Kafka events produced |
| `db_pool_size` | Gauge | — | SQLAlchemy connection pool size |
| `db_pool_checked_out` | Gauge | — | Connections currently in use |

### Chat Service
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ws_connections_active` | Gauge | type (room/lobby) | Active WebSocket connections |
| `ws_connections_total` | Counter | type | Total connections established |
| `ws_messages_total` | Counter | type, direction | WebSocket messages processed |
| `ws_active_rooms` | Gauge | — | Rooms with active connections |
| `kafka_produce_total` | Counter | topic, status | Kafka messages produced |
| `db_pool_active_conns` | Gauge | — | pgx pool active connections |
| Go runtime metrics | Various | — | Goroutines, GC, heap (auto-collected) |

### Message Service
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `kafka_messages_consumed_total` | Counter | topic, status | Kafka messages consumed |
| `kafka_consume_duration_seconds` | Histogram | topic | Per-message processing time |
| `messages_persisted_total` | Counter | type (room/private) | Messages written to DB |
| `messages_dlq_total` | Counter | — | Messages sent to Dead Letter Queue |
| `auth_service_calls_total` | Counter | status | HTTP calls to auth service |
| `auth_service_call_duration_seconds` | Histogram | — | Auth service call latency |

### File Service
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `files_uploaded_total` | Counter | status | File uploads |
| `file_upload_size_bytes` | Histogram | — | Upload file sizes |
| `files_downloaded_total` | Counter | status | File downloads |
| `kafka_produce_total` | Counter | topic, status | Kafka events produced |
| Node.js metrics | Various | — | Event loop lag, GC, memory (auto-collected) |

### Kong API Gateway
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `kong_http_requests_total` | Counter | service, route, code | Requests through gateway |
| `kong_request_latency_ms` | Histogram | service | Request latency |
| `kong_bandwidth_bytes` | Counter | service, direction | Bandwidth usage |

## Running in Docker Compose

Monitoring is an optional add-on via a separate compose file. The app works without it.

### Start with monitoring

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up --build -d
```

### Start without monitoring

```bash
docker compose up -d
```

### Access points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| App (Kong) | http://localhost | — |

Service metrics are only accessible from inside the Docker network (Prometheus scrapes them). They are not exposed to the host.

### Verify

```bash
# All 6 targets should show "up"
curl -s http://localhost:9090/api/v1/targets | \
  python3 -c "import sys,json; [print(f'{t[\"scrapeUrl\"]:50s} {t[\"health\"]}') for t in json.load(sys.stdin)['data']['activeTargets']]"

# Generate traffic and check Grafana
curl -X POST http://localhost/auth/register -H 'Content-Type: application/json' -d '{"username":"test","password":"test123"}'
# Open http://localhost:3001 > Dashboards > ChatBox
```

### Stop

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down -v
```

---

## Running in Kubernetes

Monitoring works in all K8s environments (dev, staging, prod). The ServiceMonitors are in the base manifests and are inherited by every overlay via Kustomize.

### Environment overview

| Environment | Overlay | Grafana Access | Notes |
|-------------|---------|----------------|-------|
| **Dev** (Kind) | `infra/k8s/overlays/dev` | NodePort :30030 | Local cluster, short retention (7d) |
| **Staging** | `infra/k8s/overlays/staging` | Port-forward or Ingress | 2 replicas per service, mirrors prod dashboards |
| **Prod** | `infra/k8s/overlays/prod` | LoadBalancer or Ingress | HPA, PDB, higher resources |

### Dev environment (Kind cluster)

This is the most common workflow for local development.

```bash
# 1. Set up the full local cluster (creates kind cluster + infra + deploys services)
make k8s-setup-local

# 2. Install monitoring (Prometheus + Grafana + dashboards + Kafka exporter)
make k8s-monitoring-setup

# 3. Verify everything is running
make k8s-status
kubectl get pods -n chatbox-monitoring

# 4. Access Grafana
#    Kind NodePort — no port-forward needed
open http://localhost:30030    # admin / admin

# 5. Access Prometheus (requires port-forward)
make k8s-prometheus            # http://localhost:9090
```

### Staging environment

```bash
# 1. Deploy services with staging overlay (2 replicas each)
make k8s-deploy OVERLAY=staging

# 2. Install monitoring (same command — works for any cluster)
make k8s-monitoring-setup

# 3. Access Grafana via port-forward (no NodePort in staging)
kubectl port-forward -n chatbox-monitoring svc/monitoring-grafana 3001:80
open http://localhost:3001     # admin / admin
```

### Production environment

```bash
# 1. Deploy services with prod overlay (HPA, PDB, LoadBalancer)
make k8s-deploy OVERLAY=prod

# 2. Install monitoring
make k8s-monitoring-setup

# 3. Access Grafana
#    Option A: Port-forward (temporary)
kubectl port-forward -n chatbox-monitoring svc/monitoring-grafana 3001:80

#    Option B: Expose via Ingress (recommended for prod)
#    Add an Ingress resource for monitoring-grafana in your prod overlay
```

For production, you should also:
- Change `adminPassword` in `infra/k8s/infra/helm-values/monitoring.yaml` to a strong password (or use a K8s Secret)
- Increase Prometheus storage (`storageSpec.resources.requests.storage`) to 50Gi+
- Increase retention from 7d to 30d+
- Enable AlertManager with alert rules for the key metrics listed below

### Verify (any environment)

```bash
# Check ServiceMonitors exist (should show 5: auth, chat, message, file, kong)
kubectl get servicemonitors -n chatbox

# Check Prometheus targets are UP
make k8s-prometheus   # port-forward to :9090
# Open http://localhost:9090/targets — all chatbox targets should show "up"

# Check Grafana dashboards are loaded
# Open Grafana > Dashboards > ChatBox folder — 7 dashboards
```

### What `make k8s-monitoring-setup` does

Single command that:
1. Installs/upgrades kube-prometheus-stack via Helm (Prometheus + Grafana)
2. Applies all 7 Grafana dashboard ConfigMaps
3. Deploys the Kafka exporter for consumer lag monitoring

Infrastructure metrics (Postgres, Redis) are enabled via the Helm values in `infra/k8s/infra/helm-values/postgres.yaml` and `redis.yaml` — they activate when you run `make k8s-infra-setup`.

## Dashboards

| # | Dashboard | What to look for |
|---|-----------|-----------------|
| 1 | **Service Overview** | All services at a glance — request rates, error rates, latency, WebSocket connections |
| 2 | **Auth Service** | Login/register success rates, JWT operations, DB pool usage |
| 3 | **Chat Service** | WebSocket connections, active rooms, message throughput, goroutine count |
| 4 | **Message Service** | Kafka consumer lag (most critical), DLQ rate, processing duration |
| 5 | **File Service** | Upload/download rates, file sizes, Node.js event loop lag |
| 6 | **Infrastructure** | Postgres connections & cache hit ratio, Redis memory, Kafka consumer lag |
| 7 | **Kong Gateway** | Per-route traffic, latency by upstream, rate limiting hits |

### Key metrics to watch

- **Kafka consumer lag** (Message Service): If this grows, messages are being produced faster than consumed. Check DLQ rate and processing duration.
- **Error rate > 1%**: Investigate the specific endpoint causing errors.
- **p99 latency > 1s**: For REST endpoints, this likely indicates a slow query or downstream service.
- **WebSocket connections dropping**: Check chat-service logs and goroutine count.
- **Node.js event loop lag > 100ms**: The file-service is blocking — check for synchronous file I/O.
- **DB pool checked_out near pool_size**: Connection exhaustion risk — increase pool size or optimize queries.
- **Redis evicted keys > 0**: Redis is full — increase memory or review TTLs.

## Querying Prometheus

### Accessing Prometheus UI

```bash
# Docker Compose
open http://localhost:9090

# Kubernetes (requires port-forward)
make k8s-prometheus          # shortcut
# or manually:
kubectl port-forward -n chatbox-monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
open http://localhost:9090
```

Navigate to **http://localhost:9090/graph** to run queries, or use the shortcuts on the Grafana home dashboard:
- **Prometheus: Targets** — shows all scrape targets and their health (no query needed)
- **Prometheus: ChatBox Dashboard** — opens 5 pre-filled panels using recording rules

---

### Recording Rules (chatbox: prefix)

Recording rules pre-compute expensive queries every 30s and store the results as new metrics. In the Prometheus UI, type `chatbox:` and autocomplete shows all available shortcuts.

**Why use them instead of raw queries?** They are faster (pre-computed), shorter to type, and consistent — every dashboard uses the same calculation.

| Recording Rule | What it shows |
|----------------|--------------|
| `chatbox:service_up` | 1 = UP, 0 = DOWN for each service |
| `chatbox:http_request_rate5m` | Requests/sec per service (5m rolling average) |
| `chatbox:http_error_rate5m` | 5xx errors as a fraction of total requests per service |
| `chatbox:http_p99_latency5m` | 99th percentile response time per service |
| `chatbox:http_p95_latency5m` | 95th percentile response time per service |
| `chatbox:ws_connections_active_total` | Total active WebSocket connections |
| `chatbox:ws_active_rooms` | Number of chat rooms with active connections |
| `chatbox:kafka_produce_rate5m` | Kafka messages produced/sec by topic |
| `chatbox:kafka_consume_rate5m` | Kafka messages consumed/sec by topic |
| `chatbox:messages_persisted_rate5m` | Messages written to DB/sec by type (room/private) |
| `chatbox:kafka_dlq_rate5m` | Dead Letter Queue rate — **should always be ~0** |
| `chatbox:auth_login_rate5m` | Login attempts/sec by status (success/failure) |
| `chatbox:auth_registration_rate5m` | Registration attempts/sec by status |
| `chatbox:db_pool_utilization` | DB connections in use ÷ pool size (0–1 scale) |

**Example queries using recording rules:**

```promql
# Are all services up?
chatbox:service_up

# Which service has the highest request rate?
topk(3, chatbox:http_request_rate5m)

# Is any service returning errors?
chatbox:http_error_rate5m > 0

# Which service is slowest (p99)?
sort_desc(chatbox:http_p99_latency5m)

# Is the DLQ receiving messages? (alert if > 0)
chatbox:kafka_dlq_rate5m > 0

# DB pool nearly exhausted? (alert if > 0.8)
chatbox:db_pool_utilization > 0.8
```

---

### General PromQL Queries

These use the raw metrics directly. Useful for debugging or building new dashboards.

#### Service Health

```promql
# All services UP/DOWN
up{namespace="chatbox"}

# Only show services that are DOWN
up{namespace="chatbox"} == 0
```

#### HTTP Traffic (RED Method)

```promql
# Request rate per service over 5 minutes
sum(rate(http_requests_total{namespace="chatbox"}[5m])) by (job)

# Request rate broken down by endpoint
sum(rate(http_requests_total{job="auth-service"}[5m])) by (handler, method)

# Error rate per service (5xx only)
sum(rate(http_requests_total{namespace="chatbox", status=~"5.."}[5m])) by (job)

# Error percentage per service
100 * sum(rate(http_requests_total{namespace="chatbox", status=~"5.."}[5m])) by (job)
    / sum(rate(http_requests_total{namespace="chatbox"}[5m])) by (job)

# p50 / p95 / p99 latency per service
histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{namespace="chatbox"}[5m])) by (job, le))
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{namespace="chatbox"}[5m])) by (job, le))
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{namespace="chatbox"}[5m])) by (job, le))

# Slowest endpoints in auth-service
topk(5, sum(rate(http_request_duration_seconds_sum{job="auth-service"}[5m])) by (handler)
       / sum(rate(http_request_duration_seconds_count{job="auth-service"}[5m])) by (handler))

# Currently active (in-flight) requests
sum(http_requests_in_flight{namespace="chatbox"}) by (job)
```

#### WebSocket (Chat Service)

```promql
# Active connections by type (room / lobby)
ws_connections_active{namespace="chatbox"}

# Total connections over time
rate(ws_connections_total{namespace="chatbox"}[5m])

# Active rooms
ws_active_rooms{namespace="chatbox"}

# WebSocket message throughput
rate(ws_messages_total{namespace="chatbox"}[5m])
```

#### Kafka

```promql
# Produce rate by topic (chat-service and file-service)
sum(rate(kafka_produce_total{namespace="chatbox"}[5m])) by (job, topic)

# Consume rate by topic (message-service)
rate(kafka_messages_consumed_total{namespace="chatbox"}[5m])

# Message processing duration p99 (message-service)
histogram_quantile(0.99, rate(kafka_consume_duration_seconds_bucket{namespace="chatbox"}[5m]))

# DLQ events — should be 0 at all times
increase(messages_dlq_total{namespace="chatbox"}[1h])

# Messages persisted per minute
rate(messages_persisted_total{namespace="chatbox"}[5m]) * 60
```

#### Auth Service

```promql
# Login success vs failure rate
sum(rate(auth_logins_total{namespace="chatbox"}[5m])) by (status)

# Registration duplicates (user already exists)
rate(auth_registrations_total{namespace="chatbox", status="duplicate"}[5m])

# Kafka events produced by auth-service
rate(kafka_events_produced_total{namespace="chatbox"}[5m])
```

#### File Service

```promql
# Upload rate by status
sum(rate(files_uploaded_total{namespace="chatbox"}[5m])) by (status)

# Upload size distribution (median)
histogram_quantile(0.50, rate(file_upload_size_bytes_bucket{namespace="chatbox"}[5m]))

# Download rate
rate(files_downloaded_total{namespace="chatbox"}[5m])
```

#### Database Connection Pools

```promql
# Pool utilization per service (0 = empty, 1 = exhausted)
db_pool_checked_out{namespace="chatbox"} / db_pool_size{namespace="chatbox"}

# Auth-service pool: checked out vs total
db_pool_checked_out{job="auth-service"}
db_pool_size{job="auth-service"}

# Chat-service pgx pool
db_pool_active_conns{job="chat-service"}
```

#### Kong API Gateway

```promql
# Total request rate through Kong
sum(rate(kong_http_requests_total[5m])) by (service)

# Kong p99 latency by upstream service
histogram_quantile(0.99, rate(kong_request_latency_ms_bucket[5m]))

# Bandwidth in/out
sum(rate(kong_bandwidth_bytes[5m])) by (service, direction)
```

#### Go Runtime (Chat Service)

```promql
# Goroutine count — high count can indicate leaks
go_goroutines{job="chat-service"}

# GC pause duration
rate(go_gc_duration_seconds_sum{job="chat-service"}[5m])

# Heap memory in use
go_memstats_heap_inuse_bytes{job="chat-service"}
```

#### Node.js Runtime (File Service)

```promql
# Event loop lag — above 100ms means the loop is blocked
nodejs_eventloop_lag_seconds{job="file-service"}

# Active handles (open connections, timers, etc.)
nodejs_active_handles{job="file-service"}

# Heap used vs total
nodejs_heap_size_used_bytes{job="file-service"}
nodejs_heap_size_total_bytes{job="file-service"}
```

---

### PromQL Cheat Sheet

| Pattern | Example |
|---------|---------|
| Rate of a counter over 5m | `rate(metric_total[5m])` |
| Sum across all instances | `sum(metric) by (label)` |
| Percentile from histogram | `histogram_quantile(0.99, rate(metric_bucket[5m]))` |
| Top N by value | `topk(5, metric)` |
| Filter by label | `metric{job="auth-service", status="200"}` |
| Regex label match | `metric{status=~"5.."}` |
| Alert threshold | `metric > 0.05` |
| Growth over 1 hour | `increase(metric_total[1h])` |
| Ratio (e.g. error %) | `sum(errors) / sum(total)` |

**Time ranges:** `[5m]` = last 5 minutes, `[1h]` = last hour, `[24h]` = last day.
Use shorter ranges (5m) for real-time rate calculations, longer (1h+) for trend analysis.

---

## Adding Metrics to a New Service

1. **Install the Prometheus client** for your language:
   - Python/FastAPI: `prometheus-fastapi-instrumentator`
   - Go/Gin: `github.com/prometheus/client_golang` + `promhttp.Handler()`
   - Node/Express: `prom-client` + `collectDefaultMetrics()`

2. **Expose `/metrics` endpoint** on the service port (same port as the app).

3. **Add custom business metrics** using Counter, Histogram, and Gauge types.

4. **Create a ServiceMonitor** (K8s):
   ```yaml
   apiVersion: monitoring.coreos.com/v1
   kind: ServiceMonitor
   metadata:
     name: my-service
     namespace: chatbox
     labels:
       app.kubernetes.io/name: my-service
       app.kubernetes.io/part-of: chatbox
   spec:
     selector:
       matchLabels:
         app.kubernetes.io/name: my-service
     endpoints:
       - port: http
         path: /metrics
         interval: 15s
   ```

5. **Add to Prometheus scrape config** (Docker Compose):
   ```yaml
   - job_name: my-service
     static_configs:
       - targets: ["my-service:PORT"]
     metrics_path: /metrics
   ```

6. **Create a Grafana dashboard** JSON and add it to both:
   - `infra/monitoring/grafana/dashboards/` (Docker Compose)
   - `infra/k8s/monitoring/dashboards/` as a ConfigMap (K8s)

## Troubleshooting

### Targets not showing up in Prometheus

**Docker Compose:**
- Check the service is running: `docker compose ps`
- Verify the metrics endpoint: `curl http://SERVICE:PORT/metrics`
- Check Prometheus config: `curl http://localhost:9090/api/v1/status/config`

**Kubernetes:**
- Check ServiceMonitor exists: `kubectl get servicemonitors -n chatbox`
- Check Prometheus is watching the namespace: verify `serviceMonitorNamespaceSelector` in Helm values
- Check the namespace has the correct label: `kubectl get ns chatbox --show-labels`
- Check Prometheus operator logs: `kubectl logs -n chatbox-monitoring -l app.kubernetes.io/name=prometheus-operator`

### Dashboards show "No data"

1. Check the time range in Grafana (top-right) — set to "Last 1 hour"
2. Check the datasource is configured: Settings > Data sources > Prometheus
3. Try a raw query in Prometheus UI: `up` should return results
4. Generate traffic to produce metrics: `curl http://localhost/auth/login ...`
5. Verify Prometheus is scraping: check the Targets page for errors

### High cardinality warnings

If Prometheus warns about high cardinality, check for:
- Dynamic URL paths used as labels (should use route patterns instead)
- Per-user labels (avoid — use counters without user_id labels)
- High number of unique label combinations
