from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

from cruxible_core.runtime.instance import CruxibleInstance
from cruxible_core.service import service_batch_direct_write, service_init
from cruxible_core.service.types import (
    BatchDirectWriteInput,
    BatchRelationshipWriteInput,
    EntityWriteInput,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _date_iso(value: date) -> str:
    return value.isoformat()


def _wait_for_http_ok(url: str, *, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_error: str | None = None
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5.0)
            if 200 <= resp.status_code < 300:
                return
            last_error = f"{resp.status_code} {resp.text}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"health check failed for {url}: {last_error}")


def _post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    resp = httpx.post(url, json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    resp = httpx.get(url, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def _ensure_clean_instance_root(instance_root: Path, *, reset: bool) -> None:
    if not reset:
        instance_root.mkdir(parents=True, exist_ok=True)
        return
    if instance_root.exists():
        shutil.rmtree(instance_root)
    instance_root.mkdir(parents=True, exist_ok=True)


def _init_cruxible_instance(*, instance_root: Path, config_path: Path) -> CruxibleInstance:
    metadata_path = instance_root / CruxibleInstance.INSTANCE_DIR / "instance.json"
    if metadata_path.exists():
        return CruxibleInstance.load(instance_root)
    service_init(instance_root, config_path=str(config_path), instance_mode=CruxibleInstance.DEV_MODE)
    return CruxibleInstance.load(instance_root)


def _extract_messages(state: dict[str, Any]) -> list[dict[str, Any]]:
    values = state.get("values") or {}
    messages = values.get("messages") or []
    if not isinstance(messages, list):
        return []
    result: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append({"role": "unknown", "content": str(item), "raw": item})
    return result


def _extract_json_blob(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    fence = "```json"
    start = stripped.find(fence)
    if start != -1:
        after = stripped[start + len(fence) :]
        end = after.find("```")
        if end != -1:
            candidate = after[:end].strip()
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_poc_input_from_state(state: dict[str, Any]) -> dict[str, Any]:
    for message in reversed(_extract_messages(state)):
        content = message.get("content")
        if not isinstance(content, str):
            continue
        parsed = _extract_json_blob(content)
        if parsed is None:
            continue
        if parsed.get("poc") == "settlement_reconciliation_v1":
            return parsed
    raise RuntimeError(
        "No POC input JSON found in DeerFlow thread state. "
        "Expected a message containing JSON with poc='settlement_reconciliation_v1'."
    )


def _seed_deerflow_thread(base_url: str, *, spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    thread = _post_json(
        base_url,
        "/api/threads",
        {
            "metadata": {
                "poc": True,
                "poc_name": "settlement_reconciliation_v1",
                "created_at": _utc_now_iso(),
            }
        },
    )
    thread_id = str(thread["thread_id"])
    messages = [
        {
            "id": f"{thread_id}:m0",
            "role": "user",
            "content": "生成一个清结算/对账/报表的复杂 POC 场景（参数化 spec），用于同步到 Cruxible。",
        },
        {
            "id": f"{thread_id}:m1",
            "role": "assistant",
            "content": "```json\n" + json.dumps(spec, ensure_ascii=False, indent=2) + "\n```",
        },
    ]
    _post_json(
        base_url,
        f"/api/threads/{thread_id}/state",
        {
            "values": {
                "title": "settlement reconciliation POC",
                "messages": messages,
            }
        },
    )
    state = _get_json(base_url, f"/api/threads/{thread_id}/state")
    return thread_id, state


def _scale_defaults(scale: str) -> dict[str, int]:
    if scale == "small":
        return dict(
            days=10,
            merchants=15,
            channels=4,
            orders=300,
            ledger_entries_per_order=3,
            disputes=40,
            audit_events=120,
        )
    if scale == "medium":
        return dict(
            days=15,
            merchants=25,
            channels=5,
            orders=700,
            ledger_entries_per_order=3,
            disputes=120,
            audit_events=300,
        )
    if scale == "large":
        return dict(
            days=20,
            merchants=40,
            channels=6,
            orders=1200,
            ledger_entries_per_order=3,
            disputes=200,
            audit_events=600,
        )
    raise ValueError(f"Unsupported scale={scale!r}. Use small|medium|large.")


def _build_default_spec(*, scale: str, seed: int) -> dict[str, Any]:
    counts = _scale_defaults(scale)
    return {
        "poc": "settlement_reconciliation_v1",
        "scale": scale,
        "seed": seed,
        "counts": counts,
        "currencies": ["USD", "CNY", "EUR"],
        "countries": ["US", "CN", "SG", "DE"],
    }


def _rand_choice(rng: random.Random, values: list[str]) -> str:
    return values[rng.randrange(0, len(values))]


def _money(rng: random.Random, *, low: float = 10.0, high: float = 500.0) -> float:
    return round(rng.uniform(low, high), 2)


def _clamp_int(value: int, *, min_value: int, max_value: int) -> int:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _generate_dataset(spec: dict[str, Any]) -> dict[str, Any]:
    seed = int(spec.get("seed") or 0)
    rng = random.Random(seed)
    counts = spec.get("counts") or {}
    raw_days = int(counts.get("days") or 20)
    raw_merchants = int(counts.get("merchants") or 40)
    raw_channels = int(counts.get("channels") or 6)
    raw_orders = int(counts.get("orders") or 1200)
    raw_ledger_per_order = int(counts.get("ledger_entries_per_order") or 3)
    raw_disputes = int(counts.get("disputes") or 200)
    raw_audits = int(counts.get("audit_events") or 600)

    days = _clamp_int(raw_days, min_value=1, max_value=60)
    merchant_count = _clamp_int(raw_merchants, min_value=1, max_value=500)
    channel_count = _clamp_int(raw_channels, min_value=1, max_value=20)
    order_count = _clamp_int(raw_orders, min_value=1, max_value=5000)
    ledger_per_order = _clamp_int(raw_ledger_per_order, min_value=1, max_value=6)
    dispute_count = _clamp_int(raw_disputes, min_value=0, max_value=2000)
    audit_event_count = _clamp_int(raw_audits, min_value=0, max_value=8000)
    currencies = list(spec.get("currencies") or ["USD", "CNY", "EUR"])
    countries = list(spec.get("countries") or ["US", "CN", "SG", "DE"])

    now = _utc_now()
    start_day = (now.date() - timedelta(days=days + 3))
    cycle_dates = [start_day + timedelta(days=i) for i in range(days)]

    merchants: list[dict[str, Any]] = []
    for i in range(merchant_count):
        merchant_id = f"m_{i:04d}"
        merchants.append(
            dict(
                merchant_id=merchant_id,
                name=f"Merchant {i:04d}",
                country=_rand_choice(rng, countries),
                industry=_rand_choice(rng, ["ecommerce", "travel", "gaming", "saas", "retail"]),
                risk_level=_rand_choice(rng, ["low", "medium", "high"]),
                active=True,
                created_at=(now - timedelta(days=rng.randrange(10, 365))).isoformat(),
            )
        )

    channels: list[dict[str, Any]] = []
    for i in range(channel_count):
        channel_id = f"c_{i:03d}"
        channels.append(
            dict(
                channel_id=channel_id,
                name=f"Channel {i:03d}",
                channel_type=_rand_choice(rng, ["card", "wallet", "bank_transfer", "local_pay"]),
                country=_rand_choice(rng, countries),
                settlement_cycle=_rand_choice(rng, ["D+0", "D+1", "T+1"]),
            )
        )

    fee_rules: list[dict[str, Any]] = []
    for i in range(20):
        fee_rule_id = f"fr_{i:03d}"
        rule_type = _rand_choice(rng, ["percentage", "fixed"])
        fee_rules.append(
            dict(
                fee_rule_id=fee_rule_id,
                name=f"FeeRule {i:03d}",
                rule_type=rule_type,
                rate=round(rng.uniform(0.005, 0.035), 6) if rule_type == "percentage" else 0.0,
                fixed_fee=round(rng.uniform(0.1, 1.5), 2) if rule_type == "fixed" else 0.0,
                currency=_rand_choice(rng, currencies),
                effective_from=_date_iso(start_day - timedelta(days=30)),
                effective_to=_date_iso(start_day + timedelta(days=365)),
            )
        )

    fx_rates: list[dict[str, Any]] = []
    pairs = ["USD/CNY", "EUR/USD", "EUR/CNY", "USD/SGD", "EUR/SGD"]
    for i in range(10):
        fx_rate_id = f"fx_{i:03d}"
        fx_rates.append(
            dict(
                fx_rate_id=fx_rate_id,
                pair=_rand_choice(rng, pairs),
                rate=round(rng.uniform(0.5, 9.0), 6),
                as_of=(now - timedelta(hours=rng.randrange(0, 240))).isoformat(),
                provider=_rand_choice(rng, ["ecb", "fixer", "internal"]),
            )
        )

    accounts: list[dict[str, Any]] = []
    for merchant in merchants:
        for currency in currencies:
            merchant_account_id = f"a_{merchant['merchant_id']}_{currency.lower()}_m"
            fee_account_id = f"a_{merchant['merchant_id']}_{currency.lower()}_f"
            opened_at = (now - timedelta(days=rng.randrange(30, 800))).isoformat()
            bank = _rand_choice(rng, ["Bank A", "Bank B", "Bank C"])
            accounts.append(
                dict(
                    account_id=merchant_account_id,
                    merchant_id=merchant["merchant_id"],
                    currency=currency,
                    account_type="merchant",
                    bank_name=bank,
                    opened_at=opened_at,
                )
            )
            accounts.append(
                dict(
                    account_id=fee_account_id,
                    merchant_id=merchant["merchant_id"],
                    currency=currency,
                    account_type="fees",
                    bank_name=bank,
                    opened_at=opened_at,
                )
            )

    for channel in channels:
        currency = _rand_choice(rng, currencies)
        accounts.append(
            dict(
                account_id=f"a_clearing_{channel['channel_id']}_{currency.lower()}",
                merchant_id="",
                currency=currency,
                account_type="clearing",
                bank_name=_rand_choice(rng, ["Clearing Bank 1", "Clearing Bank 2"]),
                opened_at=(now - timedelta(days=rng.randrange(30, 800))).isoformat(),
            )
        )

    batches: list[dict[str, Any]] = []
    batch_index: dict[tuple[str, str, str], str] = {}
    for channel in channels:
        for cycle in cycle_dates:
            for currency in currencies:
                batch_id = f"b_{channel['channel_id']}_{cycle.strftime('%Y%m%d')}_{currency.lower()}"
                batches.append(
                    dict(
                        settlement_batch_id=batch_id,
                        channel_id=channel["channel_id"],
                        cycle_date=_date_iso(cycle),
                        currency=currency,
                        total_amount=0.0,
                        status=_rand_choice(rng, ["generated", "paid"]),
                        generated_at=datetime.combine(cycle, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                        paid_at=(
                            datetime.combine(cycle, datetime.min.time(), tzinfo=timezone.utc)
                            + timedelta(hours=rng.randrange(6, 72))
                        ).isoformat(),
                    )
                )
                batch_index[(channel["channel_id"], _date_iso(cycle), currency)] = batch_id

    orders: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    ledger_entries: list[dict[str, Any]] = []

    merchant_ids = [m["merchant_id"] for m in merchants]
    channel_ids = [c["channel_id"] for c in channels]
    fee_rule_ids = [fr["fee_rule_id"] for fr in fee_rules]
    fx_rate_ids = [fx["fx_rate_id"] for fx in fx_rates]

    batch_totals: dict[str, float] = {b["settlement_batch_id"]: 0.0 for b in batches}
    for i in range(order_count):
        order_id = f"o_{i:06d}"
        merchant_id = merchant_ids[rng.randrange(0, len(merchant_ids))]
        channel_id = channel_ids[rng.randrange(0, len(channel_ids))]
        created_at = now - timedelta(days=rng.randrange(0, days), hours=rng.randrange(0, 24))
        currency = _rand_choice(rng, currencies)
        amount = _money(rng)
        status = _rand_choice(rng, ["captured", "captured", "captured", "refunded", "chargeback"])
        fee_rule_id = fee_rule_ids[rng.randrange(0, len(fee_rule_ids))]

        cycle = created_at.date()
        cycle_date = _date_iso(cycle if cycle in cycle_dates else cycle_dates[-1])
        batch_id = batch_index.get((channel_id, cycle_date, currency))
        if batch_id is None:
            batch_id = batch_index[(channel_id, _date_iso(cycle_dates[-1]), currency)]

        orders.append(
            dict(
                order_id=order_id,
                merchant_id=merchant_id,
                channel_id=channel_id,
                amount=amount,
                currency=currency,
                status=status,
                created_at=created_at.isoformat(),
                settled_at=(created_at + timedelta(hours=rng.randrange(1, 72))).isoformat(),
                external_ref=f"ext_{uuid.uuid4().hex[:10]}",
                fee_rule_id=fee_rule_id,
            )
        )

        transfer_id = f"t_{i:06d}"
        fx_rate_id = fx_rate_ids[rng.randrange(0, len(fx_rate_ids))]
        transfers.append(
            dict(
                transfer_id=transfer_id,
                order_id=order_id,
                direction=_rand_choice(rng, ["inbound", "outbound"]),
                amount=amount,
                currency=currency,
                executed_at=(created_at + timedelta(hours=rng.randrange(1, 12))).isoformat(),
                status=_rand_choice(rng, ["executed", "executed", "pending", "failed"]),
                fx_rate_id=fx_rate_id,
            )
        )

        fee = round(amount * rng.uniform(0.006, 0.03), 2)
        principal_account_id = f"a_{merchant_id}_{currency.lower()}_m"
        fee_account_id = f"a_{merchant_id}_{currency.lower()}_f"

        ledger_defs: list[tuple[str, float, str]] = [
            ("principal", amount, principal_account_id),
            ("fee", -fee, fee_account_id),
        ]
        if ledger_per_order >= 3:
            adjustment = round(rng.uniform(-0.8, 0.8), 2)
            ledger_defs.append(("adjustment", adjustment, principal_account_id))

        for j, (entry_type, entry_amount, account_id) in enumerate(ledger_defs[:ledger_per_order]):
            ledger_entry_id = f"le_{i:06d}_{j}"
            posted_at = created_at + timedelta(hours=rng.randrange(1, 96))
            ledger_entries.append(
                dict(
                    ledger_entry_id=ledger_entry_id,
                    account_id=account_id,
                    order_id=order_id,
                    entry_type=entry_type,
                    amount=entry_amount,
                    currency=currency,
                    posted_at=posted_at.isoformat(),
                    batch_id=batch_id,
                    transfer_id=transfer_id,
                )
            )
            batch_totals[batch_id] = round(batch_totals[batch_id] + entry_amount, 2)

    for batch in batches:
        total = batch_totals.get(batch["settlement_batch_id"], 0.0)
        batch["total_amount"] = total

    runs: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    lines_by_order: dict[str, str] = {}
    for batch in batches:
        run_id = f"r_{batch['settlement_batch_id']}"
        started = datetime.fromisoformat(batch["generated_at"])
        runs.append(
            dict(
                reconcile_run_id=run_id,
                batch_id=batch["settlement_batch_id"],
                run_type=_rand_choice(rng, ["daily", "rerun", "intraday"]),
                started_at=started.isoformat(),
                completed_at=(started + timedelta(minutes=rng.randrange(10, 180))).isoformat(),
                status=_rand_choice(rng, ["success", "success", "partial", "failed"]),
            )
        )

    orders_by_batch: dict[str, list[dict[str, Any]]] = {}
    for order in orders:
        channel_id = order["channel_id"]
        created_at = datetime.fromisoformat(order["created_at"])
        cycle_date = _date_iso(created_at.date())
        batch_id = batch_index.get((channel_id, cycle_date, order["currency"]))
        if batch_id is None:
            batch_id = batch_index[(channel_id, _date_iso(cycle_dates[-1]), order["currency"])]
        orders_by_batch.setdefault(batch_id, []).append(order)

    for batch in batches:
        run_id = f"r_{batch['settlement_batch_id']}"
        batch_orders = orders_by_batch.get(batch["settlement_batch_id"], [])
        for order in batch_orders:
            line_id = f"rl_{order['order_id']}"
            expected = float(order["amount"])
            noise = round(rng.uniform(-2.0, 2.0), 2)
            actual = round(expected + noise, 2)
            diff = round(actual - expected, 2)
            reason = (
                "rounding"
                if abs(diff) <= 0.05
                else _rand_choice(rng, ["fee_mismatch", "fx_mismatch", "duplicate", "missing_order", "unknown"])
            )
            severity = "low" if abs(diff) <= 0.5 else ("medium" if abs(diff) <= 2.0 else "high")
            resolved = abs(diff) <= 0.05
            lines.append(
                dict(
                    reconcile_line_id=line_id,
                    run_id=run_id,
                    order_id=order["order_id"],
                    expected_amount=expected,
                    actual_amount=actual,
                    diff_amount=diff,
                    diff_reason=reason,
                    severity=severity,
                    resolved=resolved,
                )
            )
            lines_by_order[order["order_id"]] = line_id

    disputes: list[dict[str, Any]] = []
    disputed_orders = rng.sample(orders, k=min(dispute_count, len(orders)))
    for i, order in enumerate(disputed_orders):
        dispute_id = f"d_{i:05d}"
        opened = datetime.fromisoformat(order["created_at"]) + timedelta(days=rng.randrange(1, 15))
        closed = opened + timedelta(days=rng.randrange(1, 45))
        disputes.append(
            dict(
                dispute_id=dispute_id,
                order_id=order["order_id"],
                dispute_type=_rand_choice(rng, ["chargeback", "refund", "reversal", "inquiry"]),
                opened_at=opened.isoformat(),
                closed_at=closed.isoformat(),
                status=_rand_choice(rng, ["open", "pending", "won", "lost"]),
                amount=round(float(order["amount"]) * rng.uniform(0.2, 1.0), 2),
                currency=order["currency"],
                reason_code=_rand_choice(rng, ["FRAUD", "DUPLICATE", "NOT_RECEIVED", "NOT_AS_DESCRIBED"]),
            )
        )

    reports: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    for batch in batches:
        report_id = f"rep_{batch['settlement_batch_id']}"
        generated = datetime.fromisoformat(batch["paid_at"])
        reports.append(
            dict(
                report_id=report_id,
                batch_id=batch["settlement_batch_id"],
                report_type=_rand_choice(rng, ["reconcile_summary", "settlement_statement", "exception_list"]),
                generated_at=generated.isoformat(),
                uri=f"s3://poc/reports/{report_id}.json",
            )
        )
        approvals.append(
            dict(
                approval_id=f"appr_{batch['settlement_batch_id']}",
                report_id=report_id,
                approver=_rand_choice(rng, ["alice", "bob", "carol", "dave"]),
                decision=_rand_choice(rng, ["approved", "approved", "approved", "rejected"]),
                decided_at=(generated + timedelta(hours=rng.randrange(1, 48))).isoformat(),
                comment=_rand_choice(
                    rng,
                    [
                        "OK",
                        "Need follow-up on exceptions",
                        "Approved with note",
                        "Reject: missing evidence",
                    ],
                ),
            )
        )

    audit_events: list[dict[str, Any]] = []
    order_ids = [o["order_id"] for o in orders]
    batch_ids = [b["settlement_batch_id"] for b in batches]
    dispute_ids = [d["dispute_id"] for d in disputes]
    for i in range(audit_event_count):
        audit_event_id = f"ae_{i:06d}"
        event_type = _rand_choice(
            rng,
            [
                "reconcile.run_started",
                "reconcile.run_completed",
                "reconcile.diff_detected",
                "dispute.opened",
                "report.generated",
                "approval.decided",
            ],
        )
        actor = _rand_choice(rng, ["system", "recon_bot", "human_reviewer"])
        occurred = now - timedelta(days=rng.randrange(0, days), hours=rng.randrange(0, 24))
        target_kind = _rand_choice(rng, ["order", "batch", "dispute"])
        payload: dict[str, Any] = {"target_kind": target_kind}
        if target_kind == "order":
            payload["order_id"] = order_ids[rng.randrange(0, len(order_ids))]
        elif target_kind == "batch":
            payload["settlement_batch_id"] = batch_ids[rng.randrange(0, len(batch_ids))]
        else:
            payload["dispute_id"] = (
                dispute_ids[rng.randrange(0, len(dispute_ids))] if dispute_ids else "d_00000"
            )
        audit_events.append(
            dict(
                audit_event_id=audit_event_id,
                event_type=event_type,
                actor=actor,
                occurred_at=occurred.isoformat(),
                payload=payload,
            )
        )

    return dict(
        spec=spec,
        merchants=merchants,
        channels=channels,
        accounts=accounts,
        fee_rules=fee_rules,
        fx_rates=fx_rates,
        settlement_batches=batches,
        reconcile_runs=runs,
        payment_orders=orders,
        transfers=transfers,
        ledger_entries=ledger_entries,
        reconcile_lines=lines,
        disputes=disputes,
        reports=reports,
        approvals=approvals,
        audit_events=audit_events,
        index=dict(lines_by_order=lines_by_order),
    )


def _chunked(items: list[Any], *, chunk_size: int) -> Iterable[list[Any]]:
    if chunk_size <= 0:
        yield items
        return
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def _http_batch_direct_write(
    *,
    daemon_url: str,
    instance_id: str,
    payload: BatchDirectWriteInput,
    dry_run: bool,
) -> dict[str, Any]:
    url = daemon_url.rstrip("/") + f"/api/v1/{instance_id}/direct-writes/batch"
    resp = httpx.post(
        url,
        json={"payload": asdict(payload), "dry_run": dry_run},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected daemon response shape for batch_direct_write")
    return data


def _build_entities_from_dataset(dataset: dict[str, Any], *, thread_id: str, state: dict[str, Any]) -> list[EntityWriteInput]:
    now = _utc_now_iso()
    values = state.get("values") or {}
    title = values.get("title") if isinstance(values, dict) else None
    metadata = {
        "checkpoint_id": state.get("checkpoint_id"),
        "parent_checkpoint_id": state.get("parent_checkpoint_id"),
        "tasks": state.get("tasks", []),
        "next": state.get("next", []),
        "raw_state": state,
        "dataset_spec": dataset.get("spec"),
    }
    entities: list[EntityWriteInput] = [
        EntityWriteInput(
            entity_type="DeerflowThread",
            entity_id=thread_id,
            properties={
                "thread_id": thread_id,
                "title": str(title) if title is not None else "",
                "metadata": metadata,
                "created_at": now,
                "updated_at": now,
            },
        )
    ]

    for index, message in enumerate(_extract_messages(state)):
        message_id = str(message.get("id") or f"{thread_id}:auto:{index}")
        role = message.get("role") or message.get("type") or "unknown"
        content = message.get("content")
        entities.append(
            EntityWriteInput(
                entity_type="DeerflowMessage",
                entity_id=message_id,
                properties={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "role": str(role),
                    "content": str(content) if content is not None else "",
                    "position": index,
                    "raw": message,
                },
            )
        )

    allowed: dict[str, set[str]] = {
        "Merchant": {
            "merchant_id",
            "name",
            "country",
            "industry",
            "risk_level",
            "active",
            "created_at",
        },
        "Channel": {"channel_id", "name", "channel_type", "country", "settlement_cycle"},
        "Account": {"account_id", "merchant_id", "currency", "account_type", "bank_name", "opened_at"},
        "FeeRule": {
            "fee_rule_id",
            "name",
            "rule_type",
            "rate",
            "fixed_fee",
            "currency",
            "effective_from",
            "effective_to",
        },
        "FXRate": {"fx_rate_id", "pair", "rate", "as_of", "provider"},
        "SettlementBatch": {
            "settlement_batch_id",
            "channel_id",
            "cycle_date",
            "currency",
            "total_amount",
            "status",
            "generated_at",
            "paid_at",
        },
        "ReconcileRun": {
            "reconcile_run_id",
            "batch_id",
            "run_type",
            "started_at",
            "completed_at",
            "status",
        },
        "PaymentOrder": {
            "order_id",
            "merchant_id",
            "channel_id",
            "amount",
            "currency",
            "status",
            "created_at",
            "settled_at",
            "external_ref",
        },
        "Transfer": {"transfer_id", "order_id", "direction", "amount", "currency", "executed_at", "status"},
        "LedgerEntry": {
            "ledger_entry_id",
            "account_id",
            "order_id",
            "entry_type",
            "amount",
            "currency",
            "posted_at",
            "batch_id",
        },
        "ReconcileLine": {
            "reconcile_line_id",
            "run_id",
            "order_id",
            "expected_amount",
            "actual_amount",
            "diff_amount",
            "diff_reason",
            "severity",
            "resolved",
        },
        "Dispute": {
            "dispute_id",
            "order_id",
            "dispute_type",
            "opened_at",
            "closed_at",
            "status",
            "amount",
            "currency",
            "reason_code",
        },
        "Report": {"report_id", "batch_id", "report_type", "generated_at", "uri"},
        "Approval": {"approval_id", "report_id", "approver", "decision", "decided_at", "comment"},
        "AuditEvent": {"audit_event_id", "event_type", "actor", "occurred_at", "payload"},
    }

    def add_many(entity_type: str, items: list[dict[str, Any]], id_key: str) -> None:
        for item in items:
            entity_id = str(item[id_key])
            allowed_keys = allowed.get(entity_type)
            properties = (
                {k: v for k, v in item.items() if k in allowed_keys}
                if allowed_keys is not None
                else item
            )
            entities.append(
                EntityWriteInput(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    properties=properties,
                )
            )

    add_many("Merchant", dataset.get("merchants") or [], "merchant_id")
    add_many("Channel", dataset.get("channels") or [], "channel_id")
    add_many("Account", dataset.get("accounts") or [], "account_id")
    add_many("FeeRule", dataset.get("fee_rules") or [], "fee_rule_id")
    add_many("FXRate", dataset.get("fx_rates") or [], "fx_rate_id")
    add_many("SettlementBatch", dataset.get("settlement_batches") or [], "settlement_batch_id")
    add_many("ReconcileRun", dataset.get("reconcile_runs") or [], "reconcile_run_id")
    add_many("PaymentOrder", dataset.get("payment_orders") or [], "order_id")
    add_many("Transfer", dataset.get("transfers") or [], "transfer_id")
    add_many("LedgerEntry", dataset.get("ledger_entries") or [], "ledger_entry_id")
    add_many("ReconcileLine", dataset.get("reconcile_lines") or [], "reconcile_line_id")
    add_many("Dispute", dataset.get("disputes") or [], "dispute_id")
    add_many("Report", dataset.get("reports") or [], "report_id")
    add_many("Approval", dataset.get("approvals") or [], "approval_id")
    add_many("AuditEvent", dataset.get("audit_events") or [], "audit_event_id")
    return entities


def _build_relationships_from_dataset(
    dataset: dict[str, Any],
    *,
    thread_id: str,
    state: dict[str, Any],
) -> list[BatchRelationshipWriteInput]:
    relationships: list[BatchRelationshipWriteInput] = []
    for index, message in enumerate(_extract_messages(state)):
        message_id = str(message.get("id") or f"{thread_id}:auto:{index}")
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="thread_has_message",
                from_type="DeerflowThread",
                from_id=thread_id,
                to_type="DeerflowMessage",
                to_id=message_id,
                properties={"position": index},
                shared_evidence_keys=[],
            )
        )

    for batch in dataset.get("settlement_batches") or []:
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="thread_produced_batch",
                from_type="DeerflowThread",
                from_id=thread_id,
                to_type="SettlementBatch",
                to_id=str(batch["settlement_batch_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    for merchant in dataset.get("merchants") or []:
        merchant_id = str(merchant["merchant_id"])
        for channel_id in set(
            o["channel_id"]
            for o in (dataset.get("payment_orders") or [])
            if o.get("merchant_id") == merchant_id
        ):
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="merchant_uses_channel",
                    from_type="Merchant",
                    from_id=merchant_id,
                    to_type="Channel",
                    to_id=str(channel_id),
                    properties={},
                    shared_evidence_keys=[],
                )
            )

    for acc in dataset.get("accounts") or []:
        merchant_id = str(acc.get("merchant_id") or "")
        if not merchant_id:
            continue
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="merchant_owns_account",
                from_type="Merchant",
                from_id=merchant_id,
                to_type="Account",
                to_id=str(acc["account_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    channels = {c["channel_id"]: c for c in (dataset.get("channels") or [])}
    for acc in dataset.get("accounts") or []:
        if str(acc.get("account_type")) != "clearing":
            continue
        account_id = str(acc.get("account_id") or "")
        prefix = "a_clearing_"
        if not account_id.startswith(prefix):
            continue
        rest = account_id[len(prefix) :]
        channel_id, _, _ = rest.partition("_")
        if not channel_id or channel_id not in channels:
            continue
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="channel_settles_to_account",
                from_type="Channel",
                from_id=str(channel_id),
                to_type="Account",
                to_id=account_id,
                properties={},
                shared_evidence_keys=[],
            )
        )

    fee_rule_by_id = {fr["fee_rule_id"]: fr for fr in (dataset.get("fee_rules") or [])}
    for order in dataset.get("payment_orders") or []:
        order_id = str(order["order_id"])
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="order_for_merchant",
                from_type="PaymentOrder",
                from_id=order_id,
                to_type="Merchant",
                to_id=str(order["merchant_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="order_via_channel",
                from_type="PaymentOrder",
                from_id=order_id,
                to_type="Channel",
                to_id=str(order["channel_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )
        fee_rule_id = str(order.get("fee_rule_id") or "")
        if fee_rule_id and fee_rule_id in fee_rule_by_id:
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="order_applied_fee_rule",
                    from_type="PaymentOrder",
                    from_id=order_id,
                    to_type="FeeRule",
                    to_id=fee_rule_id,
                    properties={},
                    shared_evidence_keys=[],
                )
            )

    transfer_by_order = {t["order_id"]: t for t in (dataset.get("transfers") or [])}
    for order_id, transfer in transfer_by_order.items():
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="order_paid_by_transfer",
                from_type="PaymentOrder",
                from_id=str(order_id),
                to_type="Transfer",
                to_id=str(transfer["transfer_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )
        fx_rate_id = str(transfer.get("fx_rate_id") or "")
        if fx_rate_id:
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="transfer_used_fx_rate",
                    from_type="Transfer",
                    from_id=str(transfer["transfer_id"]),
                    to_type="FXRate",
                    to_id=fx_rate_id,
                    properties={},
                    shared_evidence_keys=[],
                )
            )

    for entry in dataset.get("ledger_entries") or []:
        ledger_id = str(entry["ledger_entry_id"])
        order_id = str(entry["order_id"])
        transfer_id = str(entry.get("transfer_id") or "")
        if transfer_id:
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="transfer_posts_ledger_entry",
                    from_type="Transfer",
                    from_id=transfer_id,
                    to_type="LedgerEntry",
                    to_id=ledger_id,
                    properties={},
                    shared_evidence_keys=[],
                )
            )
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="ledger_entry_for_order",
                from_type="LedgerEntry",
                from_id=ledger_id,
                to_type="PaymentOrder",
                to_id=order_id,
                properties={},
                shared_evidence_keys=[],
            )
        )
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="ledger_entry_to_account",
                from_type="LedgerEntry",
                from_id=ledger_id,
                to_type="Account",
                to_id=str(entry["account_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )
        batch_id = str(entry.get("batch_id") or "")
        if batch_id:
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="ledger_entry_in_batch",
                    from_type="LedgerEntry",
                    from_id=ledger_id,
                    to_type="SettlementBatch",
                    to_id=batch_id,
                    properties={},
                    shared_evidence_keys=[],
                )
            )

    for batch in dataset.get("settlement_batches") or []:
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="batch_for_channel",
                from_type="SettlementBatch",
                from_id=str(batch["settlement_batch_id"]),
                to_type="Channel",
                to_id=str(batch["channel_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    for run in dataset.get("reconcile_runs") or []:
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="batch_reconciled_by_run",
                from_type="SettlementBatch",
                from_id=str(run["batch_id"]),
                to_type="ReconcileRun",
                to_id=str(run["reconcile_run_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    for line in dataset.get("reconcile_lines") or []:
        line_id = str(line["reconcile_line_id"])
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="run_has_line",
                from_type="ReconcileRun",
                from_id=str(line["run_id"]),
                to_type="ReconcileLine",
                to_id=line_id,
                properties={},
                shared_evidence_keys=[],
            )
        )
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="line_for_order",
                from_type="ReconcileLine",
                from_id=line_id,
                to_type="PaymentOrder",
                to_id=str(line["order_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    dispute_by_order: dict[str, str] = {}
    for dispute in dataset.get("disputes") or []:
        dispute_id = str(dispute["dispute_id"])
        order_id = str(dispute["order_id"])
        dispute_by_order[order_id] = dispute_id
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="dispute_on_order",
                from_type="Dispute",
                from_id=dispute_id,
                to_type="PaymentOrder",
                to_id=order_id,
                properties={},
                shared_evidence_keys=[],
            )
        )

    for line in dataset.get("reconcile_lines") or []:
        order_id = str(line["order_id"])
        dispute_id = dispute_by_order.get(order_id)
        if not dispute_id:
            continue
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="line_flags_dispute",
                from_type="ReconcileLine",
                from_id=str(line["reconcile_line_id"]),
                to_type="Dispute",
                to_id=dispute_id,
                properties={},
                shared_evidence_keys=[],
            )
        )

    for report in dataset.get("reports") or []:
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="report_for_batch",
                from_type="Report",
                from_id=str(report["report_id"]),
                to_type="SettlementBatch",
                to_id=str(report["batch_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    for approval in dataset.get("approvals") or []:
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="approval_for_report",
                from_type="Approval",
                from_id=str(approval["approval_id"]),
                to_type="Report",
                to_id=str(approval["report_id"]),
                properties={},
                shared_evidence_keys=[],
            )
        )

    for audit in dataset.get("audit_events") or []:
        payload = audit.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        kind = payload.get("target_kind")
        if kind == "order" and payload.get("order_id"):
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="audit_on_order",
                    from_type="AuditEvent",
                    from_id=str(audit["audit_event_id"]),
                    to_type="PaymentOrder",
                    to_id=str(payload["order_id"]),
                    properties={},
                    shared_evidence_keys=[],
                )
            )
        elif kind == "batch" and payload.get("settlement_batch_id"):
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="audit_on_batch",
                    from_type="AuditEvent",
                    from_id=str(audit["audit_event_id"]),
                    to_type="SettlementBatch",
                    to_id=str(payload["settlement_batch_id"]),
                    properties={},
                    shared_evidence_keys=[],
                )
            )
        elif kind == "dispute" and payload.get("dispute_id"):
            relationships.append(
                BatchRelationshipWriteInput(
                    relationship_type="audit_on_dispute",
                    from_type="AuditEvent",
                    from_id=str(audit["audit_event_id"]),
                    to_type="Dispute",
                    to_id=str(payload["dispute_id"]),
                    properties={},
                    shared_evidence_keys=[],
                )
            )

    return relationships


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deerflow-base-url", default="http://localhost:2026")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--seed-thread", action="store_true")
    parser.add_argument("--scale", default="large")
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--daemon-url", default=None)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument(
        "--instance-root",
        default=str(Path(".poc/cruxible_server_state/instances/inst_settlement_poc").resolve()),
    )
    parser.add_argument(
        "--config-path",
        default=str(Path(".poc/settlement/settlement_poc_config.yaml").resolve()),
    )
    parser.add_argument("--reset-instance", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--entity-batch-size", type=int, default=1200)
    parser.add_argument("--relationship-batch-size", type=int, default=800)
    parser.add_argument(
        "--output-dir",
        default=str(Path(".poc/settlement/out").resolve()),
    )
    args = parser.parse_args(argv)

    _wait_for_http_ok(args.deerflow_base_url.rstrip("/") + "/health", timeout_s=120.0)

    if args.thread_id:
        thread_id = str(args.thread_id)
        state = _get_json(args.deerflow_base_url, f"/api/threads/{thread_id}/state")
    elif args.seed_thread:
        spec = _build_default_spec(scale=str(args.scale), seed=int(args.seed))
        thread_id, state = _seed_deerflow_thread(args.deerflow_base_url, spec=spec)
    else:
        raise RuntimeError("Provide --thread-id or set --seed-thread to create a synthetic DeerFlow thread.")

    poc_input = _extract_poc_input_from_state(state)
    spec = poc_input.get("spec")
    if args.progress:
        print(
            json.dumps(
                {
                    "phase": "start_generate",
                    "thread_id": thread_id,
                    "spec": spec if isinstance(spec, dict) else poc_input,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    if isinstance(spec, dict):
        dataset = _generate_dataset(spec)
    else:
        dataset = _generate_dataset(poc_input)
    if args.progress:
        summary_counts = {
            key: len(value) if isinstance(value, list) else None
            for key, value in dataset.items()
            if key
            in {
                "merchants",
                "channels",
                "accounts",
                "fee_rules",
                "fx_rates",
                "settlement_batches",
                "reconcile_runs",
                "payment_orders",
                "transfers",
                "ledger_entries",
                "reconcile_lines",
                "disputes",
                "reports",
                "approvals",
                "audit_events",
            }
        }
        print(
            json.dumps(
                {
                    "phase": "generated",
                    "thread_id": thread_id,
                    "counts": summary_counts,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / f"dataset_{thread_id}.json"
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    entities = _build_entities_from_dataset(dataset, thread_id=thread_id, state=state)
    relationships = _build_relationships_from_dataset(dataset, thread_id=thread_id, state=state)

    receipts: list[dict[str, Any]] = []
    daemon_url = str(args.daemon_url) if args.daemon_url else None
    daemon_instance_id = str(args.instance_id) if args.instance_id else None
    if daemon_url and not daemon_instance_id:
        raise RuntimeError("--daemon-url requires --instance-id")
    if daemon_url and args.reset_instance:
        raise RuntimeError("--reset-instance is not supported when writing via daemon. Use a fresh instance root_dir.")

    if args.dry_run:
        payload = BatchDirectWriteInput(entities=entities, relationships=relationships, shared_evidence={})
        if daemon_url:
            receipts.append(
                _http_batch_direct_write(
                    daemon_url=daemon_url,
                    instance_id=daemon_instance_id or "",
                    payload=payload,
                    dry_run=True,
                )
            )
        else:
            instance_root = Path(args.instance_root).expanduser().resolve()
            config_path = Path(args.config_path).expanduser().resolve()
            if not config_path.exists():
                raise RuntimeError(f"config not found: {config_path}")
            _ensure_clean_instance_root(instance_root, reset=args.reset_instance)
            instance = _init_cruxible_instance(instance_root=instance_root, config_path=config_path)
            result = service_batch_direct_write(
                instance,
                payload,
                dry_run=True,
                source="poc_deerflow_settlement",
                source_ref=f"deerflow://{thread_id}",
            )
            receipts.append(asdict(result))
    else:
        entity_total = len(entities)
        rel_total = len(relationships)
        if args.progress:
            print(
                json.dumps(
                    {
                        "phase": "start_write",
                        "thread_id": thread_id,
                        "entities": entity_total,
                        "relationships": rel_total,
                        "dataset_path": str(dataset_path),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        entity_written = 0
        rel_written = 0
        if daemon_url:
            for chunk in _chunked(entities, chunk_size=int(args.entity_batch_size)):
                payload = BatchDirectWriteInput(entities=chunk, relationships=[], shared_evidence={})
                result = _http_batch_direct_write(
                    daemon_url=daemon_url,
                    instance_id=daemon_instance_id or "",
                    payload=payload,
                    dry_run=False,
                )
                receipts.append(result)
                entity_written += len(chunk)
                if args.progress:
                    print(
                        json.dumps(
                            {
                                "phase": "entities",
                                "written": entity_written,
                                "total": entity_total,
                                "receipt_id": result.get("receipt_id"),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

            for chunk in _chunked(relationships, chunk_size=int(args.relationship_batch_size)):
                payload = BatchDirectWriteInput(entities=[], relationships=chunk, shared_evidence={})
                result = _http_batch_direct_write(
                    daemon_url=daemon_url,
                    instance_id=daemon_instance_id or "",
                    payload=payload,
                    dry_run=False,
                )
                receipts.append(result)
                rel_written += len(chunk)
                if args.progress:
                    print(
                        json.dumps(
                            {
                                "phase": "relationships",
                                "written": rel_written,
                                "total": rel_total,
                                "receipt_id": result.get("receipt_id"),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

            stats_url = daemon_url.rstrip("/") + f"/api/v1/{daemon_instance_id}/stats"
            stats_resp = httpx.get(stats_url, timeout=60.0)
            stats_resp.raise_for_status()
            stats = stats_resp.json()
            summary = {
                "deerflow_thread_id": thread_id,
                "dataset_path": str(dataset_path),
                "daemon_url": daemon_url,
                "instance_id": daemon_instance_id,
                "dry_run": False,
                "stats": stats,
                "write_receipts": receipts,
            }
        else:
            instance_root = Path(args.instance_root).expanduser().resolve()
            config_path = Path(args.config_path).expanduser().resolve()
            if not config_path.exists():
                raise RuntimeError(f"config not found: {config_path}")
            _ensure_clean_instance_root(instance_root, reset=args.reset_instance)
            instance = _init_cruxible_instance(instance_root=instance_root, config_path=config_path)

            for chunk in _chunked(entities, chunk_size=int(args.entity_batch_size)):
                payload = BatchDirectWriteInput(entities=chunk, relationships=[], shared_evidence={})
                result = service_batch_direct_write(
                    instance,
                    payload,
                    dry_run=False,
                    source="poc_deerflow_settlement",
                    source_ref=f"deerflow://{thread_id}",
                )
                receipts.append(asdict(result))
                entity_written += len(chunk)
                if args.progress:
                    print(
                        json.dumps(
                            {
                                "phase": "entities",
                                "written": entity_written,
                                "total": entity_total,
                                "receipt_id": result.receipt_id,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

            for chunk in _chunked(relationships, chunk_size=int(args.relationship_batch_size)):
                payload = BatchDirectWriteInput(entities=[], relationships=chunk, shared_evidence={})
                result = service_batch_direct_write(
                    instance,
                    payload,
                    dry_run=False,
                    source="poc_deerflow_settlement",
                    source_ref=f"deerflow://{thread_id}",
                )
                receipts.append(asdict(result))
                rel_written += len(chunk)
                if args.progress:
                    print(
                        json.dumps(
                            {
                                "phase": "relationships",
                                "written": rel_written,
                                "total": rel_total,
                                "receipt_id": result.receipt_id,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

            graph = instance.load_graph()
            summary = {
                "deerflow_thread_id": thread_id,
                "dataset_path": str(dataset_path),
                "cruxible_instance_root": str(instance_root),
                "dry_run": False,
                "entities_total": graph.entity_count(),
                "relationships_total": graph.edge_count(),
                "counts": {
                    "Merchants": graph.entity_count("Merchant"),
                    "Channels": graph.entity_count("Channel"),
                    "Accounts": graph.entity_count("Account"),
                    "FeeRules": graph.entity_count("FeeRule"),
                    "FXRates": graph.entity_count("FXRate"),
                    "Batches": graph.entity_count("SettlementBatch"),
                    "Runs": graph.entity_count("ReconcileRun"),
                    "Orders": graph.entity_count("PaymentOrder"),
                    "Transfers": graph.entity_count("Transfer"),
                    "LedgerEntries": graph.entity_count("LedgerEntry"),
                    "ReconcileLines": graph.entity_count("ReconcileLine"),
                    "Disputes": graph.entity_count("Dispute"),
                    "Reports": graph.entity_count("Report"),
                    "Approvals": graph.entity_count("Approval"),
                    "AuditEvents": graph.entity_count("AuditEvent"),
                },
                "write_receipts": receipts,
            }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
