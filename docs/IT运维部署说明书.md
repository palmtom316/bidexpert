# BidExpert AI 辅助投标系统 — IT 运维部署说明书

> 版本：V1.0 | 更新日期：2026-02-23

## 技术架构

| 组件 | 技术 | 用途 |
|------|------|------|
| API 服务 | Python / FastAPI | 核心业务逻辑 |
| 异步任务 | Celery + Redis | 文档处理、AI 生成等耗时任务 |
| 关系数据库 | PostgreSQL 16（生产）/ SQLite（开发） | 项目、文档、审核等结构化数据 |
| 向量数据库 | Qdrant v1.12.5 | 专家知识库的向量检索 |
| 缓存/消息 | Redis 7 | Celery broker、语义缓存、限流 |
| 反向代理 | Nginx 1.27 | HTTPS 终止、静态文件、负载均衡 |
| 数据库迁移 | Alembic | Schema 版本管理 |
| 前端 | 原生 HTML/CSS/JS | 单页应用，由 Nginx 或 FastAPI 提供静态服务 |

## 部署方式

### Docker Compose 一键部署（推荐）

```bash
# 1. 克隆代码
git clone <repo> && cd bidexpert

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置以下必填项：
#   BIDEXPERT_API_KEY=<生成一个强随机字符串>
#   REDIS_PASSWORD=<Redis 密码>
#   POSTGRES_PASSWORD=<数据库密码>
#   至少一个 LLM API Key（BIDEXPERT_QWEN_API_KEY 等）

# 3. 启动全部服务
docker compose up -d

# 4. 验证
curl -H "X-API-Key: <你的key>" http://localhost:8080/health
```

服务启动顺序：PostgreSQL → Redis/Qdrant → Alembic 迁移 → API → Worker → Nginx

访问地址：`http://localhost:8080`（HTTP）或 `https://localhost:8443`（HTTPS，开发环境自动生成自签名证书）

### 本地开发模式

```bash
# 使用 SQLite，无需 PostgreSQL
pip install -e .
# 确保 .env 中 BIDEXPERT_DATABASE_URL=sqlite+pysqlite:///./bidexpert.db
uvicorn app.main:app --reload --port 8000
# 另起终端启动 worker（需要本地 Redis）
celery -A app.worker.celery_app.celery_app worker --loglevel=INFO
```

## 环境变量配置说明

### 必须配置

| 变量 | 说明 |
|------|------|
| `BIDEXPERT_API_KEY` | 接口认证密钥，auth_mode=api_key 时必填 |
| `BIDEXPERT_APP_ENV` | 环境标识：dev / test / prod |
| `BIDEXPERT_DATABASE_URL` | 数据库连接串 |
| `REDIS_PASSWORD` | Redis 密码（生产必填） |

### LLM 模型（至少配一个）

| 变量 | 说明 |
|------|------|
| `BIDEXPERT_QWEN_API_KEY` / `_BASE_URL` | 百炼 Qwen（默认推荐） |
| `BIDEXPERT_OPENAI_API_KEY` / `_BASE_URL` | OpenAI 兼容接口 |
| `BIDEXPERT_DEEPSEEK_API_KEY` / `_BASE_URL` | DeepSeek |
| `BIDEXPERT_GEMINI_API_KEY` / `_BASE_URL` | Gemini |
| `BIDEXPERT_VOYAGE_API_KEY` / `_BASE_URL` | Voyage（Embedding 专用） |

### OCR 文档识别（至少配一个）

| 变量 | 说明 |
|------|------|
| `BIDEXPERT_OCR_PROVIDER` | 引擎选择：glm-ocr / textin / tesseract / hunyuan / docai |
| `BIDEXPERT_GLM_OCR_API_KEY` / `_BASE_URL` | GLM OCR 配置 |
| `BIDEXPERT_TEXTIN_OCR_API_KEY` / `_BASE_URL` | TextIn OCR 配置 |

### 认证模式

| 变量 | 说明 |
|------|------|
| `BIDEXPERT_AUTH_MODE` | api_key（默认）/ jwt / hybrid |
| `BIDEXPERT_JWT_PUBLIC_KEY_PEM` | JWT 公钥（RS256/ES256，生产推荐） |
| `BIDEXPERT_JWT_SECRET` | JWT 共享密钥（仅 HS256 兼容时使用） |
| `BIDEXPERT_API_KEY_SECONDARY` | 备用 API Key（用于密钥轮换） |

### 安全与密钥管理

| 变量 | 说明 |
|------|------|
| `BIDEXPERT_MASTER_KEY_B64` | 主加密密钥（Base64），用于加密存储用户 API Key |
| `BIDEXPERT_VAULT_ADDR` / `_TOKEN` | HashiCorp Vault 地址和 Token |
| `BIDEXPERT_VAULT_REDIS_FALLBACK_ENABLED` | 生产必须为 false |

### 性能调优

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BIDEXPERT_API_RATE_LIMIT_REQUESTS` | 300 | 每窗口最大请求数 |
| `BIDEXPERT_API_RATE_LIMIT_WINDOW_SECONDS` | 60 | 限流窗口（秒） |
| `BIDEXPERT_MAX_PARALLEL_SECTIONS` | 4 | 最大并行章节生成数 |
| `BIDEXPERT_MAX_UPLOAD_BYTES` | 52428800 | 上传文件大小限制（50MB） |
| `BIDEXPERT_SECTION_MAX_INPUT_TOKENS` | 16000 | 单章节最大输入 token |
| `BIDEXPERT_SECTION_MAX_OUTPUT_TOKENS` | 4000 | 单章节最大输出 token |
| `BIDEXPERT_PROJECT_TOKEN_BUDGET_DEFAULT` | 500000 | 项目默认 token 预算 |

## 生产环境检查清单

系统启动时会自动校验以下生产约束（`APP_ENV=prod`）：

- `CORS_ORIGINS` 不能包含 localhost
- `DATABASE_URL` 不能使用默认密码
- `REDIS_URL` 必须包含密码
- `VAULT_REDIS_FALLBACK_ENABLED` 必须为 false

## 数据备份

Docker Compose 内置三个备份服务（ops profile）：

```bash
# PostgreSQL 备份
docker compose --profile ops run --rm pg-backup

# Qdrant 向量库备份
docker compose --profile ops run --rm qdrant-backup

# 文件数据备份（uploads、exports 等）
docker compose --profile ops run --rm data-backup
```

备份文件存储在 `./backups/` 目录。

## 监控

- 健康检查：`GET /health` — 返回 `{"status": "ok"}`
- Prometheus 指标：`GET /metrics` — 需认证（除非 `METRICS_PUBLIC_ENABLED=true`）
- 指标内容：HTTP 请求计数、延迟分布、状态码分布
- Prometheus 告警规则：`deploy/monitoring/prometheus-alerts.yml`

## 数据库迁移

```bash
# 查看当前版本
alembic current

# 升级到最新
alembic upgrade head

# Docker 环境下自动执行（migrate 服务）
```

核心数据表：project、document、requirement、expert_doc、evidence_chunk、section_content、review_report、scoring_report、workflow_run、provider_profile、project_model_policy、completed_bid、llm_call_log、tender_analysis_run 等。

## 日志

- 格式：JSON（默认）或 plain，通过 `BIDEXPERT_LOG_FORMAT` 控制
- 级别：通过 `BIDEXPERT_LOG_LEVEL` 控制（INFO/DEBUG/WARNING）
- LLM 调用审计：所有 AI 模型调用记录在 `llm_call_log` 表，包含 token 用量、延迟、缓存命中、预算消耗等

## 常见运维操作

| 场景 | 操作 |
|------|------|
| 轮换 API Key | 先设置 `API_KEY_SECONDARY` 为新 Key，通知用户切换后，将新 Key 设为 `API_KEY`，清空 secondary |
| 扩容 Worker | 调整 docker-compose.yml 中 worker 的 `--concurrency` 参数或增加 worker 副本 |
| 清理语义缓存 | 调用 `POST /v1/evidence/cache/invalidate` |
| 查看审计日志 | 调用 `GET /v1/provider/audit-logs` |
