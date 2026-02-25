# 给 Codex / Claude Code 的统一代码修改文件（合并版）
## Tender 模块 v1.1 升级版 + 《防废标红线架构 v2.0》+ Codex 修改清单（增强版）

> 目标：在现有 AI 投标辅助系统（bidexpert/同类）中，把 tender（招标文件）处理从 v1.0 升级到 v1.1：
> - 严格对齐真实评标流程：**符合性审查（初审，一票否决）→ 详细评审（打分）**
> - 增加“偏离表”机制：自动生成《商务/技术偏离表》框架并强制纳入任务图（P00）
> - 强化“行政性废标”识别：签章/份数/装订/联合体/分包等死线提取 + 最终核对清单（P00）
> - 强化“关键人员锁定与排他”：无在建/社保月数/类似业绩年限等约束→资产 SQL 硬过滤
> - 在生成 bid_blueprint 前增加 **FATAL 闸门**：若企业资产无法通过初审则直接阻断后续编写，避免无效劳动
>
> 前提：招标 PDF 使用 MinerU Windows 桌面版解析，人工打包为 `{tender_id}.tender.zip` 上传系统。系统不调用 MinerU API。

---

# Part 1：Tender 模块 v1.1 升级版（设计规格）

## 1.1 入口与产物（保持 v1.0，不破坏兼容）

### 输入（tender.zip）结构（强制）
```text
{tender_id}.tender.zip
└─ {tender_id}/
   ├─ manifest.json
   ├─ original.pdf
   ├─ full.md
   ├─ content_list_v2.json          # 可选
   ├─ block_list.json               # 可选
   └─ images/                       # 可选
```

### 输出（Project Workspace）结构（v1.1 新增字段见下）
```text
projects/{tender_id}/
  ├─ tender_source/
  ├─ derived/
  │   ├─ tender_sections.json
  │   ├─ compliance_check.json                 # v1.1 强化：分离初审/详细评审关注点
  │   ├─ preliminary_evaluation.json           # v1.1 新增：初审结构化（可选：也可内嵌在 compliance_check）
  │   ├─ scoring_model.json
  │   ├─ technical_requirements.json           # v1.1 强化：deviation_tracking
  │   ├─ deviation_tables.json                 # v1.1 新增：偏离表结构框架（预填）
  │   ├─ format_signature_constraints.json     # v1.1 新增：签章/份数/装订/联合体/分包
  │   ├─ key_personnel_constraints.json        # v1.1 新增：项目经理/安全员/技术负责人锁定要求
  │   ├─ fatal_gate_report.json                # v1.1 新增：初审资产校验与阻断原因
  │   ├─ bid_blueprint.json
  │   └─ import_report.json
  └─ logs/
```

> 注：也可只输出 `compliance_check.json` 一个文件，但 **必须包含**下文 v1.1 的四类新增结构（preliminary / deviation / format_signature / key_personnel）。为了工程清晰，推荐拆成单文件。

---

## 1.2 状态机（v1.1 强化：把“活下来”放在“拿高分”之前）

### tender_run steps（新增/调整）
- `RECEIVED`
- `UNPACKED`
- `VALIDATED`
- `SECTIONIZED`
- `PRELIM_EXTRACTED`              # v1.1 新增：初审/资格审查抽取
- `FATAL_GATE_CHECKED`            # v1.1 新增：企业资产/人员资产可行性校验（阻断点）
- `SCORING_EXTRACTED`
- `TECH_EXTRACTED`
- `DEVIATION_BUILT`               # v1.1 新增：偏离追踪与偏离表框架
- `FORMAT_SIGNATURE_EXTRACTED`    # v1.1 新增：行政死线提取与核对清单
- `BLUEPRINT_BUILT`
- `READY_FOR_WRITING`
- `FATAL_BLOCKED`                 # v1.1 新增：初审不通过，直接停止后续流程
- `FAILED`

### 关键规则（强制）
- `FATAL_GATE_CHECKED` 若发现任一 “fatal_if_unmet=true 且企业现有资产不满足” → `FATAL_BLOCKED`，并输出 `fatal_gate_report.json`。  
- 只有通过 FATAL 闸门，才允许进入 `SCORING_EXTRACTED` 与后续生成任务。

---

## 1.3 compliance_check.json（v1.1：强制分离初审与风险）

### 必须包含结构（强制）

#### A) preliminary_evaluation（初审/符合性审查，一票否决）
- `qualification_requirements`（企业资质、财务、信誉等）
- `key_personnel_requirements`（项目经理/安全员/技术负责人硬条件）
- `submission_requirements`（保证金、投标有效期、响应文件份数等）
- 每项必须包含：`fatal_if_unmet`（布尔）

示例：
```json
{
  "preliminary_evaluation": {
    "qualification_requirements": [
      {"item": "电力工程施工总承包三级及以上", "fatal_if_unmet": true, "evidence": "投标须知-xx页"}
    ],
    "submission_requirements": [
      {"item": "投标保证金按要求提交", "fatal_if_unmet": true, "evidence": "投标须知-xx页"}
    ]
  }
}
```

#### B) detailed_review_risks（详细评审风险点）
这是“扣分/争议/风险提示”，不应与初审混在一起。
```json
{"detailed_review_risks":[{"risk":"技术方案未覆盖评分点：进度保障","severity":"medium"}]}
```

---

## 1.4 偏离追踪（v1.1：deviation_tracking + deviation_tables）

### 1) technical_requirements.json 增加 deviation_tracking（强制）
从 technical/commercial/instruction 章节提取“必须响应/承诺/参数要求/条款要求”。
```json
{
  "deviation_tracking": [
    {"type":"technical","requirement":"质保期不少于3年","default_response":"无偏离","source":"技术规范书-xx"},
    {"type":"commercial","requirement":"付款方式按合同条款执行","default_response":"无偏离","source":"合同条款-xx"}
  ]
}
```

### 2) 生成 deviation_tables.json（强制）
系统必须生成“可直接填报/导出”的偏离表框架：
- 商务偏离表
- 技术偏离表
- 参数响应表（若存在参数表）

最小结构：
```json
{
  "commercial_deviation_table": [
    {"clause":"付款方式","tender_requirement":"按合同条款","bid_response":"无偏离","deviation":"无","evidence_ref":"..."},
    {"clause":"工期","tender_requirement":"120日历天","bid_response":"承诺120日历天","deviation":"无","evidence_ref":"..."}
  ],
  "technical_deviation_table": [
    {"item":"质保期","tender_requirement":"≥3年","bid_response":"承诺3年","deviation":"无","evidence_ref":"..."}
  ]
}
```

### 3) 蓝图任务图中强制加入偏离表任务（P00）
```json
{"task_type":"generate_deviation_tables","priority":"P00","inputs":["technical_requirements.json","format_signature_constraints.json"]}
```

---

## 1.5 行政性废标（Format & Signature Constraints）v1.1 强化

### 1) 新增 format_signature_constraints.json（强制）
必须专项抽取（正则优先）：
- 加盖法定代表人印章/签字
- 逐页盖章/骑缝章
- 正本/副本份数
- 装订方式（胶装/活页）
- 是否允许联合体投标
- 分包限制
- 投标文件密封方式、递交截止时间

示例：
```json
{
  "format_constraints": {
    "original_copies": 1,
    "duplicate_copies": 4,
    "require_seal_each_page": true,
    "require_cross_page_seal": true,
    "require_legal_person_signature": true,
    "binding": "胶装",
    "allow_joint_bid": false,
    "subcontract_limit": "不得分包"
  }
}
```

### 2) 蓝图任务图必须加入“行政核对清单”（P00）
```json
{"task_type":"administrative_checklist","priority":"P00","items":["逐页盖章","骑缝章","正副本份数","密封与截止时间","联合体/分包限制"]}
```

---

## 1.6 关键人员锁定与排他（Key Personnel Constraints）v1.1 强化

### 新增 key_personnel_constraints.json（强制）
重点抓取对项目经理/安全员/技术负责人等的附加限制：
- 无在建工程
- 近半年社保
- 类似业绩年限/数量
- 特定注册专业/证书等级
- 必须本单位人员（社保/劳动合同）

示例：
```json
{
  "key_personnel_constraints": [
    {
      "role": "项目经理",
      "must_have_certificate": "一级建造师",
      "no_active_project": true,
      "social_security_months": 6,
      "similar_project_years": 5,
      "fatal_if_unmet": true,
      "evidence": "资格条件-xx页"
    }
  ]
}
```

### 资产匹配（必须联动）
在人员/业绩查询 SQL 中，作为硬 WHERE 条件：
- `expiration_date > today`
- `social_security_months >= required`
- `no_active_project = true`（若要求）
- `similar_project_years >= required`（若要求）

---

## 1.7 FATAL 闸门（v1.1：阻断无效劳动的核心）

### 触发条件（强制）
只要 `preliminary_evaluation` 中出现 `fatal_if_unmet=true` 的条款，系统必须对照企业结构化资产库做可行性校验：
- 企业资质等级/范围
- 财务/注册资本（若已入库）
- 关键人员证书有效期
- 关键人员无在建/社保（若资产库有字段）

### 输出 fatal_gate_report.json（强制）
```json
{
  "result": "FATAL_BLOCKED",
  "fatal_reasons": [
    {"item":"电力工程施工总承包三级及以上","required":"三级及以上","current":"无/不满足","action":"补齐资质或放弃投标"}
  ],
  "timestamp":"..."
}
```

---

# Part 2：《防废标红线架构 v2.0》（系统级约束）

> 本部分定义“不可妥协的红线控制点”，任何生成/检索/输出都不得绕过。

## 2.1 红线 R0：符合性审查优先于一切生成
- 未通过初审 → 不允许生成任何投标写作任务（直接 FATAL_BLOCKED）。

## 2.2 红线 R1：行政性要求必须强制清单化（P00）
- 签章/份数/装订/密封/截止时间/联合体/分包 → 进入 P00 清单
- 未完成 P00 清单，不允许导出最终投标文件包（可在写作模块设“发布闸门”）。

## 2.3 红线 R2：偏离表必须先于长文本呈现
- 必须生成《商务偏离表》《技术偏离表》框架
- 偏离表未生成 → 视为关键交付缺失，阻断 READY_FOR_WRITING 或阻断最终导出（可配置）。

## 2.4 红线 R3：关键人员锁定与排他必须硬过滤
- 无在建、社保月数、证书有效期、注册专业 → 作为 SQL WHERE 硬过滤
- 不允许把“不确定/缺字段”的人直接用于投标上下文（必须标记待人工确认）。

## 2.5 红线 R4：引用资产必须过滤有效期
- 任何证书/资质/业绩证明 → expiration_date 过期直接排除
- 不允许在 LLM 上下文中出现过期资产引用。

## 2.6 红线 R5：引用规范必须优先 active 版本
- 若同一标准存在新版本 → 旧版标记 deprecated，默认不召回
- 招标文件明确要求某版本时，必须锁定到该版本并提示冲突风险。

## 2.7 红线 R6：检索与复用必须遵循项目元数据硬过滤
- 电压等级/工程类型/地区/核心设备（可选） → Qdrant filter 先行
- 防止“110kV 方案混入 10kV 标书”的灾难性错误。

---

# Part 3：Codex 修改清单（增强版，按文件/模块落地）

> 下面是可直接交给 Codex 的“仓库内改造任务”。要求 Codex 输出：
> - 新增/修改文件清单
> - 关键代码 diff 或完整文件内容
> - 最小可运行闭环（import_zip → READY_FOR_WRITING 或 FATAL_BLOCKED）
> - 对应的最小测试（至少 5 个单测）

## 3.1 新增/修改 API

### 新增
- `POST /api/tender/import_zip`
- `GET /api/tender/runs/{run_id}`
- `GET /api/tender/runs/{run_id}/report`
- `GET /api/tender/runs/{run_id}/blueprint`
- （可选）`GET /api/tender/runs/{run_id}/fatal_gate_report`
- （可选）`GET /api/tender/{tender_id}/derived/{name}`（下载 derived 中任意产物）

### 行为要求
- API 线程只做：保存文件 → 建 run → 入队 → 返回 run_id
- 所有重活在 worker 中执行

---

## 3.2 新增数据表或复用 ingestion_runs（推荐复用）

### 方案 A（推荐）：复用 ingestion_runs 增加 run_type=tender
新增列：
- `run_type`（default='ingest'，tender 用 'tender'）
- `workspace_path`
- `tender_id`（可复用 doc_id）
- `fatal_blocked_reason`（json 可选）

并扩展 step 枚举支持 tender steps。

### 方案 B：新建 tender_runs 表
按 v1.0 的 tender_runs 建表即可，但会多维护一套 run 逻辑。

---

## 3.3 新增模块与文件（必须创建）

> 路径可按仓库风格调整，但职责必须一致。

1) `tender/zip_package.py`
- `unpack_zip()` `load_manifest()` `validate_tender_package()`

2) `tender/sectionizer.py`
- `build_sections(md_text, content_list=None)->tender_sections`

3) `tender/prelim_extractor.py`  ✅ v1.1 新增
- 输入：instruction + qualification 段落
- 输出：`preliminary_evaluation`（含 fatal_if_unmet）
- 规则优先 + LLM 补全（可选）

4) `tender/key_personnel_extractor.py` ✅ v1.1 新增
- 输出：`key_personnel_constraints.json`

5) `tender/format_signature_extractor.py` ✅ v1.1 新增
- 输出：`format_signature_constraints.json`
- 规则/正则优先（中文关键词表）

6) `tender/scoring_extractor.py`
- 输出：`scoring_model.json`（必须 schema 校验 100%）

7) `tender/technical_extractor.py`
- 输出：`technical_requirements.json`（必须识别电压等级，否则 FAILED）
- 内含 `mandatory_requirements` 与 `deviation_tracking`（v1.1 强制）

8) `tender/deviation_builder.py` ✅ v1.1 新增
- 输入：`technical_requirements.json` +（可选）`format_signature_constraints.json` + `tender_sections`
- 输出：`deviation_tables.json`

9) `tender/compliance_extractor.py`
- 输出：`compliance_check.json`（必须区分 preliminary_evaluation 与 detailed_review_risks）
- v1.1：可只负责 detailed_review_risks；prelim_extractor 单独产出 preliminary_evaluation（推荐拆分）

10) `tender/fatal_gate.py` ✅ v1.1 新增（核心）
- `check_preliminary_against_assets(prelim, asset_db)->(pass|block, report)`
- 输出：`fatal_gate_report.json`
- 若 block：更新 run.step=`FATAL_BLOCKED` 并停止后续流程

11) `tender/blueprint_builder.py`
- 输入：sections + scoring + technical + compliance + deviation_tables + format_signature + key_personnel
- 输出：`bid_blueprint.json`
- 强制生成 P00 任务：`generate_deviation_tables`、`administrative_checklist`

12) `tender/pipeline.py`
- 编排整个 v1.1 状态机流程，含 FATAL 闸门

13) `tasks/tender_tasks.py`
- 任务入队 + worker 消费

14) `tender/report.py`
- 输出：`import_report.json`（包含：是否 FATAL_BLOCKED、缺失字段、抽取覆盖率、条款数量、偏离表条目数等）

---

## 3.4 资产库联动：必须提供查询接口（SQL 硬过滤）

在仓库中新增/扩展资产查询 service：
- `assets/repository.py` 或 `db/assets_repo.py`
- 必须支持：
  - `get_company_qualifications()`
  - `get_people_candidates(role, constraints)`（含 expiration_date、社保月数、无在建等 WHERE）
  - `get_project_performance(constraints)`（按电压等级/年限等）

tender/fatal_gate.py 使用这些查询来决定是否阻断。

---

## 3.5 检索与写作对接（必须预留）

新增接口（可先 stub）：
- `POST /api/tender/{tender_id}/start_writing`
  - 输入：投标人名称/项目名称（可选）
  - 读取 `bid_blueprint.json`
  - 返回：writing_run_id 或创建草稿任务

强制规则：
- 写作模块检索专家库时，必须使用 `bid_blueprint.retrieval_policy.hard_filters` 做 Qdrant filter（电压等级/工程类型）。
- 资产引用必须走 DB，并过滤有效期。

---

## 3.6 最小测试清单（Codex 必须补齐）

至少新增 5 个单测：
1) `test_validate_tender_package_missing_manifest_fails`
2) `test_prelim_extractor_detects_fatal_clause`
3) `test_fatal_gate_blocks_when_qualification_missing`
4) `test_deviation_builder_generates_tables_from_tracking`
5) `test_format_signature_extractor_extracts_copies_and_seals`

可选：
- `test_pipeline_reaches_ready_for_writing_when_pass`
- `test_pipeline_sets_fatal_blocked_when_fail`

---

## 3.7 Codex 在仓库中的定位指令（必须执行）
在 repo 根目录运行（或让 Codex 用 ripgrep）：
- `rg -n "APIRouter|FastAPI|/api" -S .`
- `rg -n "ingest|import|upload|zip" -S .`
- `rg -n "runs|status|step|ingestion_runs" -S .`
- `rg -n "assets|qualification|people|certificate" -S .`
- `rg -n "worker|celery|rq|task|background" -S .`

---

# Part 4：实施顺序（建议 Codex 按此落地，降低失败率）

1) 先实现：`POST /api/tender/import_zip` + 解压校验 + run 状态推进（最小闭环）  
2) 实现：sectionizer + prelim_extractor + fatal_gate（先把“活下来”做对）  
3) 实现：scoring_extractor + technical_extractor（进入详细评审准备）  
4) 实现：deviation_builder + format_signature_extractor（偏离表与行政清单 P00）  
5) 实现：blueprint_builder + READY_FOR_WRITING  
6) 补齐：report + tests + 前端展示（下载 derived 文件）

---

# 交付验收（强制）

- 上传 tender.zip 后：
  - 若初审不通过：run 终态 `FATAL_BLOCKED`，并能下载 `fatal_gate_report.json`
  - 若通过：run 终态 `READY_FOR_WRITING`，并能下载 `bid_blueprint.json`、`deviation_tables.json`、`format_signature_constraints.json`
- 任何时候不得绕过：
  - 初审 FATAL 闸门
  - 偏离表生成（P00）
  - 行政清单（P00）
  - 关键人员硬过滤（SQL WHERE）
