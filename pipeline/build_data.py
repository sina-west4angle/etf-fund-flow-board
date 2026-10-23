#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
20只重点ETF资金观测看板 · 自有数据管线（clean-room）

数据源（全部公开免费、无 token）：
  日线成交额/收盘 : 新浪 via akshare fund_etf_hist_sina（字段含真实成交额）
  上证日线        : 新浪 via akshare stock_zh_index_daily
  1分钟线         : 新浪 via akshare stock_zh_a_minute（每分钟含成交额）
  沪市份额        : 上交所官方 via akshare fund_etf_scale_sse（按日）
  深市份额        : 深交所官方报表 xlsx 直调（CATALOGID=scsj_fund_jjgm，区间查询）
  单位净值        : 东方财富基金 api.fund.eastmoney.com/f10/lsjz

口径：
  净流入_T(亿元) = (份额_T - 份额_{T-1}) x 单位净值_T / 1e8 ，逐只汇总
  托底日         = 20只合计净流入 > 100 亿元
  成交额         = 20只二级市场日成交额合计（新浪日K amount 字段）

用法：
  python build_data.py --days 30    # 小样本：份额只回溯近30个交易日
  python build_data.py              # 全量（份额按日回溯，带缓存断点续跑）
"""
import argparse, io, json, os, sys, time, warnings
warnings.filterwarnings("ignore")

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
SITE = os.path.join(BASE, "..", "site")
PKG_DATA = os.path.join(BASE, "..", "reference", "data")
START = "2023-10-09"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

BASKET = ["510310","588000","159915","510300","563360","159352","512100","159338",
          "510500","159949","588080","510050","510210","159845","159952","159361",
          "512050","159633","560010","159919"]
def mkt(code): return "sh" if code[0] in "56" else "sz"
def sym(code): return mkt(code) + code

os.makedirs(CACHE, exist_ok=True)

def cpath(name): return os.path.join(CACHE, name)
def load_json(name, default=None):
    p = cpath(name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: return json.load(f)
    return default
def save_json(name, obj):
    with open(cpath(name), "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False)

def retry(fn, n=2, wait=1.2):
    last = None
    for i in range(n + 1):
        try: return fn()
        except Exception as e:
            last = e; time.sleep(wait * (i + 1))
    raise last

# ---------------------------------------------------------------- 日线
def fetch_daily(ak):
    daily = {}
    for code in BASKET:
        fn = f"daily_{code}.json"
        d = load_json(fn)
        if d is None or (d and len(next(iter(d.values()))) < 3):
            df = retry(lambda: ak.fund_etf_hist_sina(symbol=sym(code)))
            d = {}
            for _, r in df.iterrows():
                dt = str(r["date"])[:10]
                if dt >= START:
                    # [close, amount_yi, volume]；新浪深市个别日 amount=0 时用 volume*close 兜底
                    amt = float(r["amount"]) / 1e8
                    vol = float(r["volume"])
                    if amt <= 0 and vol > 0:
                        amt = vol * float(r["close"]) / 1e8
                    d[dt] = [float(r["close"]), amt, vol]
            save_json(fn, d)
            print(f"  daily {code}: {len(d)} rows", flush=True)
        daily[code] = d
    idx = load_json("index_daily.json")
    if idx is None:
        df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000001"))
        idx = {str(r["date"])[:10]: float(r["close"]) for _, r in df.iterrows() if str(r["date"])[:10] >= START}
        save_json("index_daily.json", idx)
        print(f"  index daily: {len(idx)} rows", flush=True)
    return daily, idx

# ---------------------------------------------------------------- 净值
def _nav_one(code):
    fn = f"nav_{code}.json"
    d = load_json(fn)
    if d: return code, d
    d = {}  # lsjz 接口每页实际只返回 20 条，逐页拉到覆盖 START 为止
    page = 1
    while page <= 60:
        url = (f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}"
               f"&pageIndex={page}&pageSize=20")
        def _get():
            r = requests.get(url, headers={**UA, "Referer": "http://fundf10.eastmoney.com/"}, timeout=30)
            t = r.text
            if t.startswith("jQuery"): t = t[t.find("(") + 1: t.rfind(")")]
            return json.loads(t)
        data = retry(_get)
        rows = (data.get("Data") or {}).get("LSJZList") or []
        if not rows: break
        for x in rows:
            if x.get("DWJZ"): d[x["FSRQ"]] = float(x["DWJZ"])
        if min(x["FSRQ"] for x in rows) < START: break
        page += 1
        time.sleep(0.1)
    d = {k: v for k, v in d.items() if k >= START}
    save_json(fn, d)
    print(f"  nav {code}: {len(d)} rows", flush=True)
    return code, d

def fetch_nav():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as ex:
        return dict(ex.map(_nav_one, BASKET))

# ---------------------------------------------------------------- 份额
def _sse_one(d):
    """上交所直调：某日全部 ETF 份额。TOT_VOL 单位万份 → 份。"""
    url = ("https://query.sse.com.cn/commonQuery.do"
           "?sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"
           f"&STAT_DATE={d}&pageHelp.pageSize=3000&pageHelp.pageNo=1"
           "&pageHelp.beginPage=1&pageHelp.cacheSize=1&pageHelp.endPage=1")
    def _get():
        r = requests.get(url, headers={**UA, "Referer": "https://www.sse.com.cn/"}, timeout=120)
        return r.json().get("result") or []
    rows = retry(_get, n=2, wait=2.0)
    m = {}
    for r in rows:
        if r.get("STAT_DATE") != d: continue
        try: m[r["SEC_CODE"]] = [float(r["TOT_VOL"]) * 1e4, r.get("SEC_NAME", "")]
        except Exception: pass
    return m

def fetch_sse_shares(ak, days):
    """逐日缓存 sse_YYYYMMDD.json = {code: [shares, name]}；接口慢（~5-20s/次），3 并发。"""
    from concurrent.futures import ThreadPoolExecutor
    out, todo = {}, []
    for d in days:
        m = load_json(f"sse_{d.replace('-','')}.json")
        if m is None: todo.append(d)
        else: out[d] = m
    print(f"  SSE shares: {len(out)} cached, {len(todo)} to fetch", flush=True)
    done = [0]
    def work(d):
        m = _sse_one(d)
        save_json(f"sse_{d.replace('-','')}.json", m)
        done[0] += 1
        if done[0] % 25 == 0: print(f"    sse {done[0]}/{len(todo)}", flush=True)
        return d, m
    if todo:
        with ThreadPoolExecutor(max_workers=3) as ex:
            for d, m in ex.map(work, todo): out[d] = m
    return out

def fetch_szse_shares(days):
    """区间 xlsx，按季度分块。缓存 szse_all.json = {'date|code': shares}, szse_names.json"""
    names = load_json("szse_names.json", {})
    import pandas as pd
    res = {}
    lo, hi = days[0], days[-1]
    # 按年分块，避免单文件过大
    years = sorted(set(d[:4] for d in days))
    for y in years:
        s = max(lo, f"{y}-01-01"); e = min(hi, f"{y}-12-31")
        fn = f"szse_{y}.json"
        part = load_json(fn)
        if part is None:
            url = ("https://www.szse.cn/api/report/ShowReport?SHOWTYPE=xlsx"
                   "&CATALOGID=scsj_fund_jjgm&TABKEY=tab1"
                   f"&txtStart={s}&txtEnd={e}&jjlb=ETF&random=0.31")
            def _get():
                r = requests.get(url, headers={**UA, "Referer": "https://www.szse.cn/market/fund/volume/etf/index.html"}, timeout=120)
                df = pd.read_excel(io.BytesIO(r.content), engine="openpyxl")
                return df
            df = retry(_get, n=2, wait=2.0)
            part = {}
            for _, r in df.iterrows():
                try:
                    dt = str(r["日期"])[:10]; cd = str(r["基金代码"]).zfill(6)
                    part[f"{dt}|{cd}"] = float(r["基金规模(份)"])
                    names[cd] = str(r["基金简称"])
                except Exception: pass
            save_json(fn, part)
            print(f"  szse {y}: {len(part)} rows", flush=True)
            time.sleep(0.4)
        res.update(part)
    save_json("szse_all.json", res); save_json("szse_names.json", names); save_json("szse_done.json", True)
    return {tuple(k.split("|")): v for k, v in res.items()}, names

# ---------------------------------------------------------------- 分钟
def fetch_minutes(ak):
    mins = {}
    for code in BASKET:
        fn = f"minute_{code}.json"
        d = load_json(fn)
        if d is None:
            df = retry(lambda: ak.stock_zh_a_minute(symbol=sym(code), period="1", adjust=""))
            d = [[str(r["day"]), float(r["close"]), float(r["amount"])] for _, r in df.iterrows()]
            save_json(fn, d)
            print(f"  minute {code}: {len(d)} rows", flush=True)
            time.sleep(0.3)
        mins[code] = d
    idxm = load_json("minute_index.json")
    if idxm is None:
        try:
            df = retry(lambda: ak.stock_zh_a_minute(symbol="sh000001", period="1", adjust=""))
            idxm = [[str(r["day"]), float(r["close"]), float(r["amount"])] for _, r in df.iterrows()]
        except Exception as e:
            print(f"  index minute via akshare failed: {e}; fallback sina http", flush=True)
            idxm = sina_minute_http("sh000001")
        save_json("minute_index.json", idxm)
        print(f"  minute index: {len(idxm)} rows", flush=True)
    return mins, idxm

def sina_minute_http(symbol):
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/varx=/CN_MarketDataService.getKLineData"
           f"?symbol={symbol}&scale=1&ma=no&datalen=2000")
    r = requests.get(url, headers={**UA, "Referer": "https://finance.sina.com.cn/"}, timeout=30)
    t = r.text; t = t[t.find("(") + 1: t.rfind(")")]
    return [[x["day"], float(x["close"]), 0.0] for x in json.loads(t)]

# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="份额回溯的交易日数（0=全量）")
    args = ap.parse_args()
    import akshare as ak

    print("[1/6] daily ...", flush=True)
    daily, idx = fetch_daily(ak)
    cal = sorted(idx.keys())
    print(f"  calendar {cal[0]}..{cal[-1]} n={len(cal)}", flush=True)

    print("[2/6] nav ...", flush=True)
    nav = fetch_nav()

    share_days = cal if args.days == 0 else cal[-args.days:]
    print(f"[3/6] sse shares ({len(share_days)} days) ...", flush=True)
    sse = fetch_sse_shares(ak, share_days)
    print("[4/6] szse shares ...", flush=True)
    szse, sz_names = fetch_szse_shares(share_days)

    def share_of(code, d):
        if mkt(code) == "sh":
            row = sse.get(d, {}).get(code)
            return row[0] if row else None
        return szse.get((d, code))

    names = {}
    last_sse = sse.get(share_days[-1], {}) if share_days else {}
    for code in BASKET:
        if mkt(code) == "sh":
            row = last_sse.get(code); names[code] = row[1] if row else code
        else:
            names[code] = sz_names.get(code, code)

    print("[5/6] compute daily series ...", flush=True)
    dates, amount, netflow, idxs, nf_cov, amt_cov = [], [], [], [], [], []
    prev_share = {}
    for i, d in enumerate(cal):
        a_sum, a_n = 0.0, 0
        for code in BASKET:
            row = daily[code].get(d)
            if row: a_sum += row[1]; a_n += 1
        dates.append(d); amount.append(round(a_sum, 2)); amt_cov.append(a_n); idxs.append(idx[d])
        if i == 0:
            netflow.append(None); nf_cov.append(0); continue
        pd_ = cal[i - 1]
        nf_sum, nf_n = 0.0, 0
        for code in BASKET:
            s1, s0 = share_of(code, d), share_of(code, pd_)
            nv = nav[code].get(d)
            if s1 is not None and s0 is not None and nv:
                nf_sum += (s1 - s0) * nv / 1e8; nf_n += 1
        netflow.append(round(nf_sum, 2) if nf_n >= 10 else None)
        nf_cov.append(nf_n)

    # 对账基准
    bench = {}
    bpath = os.path.join(PKG_DATA, "daily_amount_netflow.csv")
    if os.path.exists(bpath):
        import csv
        with open(bpath, encoding="utf-8-sig") as f:
            for r in csv.reader(f):
                if len(r) >= 4 and r[0][:4].isdigit():
                    bench[r[0]] = (float(r[1]), float(r[2]), float(r[3]))
    sup_bench = []
    spath = os.path.join(PKG_DATA, "support_days.csv")
    if os.path.exists(spath):
        import csv
        with open(spath, encoding="utf-8-sig") as f:
            for r in csv.reader(f):
                if len(r) >= 3 and r[0][:4].isdigit(): sup_bench.append(r[0])

    rec_rows, amt_bad, nf_bad = [], 0, 0
    for i, d in enumerate(dates):
        if d in bench:
            ba, bn, _ = bench[d]
            ad = (amount[i] / ba - 1) * 100 if ba else 0.0
            nd = ((netflow[i] / bn - 1) * 100) if (netflow[i] is not None and bn and abs(bn) >= 20) else None
            if abs(ad) > 3: amt_bad += 1
            if nd is not None and abs(nd) > 3: nf_bad += 1
            rec_rows.append([d, amount[i], ba, round(ad, 2), netflow[i], bn, (round(nd, 2) if nd is not None else "")])
    with open(os.path.join(BASE, "reconcile.csv"), "w", encoding="utf-8") as f:
        f.write("date,our_amount,bench_amount,amount_diff_pct,our_netflow,bench_netflow,netflow_diff_pct\n")
        for r in rec_rows: f.write(",".join(str(x) for x in r) + "\n")

    our_sup = [dates[i] for i in range(len(dates)) if netflow[i] is not None and netflow[i] > 100]
    sup_set, bench_set = set(our_sup), set(sup_bench)
    hit = len(sup_set & bench_set)
    support = [{"date": dates[i], "amount": amount[i], "netflow": netflow[i]}
               for i in range(len(dates)) if netflow[i] is not None and netflow[i] > 100]

    print("[6/6] minutes + emit ...", flush=True)
    mins, idxm = fetch_minutes(ak)
    # 分钟按日组织
    def by_day(rows):
        out = {}
        for day, close, amt in rows:
            d, t = day[:10], day[11:16]
            out.setdefault(d, {})[t] = (close, amt)
        return out
    min_by = {c: by_day(mins[c]) for c in BASKET}
    idx_by = by_day(idxm)
    mdays = sorted(set.intersection(*[set(min_by[c].keys()) for c in BASKET] + [set(idx_by.keys())]))
    print(f"  minute common days: {mdays}", flush=True)
    SLOTS = [f"{h:02d}:{m:02d}" for h, ms in ((9, range(31, 60)), (10, range(0, 60)), (11, range(0, 31)), (13, range(1, 60)), (14, range(0, 60)), (15, range(0, 1))) for m in ms]
    def day_bars(d):
        bars, closes = [], []
        for s in SLOTS:
            tot = 0.0; ok = False
            for c in BASKET:
                v = min_by[c].get(d, {}).get(s)
                if v: tot += v[1]; ok = True
            bars.append(round(tot / 1e8, 4) if ok else None)
            iv = idx_by.get(d, {}).get(s)
            closes.append(iv[0] if iv else None)
        return bars, closes
    latest = mdays[-1]
    bars, closes = day_bars(latest)
    prev_close_idx = idx[cal[cal.index(latest) - 1]] if latest in cal and cal.index(latest) > 0 else None
    table = []
    for c in BASKET:
        rows = mins[c]
        today = [r for r in rows if r[0][:10] == latest]
        amt = sum(r[2] for r in today) / 1e8
        price = today[-1][1] if today else None
        di = cal.index(latest) if latest in cal else -1
        pc = daily[c].get(cal[di - 1], [None])[0] if di > 0 else None
        pct = round((price / pc - 1) * 100, 2) if price and pc else None
        table.append({"code": c, "name": names[c], "price": price, "pct": pct, "amount": round(amt, 2)})
    table.sort(key=lambda x: -x["amount"])

    # 累计曲线 + S1 偏离（今日 vs 其余日同时段均值曲线）
    def cum_curve(d):
        b, _ = day_bars(d)
        out, s = [], 0.0
        for v in b:
            s += (v or 0.0); out.append(round(s, 3))
        return out
    cum_today = cum_curve(latest)
    prev_day = mdays[-2] if len(mdays) > 1 else None
    cum_prev = cum_curve(prev_day) if prev_day else None
    base_days = mdays[:-1]
    base_curve = []
    for j in range(len(SLOTS)):
        vals = []
        for d in base_days:
            b, _ = day_bars(d)
            s = sum((x or 0.0) for x in b[: j + 1])
            vals.append(s)
        base_curve.append(round(sum(vals) / len(vals), 3) if vals else None)
    dev = [round(cum_today[j] / base_curve[j], 2) if base_curve[j] and base_curve[j] > 0.5 else None for j in range(len(SLOTS))]
    dev_valid = [x for x in dev if x is not None]
    s1 = {"baseDays": len(base_days), "devMax": max(dev_valid) if dev_valid else None,
          "devNow": dev_valid[-1] if dev_valid else None, "flag": bool(dev_valid and max(dev_valid) >= 2.0)}

    # 典型走势：分钟窗口内按当日净流入分组
    nf_map = {dates[i]: netflow[i] for i in range(len(dates))}
    sup_days = [d for d in mdays if (nf_map.get(d) or 0) > 100]
    mode = "netflow>100"
    if not sup_days:
        ranked = sorted(mdays, key=lambda d: -(nf_map.get(d) or -1e9))
        sup_days = ranked[:2]; mode = "top-netflow-in-window(fallback)"
    nor_days = [d for d in mdays if d not in sup_days]
    def group_curves(g):
        amt_avg, idx_avg = [], []
        for j, s in enumerate(SLOTS):
            av, iv = [], []
            for d in g:
                b, cl = day_bars(d)
                if b[j] is not None: av.append(b[j])
                day_open = next((x for x in cl if x is not None), None)
                if cl[j] is not None and day_open: iv.append((cl[j] / day_open - 1) * 100)
            amt_avg.append(round(sum(av) / len(av), 4) if av else None)
            idx_avg.append(round(sum(iv) / len(iv), 3) if iv else None)
        return amt_avg, idx_avg
    sup_amt, sup_idx = group_curves(sup_days)
    nor_amt, nor_idx = group_curves(nor_days)

    recent = [{"date": dates[i], "amount": amount[i], "netflow": netflow[i]} for i in range(max(0, len(dates) - 4), len(dates))]
    DATA = {
        "meta": {"generated": time.strftime("%Y-%m-%d %H:%M"), "basket": [{"code": c, "name": names[c]} for c in BASKET],
                 "latestDay": dates[-1], "minuteDay": latest},
        "daily": {"dates": dates, "amount": amount, "netflow": netflow, "idx": idxs, "nfCov": nf_cov, "amtCov": amt_cov},
        "support": support, "recent": recent,
        "init": {"date": latest, "preClose": prev_close_idx, "times": SLOTS, "bars": bars, "closes": closes, "table": table},
        "cum": {"times": SLOTS, "today": cum_today, "prev": cum_prev, "prevDate": prev_day, "base": base_curve, "s1": s1},
        "typ": {"slots": SLOTS, "supAmt": sup_amt, "supIdx": sup_idx, "norAmt": nor_amt, "norIdx": nor_idx,
                "supDays": sup_days, "norDays": nor_days, "mode": mode},
    }
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.__DATA = " + json.dumps(DATA, ensure_ascii=False) + ";\n")
    summary = {
        "calendar": [cal[0], cal[-1], len(cal)], "share_days": len(share_days),
        "daily_rows": len(dates), "nf_nonnull": sum(1 for x in netflow if x is not None),
        "bench_days": len(rec_rows), "amount_diff_gt3": amt_bad, "netflow_diff_gt3": nf_bad,
        "support_ours": len(our_sup), "support_bench": len(sup_bench), "support_hit": hit,
        "support_missed": sorted(bench_set - sup_set), "support_extra": sorted(sup_set - bench_set),
        "minute_days": mdays, "s1": s1, "typ_mode": mode,
        "latest": {"date": dates[-1], "amount": amount[-1], "netflow": netflow[-1], "idx": idxs[-1]},
    }
    save_json("../build_summary.json", summary) if False else json.dump(summary, open(os.path.join(BASE, "build_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
