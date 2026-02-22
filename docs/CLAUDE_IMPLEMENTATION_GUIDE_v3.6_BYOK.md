# CLAUDE_IMPLEMENTATION_GUIDE release/V1.0（BYOK：用户自带 Key + 多供应商）

> 目标：在 release/V1.0 基础上实现 BYOK。用户可选择供应商并输入 API Key，系统在不削弱安全门禁的前提下，动态调用不同商业模型服务商。

---

## 0. 实施原则（强制）
1) **任何 BYOK 不能绕过 Gateway 的 Policy Engine**（脱敏/熔断/预算/审计）。  
2) **Key 不得明文落库**，也不得出现在日志中。  
3) 供应商差异通过 `provider adapters` 统一抽象；业务层只认 task_type。  

---

## 1. 数据库 DDL（必须实现）

### 1.1 provider_profile
实现 PostgreSQL DDL（可用 Alembic）：
- id uuid pk
- scope text check in ('PROJECT','USER','TENANT')  # release/V1.0 先实现 PROJECT
- scope_id uuid not null
- provider text not null
- base_url text null
- default_model text not null
- key_storage text check in ('ENCRYPTED_DB','TEMP_REDIS','VAULT') not null
- key_secret_ref text not null          # ENCRYPTED_DB: 指向本表 encrypted_key 字段；TEMP_REDIS: redis key；VAULT: secret path
- encrypted_key bytea null              # 仅 ENCRYPTED_DB 使用（AES-GCM）
- allowed_tasks jsonb not null default '["*"]'
- created_by uuid null
- created_at timestamptz default now()
- updated_at timestamptz default now()

### 1.2 project_model_policy
- project_id uuid pk
- generate_profile_id uuid fk provider_profile(id)
- review_profile_id uuid fk provider_profile(id)
- embed_profile_id uuid fk provider_profile(id)
- enable_review boolean default true
- token_budget_total bigint default 500000
- token_budget_used bigint default 0
- concurrency_limits jsonb default '{"generate":3,"review":2,"embed":2}'

### 1.3 llm_call_log 增强
新增列：
- provider_profile_id uuid
- blocked_reason text null
- budget_remaining bigint null

---

## 2. 密钥加密存储（P0）

### 2.1 ENCRYPTED_DB：AES-GCM
实现 `secrets/crypto.py`：
- encrypt(api_key: str, master_key: bytes) -> (nonce, ciphertext, tag)
- decrypt(...) -> api_key

要求：
- master_key 从环境变量 `MASTER_KEY_B64` 读取（32 bytes）
- 数据库存储 encrypted_key = nonce+ciphertext+tag（或分列存储）
- 任何日志禁止打印明文 key

### 2.2 TEMP_REDIS（P1）
- key 写入 redis，TTL 3600 秒
- provider_profile.key_secret_ref = redis key
- 读取后可续期或不续期（默认不续期）

---

## 3. API（P0）

### 3.1 Provider Profiles
- POST /api/provider-profiles
  - 输入：provider, base_url, default_model, api_key, key_storage
  - 行为：加密存储，返回 profile_id（不返回明文 key）
- GET /api/provider-profiles?project_id=...
- POST /api/provider-profiles/{id}/test
  - 行为：用该 profile 做一次轻量调用（/models 或 /health）
- DELETE /api/provider-profiles/{id}
  - 行为：删除 profile，同时销毁 redis key（如有）

### 3.2 Project Model Policy
- PUT /api/projects/{id}/model-policy
  - 输入：generate_profile_id/review_profile_id/embed_profile_id/enable_review
- GET /api/projects/{id}/model-policy

---

## 4. Gateway / llm_client 改造（P0）

### 4.1 Router 输出“模型角色”，最终由 profile 决定 provider/model
- task_type -> role（GENERATE/REVIEW/EMBED/EXTRACT）
- role -> project_model_policy.*_profile_id
- profile_id -> provider_profile（provider, base_url, default_model, key_secret_ref）
- CredentialResolver 取回 api_key
- AdapterRegistry 调用 provider adapter

### 4.2 Policy Engine 必须在调用前执行
- pricing_guard（报价熔断）
- pii_redaction（脱敏）
- budgeting（预算扣减，超限阻断）
- audit log（写 llm_call_log，含 provider_profile_id）

---

## 5. 失败降级策略（P1）
- 若 review_profile 不可用：
  - fallback 到国内推理模型（如配置）或
  - 仅本地验证器，并在 UI 标红“未进行强推理审查”

---

## 6. Claude 编程 Prompt（直接复制）

你将为一个投标生成系统实现 BYOK（Bring Your Own Key）能力：
- 用户可在 UI/接口中创建 provider_profile（选择供应商、填写 API key、base_url、默认模型）；
- Key 必须加密存储（AES-GCM）或临时存 Redis（TTL）；
- 项目可绑定 generate/review/embed 三类 profile；
- llm_client/gateway 在每次调用时根据 task_type 找到对应 profile，动态选择 provider/model；
- 所有调用必须执行报价熔断、PII 脱敏、预算控制与审计日志；
- 日志不得包含明文 key 或 prompt 原文；
- 若审查模型不可用，需降级并给出风险提示。

请先实现最小闭环：
创建 provider_profile → 测试连接 → 绑定到项目 → 生成章节（Qwen）→ 审查（GPT）→ 导出（WPS）。
