# NebulaGraph × Cruxible 集成技术方案

## 一、当前架构分析

Cruxible 当前的图存储栈分三层：

```
┌─────────────────────────────────────────┐
│  EntityGraph (networkx.MultiDiGraph)    │  ← 内存图，运行时实体/关系的权威来源
│  ├─ 全部实体和关系在内存中             │
│  └─ 支持 BFS 遍历、邻域扩展、路径查找  │
├─────────────────────────────────────────┤
│  GraphRepositoryProtocol               │  ← 持久化抽象
│  ├─ load_graph() → EntityGraph         │
│  └─ save_graph(graph) → SQLite         │  ← 全量序列化/反序列化
├─────────────────────────────────────────┤
│  SQLite / JSON-on-disk                 │  ← 当前后端
│  ├─ state.db (graph_snapshots 表)      │
│  └─ .cruxible/snapshots/ (JSON export) │
└─────────────────────────────────────────┘
```

核心限制：
- 图数据全量在内存（NetworkX），受单机内存上限
- 每次 save_graph 是全量序列化，O(V+E) 写放大
- 图查询必须在服务进程内执行，不支持跨进程/跨机器查询
- 没有原生的图可视化能力

## 二、NebulaGraph 能力映射

| 维度 | NebulaGraph | Cruxible 需求 |
|------|-------------|---------------|
| 顶点类型 | Tag（如 `tag Actor`） | entity_types |
| 边类型 | Edge Type（如 `edge assigned_to`） | relationships |
| 属性类型 | bool/int/double/string/date/time/datetime/timestamp | PropertySchema type |
| 枚举约束 | 应用层或 property default | enum / enum_ref |
| 图遍历 | nGQL: GO / FETCH / FIND PATH / MATCH | traversal queries |
| 分布式 | 多副本 Raft + 分片 | 水平扩展 |
| 事务 | MVCC + 快照隔离 | receipt + snapshot |
| 可视化 | NebulaGraph Studio / Dashboard | inspect 工具 |

## 三、三层集成架构

集成从浅到深分三个层次，逐层依赖：

```
                    ┌────────────────────────────────┐
                    │       MCP 工具层（不变）         │
                    │  cruxible_add_entity / query /  │
                    │  evaluate / feedback / propose  │
                    └────────────┬───────────────────┘
                                 │
                    ┌────────────▼───────────────────┐
                    │   Service 业务逻辑层（基本不变）  │
                    │  service_add_entity / query /   │
                    │  neighborhood / traversal       │
                    └────────────┬───────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │         L1           │          L2          │
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ NebulaGraph     │  │ nGQL Query     │  │ NebulaGraph     │
│ EntityGraph     │  │ Engine          │  │ Receipt/FF/GP   │
│ Adapter         │  │ Adapter         │  │ Store           │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ 实现             │  │ Traversal →    │  │ 直接用          │
│ EntityGraph     │  │ nGQL GO/        │  │  NebulaGraph    │
│ 全部 36 个方法  │  │ FETCH/PATH      │  │  存收据/反馈    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │
         └────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  NebulaGraph      │
                    │  (分布式图数据库)   │
                    └───────────────────┘
```

### L1：EntityGraph 后端适配器

把 `EntityGraph` 从 networkx 后端替换为 NebulaGraph Python Client。

```python
class NebulaEntityGraph:
    """EntityGraph API 的 NebulaGraph 实现
    
    每个方法对应 nGQL 语句。
    与 networkx 版不同的是：数据不在内存，每次操作都走 NebulaGraph.
    """
    
    def __init__(self, connection_pool: NebulaConnectionPool):
        self.pool = connection_pool
    
    def add_entity(self, entity: EntityInstance) -> None:
        # INSERT VERTEX Actor(name, role) VALUES "actor-alice":("Alice Chen", "developer")
        # 支持 UPSERT: 如果存在则 UPDATE，否则 INSERT
        pass
    
    def add_relationship(self, rel: RelationshipInstance) -> None:
        # INSERT EDGE assigned_to() VALUES "Task:task-1" -> "Actor:actor-alice":()
        pass
    
    def get_entity(self, entity_type: str, entity_id: str) -> EntityInstance:
        # FETCH PROP ON Actor "actor-alice" YIELD vertex as v
        pass
    
    def expand_neighborhood(self, entity_type, entity_id, ...) -> NeighborhoodExpansion:
        # GO 1 TO N STEPS FROM "Task:task-1" OVER assigned_to 
        #   YIELD distinct vertices_, edges_
        pass
    
    # ... 36 个方法的完整实现
```

**关键设计**：

- Vertex ID 采用复合格式 `{entity_type}:{entity_id}`（与当前 EntityGraph 的 node_id 一致）
- 每个 entity_type 映射为一个 NebulaGraph Tag
- 每个 relationship 映射为一个 Edge Type
- 属性和 NebulaGraph 的属性类型对齐（string/int/float/bool/datetime）
- enum/enum_ref 在应用层校验（NebulaGraph 无原生 enum 类型）

### L2：nGQL 查询引擎适配

当 NebulaGraph 后端启用时，Cruxible 的 traversal query 可以下推到 NebulaGraph 执行：

| Cruxible Query | nGQL Translation |
|----------------|-----------------|
| `entry_point: Task` → 展开邻域 | `GO 1 STEPS FROM "Task:task-1" OVER assigned_to,depends_on` |
| `max_depth: 3` | `GO 1 TO 3 STEPS` |
| depth-first paths | `FIND ALL PATH FROM "X" TO "Y" OVER * UPTO 5 STEPS` |
| `filter: priority == critical` | `WHERE $^.Task.priority == "critical"` |
| 属性过滤 | `YIELD vertex AS v WHERE v.Task.priority == "critical"` |
| limit/offset | `| LIMIT 10 | OFFSET 20` |

**混合模式**：对于复杂约束（如 `IMPLIES` 逻辑），仍然在应用层执行。NebulaGraph 处理后返回结果集，Cruxible 做二次过滤。

### L3：NebulaGraph 作为主持久化

当前 `GraphRepositoryProtocol` 只有 `load_graph/save_graph`，对 NebulaGraph 来说需要：

```python
class NebulaGraphRepository:
    """用 NebulaGraph 替代 SQLite + JSON 的序列化方案"""
    
    def load_graph(self) -> EntityGraph:
        # 不加载全部！只返回一个 NebulaEntityGraph 包装器
        # 实际数据在 NebulaGraph 中，查询时才拉取
        return NebulaEntityGraph(self.pool)
    
    def save_graph(self, graph: EntityGraph) -> None:
        # NebulaGraph 已经实时持久化了，这里可能为 no-op
        # 或校验一致性
        pass
    
    def upsert_entities(self, entities) -> None:
        # INSERT VERTEX ... 批量写入
        pass
    
    def upsert_relationships(self, relationships) -> None:
        # INSERT EDGE ... 批量写入
        pass
```

## 四、Schema 映射：YAML Config → NebulaGraph DDL

```yaml
# Cruxible YAML ontology
entity_types:
  Actor:
    id: actor_id
    properties:
      name: {type: string, indexed: true}
      role: {type: string}
      status: {type: string, enum: [active, inactive]}

  Task:
    id: task_id
    properties:
      title: {type: string, indexed: true}
      status: {type: string, enum_ref: work_status}
      priority: {type: string, enum_ref: priority}

relationships:
  - task_belongs_to_project: Task -> Project
  - task_assigned_to_actor: Task -> Actor
  - task_depends_on_task: Task -> Task
    proposal_policy:  # ← 治理元数据存额外属性
      signals:
        source_evidence: {role: required}
```

自动生成 NebulaGraph Schema：

```sql
-- Vertex Tags
CREATE TAG IF NOT EXISTS Actor (
    actor_id string NOT NULL,
    name     string,
    role     string,
    status   string
);

CREATE TAG IF NOT EXISTS Task (
    task_id  string NOT NULL,
    title    string,
    status   string,
    priority string
);

-- Edge Types
CREATE EDGE IF NOT EXISTS task_belongs_to_project (
    created_at datetime DEFAULT now()
);

CREATE EDGE IF NOT EXISTS task_assigned_to_actor ();

CREATE EDGE IF NOT EXISTS task_depends_on_task (
    proposal_policy string  -- JSON serialized governance metadata
);

-- Indexes for indexed properties
CREATE TAG INDEX IF NOT EXISTS idx_task_title ON Task(title(20));
CREATE TAG INDEX IF NOT EXISTS idx_actor_name ON Actor(name(20));
```

**约束处理**：Cruxible 的 `constraints`（如 `no_self_dependency`）可以部分下沉：

- `no_self_dependency` → 应用层校验（NebulaGraph 不支持跨 edge 的 constraint）
- `critical_task_needs_assignee` → nGQL 可表达但复杂，也建议留在应用层用 `cruxible_evaluate`

## 五、治理层适配

Cruxible 的治理功能（proposal/review/resolve/feedback/outcome）是应用层逻辑，不直接映射到图数据库：

```
┌────────────────────────────────────────┐
│  治理层（应用逻辑，不依赖存储后端）       │
│  ├─ CandidateGroup + Member + Signal   │
│  ├─ FeedbackRecord + OutcomeRecord     │
│  ├─ DecisionRecord + DecisionEvent     │
│  └─ SourceArtifact + Evidence          │
├────────────────────────────────────────┤
│  存储层                                 │
│  ├─ 图数据 → NebulaGraph               │
│  ├─ 收据/反馈/决策 → SQLite 或 Postgres│
│  └─ Source Artifacts → 对象存储/S3     │
└────────────────────────────────────────┘
```

治理数据可以继续用 SQLite/Postgres（用 `InstanceProtocol` 的 store 抽象），使迁移风险最小化。

## 六、部署拓扑

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Agent A     │     │  Agent B     │     │  Agent C     │
│  (DeerFlow)  │     │  (DeerFlow)  │     │  (DeerFlow)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │ MCP stdio
                            ▼
                    ┌──────────────┐
                    │  Cruxible     │
                    │  MCP Server   │
                    │  (stateless)  │
                    └──────┬───────┘
                           │ HTTP API
                           ▼
                    ┌──────────────┐
                    │  Cruxible     │
                    │  Daemon(s)    │
                    │  (stateless)  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │ NebulaGraph │ │  Postgres  │ │  S3 / Minio│
     │  Cluster   │ │ (Feedback)  │ │ (Artifacts)│
     │  3+ nodes  │ │ (Receipts)  │ │            │
     └────────────┘ └────────────┘ └────────────┘
```

## 七、收益评估

| 维度 | 当前 (SQLite + NetworkX) | 集成 NebulaGraph |
|------|--------------------------|-----------------|
| 图规模上限 | 单机内存上限（~几十万节点） | 分布式，十亿级 |
| 查询性能 | 全内存，O(1) 节点/边访问 | 网络往返，~~O(log)~~ 但支持索引+并行 |
| 持久化 | 全量序列化到 SQLite | 实时持久化，无写放大 |
| 可视化 | 无原生能力 | NebulaGraph Studio / Dashboard |
| 高可用 | 无 | Raft 多副本自动故障转移 |
| 水平扩展 | 无 | 横向加节点 |
| 部署复杂度 | 单进程 | 需要管理 NebulaGraph 集群 |
| 运维成本 | 低 | 中（3+ 节点的分布式系统） |
| 查询能力 | 仅应用层 | nGQL + 应用层两层 |

## 八、风险与取舍

1. **延迟增加**：当前 EntityGraph 是纯内存操作，NebulaGraph 每次操作都要走网络 RTT。对于高频小操作（如 `get_entity`），需引入本地缓存 + 批量写入缓冲。

2. **快照一致性**：Cruxible 的 `StateSnapshot` 依赖于 SQLite 事务的隔离性。在 NebulaGraph 中需要利用其 MVCC 快照能力实现等价语义。

3. **枚举约束丢失**：NebulaGraph 没有原生 enum 类型。enum/enum_ref 的校验必须在应用层（Cruxible 的 `validate_property_payload`）执行，NebulaGraph 只存 raw string。

4. **治理数据**：feedback、outcome、group、decision 等属于结构化元数据，更适合关系型数据库。建议保持 Postgres/SQLite 作为辅助存储。

5. **迁移路径**：建议从 L1（EntityGraph 适配）开始，渐进式替换，而不是一次性重写。

## 九、实施建议：三阶段路径

### Phase 1：EntityGraph 后端接口抽象化（1-2 周）

- 将 `EntityGraph` 定义为 Protocol/ABC（当前是具体类）
- 提取 `GraphBackend` 接口（NetworkX 实现为默认）
- 不做功能变更，只做接口隔离

### Phase 2：NebulaEntityGraph Adapter（2-3 周）

- 基于 nebula3-python 客户端实现 `GraphBackend`
- CRUD 操作（add/get/update/remove entity & relationship）
- Session 管理与连接池
- 基础测试用例 + Docker Compose 本地开发环境

### Phase 3：Query 下推与 Schema Sync（2-3 周）

- traversal 查询翻译为 nGQL
- `cruxible_validate` 增加 NebulaGraph DDL 生成
- `cruxible_evaluate` 约束检查适配
- 性能测试与缓存策略

---

*本方案的核心策略是"适配器模式 + 渐进式替换"——不破坏既有 API、不重写服务层、不锁死技术选型。Phase 1 上线后，Cruxible 甚至可以支持用户在同一个实例里选择 NetworkX（单机模式）或 NebulaGraph（分布式模式）。*
