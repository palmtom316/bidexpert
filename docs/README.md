# BidExpert (release/V1.0 Quality Matrix Aligned)

基于 `AI_Tender_System_Technical_Whitepaper_v3.7_Quality_Maximized.md` 与 `AI_Programming_Prompt_v3.7_Quality_Maximized.md` 的实现。

## 已实现能力

- PostgreSQL Schema（版本化、审计、回滚基础）
- 招标文本拆解与 requirement 抽取
- 报价熔断（关键词 + 货币 + 数字密度）
- 三道防幻觉闸门（证据绑定、确定性验证、覆盖率）
- Word 模板渲染
- 真实 PDF/OCR 分块（文本提取 + OCR 回退）
- Celery 章节级异步任务（REQUIREMENT_EXTRACT/SECTION_GENERATE/SECTION_VALIDATE/RENDER_EXPORT）
- Qdrant 检索链路（upsert/search + payload 过滤 + 有效期约束）
- Schema 驱动多步 RAG（Requirement 分解 -> 子问题检索 -> 证据合并 -> 生成 -> 校验）
- 语义缓存（key: industry/template/requirement/evidence/schema）
- 项目级预算治理（Budget exceeded 阻断）
- 证据近到期预警（<=30天触发 NEED_HUMAN_INPUT）
- BYOK：Provider Profile（项目级）+ 模型策略绑定（generate/review/embed）
- BYOK：ProjectModelPolicy 支持 `rerank_profile_id`（可单独绑定检索重排模型）
- release/V1.0 六角色模型策略（extract/embed/generate/review/query_rewrite/program_support）
- Model Registry（`app/config/model_registry.json`）+ role 默认链路/fallback
- 默认商用链：`EXTRACT/GENERATE/REVIEW/QUERY_REWRITE` 优先 `qwen:qwen3.5`（可被项目策略覆盖）
- Key 安全：ENCRYPTED_DB（AES-GCM, `MASTER_KEY_B64`）+ TEMP_REDIS（TTL）
- 多供应商 Adapter Registry（OpenAI/Gemini/Qwen/DeepSeek + OpenAI-compatible fallback）
- 审查降级：审查模型不可用 -> 备用审查模型（可配置）-> 本地验证器（风险告警）
- 生成/审查 JSON Schema 强校验（章节 `content_blocks` + 审查结构化报告）

## 快速启动（Docker）

```bash
docker compose up -d --build
```

服务端点：
- API(UI): `https://127.0.0.1:8443/ui/`
- API Docs: `https://127.0.0.1:8443/docs`
- 对外仅暴露 Nginx (`8080/8443`)；Postgres/Redis/Qdrant 仅容器内网络访问

## 本地运行（非 Docker）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
celery -A app.worker.celery_app.celery_app worker --loglevel=INFO
```

## 运维与发布检查

- 备份（DB + Qdrant + 文件工件）：
  - `docker compose --profile ops run --rm pg-backup`
  - `docker compose --profile ops run --rm qdrant-backup`
  - `docker compose --profile ops run --rm data-backup`
- 月度恢复演练记录模板：`docs/runbooks/monthly-restore-drill-template.md`
- 生产应急手册：`docs/runbooks/production-emergency-runbook.md`
- 发布前运行时产物检查：
  - `scripts/release/preflight_runtime_artifacts.sh`
- Prometheus 告警规则（429/5xx/任务失败率）：
  - `deploy/monitoring/prometheus-alerts.yml`

## 关键接口

- `POST /v1/tender/ingest-upload`: 同步 PDF 分块与 requirement 提取
- `POST /v1/tasks/ingest-upload`: 异步 PDF 入库任务
- `GET /v1/tasks/{task_id}`: 查询任务状态
- `POST /v1/evidence/upsert`: 异步写入 Qdrant evidence chunk
- `POST /v1/evidence/search`: 检索 evidence
- `POST /v1/generation/draft`: 可控多步 RAG 生成 + 三闸验证 + 预算/缓存治理
- `POST /v1/tasks/generate-draft`: 异步草稿生成
- `POST /v1/workflow/section`: 章节级异步任务编排入口
- `POST /v1/cache/invalidate`: 缓存失效操作
- `POST /v1/tender/analyze-upload`: 招标 PDF 上传并生成“投标要点/评分要点/符合性要求/加分项/风险提示”
- `GET /v1/tender/analysis-runs`: 查询招标分析记录
- `GET /v1/tender/analysis-runs/{run_id}`: 查询单次分析详情（含分组关键项）
- `POST /v1/expert-library/ingest-upload`: 历史投标文件上传 -> 拆解 -> Embedding -> 本地专家库入库
- `POST /v1/evidence/extract-upsert`: 文本抽取并入库（可选传 `model_id`）
- `POST /v1/expert-library/ingest-structured`: 结构化导入规范/公司业绩/公司资质/项目管理人员资质及业绩
- `GET /v1/expert-library/docs`: 查询本地专家库文档列表
- `GET /v1/expert-library/docs/{expert_doc_id}/chunks`: 查询文档 chunks
- `POST /api/provider-profiles`: 创建 BYOK provider profile
- `GET /api/provider-profiles?project_id=...`: 查询项目 profile
- `POST /api/provider-profiles/{id}/test`: 测试 profile 连通性
- `DELETE /api/provider-profiles/{id}`: 删除 profile
- `PUT /api/projects/{id}/model-policy`: 绑定 generate/review/embed profile
- `GET /api/projects/{id}/model-policy`: 查询项目模型策略

## 环境变量

核心新增变量：
- `BIDEXPERT_MASTER_KEY_B64`：32 字节主密钥（base64）
- `MODEL_REGISTRY_PATH`：可选，模型注册表路径（优先于默认 `app/config/model_registry.json`）
- `SECTION_ROUTING_PATH`：可选，章节路由配置路径（默认 `app/config/section_routing.cn.json`）
- `BIDEXPERT_OCR_PROVIDER`：OCR 默认引擎（推荐 `glm-ocr`）
- `BIDEXPERT_GLM_OCR_API_KEY`：GLM OCR API Key
- `BIDEXPERT_GLM_OCR_BASE_URL`：GLM OCR 网关地址（OpenAI-compatible，通常以 `/v1` 结尾）
- `BIDEXPERT_GLM_OCR_MODEL`：GLM OCR 模型名（默认 `glm-ocr`）
- `BIDEXPERT_REVIEW_FALLBACK_PROVIDER`：可选，审查备用 provider
- `BIDEXPERT_REVIEW_FALLBACK_MODEL`：可选，审查备用模型
- `BIDEXPERT_REVIEW_FALLBACK_BASE_URL`：可选，审查备用 base_url
- `BIDEXPERT_REVIEW_FALLBACK_API_KEY`：可选，审查备用 key
- `BIDEXPERT_QDRANT_LLM_RERANK_ENABLED`：是否启用 LLM rerank（默认 false）
- `BIDEXPERT_QDRANT_LLM_RERANK_CANDIDATE_LIMIT`：LLM rerank 候选数
- `BIDEXPERT_QDRANT_LLM_RERANK_TOP_K`：LLM rerank 输出上限
- `BIDEXPERT_LANGEXTRACT_DEFAULT_MODEL`：可选，LangExtract 默认模型（接口未传 `model_id` 时使用）

国产模型切换示例：

```bash
# CN_DEBUG（低成本调试）
export MODEL_REGISTRY_PATH=app/config/model_registry.cn.debug.json
export SECTION_ROUTING_PATH=app/config/section_routing.cn.json

# CN_PROD（质量优先生产）
export MODEL_REGISTRY_PATH=app/config/model_registry.cn.prod.json
export SECTION_ROUTING_PATH=app/config/section_routing.cn.json
```

## 注意

- 生产部署必须提供真实 TLS 证书：`deploy/nginx/certs/tls.crt` 与 `deploy/nginx/certs/tls.key`，不再自动生成自签名证书。
- OCR 依赖 `tesseract` 系统二进制；若缺失将自动退回非 OCR 文本提取。
- 专家库接口支持可选 `ocr_provider` 覆盖（`glm-ocr/tesseract/hunyuan/docai`）：
  - `POST /v1/expert-library/convert-upload`
  - `POST /v1/expert-library/ingest-upload`
  - `POST /v1/expert-library/ingest-uploads`
- 证据不足、证据近到期或验证失败时，系统返回 `NEED_HUMAN_INPUT`。
- 命中报价熔断时，系统阻断处理。
- UI 的“BYOK 配置”页可完成：创建 profile -> 测试 -> 绑定策略 -> 生成验证。
- UI 的“AI 模型设置”页支持录入 GLM-OCR `API Key/Base URL/Model`（保存在浏览器侧，按请求覆盖到 OCR 链路）。
- UI 的“招标关键分析”页可完成：上传招标文件 -> 自动拆解分析 -> 分类查看关键要求与评分要点。
- UI 的“本地专家库”页可完成：历史投标文件上传入库 + 结构化资料入库（规范/公司业绩/公司资质/项目管理人员资质及业绩）-> 文档/Chunk 查询。
- UI 的“本地专家库”上传支持 `LangExtract model_id`（下拉预设 + 可手填；留空走后端默认）。
- 专家库推荐流程：先 `convert-upload` 结构化预览，再 `convert-confirm` 入库（分块/向量化/embedding）；`rerank` 仅在检索阶段生效。
