# GitHub 推送预案（快照方式，仓库出现即执行）

目标仓库：`sina-west4angle/etf-fund-flow-board`（用户手动建的 Public 空仓）
分支：`main` ｜ 方式：GitHub 连接器 `push_files` 快照（不用 gh / 不用 git push，
本机 gh 未登录且连接器规范禁止另起认证流）。

## 当前备好状态（2026-10-23 夜）

- 本地 git 仓库已 init + 首个 commit；推送选文件以 git 索引为准。
- 选文件清单（NUL 分隔）已生成并校验：`~/workspace/etf-board-paths.manifest`
  （放在仓库外；23 个文件、约 206 KB、全部 UTF-8、无软链、无二进制，
  在快照上限 2000 文件 / 16 MiB 内）。
- 同步记录 `~/workspace/etf-board.muse-github-snapshot-sync.json` 尚不存在
  → 这是首次上传，无历史基线。
- 已轮询 `search_repositories`：目标仓尚未出现（搜索通道本身已用 musesina 仓验通）。

## 执行步骤（发现仓库后）

1. 复查仓库仍为空：`list_branches` + `get_file_contents`（README）确认无 commit/refs；
   若已非空，停下按「已有提交仓库」流程逐文件比对基线，不直接覆盖。
2. 执行推送（清单里含本项目 README.md，provider 若自动生成初始 README 会被它替换）：
   ```bash
   /opt/hatch/bin/github push-files \
     --owner sina-west4angle --repo etf-fund-flow-board --branch main \
     --message "etf-board: initial snapshot (site + pipeline + supabase migrations)" \
     --source-dir /home/hatch/workspace/etf-board \
     --paths-file /home/hatch/workspace/etf-board-paths.manifest
   ```
3. 成功且拿到完整 commit SHA 后，把 {owner, repo, branch, source_dir, commit_sha, paths}
   追加写入 `~/workspace/etf-board.muse-github-snapshot-sync.json`（先写 .tmp-* 再原子替换）。
   失败/结果不明绝不推进记录，先对账再说。

## 已知风险与兜底

- `.github/workflows/deploy.yml`：GitHub App 若缺 workflow 权限，整快照会被拒。
  兜底：从 manifest 剔除该文件先推其余文件（记录只推进已确认提交的路径），
  deploy.yml 由用户在网页端粘贴创建一次（README 清单第 3 条）。
- 连接器目录里没有 Pages / Actions 查询工具：推送后能验的只有
  `list_commits`（head 应等于记录 SHA）与 `get_file_contents` 抽查回读；
  Pages 是否生效另行用公开地址 https://sina-west4angle.github.io/etf-fund-flow-board/
  实际打开验证（需先在 Settings → Pages 把 Source 设为 GitHub Actions，一次性）。
- 快照不带本地 git 历史/分支/删除：后续删文件需另用 delete_file 工具处理。
