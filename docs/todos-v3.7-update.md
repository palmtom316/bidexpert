# BidExpert v3.7 Update Todos

> 来源：`docs/code-review-v3.7.md`  
> 生成日期：2026-02-15

## P0（先完成）

- [x] `P0-1` 真实 Embedding 与维度对齐（3072）  
  文件：`app/services/embedding.py`、`app/services/qdrant_store.py`、`app/core/config.py`
- [x] `P0-2` 工作流任务编排打通（extract -> generate -> validate -> render）  
  文件：`app/api/routes.py`、`app/workers/tasks.py`
- [x] `P0-3` 模型级联 Fallback 真正按链路执行并修复日志计数  
  文件：`app/services/generation_pipeline.py`、`app/services/llm_gateway.py`
- [x] `P0-4` 混合检索（Vector + BM25）并做融合排序  
  文件：`app/services/qdrant_store.py`

## P1（生产可用）

- [x] `P1-1` HTTP 客户端迁移到 `httpx`，超时提升到 120s  
  文件：`app/services/adapters/providers.py`、`pyproject.toml`
- [x] `P1-2` 新增 Voyage 适配能力（避免回退 Mock）  
  文件：`app/services/adapters/providers.py`、`app/services/adapters/registry.py`
- [x] `P1-3` 并发限制落地（读取 model policy 并执行）  
  文件：`app/services/concurrency_limiter.py`、`app/services/llm_gateway.py`
- [x] `P1-4` 缓存/预算迁移 Redis（保留本地兜底）  
  文件：`app/services/semantic_cache.py`、`app/services/governance.py`
- [x] `P1-5` Context Compression（检索后生成前）  
  文件：`app/services/context_compressor.py`、`app/services/generation_pipeline.py`
- [x] `P1-6` 修复 Word 渲染路径遍历风险  
  文件：`app/services/word_renderer.py`、`app/api/routes.py`、`app/core/config.py`

## P2（兼容性与清理）

- [x] `P2-1` model registry 文件命名与内容一致（`.json`）  
  文件：`app/config/model_registry.json`、`app/llm/model_registry.py`、`docs/README.md`
- [x] `P2-2` FastAPI 生命周期迁移到 `lifespan`  
  文件：`app/main.py`
- [x] `P2-3` `datetime.utcnow()` 迁移到 `datetime.now(UTC)`  
  文件：`app/models/tables.py`、`app/services/byok/profiles.py`、`app/services/tender_analysis.py`
- [x] `P2-4` SSE 返回类型标注修正  
  文件：`app/api/routes.py`
- [x] `P2-5` 草稿响应默认模型改为 v3.7 首选  
  文件：`app/schemas/contracts.py`
- [x] `P2-6` 目录结构重构完成（`worker/extract/rag` 承载主实现，旧路径兼容转发）  
  文件：`app/worker/*.py`、`app/extract/*.py`、`app/rag/*.py`、`app/workers/*.py`、`app/services/{historical_extractor,tender_parser,rag_flow}.py`
