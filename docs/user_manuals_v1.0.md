# AI 辅助投标系统 release/V1.0 使用说明书

本文档包含两部分：
1.  **非 IT 人员使用手册**：面向业务人员、投标专员，侧重于系统操作流程和功能使用。
2.  **IT 人员维护手册**：面向运维人员、开发人员，侧重于系统架构、部署、配置与故障排查。

---

# 第一部分：非 IT 人员使用手册

## 1. 系统简介
AI 辅助投标系统是一款专为投标工作设计的智能化工具，旨在通过人工智能技术辅助您完成**专家资料入库**、**招标文件分析**、**标书编写**、**审核评分**及**最终排版**的全流程工作。

核心价值：
*   **知识复用**：将过往标书、公司资质、规范标准转化为可随时调用的“专家知识”。
*   **智能辅助**：自动拆解招标要求，生成高质量的标书内容。
*   **合规风控**：自动检查标书合规性，识别风险点。

## 2. 核心模块：公司投标专家库
“公司投标专家库”是系统的知识底座。只有将高质量的资料放入库中，AI 才能在写标书时引用这些内容。

### 2.1 功能入口
在左侧导航栏点击 **“公司投标专家库”**（第一个图标）。

### 2.2 文档结构化转换（推荐）
推荐先执行结构化转换，再确认入库，以保证专家库质量。

**操作步骤：**
1.  **选择文件**：点击“待转换文件”，上传 PDF 或 Word（docx）。
2.  **选择资料类型**：
    *   **过往投标文件**：以前做好的标书，AI 会学习其中的技术方案和措辞。
    *   **规范**：国家标准、行业规范。
    *   **公司业绩**：中标通知书、合同扫描件等，用于证明公司实力。
    *   **公司资质**：营业执照、ISO 证书等。
    *   **管理人员资质及业绩**：项目经理简历、证书等。
3.  点击 **“开始转换并预览”**，检查章节预览和告警。
4.  点击 **“确认入库（基于会话）”** 或 **“一键转换并入库”**。
    *   确认后系统会执行分块、向量化和 embedding。
    *   rerank 属于检索阶段能力，不在入库阶段执行。
5.  如需使用商用 OCR，请先在 **“AI 模型设置”** 中填写 GLM-OCR 的 API Key 与 Base URL。

### 2.3 投标资料入库（高级快速通道）
当文档格式非常稳定且质量已验证时，可跳过结构化预览直接入库。

**操作步骤：**
1.  **选择文件**：点击“资料文件”，支持 PDF、Word、Markdown，多选上传。
2.  选择资料类型，按需填写工程类别。
3.  点击 **“快速入库”**，系统将直接执行 OCR、分块、向量化和 embedding。
4.  快速入库同样读取 **“AI 模型设置”** 中的 GLM-OCR 配置（仅当前浏览器会话）。

### 2.4 结构化补录（手动补充）
如果某些信息（如零散的业绩数据）没有对应的文件，可以直接手动输入。

**操作步骤：**
1.  找到页面中部的“结构化补录”卡片。
2.  在对应的文本框中输入内容。
    *   **一行一条**：例如在“公司业绩”中，每一行写一个项目的简介（如：“2024年承建某市体育馆项目，合同额5000万”）。
3.  点击 **“提交结构化补录”**。

### 2.5 投标文件回灌专家库
当您完成一个新的投标项目，并中标或定稿后，应该将这份最新的成果“回灌”到专家库中，让 AI 越来越聪明。

**方式一：上传最终 PDF**
1.  在“投标文件回灌专家库”卡片中，上传最终版的标书 PDF。
2.  填写“回灌标题”（如：XX项目最终技术标）。
3.  点击 **“上传 PDF 回灌”**。

**方式二：章节内容回灌**
1.  在编写过程中，如果您对某个章节（如“施工组织设计”）特别满意，可以直接将其回灌。
2.  选择目标专家文档，填写章节标题和内容。
3.  点击 **“章节内容回灌”**。

### 2.6 专家库浏览
您可以随时查看库里已经有哪些资料。
1.  在“专家库浏览”卡片中，点击 **“刷新列表”**。
2.  在下拉框中选择一个文档。
3.  点击 **“查看内容片段”**，系统会显示该文档被拆解成了哪些知识块。

---

## 3. 其他模块简述
*   **招标文件分析**：上传新的招标文件，AI 自动提炼“投标要点”和“废标项”。
*   **投标文件编制**：
    *   **生成目录**：AI 根据招标文件生成目录大纲，您可修改确认。
    *   **内容生成**：AI 逐章撰写内容，自动引用专家库资料。
*   **审核评分与定稿**：AI 对写好的内容进行合规性检查（如是否响应了所有“必须”项），并打分。
*   **WPS 排版与终审**：一键导出为格式规范的 Word 文档。
*   **AI 模型设置**：(高级功能) 绑定 DeepSeek, kimi 等商用大模型的 Key。

---

# 第二部分：IT 人员维护手册

## 1. 系统架构
本系统基于微服务与模块化设计，主要组件如下：
*   **Frontend**: 原生 HTML5/CSS3/ES6 (Vanilla JS), 无需编译构建，位于 `app/ui/`。
*   **Backend**: Python FastAPI (`app/main.py`, `app/api/routes.py`)。
*   **Database**: PostgreSQL (存储结构化数据：项目、文档、审计日志)。
*   **Vector Store**: Qdrant (存储文本向量索引，支持 Hybrid Search)。
*   **Task Queue**: Redis + Celery (处理耗时任务：OCR、Embedding、LLM 生成)。
*   **LLM Gateway**: 统一接口层，支持 OpenAI 协议及 Voyage Embedding。

## 2. 核心模块：公司投标专家库 (Expert Library) 实现细节

### 2.1 数据模型
核心表结构 (`sql/schema.sql`):
*   `expert_doc`: 存储文档元数据 (id, filename, doc_kind, industry_tag)。
*   `evidence_chunk`: 存储拆解后的文本块 (content, embedding_id, doc_id)。
*   `ingest_job`: 记录异步入库任务的状态。

### 2.2 入库流程 (Ingestion Pipeline)
代码位置：`app/services/expert_library.py`, `app/worker/tasks.py`

1.  **Upload**: 用户上传文件 -> 保存至 `data/uploads` -> 创建 `ingest_job`。
2.  **Async Task**: `ingest_document_task` 被 Celery 触发。
3.  **Parsing**:
    *   PDF/Word 解析：使用 `PyMuPDF` / `python-docx`。
    *   OCR 降级：如果提取文本过少，自动回退到 OCR (需配置 Tesseract 或 PaddleOCR)。
4.  **Chunking**: 文本按语义和 Token 限制切分 (默认 800-1200 tokens)。
5.  **Embedding**: 调用 `VoyageAdapter` (或配置的其他模型) 生成向量。
6.  **Storage**:
    *   文本块存入 PostgreSQL `evidence_chunk` 表。
    *   向量 + Payload 存入 Qdrant Collection (`expert_chunks_v1`)。
    *   Payload 包含：`doc_kind`, `industry_tag`, `source_doc_id` 等，用于后续过滤。

### 2.3 检索机制 (RAG)
代码位置：`app/services/qdrant_store.py`

系统采用 **Hybrid Search (混合检索)** 策略：
1.  **Dense Retrieval**: 使用 Embedding 向量进行语义相似度搜索。
2.  **Sparse Retrieval (BM25)**: 使用关键词匹配搜索 (Qdrant 支持)。
3.  **RRF Fusion**: 使用 Reciprocal Rank Fusion 算法合并两路召回结果。
4.  **Re-ranking**: (可选) 对融合结果进行重排序 (release/V1.0 Spec)。

### 2.4 配置与环境变量
配置文件：`.env` 或 `docker-compose.yml`

关键配置项：
*   `BIDEXPERT_DATABASE_URL`: Postgres 连接串。
*   `BIDEXPERT_QDRANT_URL`: Qdrant 地址 (默认 `http://qdrant:6333`)。
*   `BIDEXPERT_CELERY_BROKER_URL`: Redis 地址。
*   `BIDEXPERT_ENABLE_OCR_FALLBACK`: `True` (开启 OCR).

## 3. 部署与运维
### 3.1 启动服务
```bash
docker-compose up -d --build
```
包含服务：`api`, `worker`, `postgres`, `redis`, `qdrant`.

### 3.2 常见问题排查
*   **入库任务卡住**：
    *   检查 Celery Worker 日志：`docker-compose logs -f worker`。
    *   检查 Redis 连接。
*   **Qdrant 连接失败**：
    *   检查 Qdrant 容器状态及端口映射 (6333)。
    *   确认 Collection 是否创建成功 (启动时会自动创建)。
*   **以及 API 报错 500**：
    *   查看 API 容器日志：`docker-compose logs -f api`。

### 3.3 版本升级 (release/V1.0 Specifics)
*   **Schema 变更**：release/V1.0 引入了 `sensitivity_level` (敏感度) 和 `review_report` 表。请确保运行了最新的 SQL 迁移或初始化脚本。
*   **BYOK**: 检查 `app/services/byok/` 模块，确保加密密钥 (`master_key`) 配置正确。
