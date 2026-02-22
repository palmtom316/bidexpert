# BidExpert 生产上线整改任务表（可执行版）

> 日期：2026-02-22  
> 目标：将当前版本从“可开发验证”推进到“可正式上线”  
> 执行原则：先清阻断（P0）再扩可靠性（P1）再做增强（P2），每项必须有验收与命令级验证

---

## 一、执行分工与节奏

| 角色 | 责任范围 |
| --- | --- |
| 后端负责人 | 鉴权、安全、迁移、业务一致性、Celery 可靠性 |
| 平台/运维负责人 | 部署基线、网络暴露、TLS、备份恢复、CI/CD |
| 测试负责人 | 测试门禁、回归脚本、上线验收单 |
| 安全负责人 | 配置基线评审、发布前安全验收 |

建议节奏：P0 用 3-5 个工作日闭环，P1 用 5-7 个工作日闭环，P2 用 1-2 周并行推进。

---

## 二、P0 阻断项（上线前必须完成）

| ID | 优先级 | 任务 | 负责人 | 预估工期 | 依赖 | 交付物 | 验收标准 | 验证命令 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0-01 | P0 | 鉴权 fail-close：未配置 `BIDEXPERT_API_KEY` 时禁止放行，`api_key` 模式启动即报错 | 后端 | 0.5d | 无 | 代码+单测 | 未配置 key 时 `/health` 返回 401/服务启动失败；配置后正常 | `.venv/bin/pytest -q app/tests/test_jwt_auth_and_actor.py tests/test_app_starts.py` |
| P0-02 | P0 | 环境基线收口：生产必须 `BIDEXPERT_APP_ENV=prod`，禁止 embedding mock fallback | 后端 | 0.5d | P0-01 | 配置校验逻辑+文档 | prod 下 embedding 失败直接报错；dev 保留 mock | `.venv/bin/pytest -q app/tests/test_phase1_audit_fixes.py app/tests/test_phase2_audit_fixes.py` |
| P0-03 | P0 | 修复迁移/模型漂移：`review_report.project_id`、`scoring_report.project_id` 与 ORM 类型统一为 UUID FK | 后端 | 1d | 无 | Alembic 新迁移+回归测试 | 新库升级后 schema 与 SQLAlchemy 模型一致 | `.venv/bin/alembic upgrade head && .venv/bin/pytest -q app/tests/test_v11_jsonb_and_migration_contract.py` |
| P0-04 | P0 | 移除运行时 DDL（`workflow_runs` 动态改表），改为纯迁移管理 | 后端 | 1d | P0-03 | 代码重构+迁移补齐 | 应用运行不再执行 ALTER TABLE | `rg -n "ALTER TABLE workflow_run|_ensure_table" app/services/workflow_runs.py && .venv/bin/pytest -q app/tests/test_workflow_run_db.py app/tests/test_workflow_resume_v11.py` |
| P0-05 | P0 | 工件路径安全：`outline_id/section_key/conversion_id` 白名单校验，阻断路径穿越 | 后端 | 1d | 无 | 输入校验+单测 | 非法路径输入返回 400；合法输入正常 | `.venv/bin/pytest -q app/tests/test_word_layout_pipeline.py app/tests/test_expert_library_api.py` |
| P0-06 | P0 | `/metrics` 加鉴权或内网隔离开关（默认关闭公网暴露） | 后端+运维 | 0.5d | P0-01 | 配置项+网关规则 | 未授权无法访问 metrics；内部采集可用 | `.venv/bin/pytest -q app/tests/test_metrics_endpoint.py` |
| P0-07 | P0 | 部署面收口：取消数据库/缓存/向量库公网映射；生产 TLS 改真实证书，不用自签默认 | 运维 | 1d | 无 | compose/部署模板更新 | 仅 nginx 对外；内网连通正常；证书可替换 | `docker compose config --quiet` |
| P0-08 | P0 | 测试门禁修复：`pytest` 默认包含 `tests` 与 `app/tests` | 测试+后端 | 0.5d | 无 | `pyproject.toml` 更新+CI 脚本 | 默认 `pytest` 收集 150+ 用例（与当前基线一致或更高） | `.venv/bin/pytest --collect-only -q` |

---

## 三、P1 可靠性与运维项（灰度前完成）

| ID | 优先级 | 任务 | 负责人 | 预估工期 | 依赖 | 交付物 | 验收标准 | 验证命令 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1-01 | P1 | 建立 CI 主流水线：lint + 单测 + migration smoke + compose config check | 运维+测试 | 1d | P0-03, P0-08 | CI 配置文件 | PR 必须全部通过才可合并 | `docker compose config --quiet && .venv/bin/pytest -q tests app/tests` |
| P1-02 | P1 | Qdrant 检索隔离：payload 增加 `project_id` 并在检索 filter 强制隔离（可选按租户） | 后端 | 1.5d | 无 | 代码+回归测试 | 不同项目数据不互相召回 | `.venv/bin/pytest -q app/tests/test_qdrant_rerank.py app/tests/test_qdrant_llm_rerank.py` |
| P1-03 | P1 | Secret 策略收口：生产关闭 `vault_redis_fallback`，临时凭据统一 TTL | 安全+后端 | 1d | 无 | 配置策略+代码 | VAULT 不可用时生产拒绝继续写密钥 | `.venv/bin/pytest -q app/tests/test_byok_vault_and_qualify.py` |
| P1-04 | P1 | Adapter 严格模式：未知 provider 不再静默 `MockAdapter`，改显式失败 | 后端 | 0.5d | 无 | 代码+单测 | 错误 provider 返回可观测错误，不再伪成功 | `.venv/bin/pytest -q app/tests/test_model_registry_defaults.py app/tests/test_provider_profile_qualify_api.py` |
| P1-05 | P1 | Celery 可靠性：关键任务增加 `autoretry_for`/指数退避/幂等键（至少 ingest+section pipeline） | 后端 | 1.5d | P0-04 | 任务重试策略+文档 | 短时故障自动恢复；重复投递不重复写入 | `.venv/bin/pytest -q app/tests/test_workflow_resume_v11.py app/tests/test_batch_ingest.py` |
| P1-06 | P1 | 备份恢复闭环：补文件类数据（`data/`）备份，形成月度恢复演练记录模板 | 运维 | 1d | 无 | runbook + 脚本 | 可在演练环境完整恢复 DB/Qdrant/文件工件 | `docker compose --profile ops run --rm pg-backup && docker compose --profile ops run --rm qdrant-backup` |
| P1-07 | P1 | 观测完善：核心业务指标与错误告警阈值（429、5xx、任务失败率） | 运维+后端 | 1d | P0-06 | 指标清单+告警规则 | 可观测到 API 与任务失败趋势 | `curl -k https://localhost:8443/metrics`（内网/鉴权场景按策略执行） |

---

## 四、P2 架构与治理增强（正式放量前完成）

| ID | 优先级 | 任务 | 负责人 | 预估工期 | 依赖 | 交付物 | 验收标准 | 验证命令 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P2-01 | P2 | 审计日志落地：关键写操作写入 `audit_log`（含 actor、对象、变更摘要） | 后端 | 1.5d | P0-01 | 审计中间层+查询接口/脚本 | 关键操作可追溯到用户与时间 | `.venv/bin/pytest -q app/tests/test_phase2_audit_fixes.py` |
| P2-02 | P2 | 发布工件治理：清理运行时产物入库风险，补 `.gitignore` 与发布前检查脚本 | 运维+测试 | 0.5d | 无 | 检查脚本 | 发布分支无本地数据库/临时文件 | `git status --short` |
| P2-03 | P2 | 文档与命令对齐：修正文档中的 worker 启动命令、部署说明、应急手册 | 测试+运维 | 0.5d | P1-01 | 更新后的 `docs/README.md` 与 runbook | 新人可按文档一次拉起并通过验收 | `docker compose up -d --build` |

---

## 五、上线准入门槛（Go / No-Go）

| 门槛项 | 通过标准 |
| --- | --- |
| 安全门 | P0 全部完成；外网仅暴露网关；鉴权 fail-close 生效 |
| 质量门 | CI 全绿；`pytest` 默认全集通过；迁移演练成功 |
| 运维门 | 备份恢复演练完成且留档；监控告警可用 |
| 业务门 | 核心流程（上传→解析→生成→审查→导出）回归通过 |

未达任一门槛则 `No-Go`。

---

## 六、建议排期（可直接执行）

| 周期 | 目标 | 任务 |
| --- | --- | --- |
| D1-D2 | 清除安全阻断 | P0-01, P0-02, P0-06, P0-07 |
| D2-D3 | 清除数据与迁移阻断 | P0-03, P0-04, P0-05 |
| D3-D4 | 质量门闭环 | P0-08, P1-01 |
| D4-D6 | 可靠性加固 | P1-02, P1-03, P1-04, P1-05 |
| D6-D7 | 运维闭环 | P1-06, P1-07 |
| W2 | 放量前治理 | P2-01, P2-02, P2-03 |

