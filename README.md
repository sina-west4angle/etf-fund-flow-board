# etf-fund-flow-board · 20只重点ETF资金观测看板（自有版）

数据落 Supabase、网站落 GitHub 的自动部署链路，按 muse12 的
「GitHub + Supabase 自动部署」方法落地（仓库即真相、双通道分工、流水线部署、接口验证）。

## 架构

```text
pipeline/build_data.py  (新浪/上交所/深交所公开源)
        │  生成
        ▼
site/  静态站 (index.html + app.js + data.js, ECharts) ──push──▶ GitHub Pages
        │
pipeline/sync_supabase.py (数据面 PostgREST, service_role)
        │  upsert
        ▼
Supabase 项目 ocqfhempmbxmriecijrg (musesina)
  ├─ etf_daily_total   一行一天: 合计成交额/净流入 (亿元)、上证收盘、托底标记
  └─ etf_daily_detail  一行一天一只: 收盘/成交额 (亿元)/份额 (份)/净流入 (亿元)
supabase/migrations/   建表 DDL (幂等), 经 Management API (sbp_) 执行
.github/workflows/deploy.yml  push 到 main 自动: 跑 SQL 迁移 -> 发布 Pages
```

## 通道分工（凭证都在保险库，绝不进仓库/聊天）

| 面 | 通道 | 本地脚本 | 状态 |
|---|---|---|---|
| 管理面 | Management API `api.supabase.com`（连接器 `custom.supabase-mgmt`，sbp_ 令牌） | `deploy/sb_mgmt.py`（项目内封装，同连接器）/ 连接器 helper `custom.supabase-mgmt/bin/sb_mgmt.py` | ✅ 已验通：查项目、跑 SQL/DDL 均可 |
| 数据面 | PostgREST（连接器 `custom.supabase`，service_role） | `deploy/sb_data.py`（透传既有 helper）、`pipeline/sync_supabase.py` | ✅ 已验通 |

注意：`custom.supabase` 那把是数据面钥匙，直接调 Management API 会回
401 `No access token provided`（它以 apikey 头投递，管理面只认 Bearer sbp_），
管理面必须走 `custom.supabase-mgmt`。报错签名对照见 muse12 方法第三节。

## 已落地状态（2026-10-23 实测）

- 两表已建（结构与 `supabase/migrations/0001_create_etf_tables.sql` 一致；
  该迁移已于当日经 Management API 幂等重跑验证无副作用）。
- 数据已同步：`etf_daily_total` 738 行（2023-10-09 ~ 2026-10-23，SQL count 实测）；
  `etf_daily_detail` 14,760 行 upsert 完成（738 日 × 20 只）。
- 份额/净流入覆盖随管线回溯进度：沪市份额 490 日已回填（至 2026-10-22），
  深市份额目前近 30 日（区间报表回溯中）；覆盖不足的日子 netflow 为 null，不编造。
  详见 `pipeline/REPORT.md`。

## 日常操作

```bash
# 管线重算 + 同步 (表已在, 直接 upsert; 表不在自动落 pipeline/supabase_rows.json)
~/workspace/muse-free-market-data/.venv/bin/python pipeline/build_data.py
python3 pipeline/sync_supabase.py

# 管理面: 查项目 / 跑任意 SQL / 查表结构
python3 deploy/sb_mgmt.py projects
python3 deploy/sb_mgmt.py query "select count(*) from public.etf_daily_total"
python3 deploy/sb_mgmt.py query-file supabase/migrations/0001_create_etf_tables.sql

# 数据面: 读表
python3 deploy/sb_data.py get --path "/rest/v1/etf_daily_total?select=*&order=trade_date.desc&limit=5"
```

## GitHub 落地清单（待办，一次性）

按 muse12 方法第七节第 3 条：GitHub 应用没有建仓与写 workflows 的权限，所以：

1. 用户在 GitHub 手动建私仓 `sina-west4angle/etf-fund-flow-board`，
   并把仓库加入 Muse GitHub 应用的授权范围。
2. 本地仓库已 init 并完成首个 commit（见下），建好仓后：
   `git remote add origin git@github.com:sina-west4angle/etf-fund-flow-board.git && git push -u origin main`
   （本机 gh 未登录、无 SSH 推送凭证时，改由 GitHub 连接器 Contents API 逐文件写入，
   注意 content 传纯文本不要传 base64 —— 方法第七节第 4 条。）
3. `.github/workflows/deploy.yml` 若经连接器写不进去（workflow scope 403），
   由用户在网页端粘贴创建一次；此后日常变更走正常 push。
4. 仓库 Settings → Secrets 添加：
   `SUPABASE_ACCESS_TOKEN`（Actions 专用 sbp_，与本地那把分开生成，有效期选 90 天）、
   `SUPABASE_PROJECT_REF` = `ocqfhempmbxmriecijrg`。
5. Settings → Pages → Source 选 “GitHub Actions”。
6. push 后看 Actions 跑完，再抽查线上页面与 Supabase 计数，完成验证闭环。
