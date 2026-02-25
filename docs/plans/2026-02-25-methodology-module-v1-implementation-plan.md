# Methodology Module v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按 `docs/methodology_module_v1_0_and_legal_safe_ingestion_and_codex_patch.md` 落地“专家经验提炼模块”，实现前端入口、后端流水线、质量闸门、人工审核、发布入库与方法论优先召回。

**Architecture:** 新增独立的 methodology 域模型与服务层，不复用现有 expert-library 入库链路；抽取任务进入 `methodology_runs`，经 L0/L1/L2/L3 质量闸门后，由人工审核触发发布到 `methodology_snippets` 和 Qdrant `kb_methodology`；写作检索阶段合并 `kb_methodology -> kb_bid_history(expert_chunks_v1) -> kb_standard` 并做风险过滤。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, Qdrant, Vanilla JS, pytest

---

## Approaches

### Approach A: 直接复用 expert-library 流程（最小改动）
- 优点：改动少，上线快。
- 缺点：难实现独立法务闸门与可追溯审核状态；易污染既有专家库语义。

### Approach B: 新增独立 methodology 子系统（推荐）
- 优点：边界清晰，审计链完整，便于后续法律合规扩展。
- 缺点：新增表、API、前端与检索融合，改动面更大。

### Approach C: 仅做 API 包装，底层仍写 expert_chunks_v1
- 优点：开发最快。
- 缺点：无法满足“kb_methodology 独立集合”和“方法论优先召回”的硬要求。

**Recommendation:** 采用 Approach B。

---

### Task 1: Red tests for legal gates and run lifecycle

**Files:**
- Create: `app/tests/test_methodology_pipeline.py`
- Create: `app/tests/test_methodology_api.py`

**Step 1: Write failing tests**
- `test_sanitize_removes_phone_and_id`
- `test_risk_scan_blocks_unknown_source_without_approval`
- `test_similarity_gate_marks_need_edit_when_high_overlap`
- `test_review_required_before_publish`

**Step 2: Run tests to verify they fail**
Run:
- `pytest app/tests/test_methodology_pipeline.py app/tests/test_methodology_api.py -q`
Expected: FAIL（模块/路由尚未实现）

**Step 3: Commit**
```bash
git add app/tests/test_methodology_pipeline.py app/tests/test_methodology_api.py
git commit -m "test: add red tests for methodology gates and lifecycle"
```

### Task 2: Database schema and migration

**Files:**
- Modify: `app/models/tables.py`
- Create: `migrations/versions/<revision>_add_methodology_runs_and_snippets.py`
- Create: `app/tests/test_methodology_migration_contract.py`

**Step 1: Add model enums and tables**
- `MethodologyRun`（run 过程表）
- `MethodologySnippet`（发布资产表）
- 字段覆盖：`source_type/source_note/risk_level/similarity_score/pii_removed/review_status/reviewer/reviewed_at/output_json_path`

**Step 2: Add Alembic migration**
- 建表、必要索引（`review_status`, `risk_level`, `created_at`, `domain`）

**Step 3: Add migration contract test**
- 校验迁移文件存在且包含 `methodology_run`、`methodology_snippet` 关键字段

**Step 4: Run tests**
Run:
- `pytest app/tests/test_methodology_migration_contract.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add app/models/tables.py migrations/versions app/tests/test_methodology_migration_contract.py
git commit -m "feat: add methodology DB schema and migration"
```

### Task 3: Core sanitize/risk/similarity services

**Files:**
- Create: `app/services/methodology/sanitize.py`
- Create: `app/services/methodology/risk_scan.py`
- Create: `app/services/methodology/similarity.py`
- Create: `app/services/methodology/types.py`
- Modify: `app/tests/test_methodology_pipeline.py`

**Step 1: Implement sanitize**
- 复用并补强 PII 规则（公司名/项目名/手机号/身份证/合同号/金额）
- 输出 `sanitized_text`, `pii_removed`, `findings`

**Step 2: Implement risk scan**
- L0：`source_type=unknown` 默认 `high`
- L1：`pii_removed=false` 阻断
- 输出 `risk_level`, `gate_status`

**Step 3: Implement similarity score**
- 3-gram overlap 分数
- 阈值（默认 `0.35`）触发 `need_edit`

**Step 4: Run tests**
Run:
- `pytest app/tests/test_methodology_pipeline.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add app/services/methodology app/tests/test_methodology_pipeline.py
git commit -m "feat: implement methodology sanitize risk and similarity gates"
```

### Task 4: Extraction pipeline and run persistence

**Files:**
- Create: `app/services/methodology/rewrite_and_extract.py`
- Create: `app/services/methodology/pipeline.py`
- Create: `app/services/methodology/repository.py`
- Modify: `app/worker/tasks.py`

**Step 1: Implement rewrite/extract**
- 输入脱敏文本，输出 `structure/template_md/tags/applicability/title/domain`
- 强制 JSON 输出；无效输出转 `FAILED/need_edit`

**Step 2: Implement state transitions**
- `RECEIVED -> SANITIZED -> EXTRACTED -> SCORED -> READY_FOR_REVIEW/NEED_EDIT/FAILED`
- 持久化 `output_json_path` 与质量指标

**Step 3: Add Celery task**
- `tasks.methodology_extract_run` 异步执行 pipeline

**Step 4: Run tests**
Run:
- `pytest app/tests/test_methodology_pipeline.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add app/services/methodology app/worker/tasks.py
git commit -m "feat: add methodology extraction pipeline and async task"
```

### Task 5: Methodology API routes and contracts

**Files:**
- Create: `app/api/endpoints/methodology.py`
- Create: `app/api/handlers/methodology.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/api/routes.py`
- Modify: `app/tests/test_methodology_api.py`

**Step 1: Add API contracts**
- `POST /api/methodology/extract`
- `GET /api/methodology/runs/{run_id}`
- `GET /api/methodology/runs/{run_id}/result`
- `POST /api/methodology/runs/{run_id}/review`
- `POST /api/methodology/runs/{run_id}/publish`
- `GET /api/methodology/snippets`
- `POST /api/methodology/search`

**Step 2: Wire router**
- `routes.py` include methodology router and context dependencies

**Step 3: Implement review gate**
- `review.status != approved` 禁止 publish

**Step 4: Run tests**
Run:
- `pytest app/tests/test_methodology_api.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add app/api/endpoints/methodology.py app/api/handlers/methodology.py app/schemas/contracts.py app/api/routes.py app/tests/test_methodology_api.py
git commit -m "feat: add methodology APIs and review gate"
```

### Task 6: Publish flow (DB + Qdrant kb_methodology)

**Files:**
- Create: `app/services/methodology/publish.py`
- Modify: `app/services/qdrant_store.py`
- Modify: `app/core/config.py`
- Modify: `app/tests/test_methodology_api.py`
- Create: `app/tests/test_methodology_qdrant.py`

**Step 1: Add publish service**
- 写 `methodology_snippets`
- 记录 `snippet_id`、审核人、风险等级、来源审计字段

**Step 2: Add Qdrant collection support**
- 新增 `qdrant_methodology_collection`（默认 `kb_methodology`）
- upsert payload 强制：`risk_level`, `review_status`, `snippet_id`, `source_type`

**Step 3: Add publish/search filters**
- 只允许 `review_status=approved`
- 排除 `risk_level=high`

**Step 4: Run tests**
Run:
- `pytest app/tests/test_methodology_qdrant.py app/tests/test_methodology_api.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add app/services/methodology/publish.py app/services/qdrant_store.py app/core/config.py app/tests/test_methodology_qdrant.py app/tests/test_methodology_api.py
git commit -m "feat: publish methodology snippets to DB and kb_methodology"
```

### Task 7: Retrieval integration with methodology-first strategy

**Files:**
- Modify: `app/rag/rag_flow.py`
- Modify: `app/services/generation_pipeline.py`
- Create: `app/tests/test_methodology_retrieval_priority.py`

**Step 1: Add methodology-first merge**
- 召回顺序：`kb_methodology` -> `expert_chunks_v1` ->（如有）标准库
- 保留现有 rerank 与 key-fact filter

**Step 2: Enforce risk/review filters in generation path**
- 仅注入 `approved + low/medium` 方法论片段

**Step 3: Run tests**
Run:
- `pytest app/tests/test_methodology_retrieval_priority.py -q`
Expected: PASS

**Step 4: Commit**
```bash
git add app/rag/rag_flow.py app/services/generation_pipeline.py app/tests/test_methodology_retrieval_priority.py
git commit -m "feat: integrate methodology-first retrieval strategy"
```

### Task 8: Frontend methodology workspace

**Files:**
- Modify: `app/ui/index.html`
- Modify: `app/ui/app.js`
- Modify: `app/ui/styles.css`

**Step 1: Add methodology panel/card**
- 输入：`source_type`, `note`, `domain`, `tags`, `text/file`
- 操作：提炼、查看 run、审核、发布、检索

**Step 2: Add frontend API bindings**
- 调用 `/api/methodology/*`
- 展示 gate 状态（L0/L1/L2/L3）和 `need_edit` 提示

**Step 3: Smoke check in browser**
Run:
- `uvicorn app.main:app --reload`
Expected: UI 可提交任务、可查看 run、可审核发布

**Step 4: Commit**
```bash
git add app/ui/index.html app/ui/app.js app/ui/styles.css
git commit -m "feat: add frontend workflow for methodology extraction and review"
```

### Task 9: Documentation and operational safeguards

**Files:**
- Modify: `docs/README.md`
- Create: `docs/methodology_module_usage.md`
- Modify: `.env.example`

**Step 1: Document config and legal boundaries**
- `BIDEXPERT_QDRANT_METHODOLOGY_COLLECTION`
- `BIDEXPERT_METHODOLOGY_SIMILARITY_THRESHOLD`
- 红线与闸门说明

**Step 2: Add runbook snippets**
- 审核流程、阻断原因、回滚与追踪方法

**Step 3: Commit**
```bash
git add docs/README.md docs/methodology_module_usage.md .env.example
git commit -m "docs: add methodology module usage and compliance runbook"
```

### Task 10: Final verification before implementation completion

**Files:**
- N/A

**Step 1: Run targeted tests**
Run:
- `pytest app/tests/test_methodology_pipeline.py -q`
- `pytest app/tests/test_methodology_api.py -q`
- `pytest app/tests/test_methodology_qdrant.py -q`
- `pytest app/tests/test_methodology_retrieval_priority.py -q`
- `pytest app/tests/test_expert_library_api.py -q`
- `pytest app/tests/test_qdrant_rerank.py -q`

**Step 2: Run migration + startup smoke**
Run:
- `alembic upgrade head`
- `uvicorn app.main:app --reload`

**Step 3: Expected**
- 六项最小测试全部通过
- 提炼任务必须经过 sanitize + similarity + review 才可 publish
- `kb_methodology` 可检索并返回可追溯 `snippet_id`
- 生成链路可启用方法论优先召回

