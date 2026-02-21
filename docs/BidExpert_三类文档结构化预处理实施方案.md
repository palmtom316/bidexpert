# BidExpert 三类文档结构化预处理实施方案（仓库对齐版）

生成时间：2026-02-21 14:19:03

仓库：https://github.com/palmtom316/bidexpert

------------------------------------------------------------------------

## 一、当前仓库关键代码位置（已存在能力）

### 1️⃣ PDF 预处理核心

文件： - `app/services/pdf_ingest.py`

关键函数： - `extract_pages()` - `build_doc_blocks()` -
`ingest_pdf_bytes()`

当前逻辑： - 使用 `pypdf` 提取文本 - 文本长度 \< 40 时使用 PyMuPDF +
Tesseract OCR 回退 - 使用 `_looks_like_table()` 判断表格 - 输出
`DocBlockItem` - 进入后续结构化与 RAG pipeline

------------------------------------------------------------------------

### 2️⃣ 关键接口（需扩展支持 docx）

文件： - `app/api/routes.py`

相关接口： - `/v1/tender/ingest-upload` - `/v1/tender/analyze-upload` -
`/v1/expert-library/ingest-upload`

目前仅支持 PDF。

------------------------------------------------------------------------

## 二、总体改造目标

统一三类文档：

1.  扫描 PDF
2.  双层 PDF（图像 + 文字层）
3.  Word（docx）

全部转换为：

-   `List[DocBlockItem]`
-   `doc.md`
-   `layout.json`
-   `chunks.jsonl`

并复用现有：

    blocks -> build_structure_v1_from_blocks()
            -> render_enterprise_markdown()
            -> chunks_for_enterprise_rag()

------------------------------------------------------------------------

## 三、改造实施步骤（按文件路径说明）

# 1️⃣ 升级 PDF 处理逻辑（双层 PDF 支持）

文件：`app/services/pdf_ingest.py`

新增函数：

    def extract_pages_v2(
        pdf_bytes: bytes,
        enable_ocr_fallback: bool = True,
        dpi: int = 260
    ) -> list[PageExtract]:

改造点：

-   替换原 `<40 字触发 OCR>` 逻辑
-   新增判定指标：
    -   text_len
    -   non_whitespace_ratio
    -   image_count
-   判定规则：

```{=html}
<!-- -->
```
    if text_len < 200 or non_whitespace_ratio < 0.01:
        trigger OCR

-   可通过 env 控制：

```{=html}
<!-- -->
```
    BIDEXPERT_PDF_OCR_TEXTLEN_THRESHOLD=200
    BIDEXPERT_PDF_RENDER_DPI=260

-   OCR 后设置：

```{=html}
<!-- -->
```
    ocr_used = True
    source = "pypdf+ocr"

修改 `ingest_pdf_bytes()` 调用 `extract_pages_v2()`

------------------------------------------------------------------------

# 2️⃣ 新增 DOCX 解析模块

新增文件：

    app/services/ingest/docx_ingest.py

实现函数：

    def ingest_docx_bytes(filename: str, docx_bytes: bytes):

内部流程：

-   使用 python-docx 解析：
    -   paragraphs
    -   tables
-   映射规则：

Heading1/2/3 → block_type="TITLE" Normal → block_type="PARA" List →
block_type="LIST" Table → block_type="TABLE"

-   生成 `List[DocBlockItem]`
-   拼接 full_text
-   调用现有：
    -   build_structure_v1_from_blocks()
    -   render_enterprise_markdown()
    -   chunks_for_enterprise_rag()

------------------------------------------------------------------------

# 3️⃣ 新增统一文件路由器

新增文件：

    app/services/ingest/file_router.py

核心函数：

    def ingest_upload_bytes(filename: str, file_bytes: bytes):
        if filename.endswith(".pdf"):
            return ingest_pdf_bytes(...)
        elif filename.endswith(".docx"):
            return ingest_docx_bytes(...)
        else:
            raise ValueError("Unsupported file type")

------------------------------------------------------------------------

# 4️⃣ 修改 API 路由

文件：`app/api/routes.py`

在上传逻辑中：

-   允许 `.docx`
-   调用 `ingest_upload_bytes()`

------------------------------------------------------------------------

## 四、输出规范

### doc.md

添加：

    <!-- page: 3 -->
    <!-- block: p3_b12 type=TABLE source=pypdf+ocr -->

------------------------------------------------------------------------

### layout.json

字段：

-   block_id
-   page_no
-   block_type
-   section_anchor
-   source
-   ocr_used

------------------------------------------------------------------------

### chunks.jsonl

字段：

-   chunk_id
-   doc_id
-   section_path
-   page_range
-   text
-   payload

------------------------------------------------------------------------

## 五、测试用例（必须新增）

新增：

    tests/test_pdf_dual_layer.py
    tests/test_docx_ingest.py

覆盖：

-   扫描 PDF 触发 OCR
-   双层 PDF 正确识别正文
-   docx 标题识别
-   docx 表格识别

------------------------------------------------------------------------

## 六、未来增强（可选）

-   引入 GLM-OCR 作为 OCR provider
-   增强表格结构识别
-   docx 非结构化规则增强
-   bbox 精确定位

------------------------------------------------------------------------

## 七、实施优先级

第一阶段：

-   docx ingest
-   双层 PDF 判型升级
-   API 支持 docx

第二阶段：

-   表格增强
-   GLM-OCR 集成

------------------------------------------------------------------------

本文件可直接用于 Codex 生成代码。
