# BidExpert（bidexpert）国产模型落地：Codex 代码修订喂养文件（可直接复制给 Codex）

> 目标：在 **仅使用国产模型** 的前提下，为仓库 https://github.com/palmtom316/bidexpert 完成可落地的代码修订与配置落盘。
>
> 你需要交付：
> 1) 新增/替换两套国产模型 registry：`model_registry.cn.debug.json` 与 `model_registry.cn.prod.json`
> 2) 新增章节级模型路由策略（哪些章节必须使用 **DeepSeek-R1** 做二次强化与审查）
> 3) 在代码层面把“章节路由”接入生成流水线（GENERATE/REVIEW），并保持现有回退（fallback）机制不被破坏
>
> 约束：
> - 只允许使用国产模型：DeepSeek / Qwen（阿里百炼）/ Kimi / GLM（智谱）/ 文心（可选）
> - 调试（debug）方案：尽量低价/免费额度但稳定
> - 生产（prod）方案：质量优异、惊艳，同时成本可控（分层路由）
> - 必须保持输出的 **JSON Schema** 稳定与可验证（校验失败即重试/降级）
> - 不要引入不必要的重构；以最小可交付改动为主

---

## 0. 你需要先做的仓库扫描（Codex 操作清单）

1. 拉取仓库并检索模型相关文件：
   - `app/config/model_registry.json`（或同名路径）
   - `app/**` 中与 role / routing / model policy / provider profiles 相关的文件
   - 生成流程（GENERATE）与审查流程（REVIEW）的位置：查找关键字 `GENERATE`, `REVIEW`, `role`, `model_registry`, `fallback`, `policy`, `router`

2. 确认系统如何选择模型：
   - 是否按 role 固定模型？
   - 是否支持 provider profile / environment overrides？
   - 是否有“按章节/任务类型”的动态路由点（如果没有，需要新增，但要最小改动）

3. 找到生成 pipeline 的输入结构：
   - 章节对象结构（如 section_id/title/weight/keywords 等）
   - 能否在 section meta 里加入 `risk_level` / `critical` 字段
   - REVIEW 是否对每章节单独跑，还是对整篇输出跑

---

## 1. 交付物 A：国产模型专用 model_registry（Debug + Prod）

> 请将下面两份 JSON 以**新文件**形式加入仓库：
> - `app/config/model_registry.cn.debug.json`
> - `app/config/model_registry.cn.prod.json`
>
> 如果仓库不是这个路径，请按现有 `model_registry.json` 所在目录放置，并在 README/配置加载处增加可选项。

### 1.1 Debug：`model_registry.cn.debug.json`

设计意图：
- 全链路可跑、便宜、稳定
- 生成用 Qwen 便宜档，审查用 R1（推理强）
- EXTRACT/QUERY_REWRITE 尽量用 Turbo/Chat 级别

```json
{
  "version": "cn-debug-1.0",
  "notes": "国产模型调试配置：低成本优先，保证 JSON 稳定与可回退。",
  "roles": {
    "EXTRACT": {
      "primary": { "provider": "deepseek", "model": "deepseek-chat" },
      "fallback": [
        { "provider": "qwen", "model": "qwen-turbo" },
        { "provider": "glm", "model": "glm-4" }
      ]
    },
    "QUERY_REWRITE": {
      "primary": { "provider": "qwen", "model": "qwen-turbo" },
      "fallback": [
        { "provider": "deepseek", "model": "deepseek-chat" }
      ]
    },
    "EMBED": {
      "primary": { "provider": "qwen", "model": "text-embedding-v3" },
      "fallback": [
        { "provider": "glm", "model": "embedding-3" }
      ]
    },
    "GENERATE": {
      "primary": { "provider": "qwen", "model": "qwen-plus" },
      "fallback": [
        { "provider": "qwen", "model": "qwen-turbo" },
        { "provider": "deepseek", "model": "deepseek-chat" }
      ]
    },
    "REVIEW": {
      "primary": { "provider": "deepseek", "model": "deepseek-reasoner" },
      "fallback": [
        { "provider": "qwen", "model": "qwen-max" }
      ]
    },
    "PROGRAM_SUPPORT": {
      "primary": { "provider": "qwen", "model": "qwen-coder" },
      "fallback": [
        { "provider": "glm", "model": "glm-4" }
      ]
    }
  },
  "providers": {
    "deepseek": {
      "base_url_env": "DEEPSEEK_BASE_URL",
      "api_key_env": "DEEPSEEK_API_KEY",
      "timeout_ms": 60000
    },
    "qwen": {
      "base_url_env": "DASHSCOPE_BASE_URL",
      "api_key_env": "DASHSCOPE_API_KEY",
      "timeout_ms": 60000
    },
    "glm": {
      "base_url_env": "ZHIPU_BASE_URL",
      "api_key_env": "ZHIPU_API_KEY",
      "timeout_ms": 60000
    }
  }
}
```

> 说明：
> - Qwen embedding 模型名可能因平台不同略有差异（如百炼/通义千问/Model Studio）。如果仓库已有更精确的 model id，请以仓库已有的命名体系为准并替换这里的占位名。
> - 重点是 role->primary/fallback 结构与 provider 环境变量对齐。

---

### 1.2 Prod：`model_registry.cn.prod.json`

设计意图：
- 质量惊艳但成本可控（分层：Qwen-Max 生成，R1 负责关键章节强化 + 终审）
- EXTRACT 使用 Kimi 长上下文（如果仓库 provider 支持），fallback 到 DeepSeek
- REVIEW 优先 R1；生成关键章节可走 “Qwen-Max → R1 强化”

```json
{
  "version": "cn-prod-1.0",
  "notes": "国产模型生产配置：质量优先 + 成本可控，采用章节分层路由与审查兜底。",
  "roles": {
    "EXTRACT": {
      "primary": { "provider": "kimi", "model": "kimi-long" },
      "fallback": [
        { "provider": "deepseek", "model": "deepseek-chat" },
        { "provider": "qwen", "model": "qwen-max" }
      ]
    },
    "QUERY_REWRITE": {
      "primary": { "provider": "qwen", "model": "qwen-turbo" },
      "fallback": [
        { "provider": "deepseek", "model": "deepseek-chat" }
      ]
    },
    "EMBED": {
      "primary": { "provider": "qwen", "model": "text-embedding-v3" },
      "fallback": [
        { "provider": "glm", "model": "embedding-3" }
      ]
    },
    "GENERATE": {
      "primary": { "provider": "qwen", "model": "qwen-max" },
      "fallback": [
        { "provider": "qwen", "model": "qwen-plus" },
        { "provider": "deepseek", "model": "deepseek-chat" }
      ]
    },
    "REVIEW": {
      "primary": { "provider": "deepseek", "model": "deepseek-reasoner" },
      "fallback": [
        { "provider": "qwen", "model": "qwen-max" }
      ]
    },
    "PROGRAM_SUPPORT": {
      "primary": { "provider": "qwen", "model": "qwen-coder" },
      "fallback": [
        { "provider": "glm", "model": "glm-4" }
      ]
    }
  },
  "providers": {
    "deepseek": {
      "base_url_env": "DEEPSEEK_BASE_URL",
      "api_key_env": "DEEPSEEK_API_KEY",
      "timeout_ms": 90000
    },
    "qwen": {
      "base_url_env": "DASHSCOPE_BASE_URL",
      "api_key_env": "DASHSCOPE_API_KEY",
      "timeout_ms": 90000
    },
    "glm": {
      "base_url_env": "ZHIPU_BASE_URL",
      "api_key_env": "ZHIPU_API_KEY",
      "timeout_ms": 90000
    },
    "kimi": {
      "base_url_env": "KIMI_BASE_URL",
      "api_key_env": "KIMI_API_KEY",
      "timeout_ms": 90000
    }
  }
}
```

> 说明：
> - 如果仓库没有 `kimi` provider 实现：请先不接入 `kimi`，保留 prod 中 EXTRACT primary=deepseek-chat 并将 `kimi` 作为未来扩展（或先实现一个最小 provider adapter）。
> - 生产阶段最重要：**章节分层路由**（见下节），让 R1 用在关键章节与终审，控制成本。

---

## 2. 交付物 B：章节级模型路由策略（必须上 R1 的章节）

> 你需要实现一个函数/模块，例如：
> - `app/core/section_router.py`
> - 或在现有 router/policy 模块中新增 `select_models_for_section(section)` 的逻辑
>
> 输入：章节 metadata（至少包含 `title`，如果有 `chapter_path/heading_level/weight` 更好）
> 输出：本章节的生成模型策略：`base_model` + `post_enhance_model` + `review_model`

### 2.1 关键章节判定规则（默认）

将以下章节视为 **Critical（必须 R1 强化/审查）**：

1) 技术方案类（极高权重）
- `技术方案`
- `施工组织设计`
- `施工方案`
- `总体方案`
- `项目实施方案`
- `技术路线`
- `工艺流程`
- `关键工序`
- `施工部署`

2) 进度/资源/组织类（高权重）
- `进度计划`
- `工期`
- `资源配置`
- `人员组织`
- `项目组织机构`
- `劳动力计划`
- `设备/机械配置`
- `材料计划`

3) 质量/安全/合规类（致命错误高风险）
- `质量保证措施`
- `质量控制`
- `质量管理体系`
- `安全文明施工`
- `安全管理`
- `HSE`
- `风险控制`
- `应急预案`
- `环保`
- `职业健康`

4) 商务响应与偏离表（最容易废标）
- `商务响应`
- `偏离表`
- `响应表`
- `资格/资信`
- `承诺函`
- `业绩`
- `类似项目`
- `条款响应`

5) 价格/清单相关（如果系统生成覆盖到此类内容）
- `报价说明`
- `工程量清单`
- `报价汇总`
- `计价`

> 只要 title 命中以上关键词（包含匹配）即可判为 Critical。
> 如果仓库已有“评分权重”字段（如 `section.weight >= 0.7`），应优先使用权重判定。

### 2.2 路由动作（Prod）

- 普通章节：
  - `base_model = qwen-max`
  - `post_enhance_model = null`（不走 R1 二次强化）
  - `review_model = deepseek-reasoner`（可选：抽样审查或仅整标终审）

- Critical 章节：
  - 先用 `qwen-max` 生成初稿（控制风格与中文表达）
  - 再用 `deepseek-reasoner` 做**二次强化**（逻辑一致性、指标一致、引用证据对齐、格式对齐）
  - 最后仍用 `deepseek-reasoner` 做**结构化审查**并输出 `review_report.json`

### 2.3 路由动作（Debug）

- 普通章节：
  - `base_model = qwen-plus`（便宜）
  - `post_enhance_model = null`
  - `review_model = deepseek-reasoner`（仅在 debug 的“质量闸门模式”开启时调用）

- Critical 章节：
  - `base_model = qwen-plus`
  - `post_enhance_model = deepseek-reasoner`（可配置开关）
  - `review_model = deepseek-reasoner`

---

## 3. 代码改动要求（你要怎么写进系统）

### 3.1 新增一个章节路由配置文件（可选但推荐）

新增：`app/config/section_routing.cn.json`

```json
{
  "version": "cn-routing-1.0",
  "critical_keywords": [
    "技术方案", "施工组织", "施工方案", "总体方案", "项目实施方案", "技术路线", "工艺流程", "关键工序", "施工部署",
    "进度计划", "工期", "资源配置", "人员组织", "组织机构", "劳动力", "设备", "机械", "材料计划",
    "质量", "质量保证", "质量控制", "质量管理", "安全", "文明施工", "HSE", "风险", "应急预案", "环保", "职业健康",
    "商务响应", "偏离表", "响应表", "资格", "资信", "承诺函", "业绩", "类似项目", "条款响应",
    "报价", "清单", "计价"
  ],
  "critical_weight_threshold": 0.7
}
```

> 你需要在代码里读取该文件（若仓库已有 config loader，沿用现有方式）。

---

### 3.2 新增/修改：章节路由函数（伪代码）

请将伪代码落为真实代码（Python/TS 以仓库为准）：

```python
def is_critical_section(section) -> bool:
    title = (section.title or "").strip()
    weight = getattr(section, "weight", None)
    if weight is not None and weight >= critical_weight_threshold:
        return True
    for kw in critical_keywords:
        if kw in title:
            return True
    return False

def select_generation_plan(section, env_mode: str):
    # env_mode in {"debug", "prod"}
    plan = {
      "base_role": "GENERATE",
      "enhance": None,
      "review": {"role": "REVIEW"}  # default
    }
    if is_critical_section(section):
        plan["enhance"] = {"role": "REVIEW", "provider": "deepseek", "model": "deepseek-reasoner"}
        plan["review"] = {"role": "REVIEW", "provider": "deepseek", "model": "deepseek-reasoner"}
    return plan
```

---

### 3.3 生成流水线接入点（必须做）

你需要在“章节生成”的主循环/任务函数里接入：

- 先用 plan.base_role 做生成（通常走 `GENERATE`）
- 如果 plan.enhance 不为空：
  - 以“差分/修订”方式调用 R1，让它**只修改**：逻辑矛盾、术语不一致、指标冲突、证据引用不匹配、格式错位
  - 严禁 R1 重写整段导致风格漂移；必须提示“保留原结构，只做必要修订”

- REVIEW：
  - 对 Critical 章节，必须跑 REVIEW 并生成 `review_report`（JSON），如果失败则触发重试或回退到 fallback 生成模型再审查

> 重点：将 “enhance” 的输出再次过一遍 JSON Schema 校验（如果系统有），不通过则重试（最多 N 次）→ 降级策略。

---

## 4. R1 强化 Prompt 模板（写入代码的系统提示词）

> 你需要把这段 prompt 作为一个模板（例如 Jinja2/format），放在：
> - `app/prompts/section_enhance_r1_cn.md`（推荐）
> 或现有 prompt 目录中。

**模板：`SECTION_ENHANCE_R1_CN`**

```text
你是投标文件专家审校员。你的任务是对“章节初稿”做最小必要修订，使其满足：
1) 与证据片段一致（不得虚构）
2) 指标/参数前后一致（不得自相矛盾）
3) 结构与标题不变（不要重写、不要改标题层级）
4) 表述更正式、更符合投标语气
5) 输出必须为 JSON，符合给定 Schema

【输入】
- 章节标题：{section_title}
- 章节路径：{section_path}
- 章节初稿（Markdown）：{draft_md}
- 证据片段（可多条）：{evidence_snippets}
- 约束与Schema：{json_schema}

【输出要求】
仅输出 JSON，不要输出任何解释文字。
JSON 中必须包含：
- fixed_md: 修订后的 Markdown（保留原结构，仅做必要修订）
- issues: [{type, severity, location, description, evidence_id}]
- pass: true/false
- suggestions: [string]

若证据不足以支撑某句，请将该句改为“待确认/以招标文件为准”的谨慎表述，并在 issues 标注。
```

---

## 5. 终审 REVIEW Prompt（整标/整章）模板

建议新增：`app/prompts/final_review_r1_cn.md`

```text
你是投标文件终审专家。请基于输入的章节集合与证据，输出结构化审查报告 JSON：
- 是否存在致命错误（fatal）
- 是否存在高风险问题（high）
- 是否存在一般问题（medium/low）
- 逐条给出修复建议（可定位到章节与段落）

【输入】
- 文档/章节清单：{sections_index}
- 全文 Markdown：{full_md}
- 证据索引：{evidence_index}
- 规则清单：{rules}

【输出】
仅输出 JSON：
{
  "fatal": [ { "section": "...", "location": "...", "reason": "...", "fix": "..." } ],
  "high":  [ ... ],
  "medium":[ ... ],
  "low":   [ ... ],
  "summary": "...",
  "pass": true/false
}
```

---

## 6. 验收标准（必须满足）

1) 能通过本地运行（或 CI）完成一次端到端生成（至少一份 demo 招标输入）
2) 调试模式：
   - 默认走 `model_registry.cn.debug.json`
   - 生成成本显著降低
   - JSON 输出可解析，失败能自动重试/降级

3) 生产模式：
   - 默认走 `model_registry.cn.prod.json`
   - Critical 章节会触发 R1 强化（能从日志中看到路由决策）
   - 终审报告 JSON 必须稳定产出
   - 成本可控：普通章节不走 R1 强化

4) 文档与配置：
   - README 增加说明：如何通过环境变量切换 `CN_DEBUG / CN_PROD`
   - 给出示例 env：
     - `MODEL_REGISTRY_PATH=app/config/model_registry.cn.prod.json`
     - `SECTION_ROUTING_PATH=app/config/section_routing.cn.json`

---

## 7. Codex 具体输出要求（你要生成的 PR 内容）

请按如下文件结构提交变更：

- ✅ 新增：
  - `app/config/model_registry.cn.debug.json`
  - `app/config/model_registry.cn.prod.json`
  - `app/config/section_routing.cn.json`（推荐）
  - `app/prompts/section_enhance_r1_cn.md`
  - `app/prompts/final_review_r1_cn.md`

- ✅ 修改：
  - 配置加载：允许通过 env 指定 registry 路径
  - 章节生成 pipeline：接入 section router 与 enhance 步骤
  - 日志：打印每章节是否 critical、使用了哪些模型（role/provider/model）
  - 单元测试（如仓库有测试体系）：至少覆盖 `is_critical_section` 与路由输出

---

## 8. 注意事项（踩坑提醒）

- 模型命名：不同平台对 Qwen/GLM/Kimi 的 model id 命名不同。以仓库当前 provider adapter 支持的 id 为准；若不一致，请在 provider 层做映射。
- R1 的输出必须严格 JSON：调用时要启用“JSON 模式”（如果 adapter 支持），或用强约束 prompt + 解析失败重试。
- 强化（enhance）必须做“最小修订”：避免重写导致引用漂移与风格不一致。
- 回退策略：任何一步失败（解析/校验/超时），都应按 registry fallback 自动切换，而不是直接报错终止。

---

以上内容可直接喂给 Codex 作为“改代码任务说明 + 配置文件内容 + prompt 模板”。
