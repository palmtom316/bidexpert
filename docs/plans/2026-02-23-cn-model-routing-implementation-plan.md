# CN Models + Section Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有 fallback 和 JSON 校验机制的前提下，落地国产模型 registry（debug/prod）与章节级路由（critical 章节 R1 强化 + 强制审查）。

**Architecture:** 扩展 model registry 读取层支持路径覆盖与双格式兼容；新增 section router 独立模块负责 critical 判定与路由计划；在 generation pipeline 中插入可选增强阶段并复用现有 fallback/review 机制；workflow 透传 section_title 以支持按章节标题决策。

**Tech Stack:** Python, FastAPI, Celery, Pydantic, pytest

---

### Task 1: Red tests for section routing

**Files:**
- Create: `app/tests/test_section_router.py`

**Step 1: Write failing tests**
- 覆盖关键词命中 critical
- 覆盖 weight>=threshold 命中 critical
- 覆盖 debug/prod 路由输出包含 base/enhance/review

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_section_router.py -q`
Expected: FAIL（模块/函数不存在）

### Task 2: Red tests for registry env override and CN format

**Files:**
- Modify: `app/tests/test_model_registry_defaults.py`

**Step 1: Write failing tests**
- 覆盖 `MODEL_REGISTRY_PATH` 指向 `roles/providers` 格式可解析
- 覆盖 `get_fallback_chain` 返回 primary+fallback

**Step 2: Run tests to verify they fail**
Run: `pytest app/tests/test_model_registry_defaults.py -q`
Expected: FAIL（当前不支持该格式/路径）

### Task 3: Implement routing/config modules

**Files:**
- Create: `app/core/section_router.py`
- Create: `app/config/section_routing.cn.json`

**Step 1: Implement `is_critical_section` + `select_generation_plan`**
- 支持 title 关键词包含匹配
- 支持 weight 阈值优先
- 输出 base/enhance/review 计划

**Step 2: Implement config loading with env override**
- 支持 `SECTION_ROUTING_PATH`
- 默认到 `app/config/section_routing.cn.json`

### Task 4: Implement registry compatibility and env path override

**Files:**
- Modify: `app/llm/model_registry.py`
- Create: `app/config/model_registry.cn.debug.json`
- Create: `app/config/model_registry.cn.prod.json`

**Step 1: Extend loader**
- 支持 `MODEL_REGISTRY_PATH` 覆盖
- 兼容 legacy 与 cn roles/providers 格式

**Step 2: Keep defaults stable**
- 保持现有 `model_registry.json` 场景行为不变

### Task 5: Wire section routing into generation workflow

**Files:**
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/worker/tasks.py`
- Modify: `app/api/handlers/workflow_generation_review.py`

**Step 1: pass section context**
- handler -> task context -> generation pipeline

**Step 2: apply section plan**
- 记录 critical 决策日志
- critical 章节触发 R1 增强（最小修订）
- critical 章节强制 REVIEW
- 保留现有 fallback 机制

### Task 6: Add prompts and docs

**Files:**
- Create: `app/prompts/section_enhance_r1_cn.md`
- Create: `app/prompts/final_review_r1_cn.md`
- Modify: `docs/README.md`

**Step 1: add prompt templates**
- 与文档给定模板一致

**Step 2: document env switching**
- `MODEL_REGISTRY_PATH` / `SECTION_ROUTING_PATH`
- debug/prod 示例

### Task 7: Verification

**Files:**
- N/A

**Step 1: Run targeted tests**
Run:
- `pytest app/tests/test_section_router.py -q`
- `pytest app/tests/test_model_registry_defaults.py -q`
- `pytest app/tests/test_byok_review_fallback.py -q`
- `pytest app/tests/test_section_confirmation_flow.py -q`

**Step 2: Run combined smoke**
Run: `pytest app/tests/test_section_router.py app/tests/test_model_registry_defaults.py app/tests/test_byok_review_fallback.py app/tests/test_section_confirmation_flow.py -q`
Expected: PASS
