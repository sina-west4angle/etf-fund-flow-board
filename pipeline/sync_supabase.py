#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把看板数据同步进 Supabase (我们自己的 Excel 底座)。

数据流: site/data.js (合计序列, 与页面展示同源) + pipeline/cache (逐只日线/份额/净值)
  -> etf_daily_total   一行一天: total_amount / total_netflow / index_close / is_support
  -> etf_daily_detail  一行一天一只: name / close / amount / shares / netflow

口径与 build_data.py 完全一致 (净流入 = Δ份额 x 当日单位净值 / 1e8, 亿元; 金额亿元)。
写入走数据面 PostgREST upsert (service_role, 经 custom.supabase 保险库 surrogate 通道,
本脚本不出现任何凭证值)。建表 DDL 不归本脚本: 在 supabase/migrations/, 由 Management
API (sbp_) 或 Actions 运行。

用法:
  python3 sync_supabase.py            # 表在 -> upsert 并读回计数验证; 表不在 -> 落 supabase_rows.json
  python3 sync_supabase.py --dry-run  # 只生成 supabase_rows.json, 不发请求
"""
import argparse, csv, io, json, os, sys, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE_DIR, "..")
CACHE = os.path.join(BASE_DIR, "cache")
HOST = "ocqfhempmbxmriecijrg.supabase.co"
CREDENTIAL_NAME = "custom.supabase"
BATCH = 1000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused")


def rest(method, path, body=None, prefer=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request("https://" + HOST + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    add_surrogate_to_request(req, CREDENTIAL_NAME, allowed_hosts=[HOST])
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=60) as resp:
            try:
                return resp.status, read_json_response(resp)
            except Exception:
                return resp.status, ""
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        return e.code, detail


def load_site_data():
    with open(os.path.join(ROOT, "site", "data.js"), encoding="utf-8") as f:
        text = f.read()
    start = text.index("{")
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    return data


def build_total_rows(data):
    daily = data["daily"]
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for i, d in enumerate(daily["dates"]):
        nf = daily["netflow"][i]
        rows.append({
            "trade_date": d,
            "total_amount": daily["amount"][i],
            "total_netflow": nf,
            "index_close": daily["idx"][i],
            "is_support": bool(nf is not None and nf > 100),
            "updated_at": now,
        })
    return rows


def _norm_date(d):
    # 沪市份额缓存用 YYYYMMDD, 其余用 YYYY-MM-DD, 统一成后者
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _read_csv_map(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[_norm_date(r["date"])] = r
    return out


def build_detail_rows(data):
    names = {b["code"]: b["name"] for b in data["meta"]["basket"]}
    dates = data["daily"]["dates"]
    # 份额: 沪市宽表 csv + 深市 'date|code' json + 深市快照 csv (兜底)
    sse = _read_csv_map(os.path.join(CACHE, "shares_sse.csv"))
    szse = {}
    szse_path = os.path.join(CACHE, "szse_all.json")
    if os.path.exists(szse_path):
        with open(szse_path, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                d, code = k.split("|")
                szse.setdefault(d, {})[code] = v
    snap = _read_csv_map(os.path.join(CACHE, "shares_szse_snapshot.csv"))
    for d, r in snap.items():
        for code, v in r.items():
            if code != "date" and v not in ("", None):
                szse.setdefault(d, {})[code] = float(v)

    def share_of(code, d):
        if code in (sse.get(d) or {}):
            v = sse[d][code]
            return float(v) if v not in ("", None) else None
        v = (szse.get(d) or {}).get(code)
        return float(v) if v is not None else None

    rows = []
    for code in names:
        daily = {}
        dpath = os.path.join(CACHE, f"daily_{code}.csv")
        if os.path.exists(dpath):
            with open(dpath, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    daily[r["date"]] = r
        nav = {}
        npath = os.path.join(CACHE, f"nav_{code}.json")
        if os.path.exists(npath):
            with open(npath, encoding="utf-8") as f:
                nav = json.load(f)
        prev_date = None
        for d in dates:
            r = daily.get(d)
            s1 = share_of(code, d)
            nf = None
            if prev_date is not None:
                s0 = share_of(code, prev_date)
                nv = nav.get(d)
                if s1 is not None and s0 is not None and nv:
                    nf = round((s1 - s0) * float(nv) / 1e8, 4)
            rows.append({
                "trade_date": d,
                "code": code,
                "name": names[code],
                "close": float(r["close"]) if r else None,
                "amount": round(float(r["amount"]) / 1e8, 4) if r else None,
                "shares": s1,
                "netflow": nf,
            })
            prev_date = d
    return rows


def table_exists(table):
    status, out = rest("GET", f"/rest/v1/{table}?select=trade_date&limit=1")
    return status == 200


def upsert(table, rows):
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        status, out = rest("POST", f"/rest/v1/{table}", body=chunk,
                           prefer="resolution=merge-duplicates")
        if status >= 300:
            raise RuntimeError(f"upsert {table} batch@{i} HTTP {status}: {str(out)[:300]}")
    print(f"  upsert {table}: {len(rows)} rows ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    data = load_site_data()
    totals = build_total_rows(data)
    details = build_detail_rows(data)
    print(f"rows: etf_daily_total={len(totals)} etf_daily_detail={len(details)}")
    out_path = os.path.join(BASE_DIR, "supabase_rows.json")
    if args.dry_run or not (table_exists("etf_daily_total") and table_exists("etf_daily_detail")):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"etf_daily_total": totals, "etf_daily_detail": details},
                      f, ensure_ascii=False)
        print(f"tables not ready (or dry-run): rows dumped to {out_path}")
        print("建表后重跑本脚本即可一键导入 (DDL: supabase/migrations/0001_create_etf_tables.sql)")
        return 0
    upsert("etf_daily_total", totals)
    upsert("etf_daily_detail", details)
    # 验证: PostgREST 单次最多返 1000 行, 全表计数不可靠 -> 抽查最新日
    latest = totals[-1]["trade_date"]
    status, out = rest("GET", f"/rest/v1/etf_daily_total?trade_date=eq.{latest}&select=*")
    print(f"  verify etf_daily_total latest {latest}: HTTP {status}, {out}")
    status, out = rest("GET", f"/rest/v1/etf_daily_detail?trade_date=eq.{latest}&select=code")
    print(f"  verify etf_daily_detail latest {latest}: HTTP {status}, "
          f"{len(out) if isinstance(out, list) else '?'} codes (expect 20)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
