# DeerFlow + MySQL + Cruxible 端到端 POC（可复现）

本 POC 打通三段链路：

1. DeerFlow-by-cc 跑一次真实对话（产生 thread/state）
2. MySQL 存储对话的 thread/messages（数据库层持久化）
3. Cruxible 从 MySQL 取数落图，并在 cruxible-app 里可视化、追溯与审核

下面步骤默认在 macOS 上执行，工作区为：

- DeerFlow：`/Users/qian/Documents/workspace/deer-flow-by-cc`
- Cruxible Core：`/Users/qian/Documents/workspace/cruxible`
- Cruxible App：`/Users/qian/Documents/workspace/cruxible-app`

---

## 0. 前置条件

- Docker Desktop / OrbStack 可用
- `uv` 可用（Cruxible 的 Python 环境管理）

本 POC 额外需要 MySQL Python 驱动（运行时依赖）：

```bash
cd /Users/qian/Documents/workspace/cruxible
uv pip install pymysql
```

---

## 1. 启动 deer-flow-by-cc（7 个服务）

进入 deer-flow-by-cc 的 docker 目录并启动：

```bash
cd /Users/qian/Documents/workspace/deer-flow-by-cc/docker
export DEER_FLOW_ROOT=/Users/qian/Documents/workspace/deer-flow-by-cc
docker compose -p deer-flow-dev -f docker-compose-dev.yaml up -d --build
```

验证入口：

```bash
curl -fsS http://localhost:2026/health
```

---

## 2. 跑一次 DeerFlow 对话（产生 thread state）

用 Gateway 的 stateless runs 接口直接跑一次对话：

```bash
curl -fsS -X POST http://localhost:2026/api/runs/wait \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id":"lead_agent","input":{"messages":[{"role":"user","content":"用一句话解释 Cruxible 是什么"}]}}'
```

如果你希望拿到 `thread_id` 做后续同步，建议通过 UI 或者通过 `POST /api/threads` 显式创建 thread，再调用：

```bash
curl -fsS -X POST http://localhost:2026/api/threads/<thread_id>/runs/wait \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id":"lead_agent","input":{"messages":[{"role":"user","content":"..."}]}}'
```

读取某个 thread 的最终 state：

```bash
curl -fsS http://localhost:2026/api/threads/<thread_id>/state
```

---

## 3. 建本体（Cruxible Config）

本 POC 采用最小可验证本体：`Thread -> Message`。

配置文件位置：

- `cruxible/.poc/deerflow_poc_config.yaml`

核心要点：

- `entity_types`
  - `DeerflowThread`（主键 `thread_id`）
  - `DeerflowMessage`（主键 `message_id`）
- `relationships`
  - `thread_has_message`（一对多，带 `position`）
- `named_queries`
  - `threads`：列出 thread
  - `messages`：列出 message

这份 config 既支撑“从 DeerFlow state 直接落图”，也支撑“从 MySQL 表读入落图”。

---

## 4. 启动 Cruxible daemon，并准备实例

启动 daemon（本机 8100）：

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run cruxible server start --port 8100 --state-dir .poc/cruxible_server_state
```

将 config 作为 `config_yaml` 注册成一个 daemon 实例（返回 `instance_id`）：

```bash
curl -fsS -X POST http://127.0.0.1:8100/api/v1/instances \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json; print(json.dumps({\"root_dir\":\"/Users/qian/Documents/workspace/cruxible/.poc/cruxible_server_state/instances/inst_deerflow\",\"config_yaml\":open(\".poc/deerflow_poc_config.yaml\",\"r\",encoding=\"utf-8\").read()}))')"
```

也可以继续使用你已有的实例（示例：`inst_a9e7076af5794bd2`）。

---

## 5. DeerFlow -> Cruxible（直接落图，产出 receipt）

把指定 `thread_id` 的 state 写入某个 Cruxible instance root：

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run python scripts/poc_deerflow_by_cc.py \
  --deerflow-base-url http://localhost:2026 \
  --thread-id <thread_id> \
  --instance-root /Users/qian/Documents/workspace/cruxible/.poc/cruxible_server_state/instances/<instance_id> \
  --config-path /Users/qian/Documents/workspace/cruxible/.poc/deerflow_poc_config.yaml
```

脚本输出里包含：

- `receipt_id`：用于追溯
- `entities_total / relationships_total`：用于验证落图成功

---

## 6. 启动 MySQL（MariaDB 兼容）并把 DeerFlow state 写入 MySQL

启动 MySQL（本 POC 用 MariaDB 作为 MySQL 兼容实现；默认映射本机 3307 -> 容器 3306）：

```bash
cd /Users/qian/Documents/workspace/cruxible/.poc/mysql
docker compose up -d
```

连接信息（默认）：

- host: `127.0.0.1`
- port: `3307`
- user: `root`
- password: `cruxible`
- database: `deerflow_poc`

本 POC 的表结构：

- `threads(thread_id, title, metadata, created_at, updated_at)`
- `messages(message_id, thread_id, role, content, position, raw)`

把 DeerFlow 的 `thread_id` state 写入 MySQL（同时也会从 MySQL 读回并落到 Cruxible）：

```bash
cd /Users/qian/Documents/workspace/cruxible
uv run python scripts/poc_mysql_to_cruxible.py \
  --mysql-host 127.0.0.1 --mysql-port 3307 --mysql-user root --mysql-password cruxible --mysql-database deerflow_poc \
  --seed-from-deerflow --deerflow-base-url http://localhost:2026 \
  --thread-id <thread_id> \
  --instance-root /Users/qian/Documents/workspace/cruxible/.poc/cruxible_server_state/instances/<instance_id> \
  --config-path /Users/qian/Documents/workspace/cruxible/.poc/deerflow_poc_config.yaml
```

你也可以只验证“数据库层 -> Cruxible”这段（不 seed），前提是你已经自行往 MySQL 写入 thread/messages：

```bash
uv run python scripts/poc_mysql_to_cruxible.py \
  --mysql-host 127.0.0.1 --mysql-port 3307 --mysql-user root --mysql-password cruxible --mysql-database deerflow_poc \
  --thread-id <thread_id> \
  --instance-root /Users/qian/Documents/workspace/cruxible/.poc/cruxible_server_state/instances/<instance_id> \
  --config-path /Users/qian/Documents/workspace/cruxible/.poc/deerflow_poc_config.yaml
```

---

## 7. 启动 cruxible-app 并观察知识图谱

由于本机 pnpm/node 环境可能不稳定，推荐用 Docker 启动 cruxible-app dev server，并通过 Vite proxy 访问本机 daemon：

```bash
docker rm -f cruxible-app-dev 2>/dev/null || true
docker run -d --name cruxible-app-dev -p 5174:5173 \
  -e CI=true \
  -e CRUXIBLE_DAEMON_URL=http://host.docker.internal:8100 \
  -e VITE_CRUXIBLE_FIXTURES=0 \
  -e VITE_CRUXIBLE_INSTANCE_ID=<instance_id> \
  -v /Users/qian/Documents/workspace/cruxible-app:/app -w /app \
  node:22-slim \
  bash -lc "rm -rf node_modules && npm i -g pnpm@9.15.0 && pnpm install --frozen-lockfile && pnpm dev --host 0.0.0.0 --port 5173"
```

打开图谱页：

```text
http://localhost:5174/i/<instance_id>/graph
```

验证 API 代理也通（cruxible-app -> daemon）：

```bash
curl -fsS http://localhost:5174/api/v1/<instance_id>/stats
```

---

## 8. 如何追溯（receipt / provenance）

### 8.1 receipt 粒度

POC 的写入全部走 `service_batch_direct_write(...)`，每次写入都会产生 `receipt_id`。

获取 receipt 详情（daemon HTTP API）：

```bash
curl -fsS http://127.0.0.1:8100/api/v1/<instance_id>/receipts/<receipt_id>
```

### 8.2 在实体/边上定位来源

查看 edges（注意 `metadata.provenance.receipt_id` / `metadata.provenance.source`）：

```bash
curl -fsS "http://127.0.0.1:8100/api/v1/<instance_id>/list/edges?limit=50"
```

查看某个 entity 的详情：

```bash
curl -fsS "http://127.0.0.1:8100/api/v1/<instance_id>/inspect/entity/DeerflowThread/<thread_id>"
```

从 MySQL 入图的 POC 会把 MySQL 连接信息写进 `DeerflowThread.properties.metadata.mysql`，用于“从图回指数据库来源”的最小演示：

```bash
curl -fsS "http://127.0.0.1:8100/api/v1/<instance_id>/inspect/entity/DeerflowThread/<thread_id>" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["properties"]["metadata"].get("mysql"))'
```

---

## 9. 如何审核（review / governed edges）

本 POC 用的是“确定性直接写入”，边默认带有 `review.status = unreviewed`（UI 会以“Unreviewed / pending”显示）。

在 cruxible-app 的 State graph 页面左侧可看到：

- Entities 分类计数（Thread/Message）
- 当前图谱 `entities/edges` 数量
- 边的 review 状态图例

如果你希望把某类边改成“治理式审核”（例如走 candidate group proposal / trust ladder），需要把写入从 direct write 切换到 governed mutation/工作流 apply（这属于下一阶段增强，本 POC 不强制）。

如果要在 HTTP 层完成一次最小“人工审核”（approve/reject），可以直接调用反馈接口。你需要先从 `list/edges` 里找到目标边的 `edge_key`：

```bash
curl -fsS "http://127.0.0.1:8100/api/v1/<instance_id>/list/edges?limit=50"
```

然后 approve（示例；按你的边信息替换字段）：

```bash
curl -fsS -X POST "http://127.0.0.1:8100/api/v1/<instance_id>/feedback" \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "approve",
    "source": "poc_manual_review",
    "from_type": "DeerflowThread",
    "from_id": "<thread_id>",
    "relationship_type": "thread_has_message",
    "to_type": "DeerflowMessage",
    "to_id": "<message_id>",
    "edge_key": 0,
    "reason": "POC: manual review",
    "reason_code": "poc"
  }'
```

---

## 10. 常用排错

- cruxible-app 页面显示 fixture 数据而不是你的实例
  - 确认 `VITE_CRUXIBLE_FIXTURES=0`，并访问 `/i/<instance_id>/graph`
- daemon stats 不更新
  - 调用 `POST /api/v1/server/restart` 触发重启后再读 stats
- MySQL 容器启动慢
  - `docker logs -f cruxible-poc-mysql`
