# .rounds —— 轮次守卫（round_guard）的状态与评分目录

这个目录由 `.github/scripts/round_guard.py` 自动维护，配合
`.github/workflows/continuous-loop.yml` 实现「每轮快照、候选与最佳分离、
自动验证、用户评分」，避免下一轮直接覆盖掉更好的方案。

## 核心概念

- **候选（candidate）**：opencode 每轮产出的改动。提交为 `snap/<时间>-r<轮次>`
  标签并**立即推送到远端**——无论后续验证结果如何，这一轮的产物都不会丢。
- **最佳（best）**：`master` 分支的当前内容。只有通过验证（或被用户采纳）
  的候选才会成为最佳。**下一轮永远从最佳出发**，而不是从上一轮的候选出发。
- **自动验证**：round_guard 按优先级探测并运行测试命令
  （pytest → make test → npm test → go test → Python 编译检查 → `main.py --help`
  → 包导入冒烟）。
  - 候选通过 → 晋升为新的最佳（master 前进一个候选）；
  - 候选失败而最佳通过 → **拒绝候选、保留最佳**，工作区重置回最佳；
  - 没有可运行的验证 → 记为「等待用户评分」。
- **用户评分**：不能自动分出高下的候选，由你裁决（见下）。

## 怎么给候选评分

打开 `.rounds/verdicts.txt`，加一行：

```
snap/20261016-061234-r3: 8
```

- 分数 1-10，**≥ 7** 自动采纳为最佳（阈值可在 state.json 的 `promote_score` 调整）；
- 也可以直接写 `accept` / `reject`；
- **采纳一个旧快照 = 把仓库回滚到该方案**（用新提交实现，不改写历史）；
- 每条候选的改动详情（diff、验证日志）在 `.rounds/pending/<快照ID>.md`；
- 总览表在 `.rounds/review.md`（当前最佳、各轮裁决一目了然）；
- 评分在下一次 job 启动或每轮结束时被处理（最多等一轮，约 30-40 分钟）。

## 文件说明

| 文件 | 谁写 | 用途 |
|---|---|---|
| `state.json` | round_guard | 当前最佳、各轮记录、未同步标签等 |
| `review.md` | round_guard | 人读的总览表 |
| `verdicts.txt` | **只由用户编辑** | 评分表；guard 只读不改 |
| `verdicts.processed.txt` | round_guard | 已处理评分的归档（防重复处理） |
| `pending/<快照ID>.md` | round_guard | 每个候选的 diff 与验证日志 |

## 快照标签

- 列出全部快照：`git ls-remote --tags origin 'snap/*'`
- 看某个快照的内容：`git show snap/20261016-061234-r3`
- 对比当前最佳：`git diff snap/20261016-061234-r3 origin/master`
- 快照会随轮次积累（每天约 7-20 个），如需清理可手动删除旧标签；
  `state.json` 与 `review.md` 的记录不受影响。

## 保护范围

`.github/`（循环自身）和 `.rounds/`（轮次状态）对 opencode 是禁区
（opencode 权限配置中已 deny），每轮结束 guard 也会把这两个目录的任何改动
回滚，防止 AI 破坏循环或伪造轮次状态。
