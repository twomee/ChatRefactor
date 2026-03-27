# ===========================================================================
# Kubernetes Targets
# ===========================================================================

OVERLAY ?= dev
SVC ?=
CLUSTER_NAME ?= chatbox

# --- Cluster Lifecycle ---

.PHONY: k8s-setup-local
k8s-setup-local: ## Full local K8s setup: kind cluster + infra + init + build + deploy
	@bash infra/k8s/scripts/setup-local.sh

.PHONY: k8s-teardown
k8s-teardown: ## Full teardown: remove everything, delete kind cluster
	@bash infra/k8s/scripts/teardown.sh

# --- Infrastructure ---

.PHONY: k8s-infra-setup
k8s-infra-setup: ## Install Postgres, Redis, Kafka via Helm
	@test -f infra/k8s/secrets.env || { echo "Error: infra/k8s/secrets.env not found. Run 'make k8s-secrets' first."; exit 1; }
	@POSTGRES_PASSWORD=$$(grep '^POSTGRES_PASSWORD=' infra/k8s/secrets.env | cut -d= -f2-); \
	REDIS_PASSWORD=$$(grep '^REDIS_PASSWORD=' infra/k8s/secrets.env | cut -d= -f2-); \
	echo "Installing infrastructure..."; \
	helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true; \
	helm repo update; \
	helm upgrade --install postgres bitnami/postgresql --namespace chatbox-infra --values infra/k8s/infra/helm-values/postgres.yaml --version 18.5.14 --set auth.postgresPassword="$$POSTGRES_PASSWORD" --set auth.password="$$POSTGRES_PASSWORD" --wait --timeout 180s; \
	helm upgrade --install redis bitnami/redis --namespace chatbox-infra --values infra/k8s/infra/helm-values/redis.yaml --version 25.3.9 --set auth.password="$$REDIS_PASSWORD" --wait --timeout 120s; \
	kubectl apply -f infra/k8s/infra/kafka.yaml; kubectl rollout status deployment/kafka --namespace chatbox-infra --timeout=120s

.PHONY: k8s-infra-teardown
k8s-infra-teardown: ## Remove Helm infra releases only
	@kubectl delete -f infra/k8s/infra/kafka.yaml --ignore-not-found 2>/dev/null || true
	@helm uninstall redis --namespace chatbox-infra 2>/dev/null || true
	@helm uninstall postgres --namespace chatbox-infra 2>/dev/null || true
	@helm uninstall monitoring --namespace chatbox-monitoring 2>/dev/null || true

.PHONY: k8s-init-jobs
k8s-init-jobs: ## Run db-init and kafka-init jobs (runs k8s-secrets first)
	@kubectl get secret chatbox-infra-secrets -n chatbox >/dev/null 2>&1 || $(MAKE) k8s-secrets
	@kubectl delete job db-init kafka-init --namespace chatbox --ignore-not-found
	@kubectl apply -f infra/k8s/jobs/
	@kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
	@kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s

# --- Application ---

.PHONY: k8s-build
k8s-build: ## Build all Docker images and load into kind
	@bash infra/k8s/scripts/build-images.sh

.PHONY: k8s-deploy
k8s-deploy: ## Deploy/update app services (default: dev overlay)
	@bash infra/k8s/scripts/deploy.sh $(OVERLAY)

.PHONY: k8s-redeploy
k8s-redeploy: ## Rebuild + reload + restart one service (usage: make k8s-redeploy SVC=auth-service)
	@if [ -z "$(SVC)" ]; then echo "Error: SVC is required. Usage: make k8s-redeploy SVC=auth-service"; exit 1; fi
	@echo "Rebuilding $(SVC)..."
	@if [ "$(SVC)" = "frontend" ]; then 		docker build -t $(SVC):latest --build-arg VITE_API_BASE=http://localhost:30080 --build-arg VITE_WS_BASE=ws://localhost:30080 frontend/; 	else 		docker build -t $(SVC):latest services/$(SVC)/; 	fi
	@kind load docker-image $(SVC):latest --name $(CLUSTER_NAME)
	@kubectl rollout restart deployment/$(SVC) --namespace chatbox
	@kubectl rollout status deployment/$(SVC) --namespace chatbox --timeout=120s

.PHONY: k8s-validate
k8s-validate: ## Dry-run kustomize and validate YAML
	@echo "Validating $(OVERLAY) overlay..."
	@kubectl kustomize infra/k8s/overlays/$(OVERLAY) | kubectl apply --dry-run=client -f -
	@echo "Validation passed!"

# --- Operations ---

.PHONY: k8s-status
k8s-status: ## Show pods, services, endpoints, recent events
	@echo "=== Pods ==="
	@kubectl get pods -n chatbox -o wide
	@echo ""
	@echo "=== Services ==="
	@kubectl get svc -n chatbox
	@echo ""
	@echo "=== Infrastructure ==="
	@kubectl get pods -n chatbox-infra
	@echo ""
	@echo "=== Recent Events ==="
	@kubectl get events -n chatbox --sort-by='.lastTimestamp' 2>/dev/null | tail -10

.PHONY: k8s-logs
k8s-logs: ## Tail logs for a service (usage: make k8s-logs SVC=auth-service)
	@if [ -z "$(SVC)" ]; then echo "Error: SVC required. Usage: make k8s-logs SVC=auth-service"; exit 1; fi
	@kubectl logs -f -l app.kubernetes.io/name=$(SVC) --namespace chatbox --all-containers --tail=100 --max-log-requests=10

.PHONY: k8s-shell
k8s-shell: ## Exec into a pod (usage: make k8s-shell SVC=auth-service)
	@if [ -z "$(SVC)" ]; then echo "Error: SVC required. Usage: make k8s-shell SVC=auth-service"; exit 1; fi
	@kubectl exec -it deployment/$(SVC) --namespace chatbox -- /bin/sh

.PHONY: k8s-restart
k8s-restart: ## Rolling restart a service (usage: make k8s-restart SVC=auth-service)
	@if [ -z "$(SVC)" ]; then echo "Error: SVC required. Usage: make k8s-restart SVC=auth-service"; exit 1; fi
	@kubectl rollout restart deployment/$(SVC) --namespace chatbox
	@kubectl rollout status deployment/$(SVC) --namespace chatbox --timeout=120s

.PHONY: k8s-port-forward
k8s-port-forward: ## Port-forward Kong and Frontend (background)
	@echo "Port-forwarding Kong (30080) and Frontend (30000)..."
	@echo "Note: With kind + NodePort, ports are already accessible."
	@echo "  Frontend: http://localhost:30000"
	@echo "  API:      http://localhost:30080"

# --- Monitoring ---

.PHONY: k8s-monitoring-setup
k8s-monitoring-setup: ## Install full monitoring stack: Prometheus, Grafana, dashboards, exporters
	@echo "Installing monitoring stack..."
	@helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
	@helm repo update
	@kubectl apply -f infra/k8s/infra/namespace.yaml
	@helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
		--namespace chatbox-monitoring \
		--values infra/k8s/infra/helm-values/monitoring.yaml \
		--version 82.14.1 \
		--wait --timeout 300s
	@echo "Applying Grafana dashboards..."
	@kubectl apply -f infra/k8s/monitoring/dashboards/ -n chatbox-monitoring
	@echo "Deploying Kafka exporter..."
	@kubectl apply -f infra/k8s/infra/kafka-exporter.yaml
	@echo ""
	@echo "Monitoring stack ready!"
	@echo "  Grafana:    http://localhost:30030 (admin/admin)"
	@echo "  Prometheus: make k8s-prometheus"
	@echo "  Dashboards: 7 provisioned in ChatBox folder"

.PHONY: k8s-grafana
k8s-grafana: ## Print Grafana URL
	@echo "Grafana: http://localhost:30030"
	@echo "Username: admin"
	@echo "Password: admin"

.PHONY: k8s-prometheus
k8s-prometheus: ## Port-forward Prometheus to http://localhost:9090
	@echo "Prometheus: http://localhost:9090"
	@echo "Press Ctrl+C to stop."
	@kubectl port-forward -n chatbox-monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090

# --- Config ---

.PHONY: k8s-secrets
k8s-secrets: ## Generate K8s secrets from .env file
	@bash infra/k8s/scripts/generate-secrets.sh
