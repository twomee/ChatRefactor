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

### Start monitoring alongside the app

```bash
# Start everything (app + monitoring)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up --build -d

# Wait for all services to be healthy
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml ps
```

### Access points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Auth metrics | http://localhost:8001/metrics | — |
| Chat metrics | http://localhost:8003/metrics | — |
| Message metrics | http://localhost:8004/metrics | — |
| File metrics | http://localhost:8005/metrics | — |
| Kong metrics | http://localhost:8100/metrics | — |

### Verify it works

```bash
# Check that services expose metrics
curl -s http://localhost:8001/metrics | head -5
curl -s http://localhost:8003/metrics | head -5

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -A2 '"health"'

# Generate some traffic
curl -X POST http://localhost/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"monitor-test","password":"testpass123"}'

curl -X POST http://localhost/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"monitor-test","password":"testpass123"}'
```

Then open Grafana at http://localhost:3001, navigate to **Dashboards > ChatBox**, and open the Service Overview dashboard.

### Stop monitoring

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down -v
```

To run the app without monitoring: `docker compose up -d` (uses only docker-compose.yml).

## Running in Kubernetes

### Prerequisites
- Kind cluster running (`make k8s-setup-local`)
- kube-prometheus-stack installed (`make k8s-monitoring-setup`)

### Deploy monitoring components

```bash
# 1. Upgrade kube-prometheus-stack with updated Helm values
#    (enables cross-namespace ServiceMonitor discovery)
make k8s-monitoring-setup

# 2. Apply Grafana dashboard ConfigMaps
kubectl apply -f infra/k8s/monitoring/dashboards/ -n chatbox-monitoring

# 3. Deploy Kafka exporter
kubectl apply -f infra/k8s/infra/kafka-exporter.yaml

# 4. Upgrade Postgres and Redis with metrics enabled
#    (re-run helm upgrade with updated values files)
helm upgrade postgres oci://registry-1.docker.io/bitnamicharts/postgresql \
  -n chatbox-infra -f infra/k8s/infra/helm-values/postgres.yaml \
  --set auth.postgresPassword=<your-password>

helm upgrade redis oci://registry-1.docker.io/bitnamicharts/redis \
  -n chatbox-infra -f infra/k8s/infra/helm-values/redis.yaml \
  --set auth.password=<your-password>
```

### Verify

```bash
# Check ServiceMonitors are created
kubectl get servicemonitors -n chatbox
kubectl get servicemonitors -n chatbox-infra

# Check Prometheus targets (port-forward first)
kubectl port-forward -n chatbox-monitoring \
  svc/monitoring-kube-prometheus-prometheus 9090:9090 &

# Open http://localhost:9090/targets
# All chatbox service targets should show "UP"

# Access Grafana
# Kind: http://localhost:30030 (NodePort)
# Or port-forward: kubectl port-forward -n chatbox-monitoring svc/monitoring-grafana 3001:80
```

### Access points (Kind cluster)

| Service | URL |
|---------|-----|
| Grafana | http://localhost:30030 |
| Prometheus | Port-forward :9090 |

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
