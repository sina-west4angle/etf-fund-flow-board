#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘中分钟取数（周一双源对比用）：新浪1分钟线拉20只ETF+上证，
聚合每分钟合计成交额与上证点位，落 JSON 到 live_out/。
用法：~/workspace/muse-free-market-data/.venv/bin/python fetch_live.py
"""
import json, os, time, warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "live_out")
BASKET = ["510310","588000","159915","510300","563360","159352","512100","159338",
          "510500","159949","588080","510050","510210","159845","159952","159361",
          "512050","159633","560010","159919"]
def sym(c): return ("sh" if c[0] in "56" else "sz") + c

def main():
    import akshare as ak
    per_code, idx_rows = {}, []
    for c in BASKET:
        df = ak.stock_zh_a_minute(symbol=sym(c), period="1", adjust="")
        per_code[c] = [[str(r["day"]), float(r["close"]), float(r["amount"])] for _, r in df.iterrows()]
        time.sleep(0.2)
    df = ak.stock_zh_a_minute(symbol="sh000001", period="1", adjust="")
    idx_rows = [[str(r["day"]), float(r["close"])] for _, r in df.iterrows()]
    days = sorted(set(r[0][:10] for r in idx_rows))
    latest = days[-1]
    slots, totals, closes = [], [], []
    idx_map = {r[0][11:16]: r[1] for r in idx_rows if r[0][:10] == latest}
    code_today = {}
    for c in BASKET:
        m = {r[0][11:16]: r[2] for r in per_code[c] if r[0][:10] == latest}
        code_today[c] = m
    for s in sorted(idx_map.keys()):
        slots.append(s)
        totals.append(round(sum(code_today[c].get(s, 0.0) for c in BASKET) / 1e8, 4))
        closes.append(idx_map[s])
    per_etf = {c: round(sum(code_today[c].values()) / 1e8, 2) for c in BASKET}
    snap = {"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "date": latest,
            "slots": slots, "total_amount_yi_per_min": totals, "index_close": closes,
            "cum_amount_yi": round(sum(totals), 2), "per_etf_amount_yi": per_etf}
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, "live_" + time.strftime("%Y%m%d_%H%M%S") + ".json")
    with open(fn, "w", encoding="utf-8") as f: json.dump(snap, f, ensure_ascii=False)
    print(json.dumps({"file": fn, "date": latest, "minutes": len(slots),
                      "cum_amount_yi": snap["cum_amount_yi"],
                      "last_index": closes[-1] if closes else None}, ensure_ascii=False))

if __name__ == "__main__":
    main()
