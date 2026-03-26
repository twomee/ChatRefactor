# Kubernetes Guide — Understanding Chatbox on K8s

This guide explains **what** the Kubernetes setup does and **why** each piece exists. If you're looking for commands and step-by-step instructions, see [k8s-operations.md](./k8s-operations.md).

---

## Table of Contents

1. [Overview](#overview)
2. [How It Maps to Docker Compose](#how-it-maps-to-docker-compose)
3. [Prerequisites Explained](#prerequisites-explained)
4. [Architecture Deep Dive](#architecture-deep-dive)
5. [How Kustomize Overlays Work](#how-kustomize-overlays-work)
6. [How the CI/CD Pipeline Works](#how-the-cicd-pipeline-works)
7. [Production Considerations](#production-considerations)
8. [K8s Concepts Glossary](#k8s-concepts-glossary)

---

## Overview

Chatbox is a real-time chat platform built as microservices. The Kubernetes setup lets you run the entire platform inside a K8s cluster — locally on your machine using `kind`, or on any cloud provider (AWS EKS, Google GKE, Azure AKS).

### What Gets Deployed

```
                        +-----------------------+
                        |   chatbox-monitoring   |
                        |  Prometheus + Grafana  |
                        +-----------------------+

+---------------------------------------------------------------+
|                      chatbox (namespace)                       |
|                                                               |
|   Browser ──► Kong Gateway ──┬──► auth-service (Python)       |
|                              ├──► chat-service (Go, WebSocket)|
|                              ├──► message-service (Python)    |
|                              └──► file-service (Node.js)      |
|                                                               |
|   Browser ──► Frontend (React/Nginx)                          |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
|                   chatbox-infra (namespace)                    |
|                                                               |
|   PostgreSQL ◄──── All services (4 databases)                 |
|   Redis      ◄──── auth-service, chat-service                 |
|   Kafka      ◄──── All services (async messaging)             |
+---------------------------------------------------------------+
```

### Services at a Glance

| Service | Language | Port | What It Does |
|---------|----------|------|-------------|
| auth-service | Python (FastAPI) | 8001 | User registration, login, JWT tokens |
| chat-service | Go (Gin) | 8003 | Chat rooms, WebSocket connections |
| message-service | Python (FastAPI) | 8004 | Message history storage |
| file-service | Node.js (Express) | 8005 | File uploads and downloads |
| frontend | React (Nginx) | 80 | Web UI |
| kong | Kong Gateway | 8000 | API routing, rate limiting, security headers |

---

## How It Maps to Docker Compose

If you already understand Docker Compose, this table shows how each concept translates to Kubernetes:

| Docker Compose | Kubernetes | What It Does |
|---------------|------------|-------------|
| `services:` section | **Deployment** | Defines what container to run, how many copies |
| `ports:` mapping | **Service** | Makes a container reachable by other containers or the outside world |
| `volumes:` | **PersistentVolumeClaim (PVC)** | Stores data that survives container restarts |
| `environment:` | **ConfigMap** + **Secret** | Passes configuration to containers |
| `.env` file | **Secret** (for passwords) + **ConfigMap** (for non-sensitive config) | Environment-specific values |
| `depends_on:` | **initContainers** | Waits for dependencies before starting |
| `healthcheck:` | **livenessProbe** + **readinessProbe** | Checks if the container is healthy |
| `docker-compose.yml` | **kustomization.yaml** | Lists all resources to deploy together |
| `docker-compose.dev.yml` (override) | **Kustomize overlay** | Environment-specific overrides |
| container name (`auth-service`) | **Service DNS name** (`auth-service.chatbox`) | How containers find each other |
| `restart: always` | **Deployment** (built-in) | K8s automatically restarts crashed containers |

### Key Difference: Declarative vs Imperative

Docker Compose: "Start these containers in this order."
Kubernetes: "I want 2 copies of auth-service running. Make it happen."

K8s continuously ensures the desired state matches reality. If a container crashes, K8s restarts it. If a node goes down, K8s reschedules pods to healthy nodes.

---

## Prerequisites Explained

### Tools You Need

| Tool | What It Is | Why You Need It |
|------|-----------|----------------|
| **Docker** | Container runtime | Builds container images for your services |
| **kubectl** | K8s command-line tool | Talks to the Kubernetes cluster (like `docker` but for K8s) |
| **kind** | "Kubernetes in Docker" | Runs a full K8s cluster inside Docker containers on your machine |
| **Helm** | Package manager for K8s | Installs complex software (PostgreSQL, Redis, Kafka) with one command |
| **kustomize** | Config management for K8s | Manages environment-specific configuration (built into `kubectl`) |

### Why kind (and not minikube)?

Both create local K8s clusters. `kind` is lighter — it runs the cluster as Docker containers, so it starts faster and uses less resources. Most companies use `kind` for local development and CI pipelines.

### System Requirements

- **RAM:** At least 8GB total (the cluster uses ~4-6GB)
- **Disk:** At least 10GB free (for Docker images and persistent volumes)
- **CPU:** 4+ cores recommended

---

## Architecture Deep Dive

### Namespaces: Why Three?

Namespaces are like folders in a filesystem — they organize resources and control access.

| Namespace | Contains | Why Separate? |
|-----------|----------|--------------|
| `chatbox` | Your app services (auth, chat, message, file, frontend, kong) | This is YOUR code. You deploy here frequently. |
| `chatbox-infra` | PostgreSQL, Redis, Kafka | Infrastructure has a different lifecycle. You don't restart Postgres when you redeploy your app. |
| `chatbox-monitoring` | Prometheus, Grafana | Monitoring is optional and independent. |

**Real-world benefit:** In production, different teams manage different namespaces. The platform team manages `chatbox-infra`, your team manages `chatbox`, and the SRE team manages `chatbox-monitoring`. Each namespace can have its own resource quotas and access policies.

### How Services Find Each Other

In Docker Compose, containers find each other by service name (`auth-service:8001`). In K8s, it works the same way — but with DNS.

Every K8s Service gets a DNS entry:
```
<service-name>.<namespace>.svc.cluster.local
```

**Within the same namespace** (`chatbox`):
```
auth-service:8001          # Short form (works because they're in the same namespace)
auth-service.chatbox:8001  # Explicit namespace
```

**Across namespaces** (app → infra):
```
postgres-postgresql.chatbox-infra.svc.cluster.local:5432
redis-master.chatbox-infra.svc.cluster.local:6379
kafka.chatbox-infra.svc.cluster.local:9092
```

### How Traffic Reaches Your App

```
User's Browser
      │
      ▼
Kong Service (NodePort:30080 on your machine)
      │
      │  Kong reads its declarative config (kong.yml)
      │  and routes requests based on URL path:
      │
      ├── /auth/*    → auth-service:8001
      ├── /rooms/*   → chat-service:8003
      ├── /ws        → chat-service:8003 (WebSocket upgrade)
      ├── /messages/* → message-service:8004
      └── /files/*   → file-service:8005

Frontend Service (NodePort:30000 on your machine)
      │
      └── Serves React SPA (static files via Nginx)
```

**NodePort** means K8s opens a port on the cluster node that maps to the service. In local development with `kind`, these ports are mapped to your `localhost`.

### How Secrets Work

Secrets in K8s are stored in `etcd` (the cluster's database) and are base64-encoded (not encrypted by default — this is important to know).

Our setup uses a **hybrid pattern**:

```
chatbox-infra-secrets (shared):
  ├── POSTGRES_PASSWORD
  ├── REDIS_PASSWORD
  ├── SECRET_KEY (JWT signing)
  └── REDIS_URL (contains password, so it's a secret)

auth-service-secrets (per-service):
  └── DATABASE_URL (contains password for chatbox_auth database)

chat-service-secrets (per-service):
  └── DATABASE_URL (contains password for chatbox_chat database)

message-service-secrets (per-service):
  └── DATABASE_URL (contains password for chatbox_messages database)

file-service-secrets (per-service):
  └── DATABASE_URL (contains password for chatbox_files database)

auth-admin-secret (auth only):
  ├── ADMIN_USERNAME
  └── ADMIN_PASSWORD
```

**Why per-service secrets?** Each service only sees the database URL for its own database. The chat-service can't access the auth database directly. This is the principle of least privilege.

### How Database Migrations Run

In Docker Compose, you might run migrations at container startup. In K8s, we use **init containers** — special containers that run before the main app container starts.

```
Pod startup sequence:
  1. init: wait-for-postgres  (waits until Postgres is reachable)
  2. init: wait-for-redis     (waits until Redis is reachable)
  3. init: wait-for-kafka     (waits until Kafka is reachable)
  4. init: run-migrations     (runs alembic upgrade head / prisma migrate deploy)
  5. main: auth-service       (starts only after all init containers succeed)
```

If any init container fails, K8s retries it. The main container never starts until all init containers succeed.

---

## How Kustomize Overlays Work

Kustomize lets you define a **base** configuration and then apply **patches** for different environments.

### The Base

`k8s/base/` contains the default configuration that works for any environment:
- 1 replica per service
- Low resource limits
- ClusterIP services (internal only)
- Default config values

### Overlays

`k8s/overlays/dev/` applies patches on top of the base:
- Changes Kong and Frontend services to `NodePort` (so you can access them locally)
- Keeps 1 replica (local dev doesn't need scaling)

`k8s/overlays/prod/` applies different patches:
- Increases replicas (2-3 per service)
- Adds `HorizontalPodAutoscaler` for chat-service
- Changes Kong to `LoadBalancer` (cloud load balancer)
- Increases resource limits
- Adds `PodDisruptionBudget` (prevents all pods from being killed at once during updates)

### How It Works Under the Hood

```
kubectl apply -k k8s/overlays/dev
```

This command:
1. Reads `k8s/overlays/dev/kustomization.yaml`
2. Which references `../../base` (the base config)
3. Merges the base with the dev patches
4. Applies the merged result to the cluster

You can see what the final merged YAML looks like:
```
kubectl kustomize k8s/overlays/dev
```

---

## How the CI/CD Pipeline Works

### Image Build Pipeline (`build-k8s-images.yml`)

```
Push to main branch
      │
      ▼
GitHub Actions triggers
      │
      ├── Build auth-service image
      ├── Build chat-service image
      ├── Build message-service image
      ├── Build file-service image
      └── Build frontend image
      │
      ▼
Push images to DockerHub
  docker.io/<user>/chatbox-auth-service:<git-sha>
  docker.io/<user>/chatbox-auth-service:latest
  ...
```

### Deploy Pipeline (`deploy-k8s.yml`)

```
Manual trigger (choose: staging or prod)
      │
      ▼
GitHub Actions:
  1. Configure kubectl with cluster credentials
  2. Update image tags in Kustomize overlay
  3. kubectl apply -k overlays/<environment>
  4. Wait for all deployments to roll out
  5. Run smoke tests (health endpoint checks)
```

### Container Registry

Images are stored on **DockerHub** (the industry default). The registry is configured as a variable — you can swap to AWS ECR, Google GCR, or GitHub GHCR by changing one value in the overlay.

---

## Production Considerations

Things to change when going to production:

### Replace In-Cluster Infra with Managed Services

| Dev (in-cluster) | Production (managed) | Why |
|------------------|---------------------|-----|
| Bitnami PostgreSQL | AWS RDS / GCP Cloud SQL | Automated backups, failover, patching |
| Bitnami Redis | AWS ElastiCache / GCP Memorystore | High availability, monitoring |
| Bitnami Kafka | AWS MSK / Confluent Cloud | Multi-broker, managed upgrades |

To switch: just change the hostnames in ConfigMaps and Secrets. Your app code stays the same.

### Add TLS/HTTPS

- Use `cert-manager` to automatically provision Let's Encrypt certificates
- Terminate TLS at the Ingress controller or Kong
- All internal traffic stays HTTP (standard practice inside the cluster)

### Add Connection Pooling

- Deploy PgBouncer in front of PostgreSQL
- Prevents connection exhaustion when services scale up

### Switch File Storage

- Replace the PVC-based file storage with S3/GCS
- This removes the single-replica limitation on file-service
- Update the file-service code to use the cloud SDK instead of local filesystem

### Add Backups

- PostgreSQL: Use `pg_dump` CronJob or the cloud provider's automated backups
- PVCs: Use Velero for volume snapshots

### Secrets Management

- Replace plain K8s Secrets with Sealed Secrets (encrypted at rest in git)
- Or use External Secrets Operator to sync from AWS Secrets Manager / HashiCorp Vault

### Monitoring

- Add application-level metrics endpoints (`/metrics`) to each service
- Configure Prometheus to scrape them
- Build custom Grafana dashboards for business metrics

---

## K8s Concepts Glossary

| Concept | What It Is | Analogy |
|---------|-----------|---------|
| **Pod** | Smallest deployable unit. Usually one container. | A single running process. |
| **Deployment** | Manages pods — ensures N replicas are running. Handles rolling updates. | `docker-compose` service with `replicas: N`. |
| **Service** | Stable network endpoint for a set of pods. Load balances between replicas. | DNS name + load balancer for a service. |
| **ConfigMap** | Key-value pairs for non-sensitive configuration. | `.env` file (without secrets). |
| **Secret** | Key-value pairs for sensitive data (passwords, tokens). Base64-encoded. | `.env` file (secrets only). |
| **PersistentVolumeClaim (PVC)** | Request for storage. The cluster provisions a disk. | Docker volume. |
| **Job** | Runs a container to completion once. | `docker run --rm` for a one-off task. |
| **Namespace** | Virtual cluster within a cluster. Isolates resources. | Folder / project boundary. |
| **initContainer** | Runs before the main container. Used for setup tasks. | `depends_on` + startup script. |
| **NodePort** | Exposes a service on a specific port on the cluster node. | Port mapping (`-p 30080:8000`). |
| **LoadBalancer** | Exposes a service via cloud provider's load balancer. | AWS ALB / NLB. |
| **ClusterIP** | Internal-only service (default). Only reachable inside the cluster. | Internal Docker network. |
| **HorizontalPodAutoscaler (HPA)** | Automatically scales replicas based on CPU/memory. | Auto-scaling group. |
| **PodDisruptionBudget (PDB)** | Limits how many pods can be down during maintenance. | "Always keep at least 1 running." |
| **Helm** | Package manager for K8s. Installs complex apps from templates. | `apt install` / `brew install` for K8s. |
| **Kustomize** | Overlay system for K8s configs. Base + patches = final config. | Docker Compose override files. |
| **kind** | Runs K8s cluster in Docker containers for local dev. | Docker-in-Docker K8s. |
