# AI 辅助投标系统
# 企业级技术白皮书 v3.6（BYOK：用户自带 API Key + 多供应商模型选择）

> v3.6 在 v3.5（LangExtract + RAG-Strategy 集成）基础上，新增 **BYOK（Bring Your Own Key）** 能力：
> 允许用户像翻译软件一样，自行配置并选择商业模型供应商（Qwen/DeepSeek/Doubao/OpenAI/Gemini…），系统只负责：
> **安全门禁（脱敏/报价熔断） + 证据绑定 + 检索增强 + 章节生成/审查编排 + WPS Web 输出 + 审计与预算治理**。

---

## 1. 目标与边界

### 1.1 目标
- 用户可在 UI 中配置 **供应商 + API Key + base_url + 默认模型**。
- 项目可选择：生成模型 / 审查模型 / embedding 模型（可不同供应商）。
- 所有模型调用仍然走统一的 **LLM Gateway**，确保安全策略一致。

### 1.2 不变的安全底线
- **报价熔断**：命中价格/报价/总价等敏感内容 → 严禁外发。
- **PII 脱敏**：身份证/电话/邮箱等敏感信息必须掩码后再外发。
- **外发最小化**：只发送“本章条款 + TopK 证据 + Schema”，禁止整本外发。
- **证据强绑定**：生成内容必须绑定 evidence_ids；缺证据输出 NEED_HUMAN_INPUT。
- **三层防线**：生成（Qwen/用户选）→ 审查（GPT/Gemini/用户选）→ 本地验证器。

---

## 2. BYOK 三种工作模式（可逐步实现）

### 2.1 模式 A：项目级 Provider Profile（推荐默认）
- 每个项目绑定一个或多个 Provider Profile（生成/审查/embedding 分别可选）。
- 优点：易用、可审计、费用归属清晰。

### 2.2 模式 B：临时 Key（最高安全）
- Key 只在本次会话有效，不落库；存内存或 Redis（TTL 30~60 分钟）。
- 优点：泄露风险最低；缺点：每次需输入。

### 2.3 模式 C：管理员集中配置（传统企业）
- 由管理员统一配置企业 Key；普通用户不可见。
- 优点：运维简单；缺点：不满足“用户自带 Key”主诉。

> v3.6 优先落地：**A + B**（项目级 + 临时 Key）。

---

## 3. 架构变化（最小改动）

### 3.1 新增核心概念：Provider Profile
- provider_profile：描述“用哪家供应商 + 怎么访问 + 用哪个模型 + Key 从哪取”。
- router 只负责：按 task_type 选“模型角色”（生成/审查/embedding），最终由 profile 决定具体 provider/model。

### 3.2 Gateway 增强：动态凭据与多供应商适配
Gateway 增加：
- `Credential Resolver`：根据 provider_profile.secret_ref 取回 key（加密存储/临时 key）。
- `Adapter Registry`：按 provider 类型调用对应 adapter。
- `Policy Engine` 不变：熔断/脱敏/预算/审计仍强制执行（BYOK 不可绕过）。

---

## 4. 数据库设计（新增/变更）

### 4.1 provider_profile（新增表）
字段建议：
- id (uuid)
- scope (PROJECT | USER | TENANT)  # v3.6 先实现 PROJECT
- scope_id (uuid)                  # project_id 或 user_id
- provider (qwen | deepseek | doubao | openai | gemini | glm ...)
- base_url (text, nullable)        # 支持自建代理/网关
- default_model (text)
- key_storage (ENCRYPTED_DB | TEMP_REDIS | VAULT)
- key_secret_ref (text)            # 指向加密存储或 Redis key
- allowed_tasks (jsonb)            # 允许哪些 task_type（RBAC）
- created_by (uuid)
- created_at, updated_at

### 4.2 project_model_policy（新增表，或并入 project 配置）
- project_id
- generate_profile_id
- review_profile_id
- embed_profile_id
- enable_review (bool)
- budget_token_total, budget_token_used
- concurrency_limits (jsonb)

### 4.3 llm_call_log（增强）
新增字段：
- provider_profile_id
- caller_id
- budget_remaining
- blocked_reason (PRICING_BLOCKED | PII_BLOCKED | BUDGET_EXCEEDED ...)

---

## 5. 密钥管理与安全实现（强制）

### 5.1 不允许明文落库
- UI 提交的 API Key 只能走 HTTPS（内网也建议 TLS）。
- 后端存储必须：
  - ENCRYPTED_DB：AES-GCM 加密后保存（主密钥来自环境变量/硬件/密钥服务）；或
  - VAULT/Barbican：保存 secret_ref；或
  - TEMP_REDIS：仅临时 TTL 存储（不落库）。

### 5.2 日志与审计
- 禁止记录：Authorization header、明文 key、完整 prompt。
- 允许记录：prompt_hash、schema_version、provider/model、token/latency、policy_report。

### 5.3 预算与滥用防护（必须）
- project budget：token_budget_total / used
- per-task caps：max_input_tokens / max_output_tokens
- retry/fallback 上限
- 并发上限（章节并发、embedding 并发）
- 超限返回：BUDGET_EXCEEDED

---

## 6. API 与 UI 交互（最小闭环）

### 6.1 Provider 配置 UI
- 选择 provider（下拉）
- 输入 API Key（密码框）
- base_url（可选）
- 默认模型（下拉或输入）
- 「测试连接」按钮（调用 /gateway/health 或 /models）
- 绑定到项目（生成/审查/embedding）

### 6.2 后端接口（示例）
- POST /api/provider-profiles  创建 profile（保存加密 key 或临时 ref）
- GET /api/provider-profiles?project_id=...
- POST /api/provider-profiles/{id}/test  测试连接
- PUT /api/projects/{id}/model-policy  绑定生成/审查/embedding profile
- GET /api/projects/{id}/model-policy

---

## 7. 多模型工作流（v3.6 推荐默认）

- 生成：Qwen3-Max（或用户选的生成 profile）
- 审查：GPT-5.3（或用户选）
- Embedding：text-embedding-v4（或用户选）

约束：
- 若审查 profile 不可用（网络/Key 缺失），降级为：
  - 国内推理模型（可选）或
  - 仅本地验证器（风险提示提升）

---

## 8. 兼容 v3.5：LangExtract + RAG-Strategy 不变
- LangExtract 抽取调用使用“生成 profile”或单独的“extract profile”
- RAG 检索管线与审计（retrieval_log）保持 v3.5 设计

---

## 9. 交付建议（实施优先级）
P0（必须）：
- provider_profile + 加密存储
- project_model_policy 绑定
- gateway 动态 adapter + policy 不可绕过
- test connection
- llm_call_log 增强（含 profile_id）

P1（建议）：
- TEMP_REDIS 临时 key
- allowed_tasks RBAC（禁止 api-server 直接 generate）
- provider 失败自动降级链（fallback）
