#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://raw.githubusercontent.com/Jessica-Zhangyj/dlquant/main/data"
DATES = ["20240206", "20240924", "20250409", "20260324"]
DATE_LABELS = ["2024-02-06", "2024-09-24", "2025-04-09", "2026-03-24"]
OUTDIR = Path("results/four_lows")


def download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 four-lows-screen"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8-sig")


def load_daily(date: str) -> dict[str, float]:
    text = download_text(f"{BASE}/daily/{date}.csv")
    reader = csv.DictReader(io.StringIO(text))
    out: dict[str, float] = {}
    for row in reader:
        code = (row.get("ts_code") or "").strip()
        low_s = (row.get("low") or "").strip()
        if not code or not low_s:
            continue
        try:
            low = float(low_s)
        except ValueError:
            continue
        if low > 0:
            out[code] = low
    return out


def load_basic() -> dict[str, dict[str, str]]:
    text = download_text(f"{BASE}/basic.csv")
    reader = csv.DictReader(io.StringIO(text))
    return {(r.get("ts_code") or "").strip(): r for r in reader if (r.get("ts_code") or "").strip()}


def exchange(code: str) -> str:
    suffix = code.rsplit(".", 1)[-1]
    return {"SH": "上交所", "SZ": "深交所", "BJ": "北交所"}.get(suffix, suffix)


def pct(a: float, b: float) -> float:
    return b / a - 1.0 if a else 0.0


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    daily = {d: load_daily(d) for d in DATES}
    basic = load_basic()
    common = set.intersection(*(set(daily[d]) for d in DATES))

    rows = []
    for code in sorted(common):
        lows = [daily[d][code] for d in DATES]
        if not (lows[0] < lows[1] < lows[2] < lows[3]):
            continue
        info = basic.get(code, {})
        name = (info.get("name") or "").strip()
        rows.append({
            "股票代码": code.split(".")[0],
            "完整代码": code,
            "股票简称": name,
            "交易所": exchange(code),
            "板块": (info.get("market") or "").strip(),
            "行业": (info.get("industry") or "").strip(),
            "地区": (info.get("area") or "").strip(),
            "2024-02-06最低价": lows[0],
            "2024-09-24最低价": lows[1],
            "2025-04-09最低价": lows[2],
            "2026-03-24最低价": lows[3],
            "第一段抬升": pct(lows[0], lows[1]),
            "第二段抬升": pct(lows[1], lows[2]),
            "第三段抬升": pct(lows[2], lows[3]),
            "累计抬升": pct(lows[0], lows[3]),
            "是否ST": "是" if "ST" in name.upper() else "否",
        })

    rows.sort(key=lambda r: (-r["累计抬升"], r["完整代码"]))
    fields = list(rows[0].keys()) if rows else []

    csv_path = OUTDIR / "A股四低点逐级抬高_完整名单.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k in ["第一段抬升", "第二段抬升", "第三段抬升", "累计抬升"]:
                out[k] = f"{r[k]:.2%}"
            w.writerow(out)

    json_path = OUTDIR / "A股四低点逐级抬高_完整名单.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    exchange_counts = Counter(r["交易所"] for r in rows)
    industry_counts = Counter((r["行业"] or "未分类") for r in rows)
    st_count = sum(1 for r in rows if r["是否ST"] == "是")
    summary = [
        "# A股四低点逐级抬高筛选结果",
        "",
        f"- 筛选规则：{DATE_LABELS[0]} low < {DATE_LABELS[1]} low < {DATE_LABELS[2]} low < {DATE_LABELS[3]} low",
        "- 价格口径：日线原始价（不复权）",
        f"- 四日均有行情股票数：{len(common)}",
        f"- 符合条件股票数：{len(rows)}",
        f"- ST数量：{st_count}",
        "",
        "## 交易所分布",
    ]
    summary += [f"- {k}: {v}" for k, v in exchange_counts.most_common()]
    summary += ["", "## 行业前20"]
    summary += [f"- {k}: {v}" for k, v in industry_counts.most_common(20)]
    summary += ["", "## 完整公司与代码"]
    summary += [f"- {r['股票代码']} {r['股票简称']}" for r in sorted(rows, key=lambda x: x["股票代码"])]
    (OUTDIR / "筛选结果摘要.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(json.dumps({
        "common_count": len(common),
        "matched_count": len(rows),
        "st_count": st_count,
        "exchange_counts": dict(exchange_counts),
        "csv": str(csv_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
