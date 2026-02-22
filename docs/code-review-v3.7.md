# BidExpert release/V1.0 代码审核报告

> 审核基准：`AI_Programming_Prompt_v3.7_Quality_Maximized.md` 及 `AI_Tender_System_Technical_Whitepaper_v3.7_Quality_Maximized.md`
>
> 审核日期：2026-02-15

---

## 一、严重问题（阻塞性 / P0）

### 1. Embedding 是伪实现，RAG 管线无法真正工作

**文件**：`app/services/embedding.py:10-27`

`embed_text()` 使用 SHA1 hash 生成伪向量，没有调用任何真实 Embedding 模型（如 `text-embedding-3-large`）。同时 `qdrant_vector_size` 配置为 256，而 `text-embedding-3-large` 实际输出 3072 维。

**影响**：整个语义检索链路在生产环境下不可用。

### 2. 工作流章节管线任务编排断裂

**文件**：`app/api/routes.py:530-531`

```python
validate_task = section_validate_task.delay("", [], [])   # 空参数！
render_task = render_export_task.delay([])                 # 空参数！
```

四个 Celery 任务完全独立发射，无 chain/chord 编排——校验任务收不到生成结果，渲染任务收不到校验结果。

**影响**：最小闭环的"生成 → 校验 → 导出"管线实际断裂。

### 3. 生成/抽取 Fallback 链未自动级联

**文件**：`app/services/generation_pipeline.py:131-154`

白皮书要求"抽取失败自动 fallback：Gemini → GPT-5 → DeepSeek"。但 `generate_with_profile` 只尝试一个 provider，失败后直接回退到本地模板拼接，没有按 `get_fallback_chain()` 逐个尝试备选模型。

**影响**：单一模型不可用即导致生成降级为简单文本拼接，质量无法保障。

### 4. 缺少 BM25 / 混合检索

**文件**：`app/services/qdrant_store.py`

白皮书明确要求"Hybrid Retrieval（Vector + BM25）"，但当前仅实现向量检索，没有 BM25 索引和融合排序。

**影响**：检索召回率不足，尤其在关键词精确匹配场景下表现差。

---

## 二、重要问题（P1）

### 5. model_registry.yaml 实际是 JSON 格式

**文件**：`app/config/model_registry.yaml`、`app/llm/model_registry.py:24-29`

文件内容为 JSON，但扩展名是 `.yaml`。代码使用 `json.loads()` 解析——如果有人按文件名提供 YAML 格式数据会直接报错。

**建议**：改为 `.json` 或引入 YAML 解析器。

### 6. HTTP 客户端不适合生产 LLM 调用

**文件**：`app/services/adapters/providers.py:86-120`

使用 `urllib.request` 同步调用，timeout 仅 12 秒。LLM 推理通常需要 30-120 秒，几乎必然超时。

**建议**：使用 `httpx`（已在 dev 依赖中）+ async，或至少增大超时至 120 秒。

### 7. Voyage Adapter 缺失

**文件**：`app/services/adapters/registry.py`

Model Registry 注册了 `voyage:voyage-law-2`，但无 VoyageAdapter。Voyage API 不兼容 OpenAI 格式，回退到 MockAdapter 会产生伪结果。

### 8. 并发控制未生效

**文件**：`app/models/tables.py`（`ProjectModelPolicy.concurrency_limits`）

`concurrency_limits` 在数据库中存储但从未被任何代码读取和执行。无 semaphore 或 rate limiter 落地。

### 9. 内存缓存跨进程不共享

**文件**：`app/services/semantic_cache.py`、`app/services/governance.py`

- `semantic_cache.py` 使用 `dict + threading.Lock`，多 worker 进程间不共享。
- `governance.py` 的预算状态同理，进程重启即丢失。

**建议**：改用 Redis 作为缓存和预算后端。

### 10. Context Compression 未实现

白皮书要求 RAG 阶段有"Context Compression"，但证据文本直接全量传入 LLM prompt，缺少上下文压缩模块。

### 11. 路径遍历安全风险

**文件**：`app/services/word_renderer.py:21-31`

`render_word()` 接受用户传入的 `output_path` 和 `template_path`，无任何路径校验/沙箱限制，可被利用写入任意位置。

---

## 三、中等问题（P2）

### 12. FastAPI 已废弃的生命周期 API

**文件**：`app/main.py:22-27`

使用 `@app.on_event("startup")`，在 FastAPI 0.109+ 已弃用。应迁移到 `lifespan` 上下文管理器。

### 13. `datetime.utcnow()` 已弃用

**文件**：`app/models/tables.py`、`app/services/byok/profiles.py`

大量使用 `datetime.utcnow()`，Python 3.12 起已弃用。应改为 `datetime.now(datetime.UTC)`。

### 14. SSE 生成器类型标注错误

**文件**：`app/api/routes.py:413`

`events()` 标注返回 `str`，实际应为 `AsyncGenerator[str, None]`。

### 15. 目录结构不一致

- 存在空的 `app/worker/` 和实际代码在 `app/workers/`。
- `app/extract/` 是空包，抽取逻辑分散在 `historical_extractor.py` 和 `tender_parser.py`。
- `app/rag/` 也是空包，逻辑在 `services/rag_flow.py`。

与白皮书要求的目录规范（`worker/`、`extract/`、`rag/`）不对应。

### 16. DraftGenerationResponse 默认值过时

**文件**：`app/schemas/contracts.py:176-177`

默认 `llm_provider="Qwen"`、`llm_model="Qwen3-Max"`，而 release/V1.0 首选应为 Gemini 3 Pro。

---

## 四、修改计划

| 优先级 | 任务 | 涉及文件 | 描述 |
|:---|:---|:---|:---|
| **P0-1** | 实现真实 Embedding 调用 | `embedding.py`, `qdrant_store.py`, `config.py` | 调用 OpenAI Embedding API（text-embedding-3-large），向量维度改为 3072，保留伪实现为测试模式 |
| **P0-2** | 修复工作流任务编排 | `routes.py`, `workers/tasks.py` | 使用 Celery `chain()` 或 `chord()` 串联 extract → generate → validate → render |
| **P0-3** | 实现模型级联 Fallback | `generation_pipeline.py`, `llm_gateway.py` | 调用失败时按 `get_fallback_chain()` 逐个尝试，而非直接回退本地模板 |
| **P0-4** | 添加 BM25 混合检索 | `qdrant_store.py`（或新增 `bm25_store.py`） | 利用 Qdrant 内置 BM25 或独立 BM25 索引，实现 RRF 融合排序 |
| **P1-1** | 替换 HTTP 客户端 | `providers.py` | `urllib.request` → `httpx.Client`，timeout 调至 120s，支持 streaming |
| **P1-2** | 添加 Voyage Adapter | `providers.py`, `registry.py` | 新增 VoyageAdapter 支持 Voyage Embedding API |
| **P1-3** | 落地并发控制 | 新增 `concurrency_limiter.py` | 基于 Redis 信号量，在 Gateway 层检查并发上限 |
| **P1-4** | 缓存/预算迁移 Redis | `semantic_cache.py`, `governance.py` | 内存 dict → Redis，支持多进程 + 持久化 |
| **P1-5** | 实现 Context Compression | 新增 `context_compressor.py` | 在 RAG 检索后、生成前，用快速模型压缩上下文 |
| **P1-6** | 修复路径遍历风险 | `word_renderer.py` | 校验 `output_path` 在允许的目录内，禁止 `..` |
| **P2-1** | 修正 YAML/JSON 命名 | `model_registry.yaml` → `.json` 或改用 YAML 解析器 | 保持文件名与内容一致 |
| **P2-2** | 迁移 FastAPI lifespan | `main.py` | `on_event("startup")` → `lifespan` context manager |
| **P2-3** | 修复 datetime 弃用 | `tables.py`, `profiles.py` 等 | `utcnow()` → `datetime.now(UTC)` |
| **P2-4** | 整理目录结构 | `worker/`, `extract/`, `rag/` | 将分散的逻辑归并到白皮书要求的模块中，删除空包 |
| **P2-5** | 修正默认值 | `contracts.py` | DraftGenerationResponse 默认 provider/model 对齐 release/V1.0 首选 |

---

## 五、建议执行顺序

```
P0-1 (Embedding) → P0-2 (任务编排) → P0-3 (Fallback 链) → P0-4 (混合检索)
    → P1-1 (HTTP 客户端) → P1-6 (路径安全) → P1-2 (Voyage)
    → P1-3 (并发控制) → P1-4 (Redis 缓存) → P1-5 (Context Compression)
    → P2-*
```

P0 全部完成后方可进入集成测试，P1 完成后具备生产部署条件。
