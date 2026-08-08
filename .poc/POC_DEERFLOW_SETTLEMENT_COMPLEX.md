# DeerFlow → Cruxible 复杂清结算/对账/报表 POC（复杂图）

目标：用 DeerFlow thread state 作为入口（“对话产物”），在 Cruxible 中落一个包含清结算批次、对账 run、账务分录、争议单、报表与审批审计链路的复杂图；并能在 cruxible-app 里可视化查看，同时支持 receipt 追溯。

本 POC 默认规模（large）：约 8k–10k 节点、2w+ 边。

---

## 0. 前置

- 已启动 deer-flow-by-cc（含 gateway），并且本机可以访问：
  - http://localhost:2026/health
- 已安装本仓库依赖：

```bash
cd /Users/qian/Documents/workspace/cruxible
uv sync --all-extras
```

---

## 1. 启动 Cruxible daemon（8100）

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run cruxible server start --port 8100 --state-dir .poc/cruxible_server_state
```

---

## 2. 用复杂清结算本体注册一个 daemon 实例

这一步会把 config 作为 `config_yaml` 注册成一个 daemon-backed instance（返回 `instance_id`）。

```bash
cd /Users/qian/Documents/workspace/cruxible
curl -fsS -X POST http://127.0.0.1:8100/api/v1/instances \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json; print(json.dumps({\"root_dir\":\"/Users/qian/Documents/workspace/cruxible/.poc/cruxible_server_state/instances/inst_settlement_poc\",\"config_yaml\":open(\".poc/settlement/settlement_poc_config.yaml\",\"r\",encoding=\"utf-8\").read()}))')"
```

记下返回里的 `instance_id`（后面 cruxible-app 会用到）。

---

## 3. 在 DeerFlow 里产出 POC 输入（两种方式）

### 方式 A：真实对话生成（推荐）

进入 DeerFlow UI，打开一个 thread（建议使用你之前创建的 `cruxible` sub-agent），并让它输出一段 JSON（体量小、可控），作为“数据生成 spec”：

请直接把下面提示词粘进去：

```text
你要生成一个用于“清结算/对账/报表/审批/审计”的 POC 输入 JSON。要求：
1) JSON 必须包在 ```json ... ``` 代码块里；
2) 顶层必须包含：poc="settlement_reconciliation_v1"；
3) 必须包含 spec 字段：{seed:int, scale:"large", counts:{days, merchants, channels, orders, ledger_entries_per_order, disputes, audit_events}, currencies:[...], countries:[...]}；
4) 不要直接生成全量订单/分录明细（会太大），只输出 spec。
```

然后复制该 thread 的 `thread_id`，用于下一步脚本同步。

### 方式 B：脚本自动 seed DeerFlow thread（一键跑通）

不走 UI 对话，脚本会直接通过 DeerFlow API 创建 thread 并写入 spec（仍然是“从 deerflow thread state 来”）。

---

## 4. DeerFlow thread → Cruxible 落图（产出 receipts）

### A) 用现有 thread_id 同步

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run python scripts/poc_deerflow_settlement_to_cruxible.py \
  --deerflow-base-url http://localhost:2026 \
  --thread-id <thread_id> \
  --daemon-url http://127.0.0.1:8100 \
  --instance-id <instance_id> \
  --progress
```

### B) 一键 seed + 同步（large）

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run python scripts/poc_deerflow_settlement_to_cruxible.py \
  --deerflow-base-url http://localhost:2026 \
  --seed-thread \
  --scale large \
  --daemon-url http://127.0.0.1:8100 \
  --instance-id <instance_id> \
  --progress
```

脚本输出包括：
- `dataset_path`：生成的全量复杂数据 JSON（完整明细在这里）
- `entities_total / relationships_total`：落图规模
- `write_receipts`：每个 batch direct write 的 receipt（可追溯）

---

## 5. 在 cruxible-app 里看复杂图

启动 cruxible-app（按你本地习惯；示例用 docker，5174）：

```bash
cd /Users/qian/Documents/workspace/cruxible-app
docker run --rm -it \
  -p 5174:5174 \
  -e VITE_CRUXIBLE_DAEMON_URL=http://host.docker.internal:8100 \
  -e VITE_CRUXIBLE_FIXTURES=0 \
  -e VITE_CRUXIBLE_INSTANCE_ID=<instance_id> \
  -v "$PWD":/app \
  -w /app \
  node:20-bullseye bash -lc "npm ci && npm run dev -- --host 0.0.0.0 --port 5174"
```

打开：

- http://localhost:5174/i/<instance_id>/graph

---

## 6. Named query + receipt 追溯示例

### 6.1 列出 settlement batches（rows）

```bash
curl -fsS -X POST "http://127.0.0.1:8100/api/v1/<instance_id>/queries/run" \
  -H 'Content-Type: application/json' \
  -d '{"query_name":"settlement_batches","params":{},"limit":20,"offset":0,"layout":"rows"}'
```

### 6.2 拉一个 batch 的“batch→merchant”路径（graph）

```bash
curl -fsS -X POST "http://127.0.0.1:8100/api/v1/<instance_id>/queries/run" \
  -H 'Content-Type: application/json' \
  -d '{"query_name":"batch_to_merchants","params":{"settlement_batch_id":"<some_batch_id>"},"limit":200,"offset":0,"layout":"graph"}'
```

返回里会带 `receipt_id`。

### 6.3 用 receipt 追溯

```bash
curl -fsS "http://127.0.0.1:8100/api/v1/<instance_id>/receipts/<receipt_id>"
```

---

## 7. 排错

- 如果脚本报 “No POC input JSON found …”，说明 DeerFlow thread 的 messages 里没有包含 `poc="settlement_reconciliation_v1"` 的 JSON 代码块。
- 如果报属性校验失败（未知字段），确认你没有手动改过 `.poc/settlement/settlement_poc_config.yaml` 的字段名。
- 如果 cruxible-app 看不到图，确认：
  - VITE_CRUXIBLE_FIXTURES=0
  - VITE_CRUXIBLE_DAEMON_URL 指向 daemon（docker 内用 host.docker.internal）
  - 你的 instance 已通过 `/api/v1/instances` 注册且 instance_id 正确
