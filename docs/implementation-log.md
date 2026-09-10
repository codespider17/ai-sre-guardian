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
