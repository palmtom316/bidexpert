# Epic D Rerank Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `RERANK` model role/policy binding and optional LLM rerank execution path with safe fallback.

**Architecture:** Extend existing BYOK role-routing pipeline with one additional role and policy field, then add an opt-in LLM rerank branch in `QdrantStore.search()` that reorders fused candidates via OpenAI-compatible chat completion JSON output.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, Qdrant client, httpx, pytest.

---

### Task 1: Add failing tests for RERANK role/policy plumbing

**Files:**
- Modify: `app/tests/test_provider_profile_qualify_api.py`
- Create: `app/tests/test_rerank_policy_mapping.py`

**Step 1: Write failing tests**
- Add assertions that policy payload/response includes `rerank_profile_id`.
- Add assertions that `resolve_profile_for_task(..., task_type="RERANK")` picks `policy.rerank_profile_id`.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/pytest app/tests/test_provider_profile_qualify_api.py app/tests/test_rerank_policy_mapping.py -q`

**Step 3: Implement minimal role/policy plumbing**
- Add enum + schema + model + handler/service mapping changes for `RERANK`.

**Step 4: Re-run tests**
- Run same command and expect PASS.

### Task 2: Add failing tests for LLM rerank behavior

**Files:**
- Create: `app/tests/test_qdrant_llm_rerank.py`

**Step 1: Write failing tests**
- Test LLM rerank returns candidate order by `ranked_chunk_ids`.
- Test fallback to lexical rerank when LLM request fails.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/pytest app/tests/test_qdrant_llm_rerank.py -q`

**Step 3: Implement minimal LLM rerank branch**
- Add settings knobs and helper methods in `qdrant_store`.
- Integrate into `search()` guarded by feature flag.

**Step 4: Re-run tests**
- Run same command and expect PASS.

### Task 3: Migration and compatibility updates

**Files:**
- Create: `migrations/versions/<new_revision>_add_rerank_profile_policy.py`
- Modify: `app/models/tables.py`

**Step 1: Add migration**
- Add nullable `rerank_profile_id` FK to `project_model_policy`.
- Patch existing rows' `concurrency_limits` to include `rerank: 2` when missing.

**Step 2: Verify migration script imports/upgrade/downgrade compile**
- Run: `.venv/bin/python -m compileall migrations app/models/tables.py`

### Task 4: Full verification for Epic D changes

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/llm/roles.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/services/byok/profiles.py`
- Modify: `app/api/handlers/provider_completed_tender.py`
- Modify: `app/services/qdrant_store.py`

**Step 1: Run targeted test set**
- Run:
  - `.venv/bin/pytest app/tests/test_rerank_policy_mapping.py app/tests/test_qdrant_llm_rerank.py app/tests/test_provider_profile_qualify_api.py app/tests/test_byok_review_fallback.py -q`

**Step 2: Run broader safety tests touching retrieval/byok**
- Run:
  - `.venv/bin/pytest app/tests/test_qdrant_rerank.py app/tests/test_phase2_audit_fixes.py -q`

**Step 3: Confirm no syntax issues**
- Run: `.venv/bin/python -m compileall app tests migrations`
