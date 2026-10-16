# .rounds —— 轮次守卫（round_guard）的状态与评分目录

这个目录由 `.github/scripts/round_guard.py` 自动维护，配合
`.github/workflows/continuous-loop.yml` 实现「每轮快照、候选与最佳分离、
自动验证、AI 评分、用户翻案」，避免下一轮直接覆盖掉更好的方案。

## 核心概念

- **候选（candidate）**：opencode 每轮产出的改动。提交为 `snap/<时间>-r<轮次>`
  标签并**立即推送到远端**——无论后续验证结果如何，这一轮的产物都不会丢。
- **最佳（best）**：`master` 分支的当前内容。只有通过验证（或被 AI / 用户
  采纳）的候选才会成为最佳。**下一轮永远从最佳出发**，而不是从上一轮的
  候选出发。
- **自动验证**：round_guard 按优先级探测并运行测试命令
  （pytest → make test → npm test → go test → Python 编译检查 → `main.py --help`
  → 包导入冒烟）。
  - 候选通过 → 晋升为新的最佳（master 前进一个候选）；
  - 候选失败而最佳通过 → **拒绝候选、保留最佳**，工作区重置回最佳；
  - 没有可运行的验证 → 交给 **AI 评分**（见下），AI 不可用才等用户。
- **AI 评分（AI Judge）**：代替人类给"测试无法裁决"的候选打分（1-10 分，
  ≥ 阈值采纳）。介入时机：
  1. 无法自动验证的候选 —— AI 打分决定采纳/拒绝；
  2. 测试通过但改动了测试文件的候选 —— AI 复核，防止"删/弱化测试凑通过"；
  3. `review_promoted` 开启时，所有测试通过的候选也做一次 AI 例行复核
     （默认关闭）。
- **用户翻案**：优先级最高，任何时候都可以裁决/翻案（见下），包括推翻
  AI 或测试已经做出的结论。

## 裁决优先级

```
用户（verdicts.txt，可翻任何案）
  > 测试结果（客观，能跑就听测试的）
    > AI 评分（主观，只在测试无法裁决或疑似作弊时介入）
      > AI 不可用 -> 等待用户评分（候选已留快照，绝不丢失）
```

## AI 评分怎么工作

- **渠道**（按优先级自动选择，无需配置即可用）：
  1. OpenAI 兼容 API —— 在仓库 secrets 配置 `AIJUDGE_API_KEY` 后启用；
     可选 `AIJUDGE_BASE_URL`（仓库变量，默认 `https://api.openai.com/v1`）、
     `AIJUDGE_API_MODEL`（仓库变量，默认 `gpt-4o-mini`）。
  2. 本机 opencode —— CI 循环本身就安装了 opencode，免费模型零配置可用
     （默认 `opencode/deepseek-v4.1-flash-free`，可用 `AIJUDGE_OC_MODEL` 覆盖）。
- **评审在临时目录里进行**（材料写成 judge_task.md），评审模型碰不到仓库，
  也不能推送；输出只认 `SCORE / VERDICT / REASON` 三个字段，解析不出就当
  失败、退回等待用户，绝不卡住循环。
- **评分与阈值**：1-10 分；≥ `promote_score`（默认 7）采纳为最佳。
  模型拿不准时被要求保守打低分——宁可错过、不可错放。
- **每条 AI 裁决都留档**：`state.json` 的轮次记录（`by: "ai"`、分数、理由）、
  `.rounds/review.md` 总览表、`.rounds/pending/<id>.md` 评审文档。

## AI 评分配置（state.json 的 `ai_judge` 字段）

```jsonc
{
  "ai_judge": {
    "enabled": true,          // false = 完全停用，回到纯人工评分
    "min_score": null,        // 采纳阈值；null = 跟随 promote_score（默认 7）
    "review_promoted": false, // true = 测试通过的候选也要 AI 复核一遍
    "timeout": 180,           // 单次 AI 调用超时（秒）
    "max_diff_chars": 100000, // 评审材料里 diff 的字符上限
    "max_backlog": 3          // 每次 init 最多补评分的积压轮数
  }
}
```

环境变量可临时覆盖（优先级最高）：`AIJUDGE_ENABLED`、`AIJUDGE_MIN_SCORE`、
`AIJUDGE_REVIEW_PROMOTED`、`AIJUDGE_TIMEOUT` 等。

手动触发积压轮次的 AI 评分：
`python3 .github/scripts/round_guard.py ai-judge`（或 `--snap snap/<id>` 单条）。

## 怎么给候选评分（人工 / 翻案）

打开 `.rounds/verdicts.txt`，加一行：

```
snap/20261016-061234-r3: 8
```

- 分数 1-10，**≥ 7** 自动采纳为最佳（阈值可在 state.json 的 `promote_score` 调整）；
- 也可以直接写 `accept` / `reject`；
- **采纳一个旧快照 = 把仓库回滚到该方案**（用新提交实现，不改写历史）；
- 被测试或 AI 拒绝的候选同样可以翻案——每条候选永远留有快照；
- 每条候选的改动详情（diff、验证日志、AI 评分）在 `.rounds/pending/<快照ID>.md`；
- 总览表在 `.rounds/review.md`（当前最佳、各轮裁决一目了然）；
- 评分在下一次 job 启动或每轮结束时被处理（最多等一轮，约 30-40 分钟）。

## 文件说明

| 文件 | 谁写 | 用途 |
|---|---|---|
| `state.json` | round_guard | 当前最佳、各轮记录（含 AI 评分）、配置、未同步标签等 |
| `review.md` | round_guard | 人读的总览表（AI 裁决会标注分数） |
| `verdicts.txt` | **只由用户编辑** | 评分表；guard 只读不改 |
| `verdicts.processed.txt` | round_guard | 已处理评分的归档（防重复处理） |
| `pending/<快照ID>.md` | round_guard | 每个候选的 diff、验证日志与 AI 评分详情 |

## 快照标签

- 列出全部快照：`git ls-remote --tags origin 'snap/*'`
- 看某个快照的内容：`git show snap/20261016-061234-r3`
- 对比当前最佳：`git diff snap/20261016-061234-r3 origin/master`
- 快照会随轮次积累（每天约 7-20 个），如需清理可手动删除旧标签；
  `state.json` 与 `review.md` 的记录不受影响。

## 保护范围

`.github/`（循环自身）和 `.rounds/`（轮次状态）对 opencode 是禁区
（opencode 权限配置中已 deny），每轮结束 guard 也会把这两个目录的任何改动
回滚，防止 AI 破坏循环或伪造轮次状态。AI 评审员（AI Judge）也在临时目录
里工作，只能读到评审材料，改不了仓库。
