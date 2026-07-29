# AI Agent 的原生记忆：当本体论遇见确定性状态引擎

## 引言：Agent 的"失忆症"

2025 年到 2026 年，AI Agent 从一个技术概念演变成了几乎每家公司都在构建的产品形态。从代码生成到客户服务，从数据分析到工作流编排，Agent 的能力边界在以月为单位被重新定义。

但每一个把 Agent 推向生产的工程师都会在某个深夜遇到同样的问题：**Agent 没有可靠的记忆。**

LLM 调用是无状态的。即便你塞进去了全部上下文，它在下一次对话中依然不记得五分钟前做过的决策。RAG 可以检索文档片段，但它无法建模结构化的、可验证的、带有权限和审计的长期状态。

而通过传统数据库来解决则意味着让 Agent 写 SQL、理解 Schema、处理约束——这条路的研究成本远高于多数团队的承受能力。

这就是本体论（Ontology）在 Agent 工程中重新进入视野的深层原因。

## 从哲学概念到工程工具

本体论原本是哲学的一个分支，研究"存在"的分类。在信息科学中，它被简化为一个非常实用的定义：

> 本体论是对某一领域共享概念的形式化、显式的规格说明。—— Tom Gruber, 1993

翻译成工程语言就是：**用机器可读的方式告诉系统你的世界里有什么东西，它们之间怎么关联，以及这些关联必须遵守什么规则。**

一个电商领域的本体论可能告诉你：

- 有 `User`、`Product`、`Order` 三种实体
- `User` 可以 `places`（下单）一个 `Order`
- `Order` 包含若干 `Product`
- 一个有效的 `Order` 必须至少包含一个 `Product`（约束）

传统的本体论实现（OWL/RDF）太过学术化，缺乏构建时验证、运行时快照、变更审计等工程能力。而 LLM 时代的本体论需要回答一个更实际的问题：

> AI Agent 如何在不写 SQL、不操作 ORM、不画 ER 图的前提下，可靠地读写结构化的领域知识？

## DeerFlow + Cruxible：Agent 平台的"左脑与右脑"

在回答这个问题之前，先看两个工具各自扮演的角色。

### DeerFlow（quickFlow）：Agent 的执行侧

DeerFlow 是一个开源的 Super Agent 框架，提供了子 Agent 协调、Sandbox 隔离、技能（Skill）管理、MCP 集成、多租户等能力。简单说，它负责 **Agent 怎么想**——推理、工具调用、子任务分解。

但它不负责 **Agent 怎么记**。DeerFlow 本身没有结构化的长期状态层。Agent 在对话中产生的决策、关系、推理链，随着会话结束就消失了。

### Cruxible：Agent 的确定性状态引擎

Cruxible 正好补上这一层。它的核心设计是四个原语：

- **Config** — 用 YAML 声明你的领域本体（实体、关系、约束、查询）
- **Ingest** — 从外部数据源按本体定义映射入图
- **Query** — 带图遍历的结构化查询（支持可视化状态过滤）
- **Feedback** — 反馈与结果记录，支持 proposal → review → resolve 治理链路

关键设计决策：**Cruxible 没有 LLM 依赖。** 它是纯粹的确定性运行时。LLM 通过 MCP 工具调用它，但它的执行不涉及任何概率推理。每一步操作都产生可验证的收据（Receipt）。

### 集成的本质：MCP 作为粘合剂

DeerFlow 原生支持 MCP（Model Context Protocol）。Cruxible 的 74 个工具全部注册为 MCP 服务。集成架构极简：

```
┌─────────────────────┐     MCP stdio     ┌──────────────────┐
│  DeerFlow Agent     │ ────────────────▶ │  Cruxible MCP     │
│  (LangGraph)        │ ◀──────────────── │  74 tools 注册     │
│                     │   工具调用+结果    │                   │
└─────────────────────┘                   └───────┬──────────┘
                                                  │ HTTP API
                                                  ▼
                                          ┌──────────────────┐
                                          │  Cruxible Daemon  │
                                          │  SQLite / graph   │
                                          └──────────────────┘
```

DeerFlow 的 `MultiServerMCPClient` 自动发现 MCP 工具列表，agent 在规划时就能看到 `cruxible_init`、`cruxible_add_entity`、`cruxible_query`、`cruxible_evaluate` 等全部工具，无需额外配置。

## Ontology 在 Cruxible 中的表达

下面是一个真实可运行的项目管理本体，它定义了一个小型 Scrum 团队的领域模型：

```yaml
version: "1.0"
name: project_demo

enums:
  priority: {values: [low, medium, high, critical], ordered: low_to_high}
  work_status: [backlog, planned, in_progress, blocked, review, done]
  decision_status: [proposed, accepted, rejected, deferred]

entity_types:
  Actor:
    id: actor_id
    properties:
      name: {type: string, indexed: true}
      role: {type: string}
  Project:
    id: project_id
    properties:
      name: {type: string, indexed: true}
      priority: {type: string, enum_ref: priority}
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
    proposal_policy:
      signals:
        source_evidence: {role: required}
        maintainer_judgment: {role: advisory}
  - decision_affects_task: Decision -> Task
```

这段 YAML 定义了一个完整的领域本体：

- **词汇层**：`enums` 声明了优先级、工作状态等共享词汇，Agent 写入时通过 `enum_ref` 自动校验
- **实体层**：`entity_types` 定义了 5 种实体，各自的属性、类型、主键
- **关系层**：`relationships` 定义了实体间的连接方式、基数方向，以及治理策略
- **治理层**：`proposal_policy` 声明了某些关系只能通过提案-审批流进入，不能直写

## 三层本体结构

在真实部署中，本体通常不是一块铁板，而是分层组合的：

```
┌──────────────────────────────────────────┐
│  应用层 (Application Ontology)           │
│  ├─ PurchaseOrder, Sprint, Release       │
│  └─ 继承自操作层和基础层                    │
├──────────────────────────────────────────┤
│  操作层 (Agent Operation Ontology)        │
│  ├─ WorkItem, Decision, Risk, Actor      │
│  ├─ ReviewRequest, StateNote             │
│  └─ 已有现成 Kit：kits/agent-operation    │
├──────────────────────────────────────────┤
│  基础层 (Base Domain Ontology)           │
│  ├─ 业务核心实体：Customer, Product, Order │
│  └─ 领域专家编写，长期稳定                  │
└──────────────────────────────────────────┘
```

Cruxible 的 Kit 机制支持这种分层。项目实例通过 `extends` 声明继承关系，组合多个 Kit 得到一个统一的、可查询的本体视图。

## 从实体到约束：本体论的约束层

仅有实体和关系，本体论是不完整的。真正的业务逻辑体现在**约束**中：

```yaml
constraints:
  - name: no_self_dependency
    rule: "depends_on.FROM.task_id != depends_on.TO.task_id"
    severity: error
  - name: critical_task_needs_assignee
    rule: "Task.priority == 'critical' IMPLIES Task.assigned_to IS NOT EMPTY"
    severity: warning
```

这些约束在 `cruxible_evaluate` 时被系统化检查，无需 Agent 自己编写规则逻辑。Agent 只需要一次调用 `evaluate` 就能发现图中的一致性违反。

## 实战演示：让 Agent 操作本体

集成完成后，DeerFlow 中的 Agent 可以这样与 Cruxible 交互：

```
用户: 帮我创建一个项目管理实例，加一个项目和两个任务

Agent (规划中看到 cruxible_init):
  1. cruxible_validate(config_yaml=...) → 校验本体配置
  2. cruxible_init(root_dir=..., config_yaml=...) → 创建实例
  3. cruxible_add_entity(entities=[...]) → 添加实体
  4. cruxible_add_relationship(relationships=[...]) → 添加关系
  5. cruxible_stats(instance_id=...) → 验证结果
```

整个过程由 Agent 自主规划并执行。因为工具是确定性的，Agent 的每一步操作都产生可审计的 Receipt。

## 为什么这对生产系统重要

纯 Prompt Engineering 的方式让 Agent 管理状态，在生产环境中有三个致命问题：

1. **不可审计** — LLM 调用是不可复现的，你无法证明它在五分钟前"知道"什么
2. **不可验证** — Agent 说"我完成了"，但你无法独立验证图中的数据完整性
3. **不可治理** — 多 Agent 场景下，Agent A 和 Agent B 可能对同一实体产生冲突的写入

Cruxible 的确定性执行 + 收据 + 治理链路解决了这三个问题：

- 每个查询和写入都有加密收据
- 约束检查由引擎执行，不依赖 LLM 的诚实度
- Proposal + Review + Resolve 链路让人类能在 Agent 的提案到达图之前拦截

## 写在最后

本体论不是一个新概念。它在知识工程时代的失败，不是因为理论错了，而是因为当时的工具需要人类手动维护，维护成本远高于收益。

LLM + 确定性引擎的组合改变了这个等式：

- **LLM 负责理解自然语言，把非结构化的需求映射到本体结构上**
- **确定性引擎负责执行、验证、审计，保证状态的一致性和可靠性**

两个系统各司其职，不越界。

DeerFlow 与 Cruxible 的 MCP 集成是这个模式的一个具体实现。它展示了 Agent 如何在不需要理解 SQL、不需要配置 ORM、不需要画 ER 图的前提下，可靠地管理结构化的长期状态。

当你下次部署 Agent 时，值得问自己一个问题：**你的 Agent 记得它五分钟前做过什么吗？**

---

*作者：qian | 2026-07-28*

*DeerFlow（quickFlow）：github.com/bytedance/deer-flow*
*Cruxible：github.com/cruxible-ai/cruxible*
