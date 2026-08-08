from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--settlement-batch-id", required=True)
    args = parser.parse_args()

    dataset_path = Path(args.dataset_path)
    batch_id = args.settlement_batch_id
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    orders = {o["order_id"]: o for o in (data.get("payment_orders") or [])}
    ledger_by_batch: dict[str, list[dict]] = defaultdict(list)
    for entry in data.get("ledger_entries") or []:
        ledger_by_batch[str(entry["batch_id"])].append(entry)

    order_ids = sorted({str(le["order_id"]) for le in ledger_by_batch.get(batch_id, [])})
    run_id = f"r_{batch_id}"
    lines = [l for l in (data.get("reconcile_lines") or []) if str(l.get("run_id")) == run_id]
    line_by_order = {str(l["order_id"]): l for l in lines}

    stats: dict[str, dict[str, float]] = defaultdict(lambda: {"orders": 0, "gmv": 0.0, "diff_lines": 0})
    for order_id in order_ids:
        order = orders.get(order_id)
        if not order:
            continue
        merchant_id = str(order.get("merchant_id") or "")
        if not merchant_id:
            continue
        stats[merchant_id]["orders"] += 1
        stats[merchant_id]["gmv"] += float(order.get("amount") or 0.0)
        line = line_by_order.get(order_id)
        if line is not None and abs(float(line.get("diff_amount") or 0.0)) > 0.05:
            stats[merchant_id]["diff_lines"] += 1

    rows = [
        {
            "merchant_id": merchant_id,
            "orders": int(values["orders"]),
            "gmv": round(float(values["gmv"]), 2),
            "diff_lines": int(values["diff_lines"]),
        }
        for merchant_id, values in stats.items()
    ]
    rows.sort(key=lambda r: (r["diff_lines"], r["orders"], r["gmv"]), reverse=True)

    print(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "settlement_batch_id": batch_id,
                "orders_in_batch": len(order_ids),
                "merchants_in_batch": len(rows),
                "top10": rows[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

