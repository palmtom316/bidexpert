# BidExpert (Stage 1)

基于 `AI_Tender_System_v2.2_Enhanced_Development_Spec_with_SQL.md` 的第一阶段可运行实现。

## 已实现能力

- PostgreSQL Schema（含版本化、审计、回滚基础）
- 招标文本分块与 requirement 抽取
- 报价内容熔断（关键词 + 数值密度）
- 三道防幻觉闸门（证据绑定、确定性验证、覆盖率）
- Word 模板占位符渲染
- FastAPI API 骨架与核心流程接口

## 快速启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

访问：`http://127.0.0.1:8000/docs`

## 使用 PostgreSQL

1. 创建数据库后执行：`sql/schema.sql`
2. 设置环境变量：

```bash
export BIDEXPERT_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/bidexpert'
```

## Docker Compose（本地开发）

```bash
docker compose up -d
```

## 注意

- 当前实现按规范强制保留 `NEED_HUMAN_INPUT` 分支。
- 报价内容命中熔断时禁止继续处理。
- 仅包含阶段一基础能力，尚未接入真实 OCR/PDF、Qdrant 与异步 Celery worker。
