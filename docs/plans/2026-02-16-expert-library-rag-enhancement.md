# Expert Library RAG Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement every requirement from `docs/投标专家系统_专家库结构增强与RAG完整方案.md` in code, including enhanced markdown rendering, expert-library directory layout, RAG chunking strategy, cost estimate support, and Claude section enhancement prompt.

**Architecture:** Add dedicated services for expert-library workspace management, section enhancement metadata, markdown rendering, and section-first chunking. Wire them into `ingest_historical_pdf` so ingestion writes stage artifacts and upserts enriched chunks with required metadata while preserving existing API contracts.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy, Qdrant client, pytest.

---

### Task 1: Add failing tests for the new requirements

**Files:**
- Create: `app/tests/test_expert_library_rag_enhancement.py`

**Step 1: Write the failing tests**

```python
def test_ensure_library_layout_creates_required_directories(tmp_path):
    ...


def test_render_enhanced_markdown_contains_required_fields():
    ...


def test_chunking_section_first_table_separate_and_required_metadata():
    ...
```

**Step 2: Run tests to verify failures**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py -v`
Expected: FAIL for missing modules/functions.

**Step 3: Commit**

```bash
git add app/tests/test_expert_library_rag_enhancement.py
git commit -m "test: add failing tests for expert-library rag enhancement"
```

### Task 2: Implement expert-library workspace layout and static assets

**Files:**
- Modify: `app/core/config.py`
- Create: `app/services/expert_workspace.py`

**Step 1: Write/update tests**

```python
def test_uploaded_artifacts_path_points_to_01_raw():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_ensure_library_layout_creates_required_directories -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
EXPERT_LIBRARY_DIRS = [
    "00_config", "01_raw", "02_extracted", "03_enriched", "04_md",
    "05_chunks", "06_index", "07_review", "99_logs",
]
```

**Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_ensure_library_layout_creates_required_directories -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/core/config.py app/services/expert_workspace.py
git commit -m "feat: add expert library workspace layout service"
```

### Task 3: Implement markdown rendering and section enhancement prompt support

**Files:**
- Create: `app/services/expert_markdown.py`
- Create: `app/services/section_enhancement.py`

**Step 1: Run markdown/prompt tests to verify failure**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_render_enhanced_markdown_contains_required_fields -v`
Expected: FAIL.

**Step 2: Implement minimal markdown renderer and prompt constant**

```python
CLAUDE_SECTION_ENHANCEMENT_PROMPT = "...严格 JSON..."

def render_enhanced_markdown(doc: dict) -> str:
    ...
```

**Step 3: Run tests to verify pass**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_render_enhanced_markdown_contains_required_fields -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add app/services/expert_markdown.py app/services/section_enhancement.py
git commit -m "feat: add enhanced markdown renderer and section prompt"
```

### Task 4: Implement section-first RAG chunking strategy

**Files:**
- Create: `app/services/expert_chunking.py`

**Step 1: Run chunking test to verify failure**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_chunking_section_first_table_separate_and_required_metadata -v`
Expected: FAIL.

**Step 2: Implement chunking strategy**

```python
def chunk_sections_for_rag(..., min_tokens=800, max_tokens=1200):
    ...
```

**Step 3: Run chunking test to verify pass**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_chunking_section_first_table_separate_and_required_metadata -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add app/services/expert_chunking.py
git commit -m "feat: implement section-first rag chunking strategy"
```

### Task 5: Integrate into ingestion and upsert metadata-complete chunks

**Files:**
- Modify: `app/services/expert_library.py`
- Modify: `app/services/qdrant_store.py`

**Step 1: Write/update integration test to fail**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py -k ingest -v`
Expected: FAIL.

**Step 2: Implement ingestion integration and metadata propagation**

```python
chunks = chunk_sections_for_rag(...)
store.upsert_chunks(...)
```

**Step 3: Run tests to verify pass**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add app/services/expert_library.py app/services/qdrant_store.py
git commit -m "feat: integrate enhanced markdown and chunking into ingestion"
```

### Task 6: Add cost estimate support and final verification

**Files:**
- Create: `app/services/expert_costing.py`
- Modify: `app/services/expert_library.py`

**Step 1: Add/execute failing test**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py::test_cost_estimate_for_100_files_matches_spec -v`
Expected: FAIL.

**Step 2: Implement minimal costing function and include in ingest output warnings/log artifacts**

```python
def estimate_knowledge_enhancement_cost(doc_count: int) -> dict:
    ...
```

**Step 3: Run focused and broader verification**

Run: `pytest app/tests/test_expert_library_rag_enhancement.py -v`
Expected: PASS.

Run: `pytest app/tests/test_expert_library_api.py app/tests/test_new_stage1_pipeline.py app/tests/test_langextract_integration.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add app/services/expert_costing.py app/services/expert_library.py app/tests/test_expert_library_rag_enhancement.py
git commit -m "feat: add expert library cost estimate and complete rag enhancement rollout"
```
