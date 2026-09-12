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

## M3：Agent状态机、只读工具与审计闭环

- 验证8个Agent状态、12条合法状态转换边和6步正常执行路径，并覆盖非法转换、终态保护、失败与快照恢复。
- 建立6个只读工具、2个Namespace白名单、4个Prometheus固定查询模板；未开放任意Shell或资源变更能力。
- 统一执行器使用固定参数数组和`subprocess.run(..., shell=False)`，并限制事件、日志和文本输出大小。
- 真实数据库Agent Run `d7e245d4-df45-4def-9c4c-0555aabe47a2`达到`completed`，关联分析`56f3e3d0-b983-4881-b7ba-a46b48099774`。
- 单次真实编排完成6个只读工具调用、6条Evidence、7条Audit和6次状态转换，最终建议为`manual_review_required`。
- M3最终专项测试7项、全量测试61项通过；依赖检查和Alembic模型漂移检查通过。

## M4：知识检索与证据约束AI分析

- 数据库迁移：a99cdb193239。
- 建立2张知识库表，写入6类知识、6份文档和6个知识片段。
- 确定性检索样例Top-1得分56，命中Kubernetes发布恢复Runbook。
- DeepSeek真实调用第1次成功，输入7条Evidence并返回7条可信引用。
- 首次结果为critical/block，置信度0.95，共6条推理要点。
- Agent集成运行状态completed，真实建议manual_review_required，置信度0.95。
- Agent关联2条Evidence，其中1条为AI结果，并生成3条审计事件。
- DeepSeek异常自动进入rules_fallback，Agent不具备危险变更工具。
- 专项测试8项、全量测试80项通过，Alembic无模型漂移。

## M5：SLO、错误预算与SLA影响计算

- 数据库迁移：21b054f993dd。
- 建立slo_policies和slo_evaluation_records两张可靠性数据表。
- 四类SLI为可用性99.87%、错误率0.13%、延迟达标率99.2%、饱和度达标率95.0%。
- 可用性SLO目标99.9%，错误预算消耗130%，燃烧率1.3，SLA影响16.8分钟。
- 延迟SLO目标99.0%，实际99.2%，错误预算消耗80%，燃烧率0.8，未违反SLO。
- 真实HTTP Policy为f29a63eb-0def-4e5c-8ccd-42dd78ff3da3。
- Evaluation为6b66b668-05ea-4ce0-9313-706e2ec0e113，重复请求复用同一记录。
- Bearer鉴权、404边界、409冲突、数据库唯一约束和OpenAPI路径均已验证。
- 可靠性API专项测试5项，全量自动化测试98项通过，Alembic无模型漂移。

## 2026-09-12 M6 DevFlow发布治理闭环

- 新增DevFlow发布观察契约，真实持久化1条发布观察和1条审计事件，
  重复Delivery保持幂等。
- 新增3类发布建议：健康发布为`proceed`，SLO违反为
  `manual_review`，critical变更为`block`。
- 新增发布建议与人工审批2张治理表；迁移版本为`b4ff2337f90f`。
- 真实建议ID为`80a74eda-b4da-4d98-a05a-c18293fc7929`，
  人工审批ID为`67a7472e-50fa-4bb5-9b14-c48071f76e37`。
- 发布治理API使用Bearer Token；建议和审批HTTP均返回201，
  未认证请求返回401，OpenAPI包含2条治理路径。
- M6结束时全量自动化测试130项通过，Alembic无模型漂移；
  自动变更能力为0，所有建议都要求人工审批。

<!-- AI_SRE_M7_A4_LOG_START -->
## M7-A4真实k6容量基线与HPA扩容实验

- k6版本：0.54.0，最大虚拟用户：20。
- 请求总数：9836，平均RPS：81.9651。
- 错误率：0%，P95：266.84771624999996 ms。
- HPA副本：1 -> 4。
- 峰值CPU：1547m，峰值内存：289.00 MiB。
- 结果：确定性容量策略通过，保留原始k6 JSON和HPA时序作为本机证据。
<!-- AI_SRE_M7_A4_LOG_END -->
