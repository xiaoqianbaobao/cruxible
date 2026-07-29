# Cruxible × 超级智能体底座 深度分析与后续规划

> 分析日期：2026-07-29
> 涵盖：项目定位、当前集成状态、本体可写方向、知识图谱能力、未来演进路线

---

## 一、项目定位回顾

### Cruxible：AI Agent 的确定性状态层

Cruxible 是一个"硬状态（Hard State）"引擎——Agent 用来存东西的地方，但要保证存进去的东西是结构化、可审计、可验证的。它的核心设计是四个原语：

| 原语 | 作用 | 给 Agent 暴露的工具 |
|------|------|-------------------|
| **Config** | YAML 定义领域本体（实体、关系、约束） | `cruxible_validate`, `cruxible_inspect_ontology` |
| **Ingest** | 按本体定义映射入图 | `cruxible_add_entity`, `cruxible_add_relationship` |
| **Query** | 带图遍历的结构化查询 | `cruxible_query`, `cruxible_get_entity`, `cruxible_stats` |
| **Feedback** | 反馈与治理 | `cruxible_feedback`, `cruxible_propose_group`, `cruxible_evaluate` |

关键设计决策：**Cruxible 没有 LLM 依赖。** 它是纯粹的确定性执行引擎，LLM 通过 MCP 工具调用它，但 Cruxible 的执行不涉及任何概率推理。每一步操作都产生可验证的 Receipt。

技术栈：Python 3.11+ / Pydantic / NetworkX（内存图）/ Polars（数据处理）/ SQLite（持久化）

### 超级智能体底座（Super Agent Base）与 Harness 能力

Cruxible 解决的是"怎么存"的问题，对应的另一面是"怎么跑"——即**超级智能体底座（Super Agent Base）**。

所谓超级智能体底座，是指支撑 AI Agent 运行的基础设施层，提供以下 **harness 能力**：

| Harness 能力 | 作用 |
|-------------|------|
| Agent 生命周期管理 | Agent 的创建、执行、暂停、恢复、终止 |
| 子 Agent 协调 | 任务分解、并行执行、结果聚合 |
| 工具集成（MCP） | 外部工具的发现、调用、结果路由 |
| 安全沙箱 | 代码执行隔离、网络策略、文件系统限制 |
| 会话管理 | 多轮对话状态保持、上下文窗口管理 |
| Skill 系统 | 可插拔的能力模块管理 |

以 **DeerFlow**（字节跳动开源）为例，它是一个具体的超级智能体底座实现，提供了完整的 harness 能力：LangGraph 驱动的子 Agent 工作流编排、Docker 沙箱隔离、MCP 工具接入、Skill 管理。你也可以理解为 Agent 的操作系统——它负责 Agent 怎么想、怎么调用工具、怎么分解任务。

## 二、集成架构成熟度

### 当前架构

```
┌──────────────────────────┐   MCP stdio   ┌──────────────────┐
│  超级智能体底座            │ ──────────── │  Cruxible MCP     │
│  （如 DeerFlow 等框架）    │ ◀─────────── │  74 tools         │
│  harness: 子Agent/沙箱/MCP │  工具调用+结果 │                   │
└──────────────────────────┘               └───────┬──────────┘
                                                    │ HTTP (8100)
                                                    ▼
                                           ┌──────────────────┐
                                           │  Cruxible Daemon  │
                                           │  networkx + SQLite│
                                           │  单进程            │
                                           └──────────────────┘
```

### 验证结果（以 DeerFlow 为底座）

| 能力 | 状态 | 说明 |
|------|------|------|
| MCP 工具发现 | ✅ | langchain-mcp-adapters 成功装载 74 个工具 |
| 本体校验 | ✅ | cruxible_validate 通过 YAML 校验 |
| 实例初始化 | ✅ | cruxible_init 创建带本体的实例 |
| 实体写入 | ✅ | cruxible_add_entity 支持批量 upsert |
| 关系写入 | ✅ | cruxible_add_relationship 支持治理策略 |
| 图查询 | ✅ | cruxible_query / cruxible_get_entity 返回结构化数据 |
| 图统计 | ✅ | cruxible_stats 返回 entity_count, edge_count |
| 质量评估 | ✅ | cruxible_evaluate 发现孤儿/覆盖缺口/约束违反 |
| 反馈治理 | ✅ | cruxible_feedback / cruxible_propose_group |

### Docker 集成详情（DeerFlow 为例）

```
宿主机: cruxible daemon --port 8100
容器:   deer-flow-langgraph（DeerFlow 框架容器）
         ├─ pip install langchain-mcp-adapters
         ├─ pip install cruxible-core==0.2.8
         └─ extensions_config.json → host.docker.internal:8100
```

## 三、关键技术决策分析

### 1. 为什么用 YAML 定义本体，而不是 OWL/RDF？

| 对比 | YAML + Cruxible | OWL / RDF |
|------|----------------|-----------|
| 学习成本 | 任何后端工程师 10 分钟上手 | 需理解 DL 语法、推理规则 |
| 可嵌入性 | 和代码在同一 repo，PR 评审 | 独立文件系统 |
| 运行时校验 | 启动时 Pydantic 全面校验 | 需额外 reasoner |
| Agent 可读性 | MCP 工具 inspect_ontology 返回结构化视图 | 需 SPARQL 端点 |
| 表达能力 | entity / relationship / constraint / enum / gate | 更完备但 Agent 用不上 |

**决策结论**：Cruxible 不追求完备的本体论表达能力。它的目标不是取代 Protégé，而是让 Agent 和业务人员能理解和操作领域知识。YAML 正好在"人可读写"和"机器可解析"之间取得平衡。

### 2. 为什么用 networkx 而不是图数据库？

| | networkx（当前） | Neo4j / NebulaGraph |
|---|---|---|
| 部署 | pip install，零配置 | 独立服务/集群 |
| 查询时延 | 内存内，微秒级 | 网络往返，毫秒级 |
| 规模上限 | 受单进程内存（~百万节点） | 分布式，十亿级 |
| ACID | 无（但 Cruxible 有 receipts + snapshots） | 完整 ACID |
| 并发 | 单线程（Cruxible daemon 串行化） | 多连接并发 |

**决策结论**：在数据量不大的阶段（十万节点以下），networkx 是正确选择。减少了一个分布式系统的运维负担。等规模上去了，EntityGraph 的 36 个方法已经做了接口抽象，换后端不难。

### 3. 为什么用 MCP 而不是直接 API 调用？

- **标准协议**：超级智能体底座原生支持 MCP，无需定制客户端
- **工具发现**：MultiServerMCPClient 自动列举 74 个工具
- **权限分离**：CRUXIBLE_MODE 控制暴露的工具集
- **传输灵活**：stdio（进程内）或 SSE（远程集群）可互换

## 四、知识图谱能力定位

Cruxible 的知识图谱能力与传统 KG 系统的对比：

| 维度 | Cruxible | Neo4j / NebulaGraph | RDF Store |
|------|----------|-------------------|-----------|
| Schema | YAML ontology | Property Graph Model | RDFS / OWL |
| 查询 | graph.iter_relationships() + BFS | Cypher / nGQL | SPARQL |
| 推理 | 无（约束在应用层 evaluate） | 有限（路径、模式匹配） | DL reasoner |
| 审计 | Receipt 驱动，全链路可追溯 | 事务日志 | 有限 |
| 治理 | proposal/review/resolve/trust | 无 | 无 |
| 规模 | 单机 ~十万级 | 十亿级 | 百亿级 |
| 部署 | 单进程 | 分布式集群 | 分布式 |

**Cruxible 不追求替代图数据库**，而是解决 Agent 场景下的独特需求：

- **谁加的这条边？** — Receipt 记录了每步操作的 actor、source、timestamp
- **这条边可信吗？** — 治理链路：propose → review → approve → resolve
- **数据一致吗？** — constraint engine 在 evaluate 时系统性检查
- **能回滚吗？** — StateSnapshot 支持分支和恢复

传统图数据库不提供以上任何能力——它们存储的是 raw graph，不是 governed graph。

## 五、"业务可写本体"：核心演进方向

从工程实践来看，Ontology 的瓶颈从来不在于"机器能不能解析"，而在于**领域知识掌握在业务人员手里**。如果每次改 ontology 都要工程师改 YAML、提 PR、等上线，它永远走不远的。

Cruxible 后续的核心方向之一，就是**让业务人员能直接定义和维护本体**。

### 5.1 当前的"写本体"体验

目前业务人员写一个本体需要：

1. 掌握 YAML 语法
2. 理解 `entity_types`、`relationships`、`enum_ref`、`primary_key` 等概念
3. 通过 `cruxible_validate` 校验语义正确性
4. 通过 `cruxible_init / cruxible_reload_config` 应用变更

这对工程师友好，但对业务人员门槛高。改进方向：

### 5.2 分层作者模式

```
业务分析师 ── 用模板/UI 配置业务实体、枚举值、简单关系
     ↑ 审核
领域建模师 ── 配置约束规则、治理策略、查询定义
     ↑ 设计
本体架构师 ── 定义 Kit 分层、跨领域关系、性能敏感索引
```

每层向下提供能力，向上屏蔽复杂度。

### 5.3 模板化本体定义

为常见业务场景提供预设模板，业务人员在模板上做加减：

```
项目管理模板：
  ├─ Project, Task, Actor, Decision, Risk（预设实体）
  ├─ belongs_to, assigned_to, depends_on（预设关系）
  ├─ priority enum（low/medium/high/critical）
  └─ 约束：no_self_dependency, critical_task_needs_assignee

客服工单模板：
  ├─ Ticket, Agent, Customer, SLA, Escalation
  ├─ assigned_to, escalated_to, belongs_to_customer
  ├─ severity enum（P0/P1/P2/P3）
  └─ 约束：p0_ticket_requires_agent, escalation_chain_must_exist

供应链跟踪模板：
  ├─ Order, Shipment, Warehouse, Supplier, InventoryItem
  ├─ contains, shipped_from, supplied_by
  ├─ status enum（ordered/in_transit/delivered/returned）
  └─ 约束：shipment_requires_valid_origin, no_negative_inventory
```

### 5.4 MCP 工具赋能

新增面向业务人员的 ontology 操作工具：

```
cruxible_ontology_add_entity_type    ← 交互式引导创建实体
cruxible_ontology_add_relationship   ← 交互式引导创建关系
cruxible_ontology_diff              ← 比较两个本体版本的差异
cruxible_ontology_suggest           ← 根据现有数据推荐新的关系
cruxible_ontology_visualize         ← 生成本体关系图
```

让超级智能体底座中的 Agent 成为业务人员与 ontology 之间的翻译层——业务用自然语言描述领域模型，Agent 调用这些工具转换成 YAML 配置，调用 `cruxible_validate` 校验，最终通过 `cruxible_reload_config` 应用。

### 5.5 从数据反推本体

对于已有业务数据但没有 ontology 的场景，提供"自底向上"的能力：

1. 传入一组现有数据（CSV/JSON）
2. 自动推断可能的实体类型和属性
3. 推荐关系结构
4. 生成可编辑的 YAML 草稿
5. 业务人员确认后生成为正式本体

这部分可以和 `polars` 数据处理能力结合，利用已有的 `ingestion` 映射配置做反向工程。

## 六、后续规划

### Phase 1：生产化部署（1-2 周）

- **稳定 HTTP 连接**：验证 daemon 的 crash recovery 和 session 重连
- **CRUXIBLE_MODE 策略**：根据 Agent 角色设定不同的权限模式
  - 只读 Agent → `read_only`
  - 可提提案的 Agent → `governed_write`
  - 管理员 Agent → `admin`
- **监控**：daemon 健康检查 + agent 工具调用 success/fail 率

### Phase 2：本体可写工具链（2-3 周）

- 实现 `cruxible_ontology_add_entity_type`、`cruxible_ontology_add_relationship` 等本体管理工具
- 预设本体模板（项目管理、客服工单、供应链跟踪）
- 本体版本比较与回滚能力
- 通过 MCP 工具暴露给底座中的 Agent，让业务人员用自然语言管理本体
- `cruxible_ontology_suggest` 数据驱动的本体推荐

### Phase 3：治理反馈闭环 + 规模化（3-4 周）

**治理闭环：**

```
Agent 做出决策 → cruxible_propose_group → cruxible_evaluate
  → cruxible_feedback → cruxible_resolve_group → 边缘进入图 + receipt 归档
```

这个闭环是 Cruxible 区别于任何图数据库的核心价值——Agent 不能直写图就完事了，而是经过确定性检查和治理链路。

**规模化：**

- 实现 `GraphBackend` 接口（当前 EntityGraph 的 36 个方法作为协议）
- 实现 `NebulaGraphBackend`（nebula3-python 客户端）
- 混合模式：图在 NebulaGraph，治理元数据在 Postgres

### 三阶段总览

| Phase | 时间 | 内容 | 关键里程碑 |
|-------|------|------|-----------|
| 1 | 1-2 周 | 生产化部署 | daemon 稳定运行、权限分级、监控就绪 |
| 2 | 2-3 周 | 本体可写工具链 | 模板化本体、MCP 本体管理工具、自然语言驱动 |
| 3 | 3-4 周 | 治理闭环 + 规模化 | 完整的 propose→resolve 链路、NebulaGraph 集成 |

## 七、风险与注意事项

1. **单点故障**：当前 Cruxible daemon 是单进程，重启时图数据从 SQLite 反序列化。十万节点 < 1s，可接受。
2. **并发限制**：Cruxible daemon 串行处理写操作（receipt 保证顺序）。多 Agent 并发写入时需注意熔断。
3. **图数据 vs 治理数据分离**：设计上建议始终不要让 Agent 直写图，而是通过 governance 管道。这是架构纪律，非技术限制。
4. **本体演进难度**：随着业务发展，本体必然需要演化。使用 `extends` 多层叠加 + StateSnapshot 分支机制来管理本体变更，避免破坏性修改。

---

*本报告对应代码与配置均在 cruxible/gzh/ 目录下。*
*相关文件：agent-ontology-v2.html（公众号文章）/ agent-ontology-article.md / nebula-integration-proposal.md*
