# Epic D Rerank Design

**Context**
- User requested to continue implementing Epic D from `docs/BidExpert_Codex_实现任务列表_v3.7.md`.
- Existing code already supports BYOK policies for `EXTRACT/GENERATE/REVIEW/EMBED/QUERY_REWRITE/PROGRAM_SUPPORT`.
- Current rerank path in `app/services/qdrant_store.py` is lexical/cross-encoder only.

**Goal**
- Add project-level profile binding for rerank (`RERANK` role).
- Add optional LLM rerank path in Qdrant retrieval flow with safe fallback.

**Design Decisions**
- Add `ModelRole.RERANK` and carry it end-to-end through schema/table/service mapping.
- Extend `project_model_policy` with `rerank_profile_id` and default concurrency key `rerank`.
- Implement LLM rerank as an optional branch guarded by config:
  - `qdrant_llm_rerank_enabled`
  - `qdrant_llm_rerank_candidate_limit`
  - `qdrant_llm_rerank_top_k`
- Use OpenAI-compatible `/chat/completions` endpoint via resolved BYOK profile for `RERANK`.
- On any LLM rerank failure, fallback to existing rerank path to keep retrieval stable.

**Approach Alternatives**
1. Minimal invasive helper-based integration (chosen): add isolated helper functions and keep existing search flow shape.
2. Full retrieval pipeline refactor: cleaner abstraction but high regression risk in current branch.
3. External rerank service module: better separation but adds files and indirection not required now.

**Risk Control**
- Add focused tests for:
  - `RERANK` policy mapping and API payload/response fields.
  - LLM rerank ordering and fallback behavior.
- Keep default config disabled to preserve current behavior unless explicitly enabled.
