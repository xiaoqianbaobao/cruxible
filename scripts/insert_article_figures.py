"""Insert 12 article illustration placeholders into the WeChat article.

Each placeholder card uses the format:

    <!-- 图 N：标题 — 示意图占位（设计待补） -->
    > **〔示意图占位｜图 N〕**
    > **标题：** …
    > **说明：** 2–3 句文案，描述图的目的和内容
    > **建议类型：** 分层图 / 流程图 / 因果有向图 / 集成拓扑 / 表格关系图 / 清单导图
    > **设计要点：**
    > - 要点一
    > - 要点二
    > - 要点三
    > *（设计师可自由发挥版式，内容以本条说明为准）*

Planned figures (12):
    图 0 — 封面：DeerFlow × Cruxible 清结算图谱 POC 主视觉
    图 1 — Agent 工程 6 大死穴 vs 解法对照矩阵
    图 2 — Cruxible 4 原语 + 3 层承诺本体工程图
    图 3 — DeerFlow × Cruxible 双引擎企业参考架构
    图 4 — 清结算本体 5 层存在独立性分层
    图 5 — 清结算 4 条因果主链有向图
    图 6 — 企业集成 4 种模式拓扑
    图 7 — 实操手册：8 步本机复现路线图
    图 8 — 企业化 10 项清单分组导图
    图 9 — 死穴 → 解法 → 对应源码/工具 闭环关联图
    图 10 — 实例 ID 默认注入：CRUXIBLE_DEFAULT_INSTANCE_ID 链路
    图 11 — 清结算本体实体 × 关系一览（总览拼图）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

MD_PATH = (
    Path(__file__).resolve().parent.parent
    / ".poc/WECHAT_DEERFLOW_CRUXIBLE_SETTLEMENT_POC.md"
)


@dataclass(frozen=True)
class Figure:
    num: int
    title: str
    anchor: str  # regex / text anchor to locate insertion (insert AFTER the matched line)
    insert_after: bool  # True=after anchor, False=before anchor
    desc: str
    figtype: str
    bullets: tuple[str, ...]


FIGURES: tuple[Figure, ...] = (
    Figure(
        num=0,
        title="封面主视觉：DeerFlow × Cruxible 清结算复杂图谱 POC",
        anchor=r"^> 本文适合人群：",
        insert_after=False,
        desc="开篇头图：左侧 DeerFlow（对话/编排）+ 中间 MCP(SSE) 通路 + 右侧 Cruxible（确定性图谱+receipts+治理），底部「清结算 5.6 万实体 / 12.8 万关系」数据标签。",
        figtype="主视觉/封面拼贴",
        bullets=(
            "主色调用两套品牌色叠加：DeerFlow 绿系 + Cruxible 蓝系；",
            "中央用一条有向箭头 MCP(SSE) 把左右打通，标注 8100 / 8123 / 2026 / 5174 端口；",
            "右下角叠一张「网络点线」图谱小图，暗示实体关系密度。",
        ),
    ),
    Figure(
        num=1,
        title="Agent 工程 6 大死穴 × Cruxible 解法对照矩阵",
        anchor=r"^# 一、Agent 在工程领域的 6 大死穴",
        insert_after=True,
        desc="2×6 矩阵：左列「死穴」、右列「Cruxible 解法 + 对应原语/承诺」。强调：这不是 prompt 能解决的问题，而是工程范式的替换。",
        figtype="对照矩阵表/分层图",
        bullets=(
            "死穴侧用红色标签（语义对齐缺失 / 推理不可证明 / 治理缺失 / 上下文爆炸 / 系统割裂 / 可复现不足）；",
            "解法侧用蓝色标签，写明「Config / Query+receipt / Permissions / Workflow 批处理 / Ingest+Integrations / Snapshot+lockfile」；",
            "底部一条总括：本体论 4 原语 + 3 层承诺 = 6 死穴一次解。",
        ),
    ),
    Figure(
        num=2,
        title="Cruxible 本体工程总览：4 原语 × 3 层承诺",
        anchor=r"^## 2\.2 Cruxible 的 4 个原语",
        insert_after=True,
        desc="四象限 + 三层三明治：4 原语 Config-Ingest-Query-Feedback 横向铺开；3 层承诺（推理层确定性/证据层 receipts/治理层 permissions+groups+feedback）纵向叠在其下，标明每一层承诺分别保障哪些原语。",
        figtype="分层架构图",
        bullets=(
            "顶部横栏：Config / Ingest / Query / Feedback 四格，每格配一句工程类比（Schema+契约 / ETL with provenance / 可证明只读 API / 治理+审核闭环）；",
            "下方三栏：推理层 → 证据层 → 治理层，用虚线箭头与上方 4 原语映射；",
            "右侧标注关键源码：schema.py / step_handlers.py / permissions.py / evaluate.py / instance_protocol.py。",
        ),
    ),
    Figure(
        num=3,
        title="DeerFlow × Cruxible 双引擎企业参考架构（端口映射）",
        anchor=r"^## 3\.2 本 POC 的企业级参考架构",
        insert_after=True,
        desc="5 层分层：交互层（DeerFlow UI/Gateway :2026）→ MCP 语义层（Cruxible SSE :8123）→ 图谱服务层（daemon :8100 + state.db）→ 接入边（CDC/Webhook/Workflow/人工审核）→ 源系统（交易/ERP/风控/对话）；标注各层典型工具（cruxible_query / cruxible_receipt / cruxible_workflow_apply / cruxible_feedback）。",
        figtype="分层拓扑图",
        bullets=(
            "用粗实线分隔 5 层；每层标注「进程名 / 端口 / 主要职责」；",
            "cruxible-app（可视化 :5174）作为旁路挂在 MCP 语义层右侧；",
            "标注右侧的权限模式：READ_ONLY / GOVERNED_WRITE / GRAPH_WRITE / ADMIN 指向对应的接入边。",
        ),
    ),
    Figure(
        num=4,
        title="清结算本体存在层：5 级独立度分层（17 类实体）",
        anchor=r"^## 4\.1 存在层 5 大类：把实体按「存在独立性」分层",
        insert_after=True,
        desc="金字塔分层：最顶层「独立存在的聚合根」(Merchant/Channel/Account) → 「规则参考对象」(FeeRule/FXRate) → 「交易资金事件」(PaymentOrder/Transfer/LedgerEntry/SettlementBatch) → 「对账治理记录」(ReconcileRun/ReconcileLine/Dispute) → 「审计报表记录」(Report/Approval/AuditEvent)；每层标注实体类型数量、主键策略、存在依赖方向。",
        figtype="分层金字塔/依赖有向图",
        bullets=(
            "金字塔由下往上：依赖箭头指向上（下层依附上层存在）；",
            "每层用不同底色（由冷到暖）；",
            "在 17 类实体旁标注主键字段（例如 settlement_batch_id / order_id）与 PII 脱敏提示（Account）。",
        ),
    ),
    Figure(
        num=5,
        title="清结算 4 条因果主链有向图（25 类关系分桶）",
        anchor=r"^## 4\.2 因果链 4 条主线：关系不是乱拉的",
        insert_after=True,
        desc="4 条并列的有向子图：A 资金链(order→transfer→ledger→account)、B 对账链(batch→run→line→order/dispute)、C 规则归属链(order→fee_rule, transfer→fx_rate)、D 报表审批审计链(report→batch, approval→report, audit→order/batch)；每条子图旁标注该链的典型查询（例：查 diff_amount Top20 → 使用 B 链）。",
        figtype="有向因果图（4 合 1）",
        bullets=(
            "用 4 种不同颜色箭头区分 A/B/C/D 链；",
            "关系名沿箭头写小标签（order_paid_by_transfer / run_has_line 等）；",
            "底部加一张小表格：25 类关系分布（A 链 x / B 链 y / C 链 z / D 链 w + 跨链辅助 m）。",
        ),
    ),
    Figure(
        num=6,
        title="Cruxible × 业务系统：企业集成 4 种模式",
        anchor=r"^# 五、Cruxible 与业务系统结合的 4 种模式",
        insert_after=True,
        desc="4 格泳道：模式 1 对话驱动 spec（DeerFlow→Cruxible workflow）；模式 2 CDC→Ingest（业务库 binlog→Cruxible ingest）；模式 3 Webhook→Governed Write（ERP 审批回写 feedback/outcome）；模式 4 数仓 T+1→Workflow Batch Apply（DWH→Cruxible workflow+lockfile）。每格写清楚触发源、Cruxible 原语、权限模式、落地工具。",
        figtype="集成泳道/模式卡片",
        bullets=(
            "每格左上角贴触发源徽章（用户对话图标 / binlog 图标 / webhook 闪电 / 数仓时钟）；",
            "每格右下角写使用到的关键工具（cruxible_init / cruxible_batch_direct_write / cruxible_feedback / cruxible_workflow_apply / cruxible_lock 等）；",
            "最右列加一列「生产优先级」（推荐 / 备选 / 小流量 / 大批次）。",
        ),
    ),
    Figure(
        num=7,
        title="实操路线图：8 步一键复现 POC（本机）",
        anchor=r"^# 六、完整实操手册：8 步跑通清结算复杂图谱 POC",
        insert_after=True,
        desc="纵向 8 步流程：① 克隆三仓库并启动服务 → ② Cruxible daemon + MCP SSE + cruxible-app → ③ DeerFlow extensions_config 切 SSE → ④ SOUL.md 保留默认实例指引（不传 instance_id 走 CRUXIBLE_DEFAULT_INSTANCE_ID） → ⑤ DeerFlow 输入清结算 spec → ⑥ 脚本落图 + worklow apply → ⑦ cruxible-app 可视化 inspect → ⑧ query/receipt/evaluate 验证。每一步旁标注关键命令行、端口、配置文件。",
        figtype="流程路线图（8 节点）",
        bullets=(
            "节点用序号 + 卡片，节点间单向箭头；",
            "把 3 个 GitHub 仓库图标放在第 ① 步；",
            "把默认实例注入链路高亮：CRUXIBLE_DEFAULT_INSTANCE_ID → MCP handlers → 不传 instance_id 的 cruxible_query 也能跑。",
        ),
    ),
    Figure(
        num=8,
        title="企业化改造 10 项清单：从 Demo 到生产",
        anchor=r"^# 七、企业化改造清单：从 Demo 到生产的 10 个必做项",
        insert_after=True,
        desc="思维导图式分组：① 多租户与别名 ② 权限分层与 RBAC ③ 持久化升级（SQLite→Postgres）④ daemon HA & 健康检查 ⑤ IdP & SSO ⑥ 全版本化 GitOps（config/lock/snapshot）⑦ 监控告警（4 类指标 + evaluate 6 检查）⑧ 幂等 + snapshot 回滚 ⑨ PII 脱敏 3 档 profile ⑩ SRE trace_id 贯穿。中心节点写「Cruxible Enterprise Checklist」。",
        figtype="分组思维导图/清单导图",
        bullets=(
            "10 项围绕中心节点放射；按主题上色（运维蓝 / 安全紫 / 治理绿 / 数据橙）；",
            "在 ① 多租户项旁边加一个小图标：实例别名 → CRUXIBLE_DEFAULT_INSTANCE_ID 的映射表；",
            "在 ⑧ 幂等项旁边标注：canonical workflow apply + StateSnapshot 不可变。",
        ),
    ),
    Figure(
        num=9,
        title="死穴 → 解法 → 源码/工具闭环图",
        anchor=r"^# 八、回到开篇：我们如何逐一解决 Agent 的 6 大死穴？",
        insert_after=True,
        desc="三列闭环：左列「6 大死穴」→ 中列「Cruxible 解法」→ 右列「源码与工具锚点」。每一行由虚线横向连接；底部一条环形箭头表示「evaluate → feedback → config 迭代」持续优化本体。",
        figtype="三列关联图/闭环回路图",
        bullets=(
            "左列保持红色死穴名称；中列蓝绿色解法；右列贴源码/工具名（settlement_poc_config.yaml、mcp/tools.py、runtime/permissions.py、workflow compiler/executor、evaluate.py、lockfile/snapshot）；",
            "底部加一个自环箭头：Feedback → Config 增量迭代；",
            "右上角贴一个小收据图标，象征 receipt 可审计。",
        ),
    ),
    Figure(
        num=10,
        title="方案 A 工程化：默认实例 ID 的自动注入链路",
        anchor=r"^## Step 4：确认 DeerFlow 的 `extensions_config\.json` 指向 SSE",
        insert_after=False,  # 放在该小节标题之前，紧跟 Step 3
        desc="纵向链路：Operator 在启动脚本里 export CRUXIBLE_DEFAULT_INSTANCE_ID=inst_xxx → Cruxible service_server/server_info 返回 ServerInfoResult.default_instance_id → MCP tools 声明里 instance_id 改为可空（未提供即默认）→ MCP handlers 统一 resolve_default_instance_id → 所有实例作用域工具自动使用默认。",
        figtype="链路流程图（纵向）",
        bullets=(
            "用 4 段泳道：Operator 环境变量 / daemon service / MCP runtime / Agent(DeerFlow) tool call；",
            "把 resolve_default_instance_id 函数画成一个菱形判断：显式 instance_id 非空？→ 是：直接用；否：读 env 兜底；",
            "特别高亮 cruxible_query / cruxible_list_queries / cruxible_workflow_apply 三个最常用工具。",
        ),
    ),
    Figure(
        num=11,
        title="清结算本体总览拼图：17 类实体 × 25 类关系图谱全景",
        anchor=r"^## 4\.3 约束锁：我们明确了什么不允许发生",
        insert_after=True,
        desc="一张综合图谱小总览：17 类实体用节点（按存在层颜色分 5 组），25 类关系用有向边并按 A/B/C/D 链分 4 色；在节点周围标注几个关键约束锁（fee_amount≥0、currency 一致、approval∈3 值等）。",
        figtype="实体关系全景图",
        bullets=(
            "节点布局按存在层 5 组垂直分布；",
            "边上用细标签写关系名（可省略全量以图清楚为主，正文补表）；",
            "右下角放一个 mini 图例：A/B/C/D 链颜色 + 5 层实体颜色。",
        ),
    ),
)


def _render(fig: Figure) -> str:
    bullet_lines = "\n".join(f"> - {b}" for b in fig.bullets)
    return (
        f"\n<!-- 图 {fig.num}：{fig.title} — 示意图占位（设计待补） -->\n"
        f"> **〔示意图占位｜图 {fig.num}〕**\n"
        f"> **标题：** {fig.title}\n"
        f"> **说明：** {fig.desc}\n"
        f"> **建议类型：** {fig.figtype}\n"
        f"> **设计要点：**\n"
        f"{bullet_lines}\n"
        f"> *（设计师可自由发挥版式，内容以本条说明为准。）*\n"
    )


def main() -> None:
    src = MD_PATH.read_text(encoding="utf-8")
    # Process in reverse figure-number order so insertions don't shift line
    # indexes of later (smaller-numbered) figures when anchors match by line.
    for fig in sorted(FIGURES, key=lambda f: f.num, reverse=True):
        # Anchor can start with '^' for regex line start. We use re.search on whole text.
        pattern = re.compile(fig.anchor, re.MULTILINE)
        m = pattern.search(src)
        if not m:
            raise SystemExit(f"figure {fig.num}: anchor not found: {fig.anchor}")
        if fig.insert_after:
            insert_at = m.end()
        else:
            insert_at = m.start()
        src = src[:insert_at] + _render(fig) + src[insert_at:]
    MD_PATH.write_text(src, encoding="utf-8")


if __name__ == "__main__":
    main()
