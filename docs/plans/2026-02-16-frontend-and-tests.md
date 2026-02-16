# Frontend Dashboard + Review/Scoring Tests Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add review/score visibility to the UI and cover generation→review→scoring with integration tests.

**Architecture:** Keep existing static UI (no framework). Add panels/cards fed by existing REST endpoints. Integration tests hit FastAPI app via TestClient and real services (no external calls, mock LLM/Redis/Qdrant where needed).

**Tech Stack:** FastAPI, plain JS/HTML/CSS, pytest + httpx TestClient.

---

### Task 1: UI – Review/Score dashboards

**Files:**
- Modify: `app/ui/index.html`
- Modify: `app/ui/styles.css`
- Modify: `app/ui/app.js`

**Steps:**
1. Add a “审核评分” summary block in review panel showing latest review report (status + created_at) and scoring total.
2. Add buttons “拉取审核” → GET `/v1/workflow/section/review`? (current is POST; use POST with stored section_key/project_id inputs) and “拉取评分” → POST `/v1/workflow/scoring/calculate`.
3. Display returned `report_json` (issues list) and `score_total` + details in cards; show loading/error states.
4. Wire inputs: project_id from ribbon, section_key select; use fetch with API key header when present.
5. Style cards to match existing aesthetic (utility/mid-tone teal/gray, subtle shadows, hover states).

### Task 2: Integration test – review endpoint

**Files:**
- Create: `tests/test_review_flow.py`

**Steps:**
1. RED: Write failing test using FastAPI TestClient that calls `POST /v1/workflow/section/review` with a prepared project/section fixture (seed minimal DB rows via SessionLocal, mock review_engine to return deterministic report).
2. Make sure test asserts HTTP 200 and payload fields (id, status, report_json contains modeled_issues array).
3. GREEN: If needed, inject fixture/mocking hook (monkeypatch run_compliance_review) to satisfy test.

### Task 3: Integration test – scoring endpoint

**Files:**
- Create: `tests/test_scoring_flow.py`

**Steps:**
1. RED: Write failing test calling `POST /v1/workflow/scoring/calculate` with seeded project and requirements/sections/review reports; monkeypatch scoring engine to return deterministic totals.
2. Assert 200, score_total float, details_json present.
3. GREEN: Add minimal hook/monkeypatch in test to satisfy assertions without hitting external services.

### Task 4: Wire API key in UI requests

**Files:**
- Modify: `app/ui/app.js`

**Steps:**
1. Add optional API key input in ribbon; store in memory.
2. All fetch calls attach `X-API-Key` header if provided.
3. Validate empty as no header; update status chip when set.

### Task 5: Verify

**Steps:**
1. Run `./.venv/bin/pytest tests/test_app_starts.py tests/test_review_flow.py tests/test_scoring_flow.py`.
2. Manual smoke: open `app/ui/index.html` via `python -m http.server` or uvicorn to ensure new UI blocks render (no JS errors).

### Task 6: (Optional) Polish

**Steps:**
1. Refine typography/color tokens in `styles.css` for new blocks if needed.
2. Keep HTML/CSS consistent with existing utility style.
