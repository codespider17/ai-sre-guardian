# AI-SRE Guardian实施记录

## M0：环境与项目边界

- Ubuntu 26.04 LTS，8 CPU、10428 MiB可用内存、70 GiB可用磁盘。
- K3s节点Ready，Jenkins与现有PostgreSQL healthy。
- DevFlow和监控栈为deployed，Harbor HTTPS API返回Pong。
- 新项目目录、两个Namespace均不存在，8010端口空闲。
- DeepSeek未认证请求返回HTTP 401，外部HTTPS链路可达。

## M1-A1：工程与运行基础

- 创建独立Git工程、Python 3.14虚拟环境和依赖锁。
- PostgreSQL 17-alpine独立容器状态healthy，仅监听127.0.0.1:55433。
- FastAPI health返回ok，ready返回ready且数据库状态为ok。
- 2项自动化测试通过。

## M1-A2：核心数据模型

- 创建Service、ChangeEvent、AnalysisRun、EvidenceItem和AuditEvent五类模型。
- Alembic迁移f36107004bda已应用，数据库与模型无差异。
- PostgreSQL公共表6张，其中核心业务表5张。
- 专项测试2项、全量测试4项通过。

## M2-A1：确定性变更风险规则

- 实现数据库迁移、Kubernetes基础设施、CI/CD流水线、依赖或镜像、安全边界和大规模变更六类规则。
- 风险分数封顶100，支持low、medium、high和critical四级分级。
- 严格样例命中全部6类规则，得到100分critical结果并输出逐条证据。
- 规则专项测试10项、全量测试14项通过。

## M2-A2：变更评估API与审计闭环

- 新增受Bearer Token保护的`POST /api/v1/changes/evaluate`接口。
- 真实请求生成Change Event、completed Analysis Run、6条Evidence和1条Audit。
- 相同Delivery ID重复投递返回duplicate并复用原Analysis Run。
- 真实验收风险分数100、等级critical、Finding数量6。
- API数据库集成测试4项、全量测试18项通过，Alembic无模型漂移。
