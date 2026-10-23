#!/usr/bin/env python3
"""etf-board 管理面脚本: Supabase Management API (custom.supabase-mgmt 凭证通道, sbp 管理面).

按 muse12 方法: 管理面 (sbp_ 账号级 Access Token) 负责结构与部署面操作:
  - GET  /v1/projects                              查项目列表 (验令牌)
  - GET  /v1/projects/<ref>/functions              查 Edge Function 状态
  - POST /v1/projects/<ref>/database/query         跑任意 SQL (含 DDL)

用法:
  sb_mgmt.py projects
  sb_mgmt.py functions
  sb_mgmt.py query '<SQL>'
  sb_mgmt.py query-file <path.sql>

凭证由保险库经 dynamic_credentials 在出口处以 surrogate 替换注入,
脚本与参数里永远不出现真实令牌。项目 ref 是公开标识, 不是秘密。
"""
import json
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

BASE = "https://api.supabase.com"
ALLOWED_HOSTS = ["api.supabase.com"]
CREDENTIAL_NAME = "custom.supabase-mgmt"
PROJECT_REF = "ocqfhempmbxmriecijrg"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/json")
    add_surrogate_to_request(request, CREDENTIAL_NAME, allowed_hosts=ALLOWED_HOSTS)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            try:
                return response.status, read_json_response(response)
            except Exception:
                return response.status, ""
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        return e.code, detail


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "projects":
        status, out = call("GET", "/v1/projects")
    elif cmd == "functions":
        status, out = call("GET", f"/v1/projects/{PROJECT_REF}/functions")
    elif cmd == "query":
        if len(argv) < 3:
            print("usage: sb_mgmt.py query '<SQL>'", file=sys.stderr)
            return 2
        status, out = call("POST", f"/v1/projects/{PROJECT_REF}/database/query",
                           {"query": argv[2]})
    elif cmd == "query-file":
        if len(argv) < 3:
            print("usage: sb_mgmt.py query-file <path.sql>", file=sys.stderr)
            return 2
        with open(argv[2], encoding="utf-8") as f:
            sql = f.read()
        status, out = call("POST", f"/v1/projects/{PROJECT_REF}/database/query",
                           {"query": sql})
    else:
        print(__doc__)
        return 2
    print(f"HTTP {status}")
    if isinstance(out, (dict, list)):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(out)
    return 0 if status < 300 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
