# AI-SRE Guardian

AI-Native SRE服务可靠性与变更风险治理平台。

平台将Git变更、Kubernetes运行状态、Prometheus指标、历史Runbook和受控AI分析组织为可审计的SRE工作流，用于变更风险识别、SLA/SLO影响计算、容量基线和高可用策略验证。

## 当前已实现

- 独立Python 3.14工程、依赖锁和FastAPI基础接口。
- 独立PostgreSQL 17运行环境和本机Secret边界。
- Service、ChangeEvent、AnalysisRun、EvidenceItem和AuditEvent五类核心模型。
- Alembic数据库迁移、约束、索引和外键。
- 数据库迁移、Kubernetes基础设施、CI/CD流水线、依赖或镜像、安全边界和大规模变更六类确定性风险规则。
- 0至100分风险计分和low、medium、high、critical四级风险分级。
- Bearer Token保护的变更评估API，以及Change、Analysis、Evidence和Audit完整持久化链。
- 基于唯一Delivery ID的幂等处理，重复投递复用原分析结果。
- Ruff静态检查及pytest规则与数据库集成测试。

## 当前接口

- `GET /health`
- `GET /ready`
- `POST /api/v1/changes/evaluate`
- `GET /docs`
- `GET /openapi.json`

## 本地开发

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
docker compose \
  --env-file .env \
  -f deploy/postgresql/compose.yaml \
  up -d
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

项目仍在持续实施中。只有完成自动化测试和真实环境验收的能力才会记录为已实现。
