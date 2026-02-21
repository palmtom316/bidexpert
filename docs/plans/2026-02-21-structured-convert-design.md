# 三类文档结构化转换与专家库初始接口 设计说明

## 目标
实现扫描 PDF/双层 PDF/docx 的统一结构化转换，前端支持“转换预览 -> 人工确认 -> 生成专家库文档”，并确保确认入库使用转换产物作为初始接口。

## 方案
采用会话式转换（conversion session）：
1. 上传文件后执行统一路由转换。
2. 生成并落盘 `doc.md` / `layout.json` / `chunks.jsonl` / `meta.json`。
3. 返回 conversion_id 供前端预览。
4. 用户确认后，后端读取该会话产物进入专家库构建流程。

## 关键改造
- PDF：`extract_pages_v2`，基于 `text_len/non_whitespace_ratio/image_count` 触发 OCR。
- DOCX：独立模块解析段落/标题/列表/表格并映射到 `DocBlockItem`。
- 路由：统一 `ingest_upload_bytes` 分发处理三类文档。
- API：新增 convert + confirm 两个接口。
- UI：新增“文档结构化转换”模块，支持预览与确认。

## 验收
- 能处理三类文档并产出三份结构化文件。
- 预览与确认入库数据一致。
- 确认后生成专家库文档并可在专家库列表查询到。
