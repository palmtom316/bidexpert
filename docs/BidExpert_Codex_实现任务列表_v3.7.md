# BidExpert（v3.7-audit-fixes / 818a297）— 可直接喂给 Codex 的实现任务列表  
目标：让仓库满足你定义的流程里**两条关键默认值**与**可选项**：  
- 文档结构化转换：默认 OCR = **glm-ocr**，且在结构化转换模块可选其他 OCR（tesseract / hunyuan / docai…）  
- 专家库入库（切片/向量化/embedding/rerank）：这些“检索侧”能力可单独设置商用 API，并把默认推荐链调整为 **qwen 3.5**（生成/抽取/评审/改写等）  
- （可选增强）rerank 支持使用商用 API（qwen 3.5）而不是仅本地 cross-encoder/lexical

> 约束：尽量不破坏现有 API（只新增可选参数/字段），对旧 UI/旧调用保持兼容。

---

## 0. 快速定位（便于 Codex 读链路）
### 结构化转换入口
- API：`POST /v1/expert-library/convert-upload`  
  - 定义：`app/api/endpoints/evidence.py::expert_library_convert_upload`  
  - handler：`app/api/handlers/evidence_expert_render.py::expert_library_convert_upload_handler`  
  - service：`app/services/expert_library.py::convert_upload_to_structured`  
  - 解析：`app/services/ingest/file_router.py::ingest_upload_bytes` → `app/services/pdf_ingest.py::extract_pages_v2`（PDF OCR 回退）

### 专家库入库入口（批量）
- API：`POST /v1/expert-library/ingest-uploads`  
  - 定义：`app/api/endpoints/evidence.py::expert_library_ingest_uploads`

### OCR 适配器
- `app/services/adapters/ocr.py::create_ocr_adapter`  
- 当前支持：`hunyuan/docai`；PDF 中 tesseract 走本地分支（`pdf_ingest.extract_pages_v2`）

### 向量化/Embedding/Rerank
- `app/services/qdrant_store.py`  
  - embedding：`resolve_profile_for_task(task_type="EMBED")` + `app/services/embedding.py::embed_text`（OpenAI-compatible `/embeddings`）  
  - rerank：lexical +（可选）sentence-transformers cross-encoder

### 模型默认链（fallback chain）
- `app/config/model_registry.json` → `app/llm/model_registry.py::get_fallback_chain/default_model_for_role`

---

# Epic A：GLM-OCR 接入 + 设为默认 OCR

## Task A1：新增 GLM-OCR 的 OCRAdapter（OpenAI-compatible 视觉 OCR 方式）
**目标**：在 `app/services/adapters/ocr.py` 中支持 `provider="glm-ocr"`，并能用 OpenAI-compatible 的 `/chat/completions` 进行图片文字识别。

### 修改文件
- `app/services/adapters/ocr.py`
- `app/core/config.py`

### 具体改动
1) 在 `Settings` 增加配置项（并给出 env 变量名注释）：
- `glm_ocr_api_key: str | None = None`
- `glm_ocr_base_url: str | None = None`  （例：`https://anyrouter.top/v1` 或你自建网关 `/v1`）
- `glm_ocr_model: str = "glm-ocr"`（允许后续切换到具体版本名）

并把默认 OCR provider 改为：
- `ocr_provider: str = "glm-ocr"`（原为 tesseract）

2) 在 `ocr.py` 增加类：
- `class GLMOCRAdapter(OCRAdapter): provider="glm-ocr"`
- `extract_image_bytes(image_bytes, page_no=None) -> str`：  
  - base64 编码 `image_bytes` 为 `data:image/png;base64,...`
  - POST `"{base_url}/chat/completions"`
  - body（示例）：
    ```json
    {
      "model": "glm-ocr",
      "messages": [{
        "role": "user",
        "content": [
          {"type": "text", "text": "请识别图片中的文字并尽量保持段落/列表结构，只输出文本。"},
          {"type": "image_url", "image_url": {"url": "data:image/png;base64,...."}}
        ]
      }],
      "temperature": 0
    }
    ```
  - 解析返回：优先取 `choices[0].message.content`（string 或 list 都要兼容）

3) `create_ocr_adapter()` 增加分支：
- `if normalized in {"glm-ocr","glmocr","glm_ocr"}: return GLMOCRAdapter()`

4) 错误处理：
- 缺少 key/base_url 时报 `OCRAdapterUnavailableError`
- 请求失败/响应结构不匹配时报 `OCRAdapterUnavailableError`

### 验收标准（Acceptance）
- 未显式传 provider 时，配置了 `GLM_OCR_*` 后会优先使用 GLM-OCR
- GLM-OCR 失败时，PDF OCR 流程仍能 fallback 到本地 tesseract（后续 Task A3 会补更清晰日志）

### 最小测试（pytest）
新增：`tests/test_ocr_adapter_glm.py`
- 用 `monkeypatch` 模拟 settings（key/base_url/model）并 mock httpx 返回
- 断言能解析返回文本；错误时抛 `OCRAdapterUnavailableError`

---

## Task A2：让 PDF OCR 调用链支持“指定 provider 覆盖默认”
**目标**：支持 per-request 传 `ocr_provider`，不必只能用全局 settings。

### 修改文件
- `app/services/pdf_ingest.py`
- `app/services/ingest/file_router.py`
- `app/services/expert_library.py`

### 具体改动
1) 修改 `pdf_ingest.extract_pages_v2` 签名：
```py
def extract_pages_v2(pdf_bytes: bytes, enable_ocr_fallback: bool = True, dpi: int | None = None, ocr_provider: str | None = None) -> list[PageExtract]:
```

2) 修改 `_ocr_page_with_configured_provider`：
- 入参增加 `ocr_provider`
- `adapter = create_ocr_adapter(ocr_provider or settings.ocr_provider)`

3) 修改 `extract_pages_v2` 内 provider 判定：
- `provider = (ocr_provider or settings.ocr_provider or "tesseract").strip().lower()`

4) 修改 `file_router.ingest_upload_bytes` 与 `_pdf_payload()`：
- 增加参数 `ocr_provider: str | None = None`
- 调 `extract_pages_v2(..., ocr_provider=ocr_provider)`

5) 修改 `expert_library._extract_upload_blocks`：
- 增加参数 `ocr_provider: str | None = None`
- 调 `ingest_upload_bytes(..., ocr_provider=ocr_provider)`

6) 修改 `expert_library.ingest_historical_pdf`、`convert_upload_to_structured`：
- 都新增入参 `ocr_provider: str | None = None`
- 传给 `_extract_upload_blocks` 或 `ingest_upload_bytes`

### 验收标准
- 同一运行环境下：全局默认仍为 glm-ocr，但某次请求传 `ocr_provider=tesseract` 时能强制走本地 OCR 分支
- `.docx` 路径不受影响（忽略 ocr_provider）

### 最小测试
`tests/test_pdf_ingest_ocr_override.py`
- mock `create_ocr_adapter` 与 `_ocr_page_with_fitz`：传入不同 ocr_provider 时走不同分支

---

## Task A3：增强“页级 meta/source”标注（便于审计）
**目标**：让产出的 `page_meta` / `PageExtract.source` 能明确显示用的是哪个 OCR provider，方便你后续排查转换质量。

### 修改文件
- `app/services/pdf_ingest.py`
- `app/services/ingest/file_router.py`

### 具体改动
- OCR 成功时，把 `PageExtract.source` 从 `"pypdf+ocr"` 改成：`f"pypdf+ocr:{provider}"`  
- `file_router._pdf_payload` 的 `page_meta[page_no]["source"]` 同步改为该字符串

### 验收标准
- 转换 artifacts/meta 中能看到每页来源（pypdf / pypdf+ocr:glm-ocr / pypdf+ocr:tesseract）

---

# Epic B：结构化转换模块内可选 OCR（API + UI）

## Task B1：convert-upload / ingest-upload(s) API 增加 ocr_provider（Form 字段）
**目标**：不破坏现有接口，仅新增可选参数。

### 修改文件
- `app/api/endpoints/evidence.py`
- `app/api/handlers/evidence_expert_render.py`

### 具体改动
1) `expert_library_convert_upload` 新增：
```py
ocr_provider: str | None = Form(default=None),
```
并传入 handler

2) `expert_library_ingest_upload` / `expert_library_ingest_uploads` 同样新增 `ocr_provider`（批量入口很重要）

3) handler 对应函数签名新增 `ocr_provider`，并在调用 service 时传入：
- `convert_upload_to_structured_fn(..., ocr_provider=(ocr_provider or "").strip() or None)`
- `ingest_historical_pdf_fn(..., ocr_provider=...)`

### 验收标准
- 不传 ocr_provider：行为与现在一致（使用 settings 默认）
- 传 ocr_provider：会覆盖默认

---

## Task B2：UI 增加 OCR 选择控件 + 传参
**目标**：在“文档结构化转换”区域增加 OCR provider 下拉框；批量入库也可选（建议同一个控件复用）。

### 修改文件
- `app/ui/index.html`
- `app/ui/app.js`

### 具体改动（建议）
1) 在结构化转换表单中新增：
- `<select id="convertOcrProvider">`
  - `glm-ocr`（默认）
  - `tesseract`
  - `hunyuan`
  - `docai`

2) 在 `app/ui/app.js` 的 convert-upload FormData 中追加：
```js
const ocrProvider = $("#convertOcrProvider").value;
if (ocrProvider) formData.append("ocr_provider", ocrProvider);
```

3) 批量入库（`/v1/expert-library/ingest-uploads`）同理追加一个选择项（可独立 `#ingestOcrProvider`）
- formData.append("ocr_provider", ...)

### 验收标准
- UI 能选择 OCR provider 并成功转换
- 若选 hunyuan/docai 而未配置 key/base_url，应在 UI 结果 `warnings` 或 `detail` 中看到明确报错（后端返回 400）

---

## Task B3：后端对 ocr_provider 做 allowlist 校验
**目标**：避免用户传任意字符串导致隐式行为不一致。

### 修改文件
- 推荐放在 `app/services/adapters/ocr.py` 或 `app/services/pdf_ingest.py`（更接近使用点）

### 具体改动
- 定义 allowlist：`{"glm-ocr","tesseract","local","hunyuan","docai",""}`  
- 超出 allowlist：抛 `ValueError("unsupported ocr provider: ...")` → API 返回 400

---

# Epic C：把“默认商用链”调整为 qwen 3.5（不影响 BYOK，可被覆盖）

> 说明：你已经有 `ProjectModelPolicy`（extract/generate/review/embed/query_rewrite/program_support）和 fallback chain 机制。这里做的是“默认顺序”调整；项目级 policy 仍然可以覆盖。

## Task C1：model_registry.json 增加 qwen3.5 并调整 role_defaults 顺序
### 修改文件
- `app/config/model_registry.json`

### 具体改动
1) 在 `models` 里新增（示例）：
```json
{
  "provider": "qwen",
  "model_name": "qwen3.5",
  "roles": ["EXTRACT","GENERATE","REVIEW","QUERY_REWRITE"],
  "capabilities": ["reasoning","generation","json_schema"],
  "max_input_tokens": 8192,
  "supports_json_schema": true,
  "supports_tool_calling": false
}
```

2) 把 `role_defaults` 的顺序改成“qwen3.5 优先”：
- `EXTRACT`: `["qwen:qwen3.5", ...]`
- `GENERATE`: `["qwen:qwen3.5", ...]`
- `REVIEW`: `["qwen:qwen3.5", ...]`
- `QUERY_REWRITE`: `["qwen:qwen3.5", ...]`

> 注意：`EMBED` 目前默认是 openai/voyage；如果你坚持“默认也用 qwen 3.5 做 embedding”，需要你的 qwen 网关支持 `/embeddings`，否则会失败。更现实做法是：  
> - `EMBED` 默认 `qwen:text-embedding-*`（若你有）或保持 openai/voyage；  
> - 由项目 policy 的 `embed_profile_id` 指向你配置的 embedding provider profile。

### 验收标准
- 不配置 project policy 时，`default_model_for_role("GENERATE")` 返回 qwen3.5
- 旧链仍可 fallback（openai/gemini/deepseek）

### 最小测试
`tests/test_model_registry_defaults.py`
- 断言 `get_fallback_chain(ModelRole.GENERATE)[0] == ("qwen","qwen3.5")`

---

# Epic D（可选增强）：让 Rerank 也能用商用 API（qwen 3.5）

> 目前 rerank 是 lexical + 本地 cross-encoder（可选）。若要满足“rerank 可单独设置商用 API”，建议引入 `RERANK` role + profile + LLM rerank。

## Task D1：新增 ModelRole.RERANK + policy 字段 rerank_profile_id
### 修改文件
- `app/llm/roles.py`
- `app/schemas/contracts.py`
- `app/models/tables.py`
- `app/services/byok/profiles.py`
- （若有 alembic）新增迁移脚本

### 具体改动
1) `ModelRole` 增加 `RERANK`
2) `ProjectModelPolicyUpsertRequest/Response` 增加：
- `rerank_profile_id: str | None = None`
3) `ProjectModelPolicy` 表新增列：
- `rerank_profile_id`（FK provider_profile.id）
- 并在 `concurrency_limits` 默认里加 `"rerank": 2`
4) `resolve_profile_for_task` 映射 `role.value == "RERANK"` 到 `policy.rerank_profile_id`

### SQLite / Postgres 迁移建议
- SQLite(dev)：删除 db 文件后 `init_db()` 重建
- Postgres(prod)：用 Alembic 生成 revision 增加列与默认值

---

## Task D2：在 qdrant_store 中引入 LLM rerank（可开关）
### 修改文件
- `app/services/qdrant_store.py`
- `app/core/config.py`

### 具体改动
1) Settings 新增：
- `qdrant_llm_rerank_enabled: bool = False`
- `qdrant_llm_rerank_candidate_limit: int = 30`
- `qdrant_llm_rerank_top_k: int = 12`（或复用 prompt_top_n）
2) 在 `QdrantStore.search()` rerank 分支中：
- 若 `qdrant_llm_rerank_enabled`：  
  - 取 fused candidates（limit = candidate_limit）  
  - 调 LLM 让它输出 top_k 的 chunk_id 顺序（JSON schema：`{"ranked_chunk_ids":[...]}`）  
  - 用该顺序重排并返回  
- 若 LLM 失败：fallback 到 `_cross_encoder_rerank_hits` / `_rerank_hits`

3) LLM 调用方式（最小可行）：
- 直接用 `resolve_profile_for_task(task_type="RERANK")` 得到 provider/base_url/api_key/model
- 使用 OpenAI-compatible `/chat/completions`（跟 byok profile 测试一致）
- Prompt 输入：query + 候选（chunk_id + text 截断 500~800 chars）
- 输出 JSON（ranked_chunk_ids）

### 验收标准
- 开关打开时：rerank 会走 LLM（成功情况下）
- LLM 不可用时：仍能退回本地 rerank，不影响生成

### 最小测试
`tests/test_qdrant_llm_rerank.py`
- mock resolve_profile_for_task + mock httpx 返回 ranked ids
- 断言返回顺序与 ranked ids 一致

---

# Epic E：文档 & 运行说明（让团队能用）
## Task E1：补充 README / env.example
### 修改文件
- `README.md` 或 `docs/ocr.md`（任选）
- `.env.example`（若存在）

### 内容要点
- 如何配置 GLM-OCR：
  - `GLM_OCR_API_KEY=...`
  - `GLM_OCR_BASE_URL=https://anyrouter.top/v1`
  - `GLM_OCR_MODEL=glm-ocr`
- OCR provider 可选值说明
- qwen3.5 默认链说明（以及如何通过 ProjectModelPolicy 覆盖）

---

## 交付清单（Codex 输出应该包含）
- 代码改动（按 task 分支提交）
- 新增/更新单测
- 更新 `.env.example` / 文档
- （若做 Epic D）Alembic migration + SQLite init 指南

---

## 建议的执行顺序（最省回滚）
1. A1 → A2 → B1 → B2 → B3（先把 glm-ocr 与 UI/参数打通）
2. C1（再改默认链）
3. D1 → D2（最后做 rerank 商用化，改动最大）

