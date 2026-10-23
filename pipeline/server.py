#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板同源代理（纯标准库）：静态托管 site/ + 新浪行情代理。
  GET /api/kline?symbol=sh510300&scale=1&datalen=260  -> 分钟/日K JSON 数组
  GET /api/hq?codes=sh510300,sz159915,sh000001        -> {code: {price,pct,amount_yi,prev_close}}
数据源：新浪 quotes.sina.cn getKLineData（与页面历史口径一致）。
用法：python3 server.py [port]   默认 8377
"""
import json, os, re, sys, time, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Referer": "https://finance.sina.com.cn/"}
_cache = {}

def sina_kline(symbol, scale, datalen):
    key = (symbol, scale, datalen)
    now = time.time()
    if key in _cache and now - _cache[key][0] < 20:
        return _cache[key][1]
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/varx=/CN_MarketDataService.getKLineData"
           f"?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}")
    req = urllib.request.Request(url, headers=UA)
    txt = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    txt = txt[txt.find("(") + 1: txt.rfind(")")]
    rows = json.loads(txt) if txt.strip().startswith("[") else []
    out = []
    for r in rows:
        o = {"day": r.get("day"), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": float(r.get("volume") or 0)}
        if r.get("amount") is not None:
            o["amount"] = float(r["amount"])
        out.append(o)
    _cache[key] = (now, out)
    return out

def hq_one(symbol):
    daily = sina_kline(symbol, 240, 2)
    if not daily:
        return None
    last = daily[-1]
    prev_close = daily[-2]["close"] if len(daily) > 1 else last["close"]
    amount_yi = None
    try:
        mins = sina_kline(symbol, 1, 300)  # getKLineData datalen 过大返回 null，300 足够覆盖当日240分钟
        today = last["day"][:10]
        amount_yi = round(sum(m.get("amount", 0.0) for m in mins if m["day"][:10] == today) / 1e8, 2)
    except Exception:
        pass
    return {"price": last["close"], "prev_close": prev_close,
            "pct": round((last["close"] / prev_close - 1) * 100, 2) if prev_close else None,
            "amount_yi": amount_yi, "date": last["day"][:10]}

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)
    def log_message(self, *a):
        pass
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/kline":
                q = parse_qs(u.query)
                symbol = (q.get("symbol") or [""])[0]
                if not re.fullmatch(r"(sh|sz)\d{6}", symbol):
                    return self._json({"error": "bad symbol"}, 400)
                scale = int((q.get("scale") or ["1"])[0])
                datalen = min(int((q.get("datalen") or ["260"])[0]), 400)
                return self._json(sina_kline(symbol, scale, datalen))
            if u.path == "/api/hq":
                q = parse_qs(u.query)
                codes = [c for c in (q.get("codes") or [""])[0].split(",") if re.fullmatch(r"(sh|sz)\d{6}", c)]
                if not codes:
                    return self._json({"error": "bad codes"}, 400)
                return self._json({c: hq_one(c) for c in codes})
        except Exception as e:
            return self._json({"error": str(e)[:200]}, 502)
        return super().do_GET()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8377
    print(f"serving {SITE} on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
