# P0 Workflow Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add missing P0 workflow controls for outline/chapter confirmation, keep budget as interface-only (non-blocking), and enforce no-pricing generation policy.

**Architecture:** Add minimal persistence-backed workflow run entities and API gates to enforce human confirmation checkpoints. Keep existing Celery and retrieval flow, but make section generation depend on confirmed outline/chapter lifecycle. Budget remains logged/audited but cannot block generation path. Pricing-related generation is globally blocked by policy checks.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Celery, Pytest, Ruff

---

### Task 1: Outline Lifecycle Contracts

**Files:**
- Modify: `app/schemas/contracts.py`
- Test: `app/tests/test_outline_workflow.py`

**Step 1: Write the failing test**

```python
def test_create_outline_returns_pending_confirmation(client):
    payload = {"project_id": "p1", "tender_text": "第一章 项目概况"}
    res = client.post("/v1/workflow/outline", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "OUTLINE_PENDING_CONFIRM"
    assert body["outline_id"]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q app/tests/test_outline_workflow.py::test_create_outline_returns_pending_confirmation`
Expected: FAIL because endpoint/contracts do not exist yet.

**Step 3: Write minimal implementation**

- Add request/response models for outline creation and confirmation.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q app/tests/test_outline_workflow.py::test_create_outline_returns_pending_confirmation`
Expected: PASS.

### Task 2: Workflow Run Persistence + Outline APIs

**Files:**
- Modify: `app/models/tables.py`
- Modify: `app/db/init_db.py`
- Modify: `app/api/routes.py`
- Modify: `app/services/tender_parser.py`
- Test: `app/tests/test_outline_workflow.py`

**Step 1: Write the failing test**

```python
def test_confirm_outline_enables_section_generation(client):
    create = client.post("/v1/workflow/outline", json={"project_id": "p1", "tender_text": "A"}).json()
    res = client.post("/v1/workflow/outline/confirm", json={"outline_id": create["outline_id"], "approved": True})
    assert res.status_code == 200
    assert res.json()["status"] == "OUTLINE_CONFIRMED"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q app/tests/test_outline_workflow.py::test_confirm_outline_enables_section_generation`
Expected: FAIL due missing persistence/confirm route.

**Step 3: Write minimal implementation**

- Add `WorkflowRun` table (id, project_id, status, outline_json, timestamps).
- Add init_db ALTER/CREATE statements for compatibility.
- Add `/v1/workflow/outline` and `/v1/workflow/outline/confirm` endpoints.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q app/tests/test_outline_workflow.py`
Expected: PASS.

### Task 3: Section Confirmation Gate

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/workers/tasks.py`
- Test: `app/tests/test_section_confirmation_flow.py`

**Step 1: Write the failing test**

```python
def test_section_generation_requires_confirmed_outline(client):
    res = client.post("/v1/workflow/section", json={"workflow_id": "wf-x", "section_key": "1.1", "requirement_text": "test"})
    assert res.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q app/tests/test_section_confirmation_flow.py::test_section_generation_requires_confirmed_outline`
Expected: FAIL as current endpoint does not enforce this gate.

**Step 3: Write minimal implementation**

- Require confirmed outline before section workflow enqueue.
- Add chapter confirm endpoint to mark section as HUMAN_CONFIRMED.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q app/tests/test_section_confirmation_flow.py`
Expected: PASS.

### Task 4: Budget Non-Blocking + Global No-Pricing Enforcement

**Files:**
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/api/routes.py`
- Modify: `app/schemas/contracts.py`
- Test: `app/tests/test_policy_constraints.py`

**Step 1: Write the failing test**

```python
def test_budget_exceeded_does_not_block_generation(monkeypatch):
    monkeypatch.setattr("app.services.generation_pipeline.reserve_budget_persistent", lambda **_: (False, 0))
    res = generate_draft_with_retrieval("r1", "资质要求")
    assert res.status != "BUDGET_EXCEEDED"

def test_pricing_content_is_blocked():
    res = client.post("/v1/generation/draft", json={"requirement_id": "r1", "requirement_text": "请给出报价清单"})
    assert res.status_code == 200
    assert res.json()["status"] == "BLOCKED_PRICING_CONTENT"
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q app/tests/test_policy_constraints.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

- Keep budget call/logging but remove hard-stop status path.
- Enforce pricing content block before generation workflow and relevant endpoints.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q app/tests/test_policy_constraints.py`
Expected: PASS.

### Task 5: Regression Verification

**Files:**
- Test: `app/tests/*.py`

**Step 1: Run focused tests**

Run: `.venv/bin/python -m pytest -q app/tests/test_outline_workflow.py app/tests/test_section_confirmation_flow.py app/tests/test_policy_constraints.py`
Expected: PASS.

**Step 2: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

**Step 3: Run lint**

Run: `.venv/bin/python -m ruff check app`
Expected: PASS.
