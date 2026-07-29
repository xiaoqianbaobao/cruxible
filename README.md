<p align="center">
  <a href="https://cruxible.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cruxible-ai/cruxible/main/assets/brand/cruxible-wordmark-white.svg">
      <img src="https://raw.githubusercontent.com/cruxible-ai/cruxible/main/assets/brand/cruxible-wordmark-black.svg" alt="Cruxible" width="360">
    </picture>
  </a>
</p>

# Cruxible — AI Agent 的确定性状态引擎

[![PyPI version](https://img.shields.io/pypi/v/cruxible?color=blue)](https://pypi.org/project/cruxible/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](https://github.com/xiaoqianbaobao/cruxible/blob/main/LICENSE)

> **本仓库是 [cruxible-ai/cruxible](https://github.com/cruxible-ai/cruxible) 的个人 Fork，在此之上增加了本体编辑工具链、数据源连接器和中文文档。**
>
> 上游专注于确定性的状态引擎核心，这个 Fork 更偏向 **"业务可写本体"** 和 **"与超级智能体底座集成"** 的实战方向。

---

## Cruxible 是什么

Cruxible 是一个**确定性的状态引擎**——AI Agent 用它来存结构化的、可审计的、可治理的长期记忆。它不跑 LLM，LLM 通过 MCP 工具调用它，每一步操作都产生可验证的收据（Receipt）。

四个核心原语：

| 原语 | 作用 | MCP 工具示例 |
|------|------|-------------|
| **Config** | YAML 定义领域本体（实体、关系、约束） | `cruxible_validate`, `cruxible_inspect_ontology` |
| **Ingest** | 按本体定义映射入图 | `cruxible_add_entity`, `cruxible_add_relationship` |
| **Query** | 带图遍历的结构化查询 | `cruxible_query`, `cruxible_get_entity` |
| **Feedback** | 反馈与治理 | `cruxible_feedback`, `cruxible_propose_group` |

## 本 Fork 的增量能力

### 新增 7 个 MCP 工具（总计 81 个）

在 upstream 的 74 个工具基础上，新增了本体编辑和数据源发现工具：

| 工具 | 类型 | 说明 |
|------|------|------|
| `cruxible_entity_type_add` | 🆕 本体编辑 | 新增实体类型（支持 dry-run） |
| `cruxible_entity_type_update` | 🆕 本体编辑 | 向已有实体添加属性 |
| `cruxible_relationship_add` | 🆕 本体编辑 | 新增关系（支持 cardinality、reverse_name） |
| `cruxible_enum_add` | 🆕 本体编辑 | 新增枚举词汇表 |
| `cruxible_enum_value_add` | 🆕 本体编辑 | 扩展已有枚举值 |
| `cruxible_ontology_describe` | 🆕 本体编辑 | 查看当前本体结构摘要 |
| `cruxible_discover_schema` | 🆕 数据源 | 从 Hive/OceanBase/SFTP 自动发现本体 |

> 新增工具均注册了 MCP 描述和权限分级（6 个 GOVERNED_WRITE + 1 个 READ_ONLY）。

### 新增 3 个数据源连接器

- **Hive/Spark 连接器** — 连接 Hive Metastore，扫描表结构，自动推断实体类型和关系。自动剥离 ODS/DWD/DIM 等前缀。
- **OceanBase 连接器** — 读取 INFORMATION_SCHEMA，检测主键和外键约束，生成 relationship 提案。
- **SFTP 连接器** — 远程 CSV/JSON 采样，推断列类型和枚举值。

将现有数据库反向工程为本体提案，支持人工审核后逐步写入。

### 本体编程式修改器

`ConfigEditor` 类提供了对运行中 ontology 的 CRUD 操作，通过 `dump_expanded()` 序列化为 YAML 后经由 `reload_config` 应用。所有修改都经过 Pydantic 校验和引擎约束检查。

### 中文文档与实战文章

`gzh/` 目录下包含了完整的分析和实操文章（均为可直接粘贴到微信公众号编辑器的 HTML 格式）：

| 文件 | 内容 |
|------|------|
| `mcp-tools-analysis.md` | 81 个工具全景分析报告 |
| `practical-integration.html` | 实战：与超级智能体底座集成 |
| `agent-ontology-v2.html` | 聚焦"业务写本体" |
| `agent-ontology-article.html` | 初版本体论文章 |
| `cruxible-deerflow-analysis.md` | 深度分析报告 + 后续规划 |
| `nebula-integration-proposal.md` | NebulaGraph 集成方案 |

## 与本 Fork 上游的差异

| 维度 | Upstream (cruxible-ai/cruxible) | 本 Fork |
|------|-------------------------------|---------|
| 工具总数 | 74 | **81**（新增 7 个） |
| 本体编辑 | 仅 `reload_config`（全量替换） | **增量编辑**：add/update entity type、relationship、enum |
| 数据源发现 | 无 | **3 个连接器**：Hive、OceanBase、SFTP |
| 中文文档 | 无 | **gzh/** 完整中文技术分析 + 公众号文章 |
| 集成方向 | Agent 状态引擎核心 | **业务写本体** + **超级智能体底座集成** |

## 快速开始

```bash
# 安装
pip install cruxible

# 或本地开发
git clone https://github.com/xiaoqianbaobao/cruxible.git
cd cruxible
uv sync --all-extras

# 启动 HTTP daemon
cruxible server start --port 8100

# 在另一个终端，启动 MCP stdio 服务
CRUXIBLE_SERVER_URL=http://127.0.0.1:8100 python -m cruxible_core.mcp.server
```

详见 `gzh/` 目录下的实战文章。

## 许可证

Apache 2.0
