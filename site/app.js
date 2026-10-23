/* 20只重点ETF资金观测看板 · 前端逻辑（自研实现）
   数据：同目录 data.js（window.__DATA，自有管线产出）；
   盘中刷新：同源 /api/kline（新浪分钟代理，见 pipeline/server.py），不可用时回落静态数据。 */
(function () {
  "use strict";
  var D = window.__DATA;
  if (!D) { document.getElementById("tagUpdate").textContent = "数据未加载"; return; }
  var BASKET = D.meta.basket;
  function sym(code) { return (code[0] === "5" || code[0] === "6" ? "sh" : "sz") + code; }
  function $(id) { return document.getElementById(id); }
  function fmt(v, n) { return v === null || v === undefined ? "--" : Number(v).toFixed(n === undefined ? 2 : n); }
  var charts = [];
  function mk(id) { var c = echarts.init($(id)); charts.push(c); return c; }
  window.addEventListener("resize", function () { charts.forEach(function (c) { c.resize(); }); });

  /* ---------- 第一部分：分钟 ---------- */
  var SLOTS = D.init.times;
  function minuteOption(bars, closes, preClose) {
    return {
      title: { text: D.init.date + " · 20只ETF分钟成交额合计 + 上证综指", textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["分钟成交额(亿)", "上证综指"], right: 0, textStyle: { fontSize: 12 } },
      grid: { left: 58, right: 64, top: 62, bottom: 30 },
      xAxis: { type: "category", data: SLOTS, axisLabel: { interval: 29, fontSize: 11 } },
      yAxis: [
        { type: "value", name: "亿元", nameGap: 14, nameTextStyle: { align: "left", padding: [0, 0, 6, 0] }, min: 0 },
        { type: "value", name: "上证(点)", scale: true, nameGap: 14, nameTextStyle: { align: "right", padding: [0, 0, 6, 0] } }
      ],
      series: [
        { name: "分钟成交额(亿)", type: "bar", data: bars, itemStyle: { color: "#24507e" } },
        { name: "上证综指", type: "line", yAxisIndex: 1, data: closes, showSymbol: false,
          lineStyle: { width: 1.6, color: "#c0392b" },
          markLine: preClose ? { silent: true, symbol: "none", lineStyle: { type: "dashed", color: "#888" },
            label: { position: "insideEndTop", distance: 6, formatter: "昨收 " + preClose }, data: [{ yAxis: preClose }] } : undefined }
      ]
    };
  }
  var chMin = mk("chartMin");
  chMin.setOption(minuteOption(D.init.bars, D.init.closes, D.init.preClose));

  function cumOption(cum) {
    var s = [
      { name: "今日", type: "line", data: cum.today, showSymbol: false, lineStyle: { width: 2.4, color: "#c0392b" } },
      { name: "近" + cum.s1.baseDays + "日同时段均值", type: "line", data: cum.base, showSymbol: false, lineStyle: { width: 1.6, color: "#24507e", type: "dashed" } }
    ];
    if (cum.prev) s.push({ name: cum.prevDate || "前一交易日", type: "line", data: cum.prev, showSymbol: false, lineStyle: { width: 1.4, color: "#e8a33d" } });
    return {
      title: { text: "累计成交额对比（亿元）", textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis" }, legend: { right: 10, textStyle: { fontSize: 12 } },
      grid: { left: 52, right: 24, top: 48, bottom: 30 },
      xAxis: { type: "category", data: cum.times, axisLabel: { interval: 29, fontSize: 11 } },
      yAxis: { type: "value", min: 0 },
      series: s
    };
  }
  var chCum = mk("chartCum");
  chCum.setOption(cumOption(D.cum));

  function s1Tag(s1) {
    var el = $("tagS1");
    if (s1 && s1.devMax !== null && s1.devMax !== undefined) {
      el.style.display = "";
      el.textContent = (s1.flag ? "⚠ 量能异常 S1：盘中累计量最高达近" + s1.baseDays + "日同时段均值的 " + s1.devMax + " 倍（阈值 2 倍）"
                                 : "量能 S1：盘中累计量峰值偏离 " + s1.devMax + " 倍（近" + s1.baseDays + "日均值，未达 2 倍异常线）");
      el.className = s1.flag ? "tag warn" : "tag";
    }
  }
  s1Tag(D.cum.s1);
  $("tagDate").textContent = "分钟数据日：" + D.init.date;

  function typOption(title, amt, idx) {
    return {
      title: { text: title, textStyle: { fontSize: 13, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 54, right: 58, top: 56, bottom: 26 },
      xAxis: { type: "category", data: D.typ.slots, axisLabel: { interval: 39, fontSize: 11 } },
      yAxis: [ { type: "value", name: "亿/分钟", nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] }, min: 0 }, { type: "value", name: "指数%", scale: true, nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] } } ],
      series: [
        { name: "平均分钟成交额", type: "bar", data: amt, itemStyle: { color: "#7fa6c9" } },
        { name: "上证相对开盘%", type: "line", yAxisIndex: 1, data: idx, showSymbol: false, lineStyle: { width: 1.4, color: "#c0392b" } }
      ]
    };
  }
  var typNote = D.typ.mode.indexOf("netflow>100") === 0 ? "净流入>100亿日" : "窗口内净流入居前日（窗口无>100亿日时的替代分组）";
  mk("chartTypSup").setOption(typOption("放量样本日均值（" + typNote + "，" + D.typ.supDays.length + " 日：" + D.typ.supDays.join("、") + "）", D.typ.supAmt, D.typ.supIdx));
  mk("chartTypNor").setOption(typOption("常态日均值（" + D.typ.norDays.length + " 日）", D.typ.norAmt, D.typ.norIdx));

  function renderTable(table) {
    var total = table.reduce(function (s, r) { return s + (r.amount || 0); }, 0);
    var max = Math.max.apply(null, table.map(function (r) { return r.amount || 0; }));
    $("etfTable").innerHTML = table.map(function (r) {
      var cls = r.pct === null ? "" : (r.pct >= 0 ? "up" : "down");
      var pct = r.pct === null ? "--" : (r.pct >= 0 ? "+" : "") + fmt(r.pct) + "%";
      var share = total ? (r.amount / total * 100).toFixed(1) + "%" : "--";
      var w = max ? (r.amount / max * 100).toFixed(1) : 0;
      return "<tr><td>" + r.code + "</td><td>" + r.name + "</td>" +
        "<td class='num'><div class='bar-bg' style='width:" + w + "%'></div><span class='v'>" + fmt(r.amount) + "</span></td>" +
        "<td class='num'>" + share + "</td><td class='num " + cls + "'>" + pct + "</td></tr>";
    }).join("");
  }
  renderTable(D.init.table);
  $("tagUpdate").textContent = "静态数据生成于 " + D.meta.generated;

  /* ---------- 盘中刷新（经同源代理） ---------- */
  var paused = false, timer = null;
  function isTrading() {
    var d = new Date(), dw = d.getDay(); if (dw === 0 || dw === 6) return false;
    var hm = d.getHours() * 100 + d.getMinutes();
    return (hm >= 930 && hm <= 1130) || (hm >= 1300 && hm <= 1500);
  }
  function fetchK(symbol) {
    return fetch("https://ocqfhempmbxmriecijrg.supabase.co/functions/v1/etf-live/kline?symbol=" + symbol + "&scale=1&datalen=400").then(function (r) { return r.json(); });
  }
  function refresh() {
    var jobs = [fetchK("sh000001")].concat(BASKET.map(function (b) { return fetchK(sym(b.code)); }));
    return Promise.all(jobs).then(function (res) {
      var idxRows = res[0], per = res.slice(1);
      var days = {}; idxRows.forEach(function (r) { days[r.day.slice(0, 10)] = 1; });
      var dayList = Object.keys(days).sort(); var today = dayList[dayList.length - 1];
      function slotOf(r) { return r.day.slice(11, 16); }
      var bars = SLOTS.map(function (s) {
        var tot = 0, ok = false;
        per.forEach(function (rows) { rows.forEach(function (r) { if (r.day.slice(0, 10) === today && slotOf(r) === s && r.amount !== undefined) { tot += r.amount; ok = true; } }); });
        return ok ? +(tot / 1e8).toFixed(4) : null;
      });
      var closes = SLOTS.map(function (s) {
        var v = null; idxRows.forEach(function (r) { if (r.day.slice(0, 10) === today && slotOf(r) === s) v = r.close; });
        return v;
      });
      chMin.setOption(minuteOption(bars, closes, D.init.preClose));
      var cum = [], ssum = 0;
      bars.forEach(function (v) { ssum += (v || 0); cum.push(+ssum.toFixed(3)); });
      var base = D.cum.base, devMax = null, devNow = null;
      cum.forEach(function (v, i) { if (base[i] > 0.5 && bars[i] !== null) { var dv = v / base[i]; if (devMax === null || dv > devMax) devMax = dv; devNow = dv; } });
      var cumObj = { times: SLOTS, today: cum, prev: D.cum.prev, prevDate: D.cum.prevDate, base: base,
                     s1: { baseDays: D.cum.s1.baseDays, devMax: devMax ? +devMax.toFixed(2) : null, flag: devMax >= 2 } };
      chCum.setOption(cumOption(cumObj)); s1Tag(cumObj.s1);
      var table = BASKET.map(function (b, i) {
        var rows = per[i].filter(function (r) { return r.day.slice(0, 10) === today; });
        var amt = rows.reduce(function (s, r) { return s + (r.amount || 0); }, 0) / 1e8;
        var price = rows.length ? rows[rows.length - 1].close : null;
        var old = D.init.table.filter(function (x) { return x.code === b.code; })[0];
        return { code: b.code, name: b.name, price: price, pct: old ? old.pct : null, amount: +amt.toFixed(2) };
      }).sort(function (a, b2) { return b2.amount - a.amount; });
      renderTable(table);
      $("tagDate").textContent = "分钟数据日：" + today;
      $("tagUpdate").textContent = "已刷新 " + new Date().toLocaleTimeString("zh-CN");
    }).catch(function () { $("tagUpdate").textContent = "代理不可用，显示静态数据（生成于 " + D.meta.generated + "）"; });
  }
  function arm() { if (timer) clearInterval(timer); timer = setInterval(function () { if (!paused && isTrading()) refresh(); }, 60000); }
  $("btnRefresh").addEventListener("click", refresh);
  $("btnPause").addEventListener("click", function () {
    paused = !paused; this.textContent = paused ? "恢复自动刷新" : "暂停自动刷新"; this.className = paused ? "off" : "";
  });
  if (location.protocol.indexOf("http") === 0) { refresh(); arm(); }

  /* ---------- 第二部分：托底信号 ---------- */
  var sup = D.support, rec = D.recent;
  $("tagSupCount").textContent = "托底日共 " + sup.length + " 天（合计净流入>100亿）";
  var lastNf = null; for (var i = D.daily.netflow.length - 1; i >= 0; i--) { if (D.daily.netflow[i] !== null) { lastNf = { d: D.daily.dates[i], v: D.daily.netflow[i] }; break; } }
  $("tagLatest").textContent = "最新净流入：" + (lastNf ? lastNf.d + " · " + fmt(lastNf.v) + " 亿" : "--");
  function supChart(id, field, colorSup, title, latestVal) {
    var xs = sup.map(function (r) { return r.date.slice(2); }).concat(rec.map(function (r) { return r.date.slice(2) + "·近"; }));
    var vals = sup.map(function (r) { return { value: r[field], itemStyle: { color: colorSup } }; })
      .concat(rec.map(function (r) { return { value: r[field], itemStyle: { color: "#e8a33d" } }; }));
    var opt = {
      title: { text: title, textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 56, right: 28, top: 56, bottom: 56 },
      xAxis: { type: "category", data: xs, axisLabel: { rotate: 38, fontSize: 10.5, interval: 0 } },
      yAxis: { type: "value", name: "亿元", nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] } },
      series: [{ type: "bar", data: vals,
        markLine: latestVal !== null && latestVal !== undefined ? { silent: true, symbol: "none",
          lineStyle: { type: "dashed", color: "#b02a24" }, label: { position: "insideEndTop", distance: 6, formatter: "最新 " + fmt(latestVal) }, data: [{ yAxis: latestVal }] } : undefined }]
    };
    mk(id).setOption(opt);
  }
  supChart("chartSupAmt", "amount", "#24507e", "成交额：托底日（蓝） vs 最近交易日（黄）", rec.length ? rec[rec.length - 1].amount : null);
  supChart("chartSupNf", "netflow", "#c0392b", "净流入：托底日（红） vs 最近已公布日（黄）", lastNf ? lastNf.v : null);

  /* ---------- 第三部分：日度全景 ---------- */
  var dy = D.daily;
  $("dailyMeta").textContent = "区间：" + dy.dates[0] + " ~ " + dy.dates[dy.dates.length - 1] + "（" + dy.dates.length + " 个交易日）｜柱：20只ETF日度成交额 / 净流入（申赎口径）｜线：上证综指收盘";
  function dailyChart(id, field, title, colorFn) {
    var data = dy[field].map(function (v, i) {
      return { value: v, itemStyle: { color: colorFn ? colorFn(v) : "#24507e" } };
    });
    mk(id).setOption({
      title: { text: title, textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["上证综指"], right: 0, textStyle: { fontSize: 12 } },
      grid: { left: 58, right: 62, top: 62, bottom: 64 },
      dataZoom: [{ type: "slider", start: 55 }, { type: "inside" }],
      xAxis: { type: "category", data: dy.dates, axisLabel: { fontSize: 11 } },
      yAxis: [ { type: "value", name: "亿元", nameGap: 14, nameTextStyle: { padding: [0, 0, 6, 0] } }, { type: "value", name: "上证(点)", scale: true, nameGap: 14, nameTextStyle: { padding: [0, 0, 6, 0] } } ],
      series: [
        { name: title, type: "bar", data: data },
        { name: "上证综指", type: "line", yAxisIndex: 1, data: dy.idx, showSymbol: false, lineStyle: { width: 1.2, color: "#666" } }
      ]
    });
  }
  dailyChart("chartDAmt", "amount", "日度成交额（亿元）", null);
  dailyChart("chartDNf", "netflow", "日度净流入（亿元，红>100亿 / 绿<0）", function (v) {
    if (v === null || v === undefined) return "#ccc"; if (v > 100) return "#c0392b"; if (v < 0) return "#1e8e4f"; return "#7fa6c9";
  });
})();
