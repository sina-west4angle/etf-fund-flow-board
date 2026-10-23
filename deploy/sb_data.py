#!/usr/bin/env python3
"""etf-board 数据面脚本: PostgREST 读写 (复用 custom.supabase 既有 helper).

数据面 (service_role) 只读写表数据行, 不做 DDL。本脚本是对已注册连接器
helper 的透传封装, 凭证通道与用法与 helper 完全一致:

  sb_data.py ping
  sb_data.py get  --path '/rest/v1/etf_daily_total?select=*&limit=5'
  sb_data.py post --path '/rest/v1/etf_daily_total' --data '[{"trade_date":"2026-10-23", ...}]'

upsert 请带 header: helper 不支持自定义 header, 批量 upsert 走
pipeline/sync_supabase.py (内含 merge-duplicates 逻辑)。
"""
import subprocess
import sys

HELPER = "/home/hatch/workspace/custom-connectors/custom.supabase/bin/supabase.py"

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("ping", "get", "post", "patch", "delete"):
        print(__doc__)
        sys.exit(2)
    sys.exit(subprocess.call([sys.executable, HELPER] + sys.argv[1:]))
