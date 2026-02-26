# Bidexpert V2.0 Gap Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对齐 `docs/Bidexpert V2.0 系统升级交付文档.md` 的强制能力，补齐当前代码在 G2 红线、G3/G6 评分、Addendum 穿透、资产池隔离、G5 防篡改与证据锚定、G0~G8 编排方面的缺口。

**Architecture:** 在现有 FastAPI + SQLAlchemy + Celery 架构上做增量重构：新增 v2.0 领域实体（addendum、mandatory clause、bid asset pool、chapter evidence link、generation run），引入独立 RedlineEngine/ScorecardEngine/ScoringEngineV2 服务，保留 v1 接口兼容，新增 v2 路由与验收测试矩阵。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, Pydantic, pytest, Jinja2, python-docx。

---

## Gap Matrix (Spec vs Current)

| Spec 条款 | 当前状态 | 差距结论 |
|---|---|---|
| G2 阻断式红线审查（P0/P1、缺件看板、Override 审计） | 仅有 `tender.fatal_gate` 布尔通过/失败，无 P0/P1 结构、无 override API | **缺失** |
| Addendum 覆盖强制条款并触发章节失效告警 | 仅 `DocKind.CLARIFICATION` 枚举，未参与流水线 | **缺失** |
| 资质/人员/社保/业绩的结构化校验与跨项目专职冲突 | 仅 `assets/repository.py` 基础 SQL 查询，未做社保/并行冲突/组合优化 | **部分实现** |
| G2.6 参数负偏离与工期算术硬校验 | 无设备参数 >= 规则，无日期-工期算术引擎 | **缺失** |
| `/api/v2/redline/check` + `RedlineReport` 结构返回 | 无 v2 redline 路由 | **缺失** |
| G3 多步评分提取（表格定位->语义结构化->人工确认） | `scoring_extractor.py` 为正则行抽取 | **缺失** |
| G6 评分公式（cov/evi/spec/risk）+ deductions/evidence_map | `scoring_engine.py` 为 PASS/FAIL 加权求和 | **缺失** |
| 数据库新增实体（TENDER_ADDENDUM/BID_ASSET_POOL/CHAPTER_EVIDENCE_LINK/GENERATION_RUN 等） | `app/models/tables.py` 无上述实体 | **缺失** |
| G5 Frozen Blocks + MD5 防篡改 | 导出链路无冻结块 hash 校验 | **缺失** |
| 实体装配模式（Jinja2 渲染资产表） | 无 BID_ASSET_POOL 驱动装配 | **缺失** |
| 严格事实锚定（章节陈述绑定证据链接） | 仅返回 `evidence_ids`，无章节级持久化链接表 | **缺失** |
| 模型路由 role_scope + JSON 提取强制 `response_format=json_object` | 现有按 task role 路由；提取链路未统一强制 JSON 模式 | **部分实现** |
| G0~G8 可恢复编排（GenerationRun + run_step 幂等） | 现有 `WorkflowRun`/`TenderImportRun`，未覆盖 v2 全链路状态机 | **部分实现** |

---

### Task 1: Add v2.0 Domain Schema and Migration Baseline

**Files:**
- Modify: `app/models/tables.py`
- Create: `migrations/versions/<revision>_add_v20_redline_scorecard_generation_tables.py`
- Create: `app/tests/test_v20_schema_contract.py`

**Step 1: Write failing tests**
- 断言存在以下实体与关键字段：`TenderAddendum.parsed_overrides_json`、`MandatoryClause`、`BidAssetPool.ownership_role`、`ChapterEvidenceLink`、`GenerationRun`、`ScoreEvaluation`、`ComplianceReport`。

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_schema_contract.py -q`
Expected: FAIL（模型/迁移未实现）。

**Step 3: Implement minimal schema + migration**
- 新增表与索引，保留 v1 表不破坏。
- 为 `GenerationRun` 设计 `current_step/step_status/retry_count/resume_from_step`。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_schema_contract.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/models/tables.py migrations/versions app/tests/test_v20_schema_contract.py
git commit -m "feat: add v2.0 core domain tables and migration baseline"
```

### Task 2: Implement Addendum Penetration and Effective Clause Merge

**Files:**
- Create: `app/services/addendum_parser.py`
- Create: `app/services/mandatory_clause_service.py`
- Modify: `app/tender/pipeline.py`
- Modify: `app/api/endpoints/tender.py`
- Create: `app/tests/test_v20_addendum_override.py`

**Step 1: Write failing tests**
- `test_addendum_overrides_mandatory_clause_by_clause_no`
- `test_addendum_marks_generated_chapters_stale`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_addendum_override.py -q`
Expected: FAIL（服务与持久化缺失）。

**Step 3: Implement minimal addendum flow**
- 解析澄清文件到 `TenderAddendum`。
- 计算“生效强制条款集”并覆盖旧条款。
- 标记受影响章节为 stale（触发告警状态）。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_addendum_override.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/addendum_parser.py app/services/mandatory_clause_service.py app/tender/pipeline.py app/api/endpoints/tender.py app/tests/test_v20_addendum_override.py
git commit -m "feat: support addendum override and chapter invalidation alerts"
```

### Task 3: Build G2 Redline Engine API (P0/P1 + Readiness Dashboard + Override)

**Files:**
- Create: `app/services/redline_engine.py`
- Create: `app/api/endpoints/redline_v2.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/api/routes.py`
- Create: `app/tests/test_v20_redline_api.py`

**Step 1: Write failing tests**
- `test_redline_returns_blocked_on_p0_negative_deviation`
- `test_redline_returns_readiness_missing_items`
- `test_redline_override_requires_audit_log`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_redline_api.py -q`
Expected: FAIL（路由与 schema 缺失）。

**Step 3: Implement redline engine + endpoint**
- 新增 `/api/v2/redline/check`。
- 输出 `status/findings/readiness_missing_items`。
- 新增 override 接口（人工确认 + audit log）。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_redline_api.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/redline_engine.py app/api/endpoints/redline_v2.py app/schemas/contracts.py app/api/routes.py app/tests/test_v20_redline_api.py
git commit -m "feat: implement v2 redline engine API with severity and override audit"
```

### Task 4: Enforce Asset Pool Isolation and Personnel Matching

**Files:**
- Create: `app/services/bid_asset_pool_service.py`
- Create: `app/services/personnel_matcher.py`
- Modify: `app/tender/assets/repository.py`
- Create: `app/tests/test_v20_asset_pool_isolation.py`

**Step 1: Write failing tests**
- `test_bid_asset_pool_prevents_cross_project_entity_usage`
- `test_personnel_matcher_enforces_social_security_and_no_active_project`
- `test_personnel_matcher_returns_best_team_combination`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_asset_pool_isolation.py -q`
Expected: FAIL。

**Step 3: Implement SQL-first asset isolation/matcher**
- 所有人员/业绩/设备查询以 `bid_document_id + ownership_role` 过滤。
- 增加社保月份、并行项目占用冲突约束。
- 输出最优团队组合与证据列表。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_asset_pool_isolation.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/bid_asset_pool_service.py app/services/personnel_matcher.py app/tender/assets/repository.py app/tests/test_v20_asset_pool_isolation.py
git commit -m "feat: add bid asset pool isolation and SQL-based personnel matcher"
```

### Task 5: Implement G3 Scorecard Parsing Pipeline (Table->JSON->Human Confirm)

**Files:**
- Create: `app/services/scorecard_parser.py`
- Create: `app/api/endpoints/scorecard_v2.py`
- Modify: `app/api/routes.py`
- Create: `app/tests/test_v20_scorecard_parser.py`

**Step 1: Write failing tests**
- `test_scorecard_parser_extracts_table_blocks_then_structures_json`
- `test_scorecard_parser_uses_response_format_json_object`
- `test_scorecard_requires_human_confirm_before_lock`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_scorecard_parser.py -q`
Expected: FAIL。

**Step 3: Implement parser and confirmation lifecycle**
- 表格检测与结构化抽取分两步执行。
- LLM 调用强制 `response_format={"type":"json_object"}`。
- 新增确认接口将 scorecard 状态锁定。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_scorecard_parser.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/scorecard_parser.py app/api/endpoints/scorecard_v2.py app/api/routes.py app/tests/test_v20_scorecard_parser.py
git commit -m "feat: add v2 scorecard parsing pipeline with human confirmation"
```

### Task 6: Implement G6 Scoring Formula and Structured Deductions

**Files:**
- Create: `app/services/scoring_engine_v2.py`
- Modify: `app/api/endpoints/workflow.py`
- Modify: `app/schemas/contracts.py`
- Create: `app/tests/test_v20_scoring_formula.py`

**Step 1: Write failing tests**
- `test_score_formula_matches_v20_weights_and_clamp`
- `test_negative_deviation_or_arithmetic_conflict_forces_zero`
- `test_scoring_output_contains_deductions_and_evidence_map`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_scoring_formula.py -q`
Expected: FAIL。

**Step 3: Implement scoring v2 service**
- 实现 `score(p)=weight*clamp(0.55*cov+0.25*evi+0.20*spec-0.50*risk,0,1)`。
- 输出 `score_total/deductions/evidence_map`。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_scoring_formula.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/scoring_engine_v2.py app/api/endpoints/workflow.py app/schemas/contracts.py app/tests/test_v20_scoring_formula.py
git commit -m "feat: implement v2 scoring formula with deductions and evidence map"
```

### Task 7: Add G5 Frozen Blocks + Entity Assembly + Chapter Evidence Links

**Files:**
- Create: `app/services/frozen_block_guard.py`
- Create: `app/services/entity_assembly.py`
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/services/word_renderer.py`
- Create: `app/tests/test_v20_frozen_and_entity_assembly.py`

**Step 1: Write failing tests**
- `test_frozen_block_hash_mismatch_blocks_export`
- `test_entity_assembly_renders_bid_asset_pool_tables_via_jinja2`
- `test_generation_persists_chapter_evidence_links`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_frozen_and_entity_assembly.py -q`
Expected: FAIL。

**Step 3: Implement deterministic generation safeguards**
- `[FROZEN]` 块签名与导出前 MD5 校验。
- 类似业绩表/机械表使用 Jinja2 + SQL 数据装配。
- 持久化章节级证据映射（`ChapterEvidenceLink`）。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_frozen_and_entity_assembly.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/frozen_block_guard.py app/services/entity_assembly.py app/services/generation_pipeline.py app/services/word_renderer.py app/tests/test_v20_frozen_and_entity_assembly.py
git commit -m "feat: enforce frozen blocks and entity assembly with chapter evidence links"
```

### Task 8: Upgrade Model Router to role_scope and Enforce JSON-mode Extraction

**Files:**
- Modify: `app/llm/model_registry.py`
- Modify: `app/services/byok/profiles.py`
- Modify: `app/services/adapters/providers.py`
- Create: `app/tests/test_v20_model_router_role_scope.py`

**Step 1: Write failing tests**
- `test_role_scope_router_selects_primary_and_fallback_models`
- `test_structured_extract_calls_include_response_format_json_object`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_model_router_role_scope.py -q`
Expected: FAIL。

**Step 3: Implement router/payload enforcement**
- 支持 `role_scope`（extract/generate/review/render 等）配置。
- 对结构化提取类调用统一注入 JSON Object response format。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_model_router_role_scope.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/llm/model_registry.py app/services/byok/profiles.py app/services/adapters/providers.py app/tests/test_v20_model_router_role_scope.py
git commit -m "feat: add role_scope model routing and enforce json-object extraction mode"
```

### Task 9: Introduce G0~G8 GenerationRun Orchestrator (Idempotent run_step)

**Files:**
- Create: `app/services/generation_run_orchestrator.py`
- Modify: `app/worker/tasks.py`
- Modify: `app/services/workflow_runs.py`
- Create: `app/tests/test_v20_generation_run_orchestrator.py`

**Step 1: Write failing tests**
- `test_run_step_is_idempotent_for_duplicate_delivery`
- `test_generation_run_resume_from_last_successful_step`
- `test_p0_block_prevents_transition_to_generation_steps`

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_v20_generation_run_orchestrator.py -q`
Expected: FAIL。

**Step 3: Implement orchestrator**
- 覆盖 G0~G8 状态机与幂等 `run_step()`。
- 统一失败重试/恢复点写回 `GenerationRun`。

**Step 4: Run tests to verify they pass**
Run: `pytest app/tests/test_v20_generation_run_orchestrator.py -q`
Expected: PASS。

**Step 5: Commit**
```bash
git add app/services/generation_run_orchestrator.py app/worker/tasks.py app/services/workflow_runs.py app/tests/test_v20_generation_run_orchestrator.py
git commit -m "feat: add v2 generation run orchestrator with idempotent step execution"
```

### Task 10: End-to-End Acceptance and Regression Gate

**Files:**
- Create: `tests/test_v20_end_to_end_acceptance.py`
- Modify: `tests/test_tender_integration.py`
- Modify: `docs/Bidexpert V2.0 系统升级交付文档.md` (实现对照勾选区，仅在完成后更新)

**Step 1: Write failing acceptance tests**
- 覆盖 DoD: 负偏离 P0 阻断、缺件看板、资产隔离、实体渲染、防篡改、扣分解释。

**Step 2: Run tests to verify they fail**
Run: `pytest tests/test_v20_end_to_end_acceptance.py -q`
Expected: FAIL。

**Step 3: Execute full verification suite**
Run:
- `pytest app/tests/test_v20_*.py -q`
- `pytest tests/test_v20_end_to_end_acceptance.py -q`
- `pytest app/tests/test_workflow_resume_v11.py tests/test_tender_integration.py -q`

Expected: 全部 PASS。

**Step 4: Commit**
```bash
git add tests/test_v20_end_to_end_acceptance.py tests/test_tender_integration.py app/tests
git commit -m "test: add v2 acceptance suite and verify regression safety"
```

---

## Execution Notes

- 先做数据库与 schema（Task 1）再做服务与 API，避免后续返工。
- v1 路由保持兼容，v2 能力优先挂在 `/api/v2/*`。
- 任何“通过/完成”声明必须以 pytest 输出为准。
- Addendum 与 Redline 为第一优先级，不通过不得进入章节正文生成。

