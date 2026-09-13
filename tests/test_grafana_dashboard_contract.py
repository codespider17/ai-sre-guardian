import json
from pathlib import Path

CHART = Path("deploy/helm/ai-sre-guardian")
DASHBOARD = CHART / "dashboards" / "ai-sre-guardian.json"


def dashboard() -> dict[str, object]:
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


def expressions(document: dict[str, object]) -> list[str]:
    panels = document["panels"]
    assert isinstance(panels, list)
    return [
        str(target["expr"]) for panel in panels for target in panel.get("targets", [])
    ]


def test_dashboard_identity_and_refresh_are_stable() -> None:
    document = dashboard()

    assert document["uid"] == "ai-sre-guardian-overview"
    assert document["title"] == "AI-SRE Guardian Overview"
    assert document["refresh"] == "15s"
    assert document["time"] == {"from": "now-1h", "to": "now"}
    assert document["editable"] is False


def test_dashboard_has_eleven_unique_panels() -> None:
    panels = dashboard()["panels"]
    assert isinstance(panels, list)

    identifiers = [panel["id"] for panel in panels]
    assert len(panels) == 11
    assert len(set(identifiers)) == 11
    assert all(panel["datasource"]["uid"] == "${DS_PROMETHEUS}" for panel in panels)


def test_dashboard_queries_only_expected_runtime_metric_families() -> None:
    queries = "\n".join(expressions(dashboard()))

    required_metrics = {
        "up",
        "kube_deployment_status_replicas_available",
        "kube_horizontalpodautoscaler_status_current_replicas",
        "kube_horizontalpodautoscaler_status_desired_replicas",
        "container_cpu_usage_seconds_total",
        "container_memory_working_set_bytes",
        "ai_sre_capacity_requests_total",
        "ai_sre_capacity_request_duration_seconds_bucket",
        "ai_sre_capacity_active_requests",
        "ai_sre_resilience_requests_total",
        "ai_sre_resilience_control_events_total",
        "kube_pod_container_status_restarts_total",
    }
    assert all(metric in queries for metric in required_metrics)
    assert 'namespace="ai-sre-lab"' in queries
    assert 'service="ai-sre-capacity-lab"' in queries


def test_dashboard_has_prometheus_datasource_variable() -> None:
    variables = dashboard()["templating"]["list"]

    assert len(variables) == 1
    assert variables[0]["name"] == "DS_PROMETHEUS"
    assert variables[0]["type"] == "datasource"
    assert variables[0]["query"] == "prometheus"


def test_configmap_uses_verified_grafana_sidecar_contract() -> None:
    values = (CHART / "values.yaml").read_text(encoding="utf-8")
    template = (CHART / "templates" / "grafana-dashboard.yaml").read_text(
        encoding="utf-8"
    )

    assert "sidecarLabel: grafana_dashboard" in values
    assert 'sidecarLabelValue: "1"' in values
    assert ".Values.grafanaDashboard.sidecarLabel" in template
    assert '.Files.Get "dashboards/ai-sre-guardian.json"' in template
