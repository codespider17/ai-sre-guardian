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

## M3：可审计的只读SRE Agent

- 使用8状态、12条合法转换边构建严格Agent状态机，正常分析路径包含6次状态转换，并保护完成、失败等终态。
- 提供Kubernetes工作负载、事件、日志、Prometheus查询、变更风险和分析证据6个只读工具，仅允许访问2个项目Namespace，变更工具数量为0。
- 工具执行固定使用参数数组且关闭命令Shell，事件最多返回100条、日志最多返回200行、文本输出最多保留65536字符。
- 完成真实数据库编排闭环：单次Agent运行调用6个工具、保存6条Evidence和7条Audit，输出`manual_review_required`人工复核建议。
- M3专项与全量回归最终达到61项测试通过，数据库迁移无漂移。

## M4：证据约束AI分析

- 使用PostgreSQL维护6类知识文档和可追溯知识片段。
- 支持确定性关键词检索、结果评分、来源和版本追踪。
- 接入DeepSeek OpenAI兼容Chat Completions接口。
- 使用Pydantic验证结构化JSON，限制风险等级、建议和Evidence引用。
- Provider异常、无效JSON或不可信Evidence引用自动降级到确定性规则。
- Agent能够持久化AI分析Evidence，并记录完整Audit审计事件。
- DeepSeek API Key仅保存在Git忽略且权限为600的本机环境文件中。
