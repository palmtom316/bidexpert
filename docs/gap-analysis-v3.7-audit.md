# BidExpert v3.7 全面代码审计报告

> 审核基准：`AI_Tender_System_Technical_Whitepaper_v3.7_Quality_Maximized.md`、`AI_Programming_Prompt_v3.7_Quality_Maximized.md`、`user_manuals_v1.0.md`、`CLAUDE_IMPLEMENTATION_GUIDE_v3.6_BYOK.md`
>
> 审核日期：2026-02-17
>
> 审核范围：全部 Python 源码（app/）、配置文件、Dockerfile、docker-compose.yml、前端 UI

---

## 一、功能性 Gap（文档要求 vs 代码实际）

### 1.1 P0 — 阻塞核心闭环

#### F1. 招标文件抽取仍是正则，未调用 LLM

- **文档要求**：白皮书 §三.2 — "LangExtract 抽取 Requirement JSON"，首选 Gemini 3 Pro，失败自动 fallback Gemini → GPT-5 → DeepSeek。
- **代码现状**：`app/extract/tender_parser.py` 仅使用正则匹配关键词（`必须/应当/不得/评分/格式`）拆分句子，无 LLM 调用。`historical_extractor.py` 使用 langextract 但那是历史标书入库管线，不是招标文件解析。
- **影响**：招标文件要点提取的准确率和覆盖率严重不足，复杂招标文件中隐含的技术要求、评分细则、资质条件基本无法正确拆解。
- **涉及文件**：`app/extract/tender_parser.py`

#### F2. 专业 OCR 未接入

- **文档要求**：白皮书 §二 模型矩阵 — OCR/版面解析首选 "HunyuanOCR / DocAI"，可替代 PaddleOCR。
- **代码现状**：`Dockerfile` 仅安装 `tesseract-ocr` + `tesseract-ocr-chi-sim`。无 HunyuanOCR、DocAI 或 PaddleOCR 适配器。`app/services/adapters/ocr.py` 存在但未接入专业 OCR 服务。
- **影响**：扫描件、图片型 PDF 的识别质量差，尤其中文表格和复杂版面场景。
- **涉及文件**：`Dockerfile`、`app/services/adapters/ocr.py`

#### F3. Embedding 无开箱可用默认凭据

- **文档要求**：白皮书 §二 — Embedding 首选 `text-embedding-3-large`，维度保持 3072 全维度。
- **代码现状**：`app/services/embedding.py:117-151` 需要 `api_key` + `base_url` 才调真实 API；dev 环境（`app_env == "dev"`）回退到 SHA1 hash 伪向量。`.env.example` 未配置任何 API key。
- **影响**：开发和新部署环境中 RAG 语义检索完全无效，只有随机匹配。向量维度正确（3072）但向量内容是伪造的。
- **涉及文件**：`app/services/embedding.py`、`.env.example`

#### F4. 生成内容 evidence_ids 绑定未严格校验

- **文档要求**：白皮书 §四.4 — "不允许生成未绑定证据内容"，"未找到证据必须输出 NEED_HUMAN_INPUT"。
- **代码现状**：`app/services/adapters/providers.py:148-179` 在 prompt 中要求 LLM 输出含 `evidence_ids` 的 JSON；`app/validator/llm_contracts.py` 的 `validate_generation_payload()` 仅检查 JSON 结构（字段存在且非空），不验证返回的 `evidence_ids` 是否真实存在于检索结果中。
- **影响**：LLM 可能编造不存在的 evidence_id，投标文件合规性无法保证。
- **涉及文件**：`app/validator/llm_contracts.py`、`app/services/adapters/providers.py`

---

### 1.2 P1 — 影响生产可用性

#### F5. 招标文件分析模块不调用 LLM 做深度解析

- **文档要求**：用户手册 §3 — "AI 自动提炼投标要点和废标项"。
- **代码现状**：`app/services/tender_analysis.py` 对 PDF 解析后走的是同一个正则 `parse_tender_requirements()`，不调用 LLM 做语义理解。
- **影响**："招标文件分析"模块的智能化程度远低于用户预期，关键信息遗漏率高。
- **涉及文件**：`app/services/tender_analysis.py`、`app/extract/tender_parser.py`

#### F6. Re-ranking 未实现

- **文档要求**：用户手册 IT 部分 §2.3 — "Re-ranking: (可选) 对融合结果进行重排序 (v3.7 Spec)"。
- **代码现状**：`app/services/qdrant_store.py` RRF 融合后直接按分数排序返回 top_k，无额外的 re-ranking 模型或逻辑。
- **影响**：检索精度在复杂查询场景下有提升空间，尤其长查询、多义查询效果不理想。
- **涉及文件**：`app/services/qdrant_store.py`

#### F7. PDF 导出依赖 LibreOffice 但 Docker 镜像未安装

- **文档要求**：用户手册 §3 — "一键导出为格式规范的 Word 文档"，代码支持 `export_pdf=True`。
- **代码现状**：`app/services/word_renderer.py:248-265` 调用 `soffice --headless --convert-to pdf`，但 `Dockerfile` 未安装 LibreOffice。
- **影响**：Docker 部署后 PDF 导出功能直接 RuntimeError 崩溃。
- **涉及文件**：`app/services/word_renderer.py`、`Dockerfile`

#### F8. Celery 管线 render 阶段未真正生成 Word 文件

- **文档要求**：编程 Prompt §六 最小闭环 — "生成章节 → 审查 → 导出 WPS 文档"。
- **代码现状**：`app/worker/tasks.py:241-252` 的 `section_render_stage_task` 仅返回状态标记 `{"render_ready": true/false}`，不调用 `render_word()` 或 `render_word_structured()` 生成实际文件。
- **影响**：Celery 工作流管线无法自动产出最终 Word 文档，需要用户手工调用 `/v1/render/word` API。
- **涉及文件**：`app/worker/tasks.py`

#### F9. 审查引擎仅支持单 section 审查，无全文级审查

- **文档要求**：白皮书 §五 — 审查输出应包含 `missing_requirements`、`logical_inconsistencies`、`risk_points`、`coverage_estimate`、`score_estimate`。gap-analysis 文档提到需要"逐条合规性审查报告"。
- **代码现状**：`app/services/review_engine.py` 的 `ComplianceReviewer` 只审查单个 section 对其 `requirement_codes` 的合规性。无全文级聚合审查、无跨章节一致性检查。
- **影响**：无法发现跨章节矛盾、全局性遗漏或重复内容。
- **涉及文件**：`app/services/review_engine.py`

#### F10. 模拟评分完全依赖审查先完成

- **文档要求**：gap-analysis 文档 — 独立 `ScoringEngine`。
- **代码现状**：`app/services/scoring_engine.py` 的 `SimulatedScorer` 需要 `ReviewReport` 存在才能判定通过/失败。若未运行审查，所有 requirement 状态为 `UNREVIEWED`，评分永远为 0。
- **影响**：评分与审查强耦合，无法在审查之前提供初步评分预估。
- **涉及文件**：`app/services/scoring_engine.py`

#### F11. Context Compression 为纯本地算法，未调用 LLM

- **文档要求**：白皮书 §二 模型矩阵 — RAG 压缩阶段首选 Gemini 3 Pro，可替代 Qwen3-Max。
- **代码现状**：`app/services/context_compressor.py` 使用本地 BM25 TF-IDF 评分对 evidence 片段排序和截断，未调用任何 LLM 做语义级压缩。
- **影响**：压缩质量低于 LLM 语义压缩方案，可能丢失语义相关但关键词不匹配的重要上下文。
- **涉及文件**：`app/services/context_compressor.py`

---

### 1.3 P2 — 功能完善性（本轮已完成）

| # | Gap | 说明 | 涉及文件 |
|---|-----|------|----------|
| **F12** | 多模型 ensemble 审查 | ✅ 已实现 `compliance_review_with_ensemble()`，支持多模型投票聚合；`/v1/workflow/review/full` 支持 `enable_ensemble/ensemble_size` 参数 | `app/services/llm_gateway.py`、`app/services/review_engine.py`、`app/api/routes.py` |
| **F13** | 自动模型质量评估 | ✅ 已实现 `evaluate_compliance_quality()`，并在 Qualify 与 ensemble 输出 `model_quality`、`quality_score` | `app/services/model_quality.py`、`app/services/byok/profiles.py`、`app/services/llm_gateway.py` |
| **F14** | RL 路由优化 | ✅ 已实现轻量 RL 路由优化（成功率/时延反馈 + 探索率），接入 generate/review/compliance fallback 链路 | `app/services/routing_optimizer.py`、`app/services/llm_gateway.py` |
| **F15** | VAULT 密钥存储 | ✅ 已实现 VAULT 存储读写删（Vault HTTP + Redis fallback），移除 `VAULT is not configured yet` 硬错误路径 | `app/services/byok/profiles.py`、`app/core/config.py` |
| **F16** | Qualify 测试集 | ✅ 已实现 `qualify_provider_profile()` 能力测试集（凭据、连通、生成契约、审查契约、合规契约）并提供 `/api/provider-profiles/{id}/qualify` | `app/services/byok/profiles.py`、`app/api/routes.py`、`app/schemas/contracts.py` |

---

## 二、生产部署 Gap（上线阻塞）

### 2.1 关键基础设施

#### D1. SQLite vs PostgreSQL 类型不兼容 — CRITICAL

- **详情**：`app/core/config.py:7` 默认 `database_url = "sqlite+pysqlite:///./bidexpert.db"`，但 `app/models/tables.py` 大量使用 PostgreSQL 专有类型：
  - `UUID(as_uuid=True)` — SQLite 无原生 UUID
  - `ARRAY(Text)` / `ARRAY(UUID)` / `ARRAY(String)` — SQLite 无 ARRAY 类型
  - `Enum` with named types — SQLite 处理不同
- **影响**：本地 `.env.example` 配置为 SQLite，直接运行必然在建表或写入时报错。项目根目录存在 `bidexpert.db`（163KB），说明部分表可能通过兼容模式创建但 ARRAY 字段操作会失败。
- **涉及文件**：`app/core/config.py`、`app/models/tables.py`、`.env.example`

#### D2. Dockerfile Python 版本不匹配

- **详情**：`Dockerfile` 使用 `python:3.11-slim`，本地 `.venv` 使用 Python 3.14。`pyproject.toml` 未声明 `requires-python` 约束。
- **影响**：依赖兼容性风险，3.14 新语法在 3.11 镜像中无法运行。
- **涉及文件**：`Dockerfile`、`pyproject.toml`

#### D3. Worker Celery 模块路径混乱

- **详情**：
  - `docker-compose.yml:24` 启动 worker 用 `app.workers.celery_app.celery_app`（`workers` 复数）
  - `app/api/routes.py:117` 导入 `from app.worker.tasks import ...`（`worker` 单数）
  - 两套文件并存：`app/worker/{celery_app.py, tasks.py}` 和 `app/workers/{celery_app.py, tasks.py}`
- **影响**：API 进程和 Worker 进程可能加载不同的 task 定义，导致任务路由失败或行为不一致。
- **涉及文件**：`docker-compose.yml`、`app/worker/`、`app/workers/`

#### D4. 缺少 MASTER_KEY_B64 配置

- **详情**：BYOK AES-GCM 加密依赖 `MASTER_KEY_B64` 环境变量（32 bytes base64）。`.env.example` 和 `docker-compose.yml` 均未配置此项。
- **影响**：首次通过 API 创建 `ENCRYPTED_DB` 类型的 provider profile 时，`load_master_key()` 抛出异常。
- **涉及文件**：`app/secrets/crypto.py`、`.env.example`、`docker-compose.yml`

#### D5. docker-compose 无任何 LLM API Key 配置

- **详情**：`docker-compose.yml` 的 environment 部分无任何 LLM 供应商 API Key、`MASTER_KEY_B64`、`BIDEXPERT_API_KEY` 配置。
- **影响**：部署后所有 LLM 调用因无 credentials 回退到 MockAdapter（返回伪结果），或在非 dev 环境直接报错。
- **涉及文件**：`docker-compose.yml`

#### D6. Docker 镜像缺少 LibreOffice

- **详情**：`app/services/word_renderer.py:248` 调用 `soffice` 命令做 PDF 导出，Dockerfile 未安装 `libreoffice`。
- **影响**：`render_word_structured(export_pdf=True)` 在 Docker 环境中必定 RuntimeError。
- **涉及文件**：`Dockerfile`

---

### 2.2 安全性

#### D7. CORS 默认允许所有来源

- **详情**：`app/core/config.py:38` `cors_origins: str = "*"`，`main.py:28-35` 直接使用该配置。
- **影响**：任意域名可跨域调用 API，存在 CSRF 和数据泄露风险。
- **涉及文件**：`app/core/config.py`、`app/main.py`

#### D8. 无用户认证体系

- **详情**：
  - 仅支持单一静态 API Key 认证（`app/api/routes.py:132-137`，Header: `X-API-Key`）
  - 无用户注册/登录、无 JWT/Session 管理、无角色权限控制
  - `created_by` 字段完全靠客户端传入，可被伪造
  - 无多租户数据隔离（project 间无访问控制）
- **影响**：无法区分用户身份，无法实施细粒度权限控制。
- **涉及文件**：`app/api/routes.py`

#### D9. 无 API 层 Rate Limiting

- **详情**：`app/services/concurrency_limiter.py` 仅管控 LLM 调用并发，HTTP API 端点无任何限流中间件。
- **影响**：API 暴露后可被暴力请求，耗尽系统资源或 LLM 配额。
- **涉及文件**：`app/main.py`

#### D10. 静态文件由 FastAPI 直接 serve

- **详情**：`app/main.py:39` `app.mount("/ui", StaticFiles(directory="app/ui"))`。
- **影响**：FastAPI 不适合高并发静态文件服务，且无法配置 CDN 缓存头。生产应使用 nginx 反向代理。
- **涉及文件**：`app/main.py`

#### D11. Alembic 迁移链不完整

- **详情**：`alembic.ini` 和 `migrations/` 目录存在，但 `docker-compose.yml` 使用 `sql/schema.sql` 作为 PostgreSQL 初始化脚本，未集成 Alembic 自动迁移。
- **影响**：数据库 schema 升级需要手工执行 SQL，版本间迁移容易出错。
- **涉及文件**：`alembic.ini`、`docker-compose.yml`、`migrations/`

---

### 2.3 运维可观测性

#### D12. 无 Health Check 配置

- **详情**：`docker-compose.yml` 中 api/worker/postgres/redis/qdrant 均无 `healthcheck` 配置。API 有 `/health` 端点但未被编排工具调用。
- **影响**：服务异常后容器不会自动重启，Kubernetes 部署无 readiness/liveness probe。
- **涉及文件**：`docker-compose.yml`

#### D13. 无结构化日志

- **详情**：全部使用 Python 默认 `logging`，无 JSON 格式化、无日志级别配置文件、无日志轮转。
- **影响**：日志难以被 ELK/Loki 等日志系统采集和检索。
- **涉及文件**：各模块

#### D14. 无监控指标

- **详情**：无 Prometheus metrics endpoint、无 Grafana dashboard 模板、无告警规则。
- **影响**：无法实时监控系统负载、LLM 调用成功率、队列积压等关键指标。
- **涉及文件**：—

#### D15. 无 HTTPS/TLS

- **详情**：无 SSL 证书配置、无反向代理（nginx）、API 运行在纯 HTTP `0.0.0.0:8000`。
- **影响**：网络传输明文，API Key 和敏感数据可被中间人拦截。
- **涉及文件**：`Dockerfile`、`docker-compose.yml`

#### D16. 无数据备份策略

- **详情**：PostgreSQL `pgdata` 和 Qdrant `qdrant_data` 使用 Docker named volume，无定时备份、无异地备份、无 PITR (Point-in-Time Recovery)。
- **影响**：数据丢失后无法恢复。
- **涉及文件**：`docker-compose.yml`

#### D17. 无文件上传大小限制

- **详情**：FastAPI 未配置 `max_upload_size`，nginx（不存在）也无 `client_max_body_size`。
- **影响**：上传超大文件可导致内存溢出 (OOM)。
- **涉及文件**：`app/main.py`、`app/api/routes.py`

---

## 三、已完成项确认

以下为 `docs/todos-v3.7-update.md` 中标记已完成的项目，经代码验证确认实现状态：

| 编号 | 任务 | 验证结果 |
|------|------|----------|
| P0-1 | 真实 Embedding 与维度对齐 3072 | ✅ `embedding.py` 支持真实 API 调用，vector_size=3072 |
| P0-2 | 工作流任务编排 chain | ✅ `routes.py:614` 使用 Celery `chain()` 串联 4 个阶段 |
| P0-3 | 模型级联 Fallback | ✅ `llm_gateway.py` 实现 `generate_with_fallback_chain` |
| P0-4 | 混合检索 Vector + BM25 | ✅ `qdrant_store.py` 实现 RRF 融合 |
| P1-1 | httpx + 120s 超时 | ✅ `providers.py`、`embedding.py` 均用 httpx |
| P1-2 | Voyage Adapter | ✅ `providers.py` 有 `VoyageAdapter` |
| P1-3 | 并发限制 Redis + 本地 | ✅ `concurrency_limiter.py` Lua 脚本 + 本地兜底 |
| P1-4 | 缓存/预算迁移 Redis | ✅ `semantic_cache.py`、`governance.py` Redis 优先 + 本地兜底 |
| P1-5 | Context Compression | ⚠️ 已实现但为本地 BM25 算法，非 LLM 语义压缩（见 F11） |
| P1-6 | 路径遍历修复 | ✅ `word_renderer.py` `_safe_path()` 做 `resolved.relative_to(base)` 校验 |
| P2-1 | model_registry → .json | ✅ `app/config/model_registry.json` |
| P2-2 | FastAPI lifespan | ✅ `main.py` 使用 `@asynccontextmanager` |
| P2-3 | datetime.now(UTC) | ✅ `tables.py` 全局 `utcnow()` 使用 `datetime.now(UTC)` |
| P2-4 | SSE 返回类型 | ✅ `routes.py:503` 标注 `AsyncGenerator[str, None]` |
| P2-5 | 默认模型对齐 v3.7 | ✅ `model_registry.json` role_defaults 首选 Gemini 3 Pro |
| P2-6 | 目录结构重构 | ⚠️ 部分完成 — `worker/`、`extract/`、`rag/` 已有代码，但 `workers/` 仍并存（见 D3） |

---

## 四、优先级矩阵

```
┌─────────────────────────────────────────────────────────────────┐
│                     上线阻塞 (Must Fix)                          │
├─────────────────────────────────────────────────────────────────┤
│ D1   SQLite/PostgreSQL 类型兼容（本地开发必崩）                    │
│ D3   Worker 模块路径统一（worker/ vs workers/）                   │
│ D4   MASTER_KEY_B64 配置引导                                     │
│ D5   LLM API Key 配置文档与模板                                   │
│ D7   CORS 收紧为白名单                                           │
│ D8   用户认证体系（至少 JWT）                                     │
│ D15  HTTPS/TLS（nginx 反向代理）                                  │
│ F1   招标文件抽取接入 LLM                                         │
│ F3   Embedding 默认配置可用（配置引导文档）                        │
│ F7   Docker 安装 LibreOffice 或禁用 PDF 导出                      │
│ F8   Celery 管线补全真实 Word 渲染                                │
├─────────────────────────────────────────────────────────────────┤
│                     生产强化 (Should Fix)                         │
├─────────────────────────────────────────────────────────────────┤
│ D2   Dockerfile Python 版本对齐                                   │
│ D6   Docker 镜像安装 LibreOffice                                  │
│ D9   API Rate Limiting 中间件                                     │
│ D10  Nginx 代理静态文件                                           │
│ D11  Alembic 迁移链完善                                           │
│ D12  Docker Health Check 配置                                     │
│ D13  结构化日志（JSON 格式）                                      │
│ D16  数据备份策略                                                  │
│ F2   专业 OCR 适配器接入                                          │
│ F4   evidence_ids 绑定有效性校验                                  │
│ F5   招标分析接入 LLM 语义理解                                    │
│ F9   全文级聚合审查能力                                           │
│ F10  独立评分能力（不依赖审查）                                   │
│ F11  LLM 语义压缩替代本地 BM25                                    │
├─────────────────────────────────────────────────────────────────┤
│                     后续优化 (Nice to Have)                       │
├─────────────────────────────────────────────────────────────────┤
│ D14  Prometheus 监控指标                                          │
│ D17  文件上传大小限制                                             │
│ F6   Re-ranking 模块                                              │
│ F12  多模型 ensemble 审查（已完成）                                │
│ F13  自动模型质量评估（已完成）                                    │
│ F14  RL 路由优化（已完成）                                         │
│ F15  VAULT 密钥存储（已完成）                                      │
│ F16  Qualify 测试集（已完成）                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、建议执行顺序

```
Phase 1 — 基础可运行（上线阻塞修复）
  D1 → D3 → D4/D5 → F3 → F1 → F8 → F7

Phase 2 — 安全加固
  D7 → D8 → D15 → D9

Phase 3 — 生产强化
  D2 → D6 → D11 → D12 → D13 → D16
  F4 → F5 → F9 → F10 → F11

Phase 4 — 功能增强
  F2 → F6 → D14 → D17

已完成项（2026-02-17）
  F12、F13、F14、F15、F16
```

---

## 六、统计摘要

| 类别 | 数量 |
|------|------|
| 功能性 Gap (F) | 16 |
| 部署/运维 Gap (D) | 17 |
| 上线阻塞级 | 11 |
| 生产强化级 | 14 |
| 后续优化级 | 8 |
| 已完成（本轮） | 5（F12~F16） |
| **总计** | **33** |
