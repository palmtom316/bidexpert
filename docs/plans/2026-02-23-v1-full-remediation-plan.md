# BidExpert V1.0 全量问题整改 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `docs/BidExpert_系统评估报告_V1.0.md` 中列出的全部问题在代码、配置、测试、运维流程四个层面整改落地，并建立可持续质量基线。

**Architecture:** 采用“风险优先、分波次交付”的增量改造：先封住生产风险与合规风险（P0），再提升领域正确性（P1）、检索与生成质量（P2）、前端安全与可维护性（P3），最后通过基准集与自动化回归固化（P4）。每波次结束均执行回归与验收门禁。

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Qdrant, Celery, pytest, 原生前端 JS/CSS。

---

## 0. 报告问题覆盖清单（整改范围基线）

| ID | 报告问题 | 代码现状锚点 | 整改目标 |
|---|---|---|---|
| R01 | 专家库分类过粗（仅4类） | `app/services/expert_library.py:50` | 扩展到 >=10 类并前后端一致 |
| R02 | `quality_score=88.0` 硬编码 | `app/services/expert_library.py:1043` | 动态质量评分（时效/完整度/匹配度/来源） |
| R03 | 稀疏检索仅 TF，无 IDF | `app/services/qdrant_store.py:41` | 实现 BM25 近似或等效 IDF 权重 |
| R04 | 回退分块最小长度 24 字符过低 | `app/services/expert_library.py:349`, `app/services/expert_enterprise_pipeline.py:370` | 提升最小阈值并可配置 |
| R05 | `pricing_guard` 中文误报高 | `app/services/pricing_guard.py:51-57` | 修正信号3/4，降低误拦 |
| R06 | `build_tender_parsing_prompt` 缺领域策略 | `app/llm/prompt_suite_v11.py:30` | 增加资审/商务/技术/评标策略 |
| R07 | 正则回退关键词过少 | `app/extract/tender_parser.py:15` | 扩充废标/资格否决/加扣分词典 |
| R08 | `build_global_facts_prompt` 仅5字段 | `app/llm/prompt_suite_v11.py:40` | 扩展到 15+ 核心字段 |
| R09 | 章节生成无类型区分 | `app/llm/prompt_suite_v11.py:57` | 按章节类型分模板与约束 |
| R10 | 审查 prompt 缺领域清单 | `app/llm/prompt_suite_v11.py:106` | 增加一致性、参数、废标覆盖检查 |
| R11 | `section_max_output_tokens=4000` | `app/core/config.py:78` | 按章节类型动态 token 上限 |
| R12 | `_compose_draft` 回退不可用 | `app/services/generation_pipeline.py:33` | 离线模板库兜底可编辑稿 |
| R13 | 前端 `app.js` 过大且全局可变状态 | `app/ui/app.js` | 模块化拆分、状态分层 |
| R14 | 前端输入校验不足 | `app/ui/index.html`, `app/ui/app.js` | 前置校验+友好错误 |
| R15 | API Key 明文 `localStorage` | `app/ui/app.js:36,461` | 默认不落盘，最小化暴露 |
| R16 | OCR 扫描识别质量不稳 | `app/services/pdf_ingest.py`, `app/services/adapters/ocr.py` | 商业 OCR 优先 + 置信度阈值 |
| R17 | 全部 LLM 不可用时回退质量低 | `app/services/generation_pipeline.py:222` | 模板化兜底 + 关键词替换 |
| R18 | 运行基线校验缺失（master key/模型有效性） | `app/core/config.py:138` | 启动前强校验 |
| R19 | 知识库到期治理机制缺失 | `app/services/expert_library.py`, `app/services/generation_pipeline.py` | 到期提醒与降权机制 |
| R20 | 结构化转换缺抽检机制 | `app/services/expert_library.py` | 10%-20% 抽检与阈值联动 |
| R21 | 检索缺同义词扩展 | `app/services/qdrant_store.py` | 同义词词典与查询扩展 |
| R22 | rerank 权重缺实证优化 | `app/services/qdrant_store.py:90` | A/B 配置化与指标评估 |
| R23 | 缺分级人工审核闭环 | `app/services/generation_pipeline.py`, `app/services/review_engine.py` | PASS/复核/重写三级门禁 |
| R24 | 核心服务测试覆盖不足 | `app/services/*`, `app/tests/*` | 补齐核心单测和契约测试 |
| R25 | 缺投标质量基准测试集 | `tests/` | 10-20 套样本与质量指标自动评估 |
| R26 | 已知缺陷：`gemini-3-pro`、`DraftGenerationResponse` 默认值、`CompletedBid.project_id` FK、`MASTER_KEY_B64` 校验 | `app/config/model_registry.json`, `app/schemas/contracts.py:246`, `app/models/tables.py:396`, `app/core/config.py:138` | 一次性修复并补迁移与回归 |

---

## 1. 实施路径备选（审批项）

### 方案 A：一次性大改（Big Bang）
- 优点：单次完成，整体一致性高。
- 风险：回归面过大，定位问题慢，生产风险高。

### 方案 B：分波次风险优先（推荐）
- 优点：可控、可回滚，先消高风险，再做质量优化。
- 风险：总周期略长，需要严格版本管理。

### 方案 C：按业务链路纵切（入库→解析→生成→发布）
- 优点：用户可较快感知端到端改善。
- 风险：基础能力（检索、配置基线）可能滞后，难控系统性风险。

**推荐：方案 B（分波次风险优先）**

---

## 2. 里程碑与门禁

| 里程碑 | 范围 | 目标时长 | 放行门禁 |
|---|---|---|---|
| M1 (P0) | 生产与合规高风险项（R05/R11/R18/R26 部分） | 3-4 天 | 核心回归通过，无启动阻断缺陷 |
| M2 (P1) | 解析与生成领域深度（R06/R07/R08/R09/R10/R23） | 5-7 天 | 废标条款覆盖率测试通过 |
| M3 (P2) | 检索质量与知识治理（R01/R02/R03/R04/R19/R20/R21/R22） | 5-7 天 | 检索相关性与误报指标达标 |
| M4 (P3) | 前端安全与可维护性（R13/R14/R15/R16/R17） | 4-6 天 | 前端安全基线 + 可用性测试通过 |
| M5 (P4) | 测试基线与基准集（R24/R25） | 4-6 天 | 质量基线报告可自动产出 |

---

## 3. 详细任务分解

### Task 1: 生产基线与已知阻断缺陷修复（P0）

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/config/model_registry.json`
- Modify: `app/schemas/contracts.py`
- Modify: `app/models/tables.py`
- Create: `migrations/versions/<new_revision>_completed_bid_project_fk_and_baseline_checks.py`
- Test: `app/tests/test_phase2_audit_fixes.py`
- Test: `app/tests/test_v11_jsonb_and_migration_contract.py`

**Step 1: 写失败测试（运行基线）**
- 断言 `validate_runtime_baseline()` 在 `prod` 环境下缺 `BIDEXPERT_MASTER_KEY_B64` 时抛错。
- 断言默认模型链中不存在未注册模型。

**Step 2: 写失败测试（Schema 与迁移）**
- 断言 `CompletedBid.project_id` 为 UUID 外键（`project.id`）。
- 断言 `DraftGenerationResponse` 默认 provider/model 与 registry 默认一致。

**Step 3: 最小实现**
- 在 `validate_runtime_baseline()` 增加 `master_key` 与模型有效性检查。
- 修正 `langextract_default_model` 与 `DraftGenerationResponse` 默认值到 registry 中存在的模型。
- 为 `completed_bid.project_id` 增加 UUID FK 迁移与兼容处理。

**Step 4: 回归命令**
- Run: `python3 -m pytest app/tests/test_phase2_audit_fixes.py -q`
- Run: `python3 -m pytest app/tests/test_v11_jsonb_and_migration_contract.py -q`

**Step 5: 提交**
- Commit: `fix: enforce runtime baseline and align completed_bid foreign key`

### Task 2: pricing_guard 中文误报治理（P0）

**Files:**
- Modify: `app/services/pricing_guard.py`
- Test: `app/tests/test_stage1_services.py`
- Create: `app/tests/test_pricing_guard_cn_false_positive.py`

**Step 1: 写失败测试**
- “含 RMB + 技术参数”不应直接阻断。
- 中文无空格文本中数字密度计算不应异常放大。

**Step 2: 最小实现**
- 信号3改为上下文窗口联动判定。
- 信号4改为中文友好分词策略（不再依赖 `text.split()` 分母）。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_stage1_services.py app/tests/test_pricing_guard_cn_false_positive.py -q`

**Step 4: 提交**
- Commit: `fix: reduce pricing_guard false positives for chinese technical docs`

### Task 3: 章节输出长度与 LLM 全故障兜底（P0）

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/services/generation_pipeline.py`
- Create: `app/services/fallback_templates.py`
- Create: `templates/fallback/section_*.md`
- Test: `app/tests/test_generation_fallback_templates.py`

**Step 1: 写失败测试**
- 按章节类型验证不同 `max_output_tokens`。
- 全 provider 失败时返回结构化可编辑模板稿而非拼接首句。

**Step 2: 最小实现**
- 增加 `section_output_tokens_map` 配置（施工方案>=12000 等）。
- `_compose_draft` 改为模板库渲染（关键词替换 + 必备段落骨架）。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_generation_fallback_templates.py -q`

**Step 4: 提交**
- Commit: `feat: typed output token limits and offline section fallback templates`

### Task 4: 招标解析领域化（P1）

**Files:**
- Modify: `app/llm/prompt_suite_v11.py`
- Modify: `app/extract/tender_parser.py`
- Modify: `app/services/tender_analysis.py`
- Test: `app/tests/test_v11_prompt_suite.py`
- Create: `app/tests/test_tender_parser_disqualify_rules.py`

**Step 1: 写失败测试**
- 正则回退可识别“否则作废标处理/不予通过资格审查/取消投标资格/加分项/优先考虑”。
- prompt 含资审/商务/技术/评标四类解析指引与废标条款提取要求。

**Step 2: 最小实现**
- 扩展关键词词典与分类规则。
- 将废标条款与扣分条款在结构中明确区分。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_v11_prompt_suite.py app/tests/test_tender_parser_disqualify_rules.py -q`

**Step 4: 提交**
- Commit: `feat: domain-specific tender parsing and disqualify extraction`

### Task 5: 全局事实扩容（P1）

**Files:**
- Modify: `app/llm/prompt_suite_v11.py`
- Modify: `app/services/global_facts.py`
- Modify: `app/services/generation_pipeline.py`
- Create: `app/tests/test_global_facts_extended_fields.py`

**Step 1: 写失败测试**
- 新增字段：建设单位、监理单位、质量标准、安全文明等级、分包限制、工期节点、保证金等。

**Step 2: 最小实现**
- `GlobalFacts` schema 扩到 15+ 字段。
- 冲突检测与生成前校验覆盖新增字段。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_global_facts_extended_fields.py -q`

**Step 4: 提交**
- Commit: `feat: extend global facts schema and conflict checks`

### Task 6: 章节类型化生成与审查清单（P1）

**Files:**
- Modify: `app/services/adapters/base.py`
- Modify: `app/services/llm_gateway.py`
- Modify: `app/services/adapters/providers.py`
- Modify: `app/llm/prompt_suite_v11.py`
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/worker/tasks.py`
- Modify: `app/api/handlers/workflow_generation_review.py`
- Create: `app/tests/test_section_typed_prompt_and_review_checklist.py`

**Step 1: 写失败测试**
- 不同章节类型生成 prompt 包含不同结构约束与术语词表。
- review prompt 包含工期一致性、证书一致性、参数一致性、废标条款覆盖率检查。

**Step 2: 最小实现**
- 在 generation/review 请求中引入 `section_type`。
- 在流程链路透传 `section_type`（API -> worker -> pipeline -> adapter）。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_section_typed_prompt_and_review_checklist.py -q`

**Step 4: 提交**
- Commit: `feat: typed section generation and domain review checklist`

### Task 7: 三级人工审核门禁（P1）

**Files:**
- Modify: `app/services/generation_pipeline.py`
- Modify: `app/services/review_engine.py`
- Modify: `app/schemas/contracts.py`
- Create: `app/tests/test_review_triage_gate.py`

**Step 1: 写失败测试**
- 自动通过：PASS + 废标覆盖 + 无冲突。
- 人工复核：ADJUST_PASS 或 warnings。
- 强制重写：REWRITE 或废标未覆盖。

**Step 2: 最小实现**
- 明确状态机与阻断条件。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_review_triage_gate.py -q`

**Step 4: 提交**
- Commit: `feat: add triage review gates for bid compliance`

### Task 8: 专家库分类扩展与结构化入库改造（P2）

**Files:**
- Modify: `app/services/expert_library.py`
- Modify: `app/schemas/contracts.py`
- Modify: `app/api/handlers/evidence_expert_render.py`
- Modify: `app/ui/index.html`
- Modify: `app/ui/app.js`
- Test: `app/tests/test_expert_library_api.py`

**Step 1: 写失败测试**
- 新分类输入字段可被 API 接收、落库、回传统计。

**Step 2: 最小实现**
- `_STRUCTURED_CATEGORY_MAP` 扩展至 >=10 类。
- 前后端字段与中文标签同步。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_expert_library_api.py -q`

**Step 4: 提交**
- Commit: `feat: expand expert library categories to bidding domain taxonomy`

### Task 9: 动态质量评分、到期治理、抽检机制（P2）

**Files:**
- Modify: `app/services/expert_library.py`
- Modify: `app/services/expert_chunking.py`
- Create: `app/services/knowledge_quality.py`
- Create: `app/services/quality_sampling.py`
- Create: `app/tests/test_knowledge_quality_scoring.py`

**Step 1: 写失败测试**
- 质量评分随时效、完整度、匹配度、来源变化。
- 证书/业绩到期提醒与降权生效。
- 抽检比例阈值可配置并记录结果。

**Step 2: 最小实现**
- 替换 `88.0` 固定分为动态评分。
- 增加抽检日志、准确率阈值触发全量人工审核标记。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_knowledge_quality_scoring.py -q`

**Step 4: 提交**
- Commit: `feat: dynamic quality scoring with expiry governance and sampling`

### Task 10: 检索 BM25/同义词/rerank A-B（P2）

**Files:**
- Modify: `app/services/qdrant_store.py`
- Create: `app/services/retrieval_synonyms.py`
- Modify: `app/core/config.py`
- Modify: `app/tests/test_qdrant_rerank.py`
- Create: `app/tests/test_qdrant_bm25_idf.py`

**Step 1: 写失败测试**
- 低频专业词（如电压等级+设备型号）获得更高稀疏得分。
- 同义词扩展可召回别名表达。
- rerank 权重可配置并对比 A/B 指标。

**Step 2: 最小实现**
- `_build_sparse_vector` 引入 IDF（语料统计或近似统计）。
- 查询端同义词扩展。
- rerank 权重参数化（默认保持兼容）。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_qdrant_rerank.py app/tests/test_qdrant_bm25_idf.py -q`

**Step 4: 提交**
- Commit: `feat: bm25-idf sparse retrieval with synonym expansion and rerank ab config`

### Task 11: 分块噪声控制（P2）

**Files:**
- Modify: `app/services/expert_library.py`
- Modify: `app/services/expert_enterprise_pipeline.py`
- Modify: `app/core/config.py`
- Create: `app/tests/test_chunk_min_length_threshold.py`

**Step 1: 写失败测试**
- 小于最小语义阈值文本不入库。

**Step 2: 最小实现**
- 把 24 字符阈值提升到可配置（建议中文 >=80 字符或 >=50 token）。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_chunk_min_length_threshold.py -q`

**Step 4: 提交**
- Commit: `fix: raise and configure minimum chunk length to reduce retrieval noise`

### Task 12: 前端模块化与状态治理（P3）

**Files:**
- Split: `app/ui/app.js` -> `app/ui/modules/*.js`
- Modify: `app/ui/index.html`
- Create: `app/ui/modules/state.js`
- Create: `app/ui/modules/validation.js`
- Create: `app/tests/test_ui_module_contract.py`

**Step 1: 写失败测试/契约检查**
- 关键按钮事件绑定与 API 请求行为保持一致。

**Step 2: 最小实现**
- 把 ExpertHub/TenderHub/BidWorkbench/Review/Publish 拆为独立模块。
- 收敛全局可变状态到单一状态容器。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_ui_module_contract.py -q`

**Step 4: 提交**
- Commit: `refactor: modularize frontend app and centralize ui state`

### Task 13: 前端输入前置校验与错误体验（P3）

**Files:**
- Modify: `app/ui/index.html`
- Modify: `app/ui/modules/validation.js` (or `app/ui/app.js`)
- Create: `app/tests/test_ui_input_validation_rules.py`

**Step 1: 写失败测试**
- 文件、project_id、结构化补录、BYOK/OCR 配置等输入在提交前可校验。

**Step 2: 最小实现**
- 添加必填、格式、长度、枚举校验。
- 错误定位到字段级而非仅 Toast。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_ui_input_validation_rules.py -q`

**Step 4: 提交**
- Commit: `feat: add client-side validation and field-level error feedback`

### Task 14: API Key 存储安全与 OCR 置信度策略（P3）

**Files:**
- Modify: `app/ui/app.js`
- Modify: `app/services/pdf_ingest.py`
- Modify: `app/services/adapters/ocr.py`
- Modify: `app/services/ingest/file_router.py`
- Modify: `app/core/config.py`
- Create: `app/tests/test_ocr_confidence_threshold.py`
- Create: `app/tests/test_ui_api_key_storage_policy.py`

**Step 1: 写失败测试**
- UI 默认不将 API Key 永久存储到 `localStorage`。
- OCR 结果低于置信度阈值时标记“需人工校对”。

**Step 2: 最小实现**
- API Key 默认内存态（可选 session 级），清理明文落盘路径。
- OCR 适配层返回置信度，PDF ingest 写入 `page_meta` 并触发 warning。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests/test_ocr_confidence_threshold.py app/tests/test_ui_api_key_storage_policy.py -q`

**Step 4: 提交**
- Commit: `feat: harden api-key client storage and add ocr confidence gating`

### Task 15: 测试覆盖与投标质量基准集（P4）

**Files:**
- Create: `tests/benchmark/fixtures/*`
- Create: `tests/benchmark/test_bid_quality_benchmark.py`
- Create: `app/tests/test_generation_pipeline_conflict_and_disqualify.py`
- Create: `app/tests/test_tender_parser_disqualify_coverage.py`
- Create: `app/tests/test_pricing_guard_regression_matrix.py`
- Create: `scripts/quality_benchmark_report.py`

**Step 1: 写失败测试**
- 指标：废标条款覆盖率=100%、评分项响应率>=95%、关键参数一致性=100%。

**Step 2: 最小实现**
- 构建 10-20 套脱敏样本与自动评分脚本。
- 将 benchmark 纳入 CI 可选作业。

**Step 3: 回归命令**
- Run: `python3 -m pytest app/tests -q`
- Run: `python3 -m pytest tests/benchmark/test_bid_quality_benchmark.py -q`

**Step 4: 提交**
- Commit: `test: add benchmark suite and core service coverage for bid quality`

---

## 4. 验收标准（批准后执行时使用）

| 维度 | 指标 |
|---|---|
| 合规安全 | 废标条款覆盖率 100%，pricing_guard 中文误报显著下降 |
| 生成质量 | 施工方案章节长度与结构满足模板要求，回退稿可人工直接编辑 |
| 检索质量 | 专业术语召回率提升，低相关噪声片段下降 |
| 工程稳定 | 启动基线校验完整，迁移与模型配置无阻断 |
| 前端安全 | API Key 不再默认明文持久化 |
| 可维护性 | 前端模块化后关键流程回归通过 |
| 测试保障 | 新增核心单测 + 基准集测试可重复执行 |

---

## 5. 风险与回滚策略

| 风险 | 应对 |
|---|---|
| Prompt 改造导致输出格式漂移 | 所有 prompt 变更必须配套 schema 验证测试 |
| BM25/IDF 改造影响召回稳定性 | 增加 feature flag 与灰度开关 |
| 前端拆分引入交互回归 | 先做契约测试，再模块迁移 |
| 完成历史数据迁移失败 | 先备份，迁移脚本幂等，保留回滚脚本 |

---

## 6. 执行顺序（审批后）

1. 执行 Task 1-3（P0）。
2. 执行 Task 4-7（P1）。
3. 执行 Task 8-11（P2）。
4. 执行 Task 12-14（P3）。
5. 执行 Task 15（P4）并出具整改验收报告。

