# BidExpert AI 辅助投标系统 — IT 运维部署说明书

> 版本：V1.1 | 更新日期：2026-02-25

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

## 灾难恢复

### RPO / RTO 目标

| 级别 | RPO（数据丢失容忍） | RTO（恢复时间） | 适用场景 |
|------|---------------------|-----------------|---------|
| 标准 | ≤ 1 小时 | ≤ 2 小时 | 单机部署 |
| 高可用 | ≤ 5 分钟 | ≤ 30 分钟 | 多副本部署 |

### 备份策略

| 数据源 | 频率 | 保留周期 | 方式 |
|--------|------|---------|------|
| PostgreSQL | 每日全量 + 持续 WAL 归档 | 全量 30 天，WAL 7 天 | `pg_basebackup` + WAL 归档到对象存储 |
| Qdrant | 每日快照 | 14 天 | `docker compose --profile ops run --rm qdrant-backup` |
| 文件数据 | 每日增量 | 30 天 | `docker compose --profile ops run --rm data-backup` |
| Redis | 不备份 | — | 缓存数据可重建，Celery 任务可重投 |

### 恢复流程

1. 停止所有服务：`docker compose down`
2. 恢复 PostgreSQL：
   ```bash
   # 从全量备份恢复
   docker compose run --rm pg-backup restore <backup_file>
   # 或使用 WAL 做时间点恢复（PITR）
   ```
3. 恢复 Qdrant 快照：
   ```bash
   docker compose --profile ops run --rm qdrant-backup restore <snapshot_name>
   ```
4. 恢复文件数据：将 `backups/data-*.tar.gz` 解压到 `data/` 目录
5. 启动服务：`docker compose up -d`
6. 验证：`curl -H "X-API-Key: <key>" http://localhost:8080/health`
7. 执行数据库迁移（如有版本差异）：`docker compose run --rm migrate alembic upgrade head`

### 故障场景处理

| 故障 | 影响 | 恢复方式 |
|------|------|---------|
| API 容器崩溃 | 服务不可用 | Docker 自动重启（restart: unless-stopped） |
| PostgreSQL 宕机 | 全部写操作失败 | 从最近备份恢复，重放 WAL |
| Qdrant 宕机 | 检索不可用，生成降级 | 从快照恢复，或重建索引 |
| Redis 宕机 | 缓存失效、任务队列中断 | 重启 Redis，未完成任务自动重试 |
| 磁盘满 | 服务异常 | 清理日志/临时文件，扩容磁盘 |
| 数据损坏 | 数据不一致 | PITR 恢复到损坏前时间点 |

## 监控告警配置

### Prometheus 集成

系统暴露 `/metrics` 端点（需认证），提供以下指标：

| 指标 | 类型 | 说明 |
|------|------|------|
| `http_requests_total` | Counter | HTTP 请求总数（按 method、path、status） |
| `http_request_duration_seconds` | Histogram | 请求延迟分布 |
| `llm_calls_total` | Counter | LLM 调用次数（按 provider、model） |
| `llm_tokens_used_total` | Counter | Token 消耗总量 |
| `celery_tasks_total` | Counter | 异步任务执行次数（按 task_name、status） |

### 告警规则

在 `deploy/monitoring/prometheus-alerts.yml` 中配置，关键规则：

```yaml
# API 高错误率
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "API 5xx 错误率超过 5%"

# API 响应慢
- alert: HighLatency
  expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "P95 延迟超过 10 秒"

# 服务不可用
- alert: ServiceDown
  expr: up{job="bidexpert"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "BidExpert 服务不可达"

# 磁盘空间不足
- alert: DiskSpaceLow
  expr: node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} < 0.15
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "磁盘剩余空间低于 15%"
```

### 告警通知渠道

通过 Alertmanager 配置通知：

| 渠道 | 配置方式 | 适用场景 |
|------|---------|---------|
| 企业微信 | Alertmanager webhook | 生产告警 |
| 邮件 | Alertmanager email_configs | 日报/周报 |
| 钉钉 | Alertmanager webhook + 钉钉机器人 | 生产告警 |

## 扩容策略

### 垂直扩容（单机）

| 组件 | 基础配置 | 推荐生产配置 | 调整方式 |
|------|---------|-------------|---------|
| API | 2 CPU / 2GB | 4 CPU / 8GB | docker-compose.yml `deploy.resources` |
| Worker | 2 CPU / 2GB | 4 CPU / 8GB | `--concurrency` 参数（建议 CPU 核数 × 2） |
| PostgreSQL | 1 CPU / 1GB | 2 CPU / 4GB | `shared_buffers`、`work_mem` 调优 |
| Qdrant | 1 CPU / 1GB | 2 CPU / 4GB | `--memory-limit` 启动参数 |
| Redis | 1 CPU / 512MB | 1 CPU / 2GB | `maxmemory` 配置 |

### 水平扩容

| 组件 | 扩容方式 | 注意事项 |
|------|---------|---------|
| API | 增加副本 + Nginx 负载均衡 | 无状态，直接扩容 |
| Worker | 增加 Celery worker 副本 | 共享 Redis broker，注意并发限制 |
| PostgreSQL | 读写分离（主从复制） | 写操作仅主库，读操作可分发到从库 |
| Qdrant | 分片集群模式 | 需 Qdrant 集群配置，数据量 > 100 万向量时考虑 |
| Nginx | 多实例 + DNS 轮询或 LB | 前置云负载均衡器 |

### 扩容决策参考

| 指标 | 阈值 | 建议操作 |
|------|------|---------|
| API P95 延迟 > 5s | 持续 10 分钟 | 增加 API 副本 |
| Worker 队列积压 > 100 | 持续 5 分钟 | 增加 Worker 副本或提高 concurrency |
| PostgreSQL CPU > 80% | 持续 15 分钟 | 垂直扩容或读写分离 |
| Qdrant 内存 > 85% | 持续 | 垂直扩容或启用分片 |
| 磁盘使用 > 80% | — | 清理或扩容磁盘 |
