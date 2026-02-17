# BidExpert 全面代码审核报告 (VV1.0)

**审核日期**: 2026年2月17日  
**审核范围**: 完整代码库 (`/Users/palmtom/Projects/bidexpert`)  
**技术栈**: Python 3.11+, FastAPI, SQLAlchemy, Celery, Qdrant, PostgreSQL  

---

## 执行摘要

本报告对 BidExpert 投标专家系统进行全面技术审核。系统采用 FastAPI + SQLAlchemy + Celery + Qdrant 架构，具备 LLM Gateway、BYOK (Bring Your Own Key)、RAG 检索、文档生成等核心功能。

**整体评估**: 代码架构清晰，功能模块划分合理，但在 **安全性、数据库一致性、性能优化** 方面存在需要优先处理的问题。

**风险等级分布**:
- 🔴 **P0 紧急**: 6 项（安全问题、数据不一致风险）
- 🟠 **P1 高优**: 11 项（架构债务、性能瓶颈）
- 🟡 **P2 中优**: 12 项（可维护性、部署问题）
- 🟢 **P3 低优**: 8 项（优化建议、编码规范）

---

## 一、架构级问题 (Critical)

### 1. 🔴 `init_db.py` 使用原始 SQL 做数据库迁移 — 与 Alembic 严重冲突

**文件**: `app/db/init_db.py`

**问题描述**:
`_apply_postgres_runtime_migrations()` 用 46 条原始 DDL SQL 做 schema 变更，同时项目又配置了 Alembic。两套迁移机制并存会导致：
- Alembic autogenerate 检测到不一致，产生重复/冲突迁移
- 生产部署不可重复，回滚无法追踪
- `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` 不等于幂等（枚举类型、约束可能遗漏）

**代码片段**:
```python
def _apply_postgres_runtime_migrations() -> None:
    stmts = [
        "CREATE TABLE IF NOT EXISTS workflow_run...",
        "ALTER TABLE project ADD COLUMN IF NOT EXISTS...",
        # 46 条原始 SQL
    ]
```

**修复建议**:
- 将所有原始 SQL 迁移转为 Alembic revision
- 删除 `_apply_postgres_runtime_migrations()`
- `init_db()` 只做 `Base.metadata.create_all()` 用于 SQLite 开发

---

### 2. 🟠 `app/worker` 与 `app/workers` 冗余

**文件**: `app/workers/celery_app.py`, `app/workers/tasks.py`

**问题描述**:
两个包完全重复：`app/workers/` 只是 re-export `app/worker/` 的内容，维护成本高。

**修复建议**:
删除 `app/workers/` 目录，全部统一用 `app/worker`。

---

### 3. 🟠 `routes.py` 超 1050 行 — God File 反模式

**文件**: `app/api/routes.py`

**问题描述**:
集中了全部 40+ 个 endpoint，违反单一职责原则，难以维护和测试。

**修复建议**:
按业务域拆分：
```
app/api/endpoints/
  tender.py          # tender parse/analyze
  workflow.py         # outline/section/confirm
  generation.py       # draft generation
  evidence.py         # evidence upsert/search
  expert_library.py   # expert lib CRUD
  provider.py         # BYOK profiles/policy
  review.py           # review/scoring
  render.py           # word rendering
```

---

### 4. 🟠 `testpaths` 配置指向 `app/tests`，但测试文件在项目根 `tests/`

**文件**: `pyproject.toml` 第 43 行

```toml
[tool.pytest.ini_options]
testpaths = ["app/tests"]  # ❌ 配置错误
pythonpath = ["."]
```

**修复建议**:
```toml
testpaths = ["tests"]
```

---

## 二、安全问题 (High Priority)

### 5. 🔴 JWT 仅支持 HS256 — 生产环境不推荐

**文件**: `app/security/auth.py`

**问题描述**:
HS256 使用对称密钥，验签方和签名方共享同一个 secret。任何能验证 JWT 的服务都能伪造 JWT，不适合微服务架构。

**修复建议**:
- 增加 RS256/ES256 非对称算法支持
- 至少在文档中注明 HS256 的限制

---

### 6. 🔴 API Key 验证使用直接字符串比较（非时间恒定比较）

**文件**: `app/api/routes.py` 第 187 行

```python
if not key or key != expected:  # ❌ 可能存在时序攻击风险
```

**修复建议**:
```python
import hmac
if not key or not hmac.compare_digest(key, expected):  # ✅ 时间恒定比较
```

---

### 7. 🟠 CORS 配置过于宽松

**文件**: `app/main.py` 第 86-92 行

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],  # ❌ 过于宽松
    allow_headers=["*"],  # ❌ 过于宽松
)
```

**修复建议**:
```python
allow_methods=["GET", "POST", "PUT", "DELETE"],
allow_headers=["Authorization", "Content-Type", "X-API-Key"],
```

---

### 8. 🔴 路径遍历风险

**文件**: `app/api/routes.py`

**问题描述**:
- `/v1/render/word`: `RenderWordRequest.output_path` 直接来自用户输入
- `/v1/tasks/ingest-directory`: `BatchIngestDirectoryRequest.directory` 直接用于 `rglob("*")`

**修复建议**:
```python
from pathlib import Path

def _safe_path(user_input: str, base_dir: Path) -> Path:
    resolved = (base_dir / user_input).resolve()
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise ValueError("Path traversal detected")
    return resolved
```

---

### 9. 🟠 `_should_apply_rate_limit` 逻辑问题

**文件**: `app/main.py` 第 35-41 行

```python
def _should_apply_rate_limit(path: str) -> bool:
    return (
        path == "/health"  # ❌ health 被限流
        or path.startswith("/v1/")
        or path.startswith("/api/")
        or path.startswith("/stats/")
    )
```

**修复建议**:
```python
def _should_apply_rate_limit(path: str) -> bool:
    return (
        path.startswith("/v1/")
        or path.startswith("/api/")
        or path.startswith("/stats/")
    ) and path != "/health"
```

---

## 三、可靠性与并发问题 (High Priority)

### 10. 🟠 QdrantStore 在每次调用时重新初始化

**文件**: `app/services/qdrant_store.py`

**问题描述**:
`QdrantStore.__init__` 每次执行都检查/创建 collection，调用多个 Qdrant API — 在高并发下是严重的性能瓶颈和竞态条件源。

**修复建议**:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_qdrant_store() -> QdrantStore:
    return QdrantStore()
```

---

### 11. 🟠 Prometheus metrics `path` 标签基数爆炸

**文件**: `app/observability/metrics.py`

```python
HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=str(status_code)).inc()
```

**问题描述**:
路径参数如 `/v1/tasks/{task_id}` 会产生无限基数。

**修复建议**:
使用路由模板而非实际 URL：
```python
# 在 middleware 中获取路由模板
path_template = request.scope.get("route").path
```

---

### 12. 🟠 SSE 端点 `task_status_stream` 无超时机制

**文件**: `app/api/routes.py` 第 595-606 行

**修复建议**:
```python
MAX_POLL_SECONDS = 300  # 5 分钟最大轮询时间

@router.get("/v1/tasks/{task_id}/stream")
async def task_status_stream(task_id: str) -> StreamingResponse:
    start_time = time.time()
    async def events() -> AsyncGenerator[str, None]:
        while time.time() - start_time < MAX_POLL_SECONDS:
            result = get_task_result(task_id)
            yield f"data: {json.dumps(result)}\n\n"
            if result["status"] in {"SUCCESS", "FAILURE", "REVOKED"}:
                break
            await asyncio.sleep(1)
```

---

### 13. 🟠 `semantic_cache.py` 内存泄漏风险

**文件**: `app/services/semantic_cache.py`

**问题描述**:
`_CACHE` dict 只在过期时才惰性清理，如果没有后续读取，过期数据会一直驻留内存。

**修复建议**:
增加 TTL 清理线程或使用 `cachetools.TTLCache`。

---

## 四、数据库层问题 (Medium-High)

### 14. 🟠 `updated_at` 字段不会自动更新

**文件**: `app/models/tables.py`

**问题描述**:
所有 `updated_at` 字段使用 `default=utcnow`，但没有设置 `onupdate=utcnow`。

**修复建议**:
```python
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=utcnow,
    onupdate=utcnow  # ✅ 增加此行
)
```

---

### 15. 🟡 缺少数据库索引

| 表 | 字段/组合 | 查询场景 | 建议索引 |
|---|----------|---------|---------|
| SectionContent | (project_id, section_key) | 按 section 查询 | `CREATE INDEX ...` |
| LLMCallLog | project_id | 审计查询 | 单列索引 |
| ComplianceMatrix | project_id | 合规矩阵查询 | 单列索引 |
| ReviewReport | (project_id, section_key) | 评审报告查询 | 复合索引 |

---

### 16. 🟡 Session 管理不一致

**问题描述**:
- 部分代码使用 `with SessionLocal() as db:`
- 部分使用 `get_db()` generator（但几乎没有被使用）
- API routes 没有注入 db session

**修复建议**:
统一使用 FastAPI 依赖注入：
```python
@router.get("/api/projects/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db)  # ✅ 统一依赖注入
):
    ...
```

---

## 五、代码质量问题 (Medium)

### 17. 🟡 `type: ignore[no-untyped-def]` 大量使用

**文件**: `app/db/types.py`

**修复建议**:
给 `dialect` 参数加类型标注：
```python
from sqlalchemy.engine import Dialect

def load_dialect_impl(self, dialect: Dialect) -> Any:
    ...
```

---

### 18. 🔴 `DraftGenerationResponse` 字段名不一致

**文件**: `app/schemas/contracts.py` vs `app/services/generation_pipeline.py`

**问题描述**:
```python
# generation_pipeline.py 第 86-92 行
return DraftGenerationResponse(
    draft="",  # ❌ 应为 generated_text
    review_passed=False,  # ❌ 不存在
    review_comment="",  # ❌ 不存在
    gate_results={},  # ❌ 不存在
    ...
)
```

**影响**: 运行时会产生 Pydantic ValidationError。

**修复建议**: 统一字段名或修改 schema。

---

### 19. 🟡 `pricing_guard.py` 误报率高

**文件**: `app/services/pricing_guard.py`

**问题描述**:
关键词集合包含 `"元"`、`"合计"` 等日常用语，在中文投标文档中极易误触发。

**修复建议**:
```python
# 增加上下文窗口检查
def detect_pricing_content(text: str) -> tuple[bool, list[str]]:
    # 原有逻辑...
    # 增加：检查关键词周围 20 个字符是否包含金额数字
    for kw in matched_keywords:
        for match in re.finditer(kw, text):
            context = text[max(0, match.start()-20):match.end()+20]
            if CURRENCY_PATTERN.search(context) and NUMBER_PATTERN.search(context):
                reasons.append(f"高置信度定价内容: {kw}")
```

---

### 20. 🟠 `_read_upload_with_limit` 先读完全部字节再检查大小

**文件**: `app/api/routes.py` 第 204-211 行

```python
data = await file.read()  # ❌ 全部读入内存
if len(data) > int(settings.max_upload_bytes):
    raise HTTPException(...)
```

**修复建议**:
使用分块读取或 `Content-Length` 预检：
```python
async def _read_upload_with_limit(file: UploadFile) -> bytes:
    content_length = file.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_bytes:
        raise HTTPException(413, "...")
    # 或使用 Starlette 的 UploadFile 限制
```

---

### 21. 🟡 `generate_draft_with_retrieval` 函数过长（~340 行）

**修复建议**:
拆分为独立步骤函数：
```python
def generate_draft_with_retrieval(...):
    retrieval = _retrieve_evidence(...)
    generated = _generate_content(...)
    reviewed = _review_content(...)
    return _assemble_response(retrieval, generated, reviewed)
```

---

## 六、Docker 与部署 (Medium)

### 22. 🔴 Dockerfile 使用 Python 3.14-slim（未正式发布）

**文件**: `Dockerfile` 第 1 行

```dockerfile
FROM python:3.14-slim  # ❌ 3.14 尚未发布
```

**修复建议**:
```dockerfile
FROM python:3.11-slim  # ✅ 稳定版本
```

---

### 23. 🟠 docker-compose.yml 环境变量大量重复

**问题描述**:
`api` 和 `worker` 服务 36 个环境变量完全重复。

**修复建议**:
```yaml
x-common-env: &common-env
  BIDEXPERT_DATABASE_URL: ...
  BIDEXPERT_AUTH_MODE: ...
  # ... 其他共享配置

services:
  api:
    environment:
      <<: *common-env
      BIDEXPERT_SPECIFIC_VAR: value
  
  worker:
    environment:
      <<: *common-env
```

---

### 24. 🟠 postgres 使用硬编码密码

**修复建议**:
```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bidexpert}
```

---

### 25. 🟡 缺少非 root 用户

**文件**: `Dockerfile`

**修复建议**:
```dockerfile
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app
```

---

## 七、测试与可观测性 (Medium)

### 26. 🟠 `stats.py` 端点无认证

**文件**: `app/api/endpoints/stats.py`

**问题描述**:
`stats_router` 在 `main.py` 中独立挂载，不经过 `_require_auth` 依赖。

**修复建议**:
给 stats 路由也加上认证依赖：
```python
router = APIRouter(dependencies=[Depends(_require_auth)])
```

---

### 27. 🟡 测试覆盖不足

**现状**:
- 4 个测试文件，测试用例数量有限
- 核心 services (llm_gateway, generation_pipeline 等) 缺乏单元测试

**修复建议**:
- 为核心 services 添加单元测试
- 添加集成测试（Mock LLM Adapter）
- 使用 `pytest-cov` 监控测试覆盖率

---

## 八、性能优化建议 (Low-Medium)

### 28. 🟡 `_rerank_score` 在 `_rerank_hits` 中被计算两次

**文件**: `app/services/qdrant_store.py`

**修复建议**:
```python
def _rerank_hits(query: str, items: list[RetrievedEvidence], top_k: int) -> list[RetrievedEvidence]:
    scored = [(item, _rerank_score(item)) for item in items]  # 预计算
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)
    return [
        RetrievedEvidence(
            chunk_id=item.chunk_id,
            score=score,  # 直接使用预计算分数
            text=item.text,
            payload=item.payload,
        )
        for item, score in ranked[:top_k]
    ]
```

---

### 29. 🟡 httpx Client 在每次 LLM 调用中重新创建

**文件**: `app/services/adapters/providers.py`

**修复建议**:
```python
class OpenAICompatibleAdapter(LLMAdapter):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._client = httpx.Client(timeout=...)  # 复用 client
```

---

### 30. 🟡 `_build_sparse_vector` 的 hash 碰撞概率高

**文件**: `app/services/qdrant_store.py`

```python
idx = int.from_bytes(token.encode("utf-8")[:4].ljust(4, b"\x00"), "big") % (2**31)
```

**修复建议**:
使用完整 token 的 hash：
```python
import mmh3  # pip install mmh3
idx = mmh3.hash(token) % (2**31)
```

---

## 九、其他发现

| # | 文件 | 问题 | 建议 |
|---|------|------|------|
| 31 | `pricing.py` | 定价数据硬编码，无更新机制 | 改为配置文件或远程加载 |
| 32 | `pricing.py` | 偏序匹配 `if p_key in key` 可能错配 | 使用精确匹配或前缀匹配 |
| 33 | `pii_policy.py` | 身份证正则只匹配 18 位，不验证校验位 | 增加校验位验证 |
| 34 | `evidence_validator.py` | `fuzz.partial_ratio` 阈值 88 硬编码 | 改为可配置 |
| 35 | `.env.example` vs `config.py` | 字段命名不完全对应 | 保持同步 |
| 36 | `scoring_engine.py:48-49` | 任何 ≥120 字的 section 都给 0.55 分 — 过于宽松 | 增加内容相关性检查 |
| 37 | `main.py:97` | `StaticFiles` 使用相对路径 | 使用绝对路径 |

---

## 十、修复优先级建议

### 🔴 P0 紧急（立即修复）
1. **#5** JWT 安全：增加 RS256 支持
2. **#6** API Key 时序攻击：使用 `hmac.compare_digest`
3. **#8** 路径遍历风险：验证上传路径
4. **#18** schema 不匹配：修复 `DraftGenerationResponse` 字段
5. **#22** Docker 基础镜像：降级到 3.11-slim

### 🟠 P1 高优（本周修复）
1. **#1** 迁移冲突：统一使用 Alembic
2. **#3** routes 拆分：按业务域重构
3. **#10** Qdrant 性能：使用单例模式
4. **#14** updated_at：增加 onupdate
5. **#27** stats 无认证：增加认证依赖
6. **#19** pricing_guard 误报：优化检测逻辑

### 🟡 P2 中优（本月修复）
1. **#2** workers 冗余：删除重复目录
2. **#9** 限流逻辑：排除 health
3. **#11** metrics 基数：使用路由模板
4. **#12** SSE 超时：增加最大轮询
5. **#20** 上传内存：使用分块读取
6. **#23** env 重复：使用 YAML anchor

### 🟢 P3 低优（持续改进）
1. **#15** 数据库索引
2. **#17** 类型标注完善
3. **#28-30** 性能微优化
4. **#31-37** 其他杂项

---

## 附录：推荐的代码重构计划

### 阶段一：紧急修复（1-2 天）
- [ ] 修复 #5, #6, #8, #18, #22

### 阶段二：架构清理（1 周）
- [ ] 迁移 SQL → Alembic (#1)
- [ ] 拆分 routes.py (#3)
- [ ] 删除 workers 冗余 (#2)
- [ ] 修复 session 管理 (#16)

### 阶段三：性能与安全加固（2 周）
- [ ] Qdrant 单例 (#10)
- [ ] metrics 基数 (#11)
- [ ] 数据库索引 (#15)
- [ ] 测试覆盖提升 (#27)

### 阶段四：优化与打磨（持续）
- [ ] 性能优化项 (#28-30)
- [ ] 文档完善
- [ ] 监控告警

---

*报告生成时间: 2026-02-17*  
*审核人: AI Technical Reviewer*
