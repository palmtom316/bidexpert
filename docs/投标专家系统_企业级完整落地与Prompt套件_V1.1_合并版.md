# 投标专家系统｜企业级完整落地与 Prompt 套件 release/V1.0（合并版）

> 合并时间：2026-02-21 本文档包含： 1️⃣ 企业级质量控制 + AI 编程落地包
> release/V1.0\
> 2️⃣ Claude Prompt 套件 release/V1.0

# 第一部分：企业级质量控制 + AI 编程落地包

# 投标专家系统｜企业级质量控制 + AI 编程落地包（release/V1.0 修订增强版）

> 修订时间：2026-02-20
> 本版本整合深度审查意见，增强任务编排、二阶段检索、父子块策略、全局事实表、一致性前置约束、结构化输出自修正机制。

------------------------------------------------------------------------

# 一、任务编排与断点续跑（新增）

## 异步任务架构

采用 Celery / RQ / 异步任务队列实现生成流水线。

### generation_runs 表新增字段：

-   current_step: G0/G1/G2/G3/G4/G5
-   step_status: parsing_done / generating / validating / failed /
    paused
-   resume_from_step: 可断点恢复
-   retry_count
-   last_error

原则：

-   每个闸门产物必须落地 JSON 文件
-   任何步骤失败可从最近成功闸门继续
-   禁止整链路重跑

------------------------------------------------------------------------

# 二、检索增强升级

## 二阶段检索架构（Hybrid + Rerank）

流程：

1.  Qdrant Hybrid TopK = 50\~100
2.  Cross-Encoder Reranker 精排
3.  取 TopN = 10\~20 进入 Prompt
4.  关键数字/型号执行规则过滤

目的：避免电压等级、型号数值混淆。

------------------------------------------------------------------------

# 三、Parent-Child Chunk 策略

## 新增字段

-   parent_chunk_id
-   anchor_type: clause / table / paragraph

使用方式：

-   检索命中子块
-   拼装时通过 parent_chunk_id 拉取完整父段落或整表
-   保证上下文完整

------------------------------------------------------------------------

# 四、Global Facts Sheet（前置一致性约束）

在 G1 阶段生成 global_facts.json：

``` json
{
  "project_name": "",
  "total_duration_days": 120,
  "project_manager": {
    "name": "",
    "certificate_no": ""
  },
  "voltage_level": "110kV"
}
```

所有章节生成必须引用该事实表，禁止自行编造冲突变量。

------------------------------------------------------------------------

# 五、一致性抽取升级

策略：

1.  正则/规则抽取 70%
2.  抽取失败 → 本地 LLM Function Calling 兜底
3.  Pydantic 校验
4.  冲突检测

------------------------------------------------------------------------

# 六、结构化输出自修正（Instructor 推荐）

建议引入 Instructor 库：

优势：

-   自动 JSON Schema 校验
-   自动重试修正
-   减少手写重试逻辑

原则：所有 LLM 输出必须通过 Schema 校验。

------------------------------------------------------------------------

# 七、证据可视化增强

在 python-docx 输出时：

-   将 evidence 转为 Word Comment
-   或生成脚注/尾注
-   高风险段落高亮显示

------------------------------------------------------------------------

# 八、JSONB + GIN 索引优化

-   所有 \*\_json 字段使用 PostgreSQL JSONB
-   建立 GIN 索引
-   支持风险统计分析

------------------------------------------------------------------------

# 九、优先级排序

P0：

-   异步任务编排
-   二阶段检索
-   Global Facts Sheet
-   Parent-Child Chunk
-   Instructor 校验

P1：

-   Word 批注溯源
-   JSONB 索引
-   本地模型辅助抽取

------------------------------------------------------------------------

# 结论

release/V1.0 版本实现：

-   异步可恢复流水线
-   精排防误检索
-   前置一致性控制
-   可视化证据溯源
-   结构化输出稳定机制

# 第二部分：Claude Prompt 套件

# Claude Prompt 套件 release/V1.0（投标专家系统专用）

> 生成时间：2026-02-20 适配版本：投标专家系统 企业级质量控制 release/V1.0
> 目标：将 Claude 从"写作助手"升级为"结构化投标生成引擎"

------------------------------------------------------------------------

# 一、通用规则（所有 Prompt 必须包含）

你是结构化投标生成引擎。

必须遵守：

1.  只输出合法 JSON。
2.  不允许输出 JSON 以外的任何文本。
3.  若信息不足，填 null，不允许编造。
4.  所有关键陈述必须附带 evidence。
5.  不得生成与 Global Facts 冲突的变量。
6.  不得使用宣传性或夸大承诺语言。

------------------------------------------------------------------------

# 二、招标拆解 Prompt（Tender Parsing）

用途：生成 TenderRules JSON。

Prompt 模板：

你是招标规则拆解引擎。

任务：抽取 mandatory_requirements、scoring_items、deliverables。

必须输出合法 JSON。

输入： {{tender_md}}

------------------------------------------------------------------------

# 三、Global Facts 生成 Prompt

用途：生成全局事实表。

Prompt 模板：

你是全局事实提取引擎。

只输出 JSON：

{ "project_name": "","total_duration_days": null, "project_manager": {
"name": null, "certificate_no": null }, "voltage_level": null,
"contract_amount": null }

输入： {{confirmed_data}}

------------------------------------------------------------------------

# 四、章节生成 Prompt（核心）

Prompt 模板：

你是结构化投标生成引擎。

【Global Facts】 {{global_facts_json}}

【招标规则子集】 {{relevant_requirements}}

【评分项子集】 {{relevant_scoring}}

【Rerank 后检索证据（含 parent_context）】 {{top_chunks}}

输出 JSON：

{ "section_path": "","content": "","covers_req": \[\], "targets_score":
\[\], "evidence": \[ { "doc_id": "","page_range": {"start_page": 0,
"end_page": 0}, "chunk_id": "" } \], "assumptions": \[\], "risk_flags":
\[\] }

------------------------------------------------------------------------

# 五、一致性抽取 Prompt

提取字段：

{ "total_duration_days": null, "project_manager_name": null,
"certificate_no": null, "voltage_level": null }

输入： {{document_text}}

------------------------------------------------------------------------

# 六、审稿 Prompt

只输出 JSON：

{ "issues": \[ { "severity": "high\|medium\|low", "type": "","location":
"","desc": "","suggest_fix": "" } \], "overall_risk":
"low\|medium\|high" }

输入： {{generated_section_json}}

------------------------------------------------------------------------

# 七、修复 Prompt

根据 issues 修复章节。

保持 JSON 结构不变。 不得修改 Global Facts。

输入： {{issues_json}} {{original_section_json}}

------------------------------------------------------------------------

# 八、温度建议

  模块           temperature
  -------------- -------------
  招标拆解       0\~0.2
  Global Facts   0
  一致性抽取     0
  章节生成       0.3\~0.5
  审稿           0\~0.2
  修复           0.2\~0.3

------------------------------------------------------------------------

# 结论

Claude 的角色：

结构化生成与审查引擎。

所有输出必须可验证、可溯源、可修复。
