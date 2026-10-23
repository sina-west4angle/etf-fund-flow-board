-- 0001_create_etf_tables.sql
-- 20只重点ETF资金观测看板 · 自有数据底座 (Supabase = 我们的 Excel)
-- 口径与 pipeline/build_data.py 一致:
--   成交额 amount   : 新浪日K amount 字段加总/逐只, 单位亿元
--   净流入 netflow  : (份额_T - 份额_{T-1}) x 单位净值_T / 1e8, 单位亿元 (申赎口径)
--   份额 shares     : 交易所官方规模 (上交所 TOT_VOL / 深交所报表), 单位份
--   托底日 is_support: 20只合计净流入 > 100 亿元 (净流入覆盖不足的日子为 false 且 netflow 为 null)
-- 幂等: 可重复执行。经 Management API POST /v1/projects/{ref}/database/query 运行,
-- 或 GitHub Actions deploy.yml 自动运行, 或 SQL Editor 手工粘贴 (兜底)。

create table if not exists public.etf_daily_total (
  trade_date    date primary key,
  total_amount  numeric,                    -- 20只合计成交额 (亿元)
  total_netflow numeric,                    -- 20只合计净流入 (亿元, 覆盖不足时 null)
  index_close   numeric,                    -- 上证综指收盘
  is_support    boolean not null default false,
  updated_at    timestamptz not null default now()
);

comment on table public.etf_daily_total is 'ETF看板日度合计: 一行一天 (成交额/净流入/上证收盘/托底标记)';

create table if not exists public.etf_daily_detail (
  trade_date date not null,
  code       text not null,
  name       text,                          -- 交易所官方基金简称
  close      numeric,                       -- 收盘价 (新浪日K)
  amount     numeric,                       -- 当日成交额 (亿元)
  shares     numeric,                       -- 当日份额 (份, 交易所官方规模)
  netflow    numeric,                       -- 当日净流入 (亿元, = Δ份额 x 单位净值 / 1e8)
  primary key (trade_date, code)
);

comment on table public.etf_daily_detail is 'ETF看板逐只日度: 一行一天一只 (收盘/成交额/份额/净流入)';

create index if not exists idx_etf_daily_detail_code_date
  on public.etf_daily_detail (code, trade_date desc);

create index if not exists idx_etf_daily_total_support
  on public.etf_daily_total (trade_date desc) where is_support;
