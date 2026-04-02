"""Monitoring tests — Grafana and Prometheus health (auto-skipped if unavailable)."""

import pytest
import requests


def _grafana_available() -> bool:
    """Check if Grafana is reachable on the K8s NodePort."""
    try:
        r = requests.get("http://localhost:30030/api/health", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


skip_no_monitoring = pytest.mark.skipif(
    not _grafana_available(),
    reason="Grafana not reachable at localhost:30030 (monitoring tests require K8s)",
)


@skip_no_monitoring
class TestGrafana:
    """Grafana health and datasource checks."""

    @pytest.mark.monitoring
    def test_grafana_health(self):
        resp = requests.get("http://localhost:30030/api/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("database") == "ok"

    @pytest.mark.monitoring
    def test_grafana_version(self):
        resp = requests.get("http://localhost:30030/api/health", timeout=5)
        data = resp.json()
        assert "version" in data

    @pytest.mark.monitoring
    def test_grafana_has_datasources(self):
        resp = requests.get(
            "http://localhost:30030/api/datasources",
            auth=("admin", "admin"),
            timeout=5,
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


@skip_no_monitoring
class TestPrometheus:
    """Prometheus health via kubectl (requires K8s context)."""

    @pytest.mark.monitoring
    def test_prometheus_healthy(self):
        import subprocess

        try:
            pod = subprocess.check_output(
                ["kubectl", "get", "pod", "-n", "chatbox-monitoring",
                 "-l", "app.kubernetes.io/name=prometheus",
                 "-o", "jsonpath={.items[0].metadata.name}"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            pytest.skip("Cannot find Prometheus pod")

        result = subprocess.check_output(
            ["kubectl", "exec", pod, "-n", "chatbox-monitoring",
             "-c", "prometheus", "--",
             "wget", "-qO-", "http://localhost:9090/-/healthy"],
            timeout=10, stderr=subprocess.DEVNULL,
        ).decode()
        assert "Healthy" in result

    @pytest.mark.monitoring
    def test_prometheus_has_active_targets(self):
        import json
        import subprocess

        try:
            pod = subprocess.check_output(
                ["kubectl", "get", "pod", "-n", "chatbox-monitoring",
                 "-l", "app.kubernetes.io/name=prometheus",
                 "-o", "jsonpath={.items[0].metadata.name}"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            pytest.skip("Cannot find Prometheus pod")

        result = subprocess.check_output(
            ["kubectl", "exec", pod, "-n", "chatbox-monitoring",
             "-c", "prometheus", "--",
             "wget", "-qO-", "http://localhost:9090/api/v1/targets?state=active"],
            timeout=10, stderr=subprocess.DEVNULL,
        ).decode()
        data = json.loads(result)
        targets = data.get("data", {}).get("activeTargets", [])
        up = sum(1 for t in targets if t.get("health") == "up")
        assert up > 0, f"No healthy targets: {len(targets)} total"
