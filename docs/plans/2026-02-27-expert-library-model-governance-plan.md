# Expert Library Model Governance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将“专家库入库各阶段模型 + 专家库生成模型”纳入统一 AI 模型设置，并形成可视化质量控制、模型比较、阈值调整的可落地改造路径。

**Architecture:** 复用现有 `project_model_policy` 接口，不新增表结构；通过策略扩展字段保存阶段模型绑定。前端在“AI 模型设置”新增入库阶段与专家库生成分区。后续在 `expert_library` 流程接入质量仪表与阈值调优闭环。

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy(JSON policy), Vanilla JS UI, Qdrant

---

### Task 1: 扩展策略契约（API Schema）

**Files:**
- Modify: `app/schemas/contracts.py`

**Step 1: 增加策略字段**

- 在 `ProjectModelPolicyUpsertRequest` 新增：
  - `expert_ingest_profiles`
  - `expert_generation_profiles`
- 在 `ProjectModelPolicyResponse` 新增同名返回字段。

**Step 2: 保持兼容**

- 保持原有 6 个流程角色字段不变。
- 新字段为可选，不影响旧客户端。

### Task 2: 后端策略读写扩展（无表迁移）

**Files:**
- Modify: `app/api/handlers/provider_completed_tender.py`
- Modify: `app/services/byok/profiles.py`

**Step 1: handler 层透传新字段并记录变更字段**

- `put_model_policy_handler` 向 service 透传新字段。
- 审计字段 `changed_fields` 包含新字段。

**Step 2: service 层持久化方案**

- 将专家库阶段模型绑定写入 `concurrency_limits` 的保留元数据键：
  - `__expert_ingest_profiles`
  - `__expert_generation_profiles`
- 保持原并发限制键值语义不变。
- 返回策略时清理内部元数据键，单独通过新增响应字段输出。

### Task 3: 前端 AI 模型设置增强

**Files:**
- Modify: `app/ui/index.html`
- Modify: `app/ui/app.js`

**Step 1: 新增配置区块**

- 专家库入库阶段模型：
  - S1 文档结构补抽
  - S2 字段抽取
  - S3 回退抽取
  - S4 冲突仲裁
  - S5 Embedding
  - S6 Rerank
- 专家库生成模型（单独列出）：
  - G1 生成
  - G2 审查
  - G3 排版

**Step 2: 策略联动**

- `loadPolicy()` 回填新增字段。
- `savePolicy()` 提交新增字段。
- 新增“专家库生成模型清单”可视化摘要（从当前 Profile 解析 `provider:model`）。

### Task 4: 后续质量治理增强（下一迭代）

**Files:**
- Planned: `app/api/endpoints/stats.py`（新增质量指标 API）
- Planned: `app/services/expert_library.py`（阶段指标埋点）
- Planned: `app/ui/app.js` + `app/ui/index.html`（质量看板与阈值调参面板）

**Step 1: 可视质量控制**

- 输出并展示：schema 通过率、关键字段完整率、回退触发率、人工复核率、证据覆盖率。

**Step 2: 模型比较**

- 按阶段统计不同模型的通过率、失败类型、平均时延、成本。
- 支持按时间窗口对比。

**Step 3: 阈值调整**

- 增加阈值配置入口（低置信度阈值、回退阈值、必审阈值）。
- 支持“当前值-建议值-上线值”对照。

### Recommended Stage Model Selection (国产优先)

1. 文档结构化主引擎：MinerU（非 LLM，结构优先）
2. 低置信页补抽：`qwen3-vl-plus` 或 `glm-4.5v`
3. 字段抽取（strict JSON）：`qwen3.5-plus` / `qwen-max`
4. 回退抽取：`deepseek-chat`
5. 冲突仲裁：`glm-4.7` 或 `deepseek-reasoner`
6. 向量化：`text-embedding-v4`（国内网关可用版本）
7. 重排：`qwen3-rerank` 或 `gte-rerank-v2`
8. 专家库生成：`qwen-max`（生成）+ `deepseek-reasoner`（审查）+ `glm-4.7`（程序化支持）

### Acceptance Criteria

1. AI 模型设置页面可配置并保存新增阶段模型字段。
2. `/api/projects/{project_id}/model-policy` 返回新增字段。
3. 专家库生成模型在 UI 独立摘要展示。
4. 旧策略读写与旧页面行为保持兼容。
