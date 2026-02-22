# AI 辅助投标系统

# 开发规范与实施指令 (release/V1.0 - Enhanced Engineering Edition)

------------------------------------------------------------------------

## 1. 项目目标

构建企业级 AI 辅助投标系统，实现：

-   招标文件结构化拆解
-   响应矩阵驱动的 RAG 生成
-   证据强绑定防幻觉机制
-   自动 Word 模板渲染
-   自动审查与模拟评分
-   中标标书自动回灌专家库
-   永久性不支持报价生成/处理

系统必须具备：

-   可审计
-   可回滚
-   可扩展
-   安全隔离
-   工程可落地性

------------------------------------------------------------------------

## 2. 总体架构原则

### 2.1 分层架构

IaaS 层：OpenStack（Nova / Neutron / Swift / Barbican）

容器层：Kubernetes（Magnum）或 Docker Compose

应用层： - API Server - Worker - Ingest Worker - Policy Engine - Doc
Render Service - PostgreSQL - Qdrant - Redis

------------------------------------------------------------------------

### 2.2 网络安全边界

仅 Worker 容器允许访问外部 LLM API。

  服务            是否允许出网
  --------------- ------------------
  API Server      否
  DB / Qdrant     否
  Doc Render      否
  Worker          是（仅 LLM API）
  Ingest Worker   否

------------------------------------------------------------------------

## 3. 技术栈约束

### 前端

-   React / Vue (SPA)
-   TipTap Editor（结构化块编辑）
-   evidence_id 高亮绑定机制

### 后端

-   Python + FastAPI
-   Celery + Redis
-   WebSocket 进度推送

### 存储

-   PostgreSQL（主库）
-   Qdrant（向量检索）
-   Swift（对象存储）
-   Redis（队列）

### AI 引擎

-   Qwen3-Max（生成）
-   Qwen3-Max-Thinking（辅助推理）
-   禁止依赖模型自校验替代规则校验

------------------------------------------------------------------------

## 4. 核心工程机制

### 4.1 招标文件拆解

必须采用分块解析：

PDF → 页级切分 → 章节识别 → 条款切分 → 小块抽取 → 汇总

每个 requirement 必须包含：

-   requirement_id
-   原文文本
-   页码
-   章节锚点
-   是否必须项
-   评分权重
-   格式约束

解析失败必须输出：

NEED_HUMAN_INPUT

------------------------------------------------------------------------

### 4.2 响应矩阵驱动生成

生成流程：

Requirement → 检索 Evidence → 生成文本 → 验证器校验 → 写入版本

------------------------------------------------------------------------

### 4.3 三道防幻觉闸门

#### 闸门一：证据绑定闸

生成文本必须包含 evidence_ids 列表。 无 evidence 句子禁止进入最终版本。

#### 闸门二：确定性验证器

-   提取生成文本关键事实句
-   子串匹配 evidence 原文
-   未匹配则标记 NEED_HUMAN_INPUT

禁止仅依赖 Thinking 模型。

#### 闸门三：矩阵覆盖闸

每条 requirement 必须映射章节与证据。 覆盖率低于阈值禁止导出。

------------------------------------------------------------------------

### 4.4 报价内容熔断（三层机制）

永久禁止处理报价内容。

第一层：关键词检测（投标报价、单价、合计、税率、¥、RMB 等）

第二层：表格结构检测（高数字密度、金额列、货币符号）

第三层：模型辅助分类（是否为报价表）

任一命中：禁止外发、禁止入库、禁止生成。

------------------------------------------------------------------------

### 4.5 中标标书回灌（无审批流）

流程：

1.  上传
2.  自动检测
3.  报价剔除
4.  敏感脱敏
5.  分块入库

必须支持： - 入库报告生成 - 一键回滚

------------------------------------------------------------------------

## 5. 数据模型规范

### PostgreSQL 核心表

-   project
-   tender_document
-   requirement
-   compliance_matrix
-   expert_doc
-   evidence_chunk
-   generation_version
-   audit_log

必须支持版本化与回滚。

### Qdrant Payload

-   doc_id
-   chunk_id
-   doc_type
-   section_type
-   industry_tag
-   sensitivity_level
-   expiry_date

------------------------------------------------------------------------

## 6. Word 渲染规范

-   基于固定模板
-   禁止 UI 自由字体修改
-   仅允许占位符填充
-   自动生成目录

------------------------------------------------------------------------

## 7. 安全与审计

-   API Key 存储于 Barbican
-   外发最小化原则
-   项目级隔离
-   专家库分层
-   记录 LLM 调用元数据（不存明文）

------------------------------------------------------------------------

## 8. 开发阶段划分

阶段一：

-   数据库 Schema
-   三道防幻觉闸
-   报价熔断机制
-   招标拆解分块
-   Word 模板渲染

阶段二：

-   Thinking 增强
-   模拟评分优化
-   权重调优
-   行业标签体系

------------------------------------------------------------------------

## 9. 强制输出规则

若证据缺失或解析不确定，必须输出：

NEED_HUMAN_INPUT

严禁：

-   虚构资质
-   虚构证书编号
-   虚构案例
-   虚构参数指标

------------------------------------------------------------------------

## 10. 设计哲学

本系统不是"AI 写作文工具"，\
而是"基于证据驱动的合规生成系统"。

任何无法被证据验证的内容，必须被系统阻断。

------------------------------------------------------------------------

End of Document


---

# 附录 A：SQL 设计（PostgreSQL Schema DDL）

> 说明：该 Schema 面向 **项目隔离、证据追溯、版本化、可回滚、可审计** 的投标生成流程。  
> 默认使用 `uuid` 作为主键（建议启用扩展 `pgcrypto` 或 `uuid-ossp` 生成 UUID）。

## A.1 必要扩展

```sql
-- 推荐其一：
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid()
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- uuid_generate_v4()
```

## A.2 枚举类型（可用 CHECK 约束替代）

```sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_kind') THEN
    CREATE TYPE doc_kind AS ENUM ('TENDER', 'CLARIFICATION', 'EXPERT', 'AWARD');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sensitivity_level') THEN
    CREATE TYPE sensitivity_level AS ENUM ('PUBLIC_OK', 'SENSITIVE');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'requirement_strength') THEN
    CREATE TYPE requirement_strength AS ENUM ('MUST', 'SCORE', 'FORMAT', 'OTHER');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'matrix_status') THEN
    CREATE TYPE matrix_status AS ENUM ('SUPPORTED', 'NEED_HUMAN_INPUT', 'NOT_FOUND');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
    CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED');
  END IF;
END$$;
```

## A.3 核心表：项目与文件

### A.3.1 project（投标项目）

```sql
CREATE TABLE IF NOT EXISTS project (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL,
  owner_user_id    text NOT NULL,
  description      text,
  industry_tag     text,
  customer_tag     text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_owner ON project(owner_user_id);
```

### A.3.2 document（原始文档元数据；实际文件存对象存储）

```sql
CREATE TABLE IF NOT EXISTS document (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         uuid REFERENCES project(id) ON DELETE CASCADE,
  kind              doc_kind NOT NULL,
  filename          text NOT NULL,
  content_type      text,
  object_uri        text NOT NULL,
  sha256            text,
  page_count        int,
  language          text,
  sensitivity       sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK',
  created_by        text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_project ON document(project_id);
CREATE INDEX IF NOT EXISTS idx_document_kind ON document(kind);
CREATE INDEX IF NOT EXISTS idx_document_sha256 ON document(sha256);
```

## A.4 解析产物：段落/块（用于定位与追溯）

```sql
CREATE TABLE IF NOT EXISTS doc_block (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id        uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  block_type         text NOT NULL,          -- 'PARA' | 'TABLE' | 'LIST' | 'HEADING'
  page_no            int,                    -- 1-based
  section_anchor     text,
  content_text       text,
  content_json       jsonb,
  char_start         int,
  char_end           int,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_block_document ON doc_block(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_block_page ON doc_block(document_id, page_no);
CREATE INDEX IF NOT EXISTS idx_doc_block_anchor ON doc_block(document_id, section_anchor);
```

## A.5 招标要求：requirement（结构化条款）

```sql
CREATE TABLE IF NOT EXISTS requirement (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  requirement_code    text NOT NULL,                 -- e.g. "R-TECH-0012"
  strength            requirement_strength NOT NULL,  -- MUST/SCORE/FORMAT/OTHER
  score_weight        numeric(6,2),
  title              text,
  original_text       text NOT NULL,
  location_document_id uuid REFERENCES document(id),
  location_page_no    int,
  location_anchor     text,
  constraints         jsonb,
  deliverables        jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_requirement_code_per_project
  ON requirement(project_id, requirement_code);

CREATE INDEX IF NOT EXISTS idx_requirement_strength ON requirement(project_id, strength);
```

## A.6 专家库：expert_doc / evidence_chunk

```sql
CREATE TABLE IF NOT EXISTS expert_doc (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id  uuid REFERENCES document(id) ON DELETE SET NULL,
  doc_type            text NOT NULL,          -- 'CERT' | 'CASE' | 'TEMPLATE' | 'WIN_BID'
  title               text,
  industry_tag        text,
  section_type        text,
  sensitivity         sensitivity_level NOT NULL DEFAULT 'PUBLIC_OK',
  valid_from          date,
  valid_to            date,
  forbidden_tags      text[] NOT NULL DEFAULT ARRAY[]::text[],
  created_by          text NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expert_doc_type ON expert_doc(doc_type);
CREATE INDEX IF NOT EXISTS idx_expert_doc_sensitivity ON expert_doc(sensitivity);
CREATE INDEX IF NOT EXISTS idx_expert_doc_validity ON expert_doc(valid_to);

CREATE TABLE IF NOT EXISTS evidence_chunk (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  expert_doc_id       uuid NOT NULL REFERENCES expert_doc(id) ON DELETE CASCADE,
  chunk_no            int NOT NULL,
  excerpt_text        text NOT NULL,
  excerpt_hash        text,
  location            jsonb,
  quality_score       numeric(5,2) NOT NULL DEFAULT 0,
  forbidden_tags      text[] NOT NULL DEFAULT ARRAY[]::text[],
  qdrant_point_id     text,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_no_per_doc
  ON evidence_chunk(expert_doc_id, chunk_no);

CREATE INDEX IF NOT EXISTS idx_evidence_qdrant_point ON evidence_chunk(qdrant_point_id);
```

## A.7 响应矩阵：compliance_matrix

```sql
CREATE TABLE IF NOT EXISTS compliance_matrix (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  requirement_id      uuid NOT NULL REFERENCES requirement(id) ON DELETE CASCADE,
  status             matrix_status NOT NULL DEFAULT 'NOT_FOUND',
  planned_section     text,
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  notes              text,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_matrix_per_requirement
  ON compliance_matrix(project_id, requirement_id);

CREATE INDEX IF NOT EXISTS idx_matrix_status ON compliance_matrix(project_id, status);
```

## A.8 版本化与逐章产物：generation_version / section_content

```sql
CREATE TABLE IF NOT EXISTS generation_version (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_no            int NOT NULL,
  status               job_status NOT NULL DEFAULT 'PENDING',
  created_by           text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  model_used           text,
  config               jsonb,
  output_doc_object_uri text
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_version_no_per_project
  ON generation_version(project_id, version_no);

CREATE INDEX IF NOT EXISTS idx_version_status ON generation_version(project_id, status);

CREATE TABLE IF NOT EXISTS section_content (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_id          uuid NOT NULL REFERENCES generation_version(id) ON DELETE CASCADE,
  section_key         text NOT NULL,                 -- e.g. "3.2"
  section_title       text NOT NULL,
  content_md          text NOT NULL,
  content_json        jsonb,
  requirement_codes   text[] NOT NULL DEFAULT ARRAY[]::text[],
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  has_placeholders    boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_section_project_version ON section_content(project_id, version_id);
CREATE INDEX IF NOT EXISTS idx_section_key ON section_content(project_id, section_key);
```

## A.9 入库/回灌任务：ingest_job

```sql
CREATE TABLE IF NOT EXISTS ingest_job (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  source_document_id  uuid REFERENCES document(id) ON DELETE SET NULL,
  status              job_status NOT NULL DEFAULT 'PENDING',
  report_json         jsonb,
  created_by          text NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz
);

CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_job(status);
```

## A.10 审计与 LLM 调用元数据：audit_log / llm_call_log

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  actor_user_id       text NOT NULL,
  action              text NOT NULL,
  target_id            text,
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_project_time ON audit_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_log(actor_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_call_log (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid REFERENCES project(id) ON DELETE SET NULL,
  version_id          uuid REFERENCES generation_version(id) ON DELETE SET NULL,
  actor_user_id       text NOT NULL,
  model_name          text NOT NULL,
  purpose             text NOT NULL,
  evidence_ids        uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  prompt_hash         text,
  input_tokens        int,
  output_tokens       int,
  latency_ms          int,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_project_time ON llm_call_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_model_purpose ON llm_call_log(model_name, purpose);
```

---

# 附录 B：Qdrant 向量库设计（Collection & Payload）

- Collection：`expert_chunks_v1`
- Distance：`Cosine`
- 每条 point payload（建议）：

```json
{
  "expert_doc_id": "uuid",
  "chunk_id": "uuid",
  "doc_type": "CERT|CASE|TEMPLATE|WIN_BID",
  "section_type": "技术方案|实施计划|验收|组织管理|...",
  "industry_tag": "电网|轨交|医疗|政企|...",
  "sensitivity_level": "PUBLIC_OK|SENSITIVE",
  "valid_to": "2027-01-01",
  "forbidden_tags": ["PRICING_RELATED","PERSONAL_INFO"],
  "quality_score": 85.5
}
```

默认过滤建议：
- `sensitivity_level == PUBLIC_OK`（无权限不放开 SENSITIVE）
- `forbidden_tags` 不包含 `PRICING_RELATED`
- `valid_to` 未过期（若存在）

---
