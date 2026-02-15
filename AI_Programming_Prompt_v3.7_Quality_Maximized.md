# AI 编程实施 Prompt 文件

# v3.7 质量最大化版本

目标：实现支持"质量最大化模型矩阵"的投标系统。

------------------------------------------------------------------------

## 一、必须实现的能力

1.  支持以下角色模型：
    -   EXTRACT
    -   EMBED
    -   GENERATE
    -   REVIEW
    -   QUERY_REWRITE
    -   PROGRAM_SUPPORT
2.  每个角色通过 provider_profile 动态选择模型。
3.  必须支持多供应商并可替换。
4.  所有模型调用必须经过 Gateway。

------------------------------------------------------------------------

## 二、必须实现的结构

-   api/
-   worker/
-   llm/
-   rag/
-   validator/
-   extract/
-   renderer/
-   models/
-   config/

------------------------------------------------------------------------

## 三、关键实现任务

### 1. Model Registry

实现 model_registry.yaml： - provider - model_name - capabilities -
max_input_tokens - supports_json_schema - supports_tool_calling

### 2. Adapter Registry

支持： - OpenAI Adapter - Gemini Adapter - Qwen Adapter - DeepSeek
Adapter

### 3. Quality Enforcement

-   所有生成输出必须通过 JSON Schema 校验
-   审查输出必须 JSON
-   MUST 条款覆盖率校验
-   子串证据匹配校验

------------------------------------------------------------------------

## 四、默认首选模型（可替换）

-   EXTRACT: Gemini 3 Pro
-   EMBED: text-embedding-3-large
-   GENERATE: Gemini 3 Pro
-   REVIEW: OpenAI o1
-   QUERY_REWRITE: Gemini 3 Flash
-   PROGRAM_SUPPORT: GPT-5.3-Codex

替换规则： 如 profile 未配置首选模型，则 fallback 至备选模型。

------------------------------------------------------------------------

## 五、安全要求

-   报价熔断
-   PII 脱敏
-   Token 预算控制
-   不记录 API Key

------------------------------------------------------------------------

## 六、最小闭环目标

1.  上传招标文件
2.  抽取 Requirement JSON
3.  构建矩阵
4.  检索 TopK 证据
5.  生成章节
6.  审查
7.  导出 WPS 文档

------------------------------------------------------------------------

请先实现最小闭环版本，再逐步优化。
