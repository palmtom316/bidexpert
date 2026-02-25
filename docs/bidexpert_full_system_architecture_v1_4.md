
# AI 投标辅助系统 v1.4 防呆增强版
## （在 v1.3 基础上增加 Metadata 强过滤 + 表格感知切片 + 生命周期红线控制）

---

# 一、总体升级目标

v1.4 的核心目标：

> 从“可用的专家库”升级为“企业级零废标风险控制系统”

新增三大安全增强模块：

1️⃣ 自动 Metadata 打标引擎（电压等级/工程类型/设备/地区）  
2️⃣ Table-Aware Chunking（表格边界感知切片）  
3️⃣ 生命周期红线控制（资产有效期 + 规范版本管理）  

---

# 二、增强后的总流程图

```
上传文件
   │
   ▼
MinerU / pandoc 解析
   │
   ▼
规则抽取（正则：电压等级/年份等）
   │
   ▼
轻量 LLM Metadata Extractor
   │
   ▼
生命周期校验（资产/规范版本）
   │
   ▼
Table-Aware Chunking
   │
   ▼
chunk_manifest.json
   │
   ▼
Embedding Queue
   │
   ▼
Qdrant Upsert（含 Metadata Payload）
   │
   ▼
KB_READY
   │
   ▼
查询时：强制 Metadata Filter + 生命周期过滤
   │
   ▼
Hybrid Recall → Rerank → LLM 生成
```

---

# 三、增强模块一：Metadata 自动打标引擎

## 3.1 必须提取的核心字段

| 字段 | 示例 |
|------|------|
| voltage_level_kv | 10 / 35 / 110 |
| project_type | 新建 / 改造 / 扩建 |
| core_equipment | 变压器 / 开关柜 / 电缆 |
| region | 江苏 / 山东 |

## 3.2 抽取策略

优先级：

1. 正则规则抽取（稳定低成本）
2. 轻量 LLM 补全（Qwen-Flash 等）

## 3.3 写入 Qdrant Payload

```json
{
  "voltage_level_kv": 10,
  "project_type": "业扩配电",
  "region": "江苏"
}
```

## 3.4 检索强制过滤

在 /api/search 中：

```
filter:
  must:
    voltage_level_kv = 当前项目
    project_type = 当前项目
```

未匹配直接不召回。

---

# 四、增强模块二：Table-Aware Chunking

## 4.1 问题

技术参数表被切断会导致向量失真。

## 4.2 解决规则

1. 识别 Markdown 表格（|---|）
2. 若表格长度 < chunk_limit → 整体入库
3. 若超长 → 分块但强制补全表头
4. table 单独 chunk_kind="table"

## 4.3 示例 Payload

```json
{
  "chunk_kind": "table",
  "table_header": ["型号","容量","电压"],
  "is_parameter_table": true
}
```

---

# 五、增强模块三：生命周期红线控制

## 5.1 资产有效期（强制）

数据库字段：

- expiration_date
- is_valid = expiration_date > today

查询资产时：

SQL 层过滤过期数据，绝不进入向量召回。

---

## 5.2 规范版本管理

新增字段：

- standard_code（GB50052）
- version_year（2009 / 2024）
- status（active / deprecated）

规则：

若检测到新版本：
旧版本自动标记 deprecated。

检索默认：
只召回 status=active。

---

# 六、状态机扩展（v1.4）

新增步骤：

- METADATA_EXTRACTED
- LIFECYCLE_VALIDATED
- TABLE_CHUNKED

完整顺序：

RECEIVED  
PARSE_READY  
METADATA_EXTRACTED  
LIFECYCLE_VALIDATED  
TABLE_CHUNKED  
CHUNKED  
EMBEDDING_DONE  
UPSERTED  
KB_READY  

---

# 七、优先级实施顺序

1️⃣ 生命周期红线控制（最高优先）  
2️⃣ Metadata + 强制 Filter  
3️⃣ Table-Aware Chunking  

---

# 八、最终系统特征

✔ 不会引用过期资质  
✔ 不会引用废止规范  
✔ 不会混入错误电压等级内容  
✔ 不会撕裂技术参数表  
✔ 支持 Hybrid + Rerank 高质量检索  

---

# 九、总结

v1.4 标志着系统进入：

“企业级防呆 + 合规红线 + 技术排他性控制”阶段。

