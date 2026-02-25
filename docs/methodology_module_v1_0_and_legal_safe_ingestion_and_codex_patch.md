# 《专家经验提炼模块 v1.0》+《安全入库流程与法律风险控制架构》+ Codex 代码修订文件（合并版）
## 用途
当你在“其他单位/公开资料/培训资料/论坛/样例标书”中看到值得参考的片段时，**不直接把原文入库**，而是通过“提炼→去标识→改写→结构化→审核→入库”的流水线，生成可安全复用的“方法论资产/表达模板”。

> 本文件一份搞定：
> 1) 专家经验提炼模块 v1.0（产品/流程/数据结构）
> 2) 安全入库流程与法律风险控制架构（红线与闸门）
> 3) 可直接喂给 Codex/Claude Code 的代码修订清单（实现到系统里）

---

# Part A：《专家经验提炼模块 v1.0》

## A1. 实操目标（你问的“怎么操作”）
你看到一个外部片段（段落/表格/流程图/目录结构/评分点响应套路），正确实操是：

**步骤 0：判断来源类型（必须）**
- 公开规范/国标/行业标准：可入“规范库”（standard）
- 公开招标文件/评分表：进入“tender 工作区”（不进长期库）
- 外部标书片段/同行资料：进入“经验提炼模块”（本文件）
- 不确定来源或疑似泄露：禁止入库（直接丢弃）

**步骤 1：粘贴片段到“提炼入口”**
- 支持：复制粘贴文本/上传 md/docx/pdf（只抽取片段，不存原文件）
- 录入最少信息：
  - 来源类型：public_doc / training / sample / unknown
  - 你认为它属于哪个评分点/章节：如“进度保障/质量管理/安全文明”
  - 适用范围：电压等级/工程类型/地区（可选）

**步骤 2：系统自动“去标识 + 风险扫描”**
- 自动识别并剔除：公司名、项目名、地名细粒度、金额、合同号、人员身份证等
- 自动标注风险：版权/商业秘密/敏感个人信息（PII）

**步骤 3：系统自动“抽象结构 + 改写生成”**
- 产出三类资产（可选全产）：
  1) 方法论框架（methodology）
  2) 表达模板（template_md）
  3) 检索标签（metadata）

**步骤 4：人工审核（强制）**
- 审核点：
  - 是否仍可反推出来源单位？
  - 是否保留了独特专有参数/专利工艺？
  - 是否存在“可识别式抄袭”（长句重复）？
- 审核结论：approve / reject / need_edit

**步骤 5：入库（安全入库）**
- 只入：`kb_methodology`（新集合）或 `templates`（模板库）
- 不入：`kb_bid_history`（除非是你们公司自有文件）

---

## A2. 产物与数据结构（强制）

### A2.1 新增知识类型：methodology_snippet
这是“外部经验提炼后”的标准入库对象。

```json
{
  "snippet_id": "MSNIP-2026-0001",
  "title": "进度保障措施：关键路径 + 周计划闭环（通用框架）",
  "domain": "电力施工/配网",
  "tags": ["进度", "关键路径", "资源保障"],
  "applicability": {
    "voltage_level_kv": [10, 35],
    "project_type": ["业扩配电", "配网改造"],
    "region": ["通用"]
  },
  "structure": [
    "目标与原则",
    "组织保障",
    "技术保障（关键路径/里程碑）",
    "资源保障（人机料）",
    "风险预案（雨季/停电/材料）"
  ],
  "template_md": "### 进度保障措施（通用框架）\n1....",
  "quality": {
    "rewrite_similarity_score": 0.18,
    "pii_removed": true,
    "risk_level": "low"
  },
  "source_record": {
    "source_type": "public_doc|training|sample|unknown",
    "source_note": "仅内部记录，勿用于对外",
    "collected_by": "user",
    "collected_at": "2026-02-24T00:00:00Z"
  },
  "review": {
    "status": "approved|rejected|need_edit",
    "reviewer": "user/admin",
    "reviewed_at": "2026-02-24T00:00:00Z",
    "comment": "…"
  }
}
```

### A2.2 新增集合（Qdrant）
- `kb_methodology`：专门存“抽象后的方法论/框架/模板”，避免污染历史标书库。

### A2.3 新增对象存储（可选）
- 不保存原始外部文件；如确需留档，只保存“脱敏后片段”的审计副本：
  - `external_snippets/{snippet_id}/sanitized_input.txt`
  - `external_snippets/{snippet_id}/review_log.json`

---

## A3. 提炼算法建议（MVP 可落地）
### A3.1 去标识/脱敏（规则优先）
- 公司/项目：常见后缀词典（有限公司/集团/工程/项目部/标段）+ NER（可选）
- 金额/合同号：正则
- 个人信息：身份证/手机号/邮箱/证书号（正则）

### A3.2 改写与结构抽取（LLM）
- 输入：脱敏后的文本
- 输出：structure + template_md + tags + applicability
- 要求：禁止复述原文长句；更多用“要点列表/可迁移框架”。

### A3.3 相似度检测（防抄袭）
- 目标：避免“可识别式抄袭”
- MVP：
  - 计算句子 3-gram overlap 比例
  - 超过阈值（如 0.35）→ need_edit
- 进阶：用 embedding 相似度做对比（同文本 vs 改写文本）

---

# Part B：《安全入库流程与法律风险控制架构》

## B1. 三条铁律（红线）
1) **不存外部原文**：外部标书/同行资料不允许原文入库（除非明确授权）。  
2) **不存可识别信息**：公司名、项目名、人员证件、金额合同号等必须剔除。  
3) **不存专有核心方案**：专利/独家工艺/特定品牌绑定等，不可直接复用。

## B2. 风险分级（Risk Level）
- `low`：通用框架/方法论/通用表达
- `medium`：含较强行业细节但已脱敏改写，需要人工确认
- `high`：来源不明/疑似泄露/含大量专有细节 → 禁止入库

## B3. 必须的质量闸门（Quality Gates）
- Gate L0（来源门）：source_type=unknown 且无授权 → 默认 high，阻断
- Gate L1（脱敏门）：pii_removed=false → 阻断
- Gate L2（相似度门）：rewrite_similarity_score > threshold → need_edit
- Gate L3（人工审核门）：review.status != approved → 不允许写入 Qdrant

## B4. 审计与追溯
- 每个 snippet 必须保留：source_type、收集人、审核人、时间戳、风险等级、修改记录
- 导出/生成时引用 methodology_snippet，必须携带 snippet_id（可追溯）

---

# Part C：整合进系统的 Codex 代码修订文件（增强版）

> 目标：在现有系统中新增“专家经验提炼模块”，并把其产物安全入 `kb_methodology`，与 tender 模块/知识库共存。

## C1. 新增 API（必须）

### 1) 创建提炼任务
- `POST /api/methodology/extract`
  - 输入：text 或 file（可选）
  - 元数据：source_type、note、domain、tags（可选）
  - 返回：extract_run_id

### 2) 查询提炼结果
- `GET /api/methodology/runs/{run_id}`
- `GET /api/methodology/runs/{run_id}/result`

### 3) 审核与入库
- `POST /api/methodology/runs/{run_id}/review`
  - body: {status: approved|rejected|need_edit, comment: ""}
- `POST /api/methodology/runs/{run_id}/publish`
  - 仅当 status=approved 且 gates 通过，才写入 kb_methodology

### 4) 列表与检索（可选）
- `GET /api/methodology/snippets?tag=...&domain=...`
- `POST /api/methodology/search`（可复用现有检索）

---

## C2. 新增数据表（Postgres）

### methodology_runs
- run_id (pk)
- status / step / progress
- source_type / source_note
- input_kind (text|file)
- sanitized_input_path (optional)
- output_json_path
- risk_level
- similarity_score
- pii_removed (bool)
- reviewer / review_status / review_comment / reviewed_at
- created_at / updated_at

### methodology_snippets（发布后正式资产）
- snippet_id (pk)
- title
- domain
- tags (jsonb)
- applicability (jsonb)
- structure (jsonb)
- template_md (text)
- payload (jsonb)
- risk_level
- source_type / source_note
- created_by / created_at
- reviewed_by / reviewed_at

---

## C3. 新增 Qdrant collection
- `kb_methodology`
  - points：snippet_id 或 chunk_id
  - payload：domain/tags/applicability/risk_level/created_at

---

## C4. 新增模块与文件（建议路径）

1) `methodology/ingest.py`
- `accept_text_or_file()` → raw_text
- 文件解析：docx/pdf/md（MVP 可仅 text）

2) `methodology/sanitize.py`
- `remove_pii(raw_text)->sanitized_text, pii_removed, findings`

3) `methodology/risk_scan.py`
- `assess_source_risk(source_type, findings)->risk_level`
- L0 Gate：unknown/high → block

4) `methodology/rewrite_and_extract.py`
- LLM 调用（可配置）生成：structure/template_md/tags/applicability
- **要求**：输出 JSON + markdown 模板

5) `methodology/similarity.py`
- 计算 rewrite_similarity_score（n-gram overlap 等）
- Gate L2：> threshold → need_edit

6) `methodology/pipeline.py`
- 编排：RECEIVED → SANITIZED → EXTRACTED → SCORED → READY_FOR_REVIEW → APPROVED/REJECTED → PUBLISHED

7) `methodology/publish.py`
- 写 DB `methodology_snippets`
- upsert 到 Qdrant `kb_methodology`

8) `api/methodology.py`
- Router 与 endpoints

9) `tasks/methodology_tasks.py`
- 后台任务队列（同 tender）

---

## C5. 与投标编写的集成点（必须）
在写作检索层增加一个“方法论优先召回”策略（可配置）：
- 对评分项/章节写作：优先从 `kb_methodology` 召回结构模板
- 再从 `kb_bid_history` 召回公司自有表达
- 再从 `kb_standard` 补充规范依据

并强制 filter：
- risk_level != high
- review_status=approved

---

## C6. 最小测试清单（至少 6 个）
1) `test_sanitize_removes_phone_and_id`
2) `test_risk_scan_blocks_unknown_source_without_approval`
3) `test_similarity_gate_marks_need_edit_when_high_overlap`
4) `test_review_required_before_publish`
5) `test_publish_writes_db_and_qdrant`
6) `test_search_only_returns_approved_low_medium`

---

## C7. 实施顺序（降低失败率）
1) 先跑通：extract(text) → sanitized → extracted → ready_for_review
2) 再做：review → publish → 写 DB + Qdrant
3) 最后做：写作检索集成（kb_methodology 优先）

---

# 交付验收（必须）
- 外部片段无法直接入库：必须经过 sanitize + similarity gate + 人工审核
- 发布后能在 `kb_methodology` 检索到，并带 snippet_id 可追溯
- 写作模块可选开启“方法论优先”召回策略
