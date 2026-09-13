from pathlib import Path

CHART = Path("deploy/helm/ai-sre-guardian")
TEMPLATES = CHART / "templates"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_service_account_keeps_runtime_token_unmounted() -> None:
    values = read(CHART / "values.yaml")
    deployment = read(TEMPLATES / "deployment.yaml")
    service_account = read(TEMPLATES / "serviceaccount.yaml")

    assert "automountServiceAccountToken: false" in values
    assert "serviceAccountName:" in deployment
    assert "automountServiceAccountToken:" in deployment
    assert "automountServiceAccountToken:" in service_account


def test_role_is_read_only_and_cannot_read_secrets() -> None:
    role = read(TEMPLATES / "role.yaml")

    for verb in ("create", "update", "patch", "delete", "deletecollection"):
        assert f"- {verb}" not in role
    assert "- secrets" not in role
    assert "- pods/log" in role
    assert "- deployments" in role
    assert "- statefulsets" in role


def test_network_policy_limits_expected_ingress_and_egress() -> None:
    values = read(CHART / "values.yaml")
    network_policy = read(TEMPLATES / "networkpolicy.yaml")

    assert "cidr: 192.168.87.71/32" in values
    assert "kubernetes.io/metadata.name: kube-system" in network_policy
    assert "k8s-app: kube-dns" in network_policy
    assert ".Values.networkPolicy.postgresql.cidr" in network_policy
    assert ".Values.networkPolicy.externalHttps.cidr" in network_policy


def test_pdb_preserves_one_available_replica() -> None:
    values = read(CHART / "values.yaml")
    pdb = read(TEMPLATES / "poddisruptionbudget.yaml")

    assert "minAvailable: 1" in values
    assert "apiVersion: policy/v1" in pdb
    assert "kind: PodDisruptionBudget" in pdb
    assert ".Values.podDisruptionBudget.minAvailable" in pdb


def test_rolling_update_allows_no_unavailable_replica() -> None:
    deployment = read(TEMPLATES / "deployment.yaml")

    assert "maxUnavailable: 0" in deployment
    assert "maxSurge: 1" in deployment
    assert "readOnlyRootFilesystem: true" in deployment
    assert "allowPrivilegeEscalation: false" in deployment
    assert "type: RuntimeDefault" in deployment
