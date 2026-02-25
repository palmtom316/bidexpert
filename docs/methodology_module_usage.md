# Methodology Module Usage

## Purpose

`methodology` 模块用于把外部资料片段转换为可复用且合规的“方法论资产”，避免原文直接入库。

## Legal Gates

- `L0 来源门`：`source_type=unknown` 默认 `high risk`，阻断自动发布。
- `L1 脱敏门`：未完成脱敏 (`pii_removed=false`) 阻断。
- `L2 相似度门`：`rewrite_similarity_score > BIDEXPERT_METHODOLOGY_SIMILARITY_THRESHOLD` 标记 `need_edit`。
- `L3 人工审核门`：`review_status != approved` 不允许发布。

## API Flow

1. `POST /api/methodology/extract`
- 输入：`text`, `source_type`, `source_note`, `domain`, `tags`
- 输出：`run_id`

1.1 `POST /api/methodology/extract-upload`
- 输入：`file` + `source_type/source_note/domain/tags`
- 支持：`pdf/docx/md/txt`

2. `GET /api/methodology/runs/{run_id}`
- 查看运行状态、风险等级、审核状态

3. `GET /api/methodology/runs/{run_id}/result`
- 查看提炼结果（`structure/template_md/tags/applicability`）

4. `POST /api/methodology/runs/{run_id}/review`
- 审核：`approved | rejected | need_edit`

5. `POST /api/methodology/runs/{run_id}/publish`
- 发布：写入 `methodology_snippet` + Qdrant `kb_methodology`

6. `POST /api/methodology/search`
- 仅检索 `approved` 且 `risk_level != high` 的方法论资产

## Frontend Entry

在“投标专家库”面板新增“专家经验提炼模块（Methodology）”卡片，可完成：

- 文本提炼提交
- run 查询
- 审核通过/退回
- 发布入库
- 方法论检索

## Configuration

- `BIDEXPERT_QDRANT_METHODOLOGY_COLLECTION=kb_methodology`
- `BIDEXPERT_METHODOLOGY_SIMILARITY_THRESHOLD=0.35`
- `BIDEXPERT_METHODOLOGY_STORAGE_DIR=data/methodology`
