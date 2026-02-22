# 投标专家系统 release/V1.0 全量落地 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `docs/投标专家系统_企业级完整落地与Prompt套件_V1.1_合并版.md` 的 release/V1.0 要求全部落地到当前代码库，覆盖异步断点续跑、二阶段检索、父子块、Global Facts、一致性约束、Prompt 套件、证据可视化和 JSONB+GIN 优化。

**Architecture:** 以现有 `workflow_run + celery stage tasks + generation_pipeline + qdrant_store + word_renderer` 为主干，增量加入状态机字段、闸门工件落盘、可恢复执行、检索后处理、事实表约束和结构化输出统一校验。数据库侧通过 SQLAlchemy 类型 + Alembic 迁移完成 JSONB 化与 GIN 索引。

**Tech Stack:** FastAPI, Celery, SQLAlchemy 2, Alembic, Qdrant, Pydantic, python-docx。

---

### Task 1: 断点续跑与闸门工件持久化

**Files:**
- Modify: `app/models/tables.py`
- Modify: `app/services/workflow_runs.py`
- Modify: `app/worker/tasks.py`
- Modify: `app/api/handlers/workflow_generation_review.py`
- Modify: `app/api/routes.py`
- Create: `app/services/workflow_artifacts.py`
- Test: `app/tests/test_workflow_resume_v11.py`

### Task 2: 二阶段检索 + Parent-Child

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/services/expert_chunking.py`
- Modify: `app/services/qdrant_store.py`
- Modify: `app/rag/rag_flow.py`
- Test: `app/tests/test_v11_retrieval_parent_child.py`

### Task 3: Global Facts + 一致性约束 + 结构化自修正

**Files:**
- Create: `app/services/global_facts.py`
- Modify: `app/validator/llm_contracts.py`
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/services/adapters/providers.py`
- Test: `app/tests/test_v11_global_facts_and_schema.py`

### Task 4: Prompt 套件落地

**Files:**
- Create: `app/llm/prompt_suite_v11.py`
- Modify: `app/services/adapters/providers.py`
- Test: `app/tests/test_v11_prompt_suite.py`

### Task 5: Word 证据可视化增强

**Files:**
- Modify: `app/schemas/contracts.py`
- Modify: `app/services/word_renderer.py`
- Test: `app/tests/test_word_evidence_visualization_v11.py`

### Task 6: JSONB+GIN

**Files:**
- Modify: `app/db/types.py`
- Modify: `app/models/tables.py`
- Create: `migrations/versions/<new_revision>_v11_jsonb_gin_and_workflow_fields.py`
- Test: `app/tests/test_v11_jsonb_and_migration_contract.py`

### Task 7: 验证

**Files:**
- N/A

**Verification commands:**
- `pytest app/tests/test_workflow_resume_v11.py -q`
- `pytest app/tests/test_v11_retrieval_parent_child.py -q`
- `pytest app/tests/test_v11_global_facts_and_schema.py -q`
- `pytest app/tests/test_v11_prompt_suite.py -q`
- `pytest app/tests/test_word_evidence_visualization_v11.py -q`
- `pytest app/tests/test_v11_jsonb_and_migration_contract.py -q`
- `pytest app/tests -q`
- `pytest tests -q`
