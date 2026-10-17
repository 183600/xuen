# xuen

一个"随机灵感词 × 外部 agent 模拟人类研究者"的 **TUI** 循环。

xuen **只调用外部 agent**（如 opencode）来完成所有思考：首次运行让外部 agent
生成领域词库；每轮从词库**纯随机**抽取灵感词（此步绝不调任何模型），把
「任务 + 灵感词 + 当前想法区/产物区 + 用户输入」拼成提示词交给外部 agent，
由它覆盖「想法区 / 产物区」。

## 界面（TUI）

```
┌ 修改想法区 ────────────────┐
│ [修改想法区]                │  ← 想法区每次被覆盖后，显示
│ <写入想法区的内容>           │     [修改想法区]<写入想法区的内容>
├ 修改产物区 ────────────────┤
│ [修改产物区]                │  ← 产物区每次被覆盖后，显示
│ <写入产物区的内容>           │     [修改产物区]<写入产物区的内容>
├ 输出日志 ──────────────────┤
│ 外部 agent 的 stdout/stderr │
│ 与循环消息（滚动）            │
├────────────────────────────┤
│ 状态栏                      │
└ 输入框 ⌨                   ┘
  输入内容会在下次调用 agent 时带给 agent
```

- 底部**输入框**：回车提交后进入队列，**下一次调用 agent 时**以
  「【用户输入】」段落拼进提示词带给 agent；
- `q` / `Ctrl+C` 退出（会先终止正在运行的外部 agent）。

## 整体流程

```
python main.py "任务"
   │
   ├─ ① 解析命令行 ──► 加载 config.yaml ──► CLI 覆盖同名配置 ──► 校验
   ├─ ② 初始化工作区：research.md（想法区/产物区）+ 写入助手 write_section.py
   ├─ ③ 构建外部 agent：ShellAgent（按 agent.command 模板，$prompt / $prompt_file）
   │
   ├─ ④ 领域词库（仅 words.pick > 0 时）
   │      words.txt 已存在且 reuse=true ──► 直接复用（--regen-words 强制重建）
   │      否则 ──► 外部 agent 分批生成 ──► 解析/清洗/去重 ──► 原子保存 words.txt
   │
   └─ ⑤ 研究循环 × N 轮（loop.iterations，支持 inf 无限循环）
          1. 纯随机抽词：random.sample 抽 n 个灵感词（此步绝不调任何模型）
          2. 取出底部输入框中积累的用户输入
          3. 拼提示词：extra_notes + 任务 + 轮次 + 灵感词
             + 当前想法区/产物区内容 + 用户输入 + 覆盖区块的写入指令
          4. 调用外部 agent（如 opencode run "$prompt"）：
             思考过程实时打到输出日志；经 write_section.py 整体覆盖想法区/产物区
          5. 重读 research.md 做 diff：哪个区块被改了，
             就在屏幕上显示 [修改xx区]<新内容>
          6. 轮次守卫（rounds.enabled，默认开）：快照 → 验证 → 晋升/还原
             （见下节；守卫异常一律降级，绝不阻断研究循环）
```

### 各阶段说明

**① 启动与配置**（`main.py` → `xuen/cli.py`）
- 解析命令行：任务描述（位置参数 / `--task-file` / 交互输入）、`--iterations`（整数或 `inf`）、
  `--pick`（每轮词数 n ≥ 0）、`--workspace`、`--regen-words`、`--no-tui`、`--no-color`；
- 加载 `config.yaml`（默认查找 `config.yaml` / `config.yml` / `xuen.yaml`，或 `-c` 指定），
  CLI 参数覆盖同名配置，覆盖 `--workspace` 后重新校验。

**② 界面选择**
- 默认启用 TUI（需安装 `textual` 且在真实终端中运行）；
- 条件不满足或指定 `--no-tui` 时，自动降级为纯终端输出。

**③ 工作区初始化**（`xuen/state.py`）
- 创建状态文件 `research.md`：标题为任务，含 `IDEA`（想法区）与 `ARTIFACT`（产物区）
  两个跨轮保留的标记区块；已存在则自动续用；
- 生成独立写入助手 `write_section.py`：外部 agent 用 stdin 整体覆盖指定区块
  （`python write_section.py idea|artifact`），内置跨进程文件锁，防止并发写互相覆盖。

**④ 外部 agent 调用**（`xuen/agents.py`）
- `agent.command` 命令模板支持两种占位符：`$prompt`（整段提示词按所在 shell 语境的
  引号规则转义后替换）、`$prompt_file`（提示词写入工作区内唯一临时文件后替换为路径，
  跨平台推荐）；
- 渲染器跟踪模板的 shell 语法：命令替换 `$(...)` / 反引号、算术语境、heredoc 正文、
  注释、`${...}` 参数展开等无法安全转义的区域不改写占位符（提示词里的 `$(...)` /
  反引号不会被注入执行）；占位符落在这些区域或模板用了 `$'...'` / `$"..."`
  / 数组赋值 `NAME=(...)` 等随 `/bin/sh` 方言变化（或会被 bash 的语法错误恢复
  把后续行当命令执行）的写法时，配置校验直接报错提示，而不是静默丢弃提示词；
- `agent.timeout` 超时后强制终止整个进程树；TUI 中 `q` / `Ctrl+C` 也会先终止正在运行的 agent；
  提示词超过系统单参数上限（`$prompt` 模式）时给出改用 `$prompt_file` 的明确建议并中止循环。

**⑤ 词库生成**（`xuen/words.py`）
- 分批向外部 agent 请求「为研究方向列出 N 个术语/关键词」，程序只负责解析、清洗、去重
  （剥序号/引号/冒号解释等），原子写入 `words.txt`；
- 词表不再增长则提前结束；生成失败时回退复用磁盘上的旧词库；
  `words.pick=0` 时跳过词库，循环中不给灵感词。

**⑥ 研究循环**（`xuen/runner.py`）
- 每轮顺序执行：纯随机抽词 → 收集用户输入 → 拼提示词 → 运行外部 agent → diff 区块变化
  → 轮次守卫（快照/验证/晋升或还原）；
- 提示词要求 agent：输出思考过程（供用户在屏幕前看），并完整保留区块标记行的前提下
  整体覆盖想法区 / 产物区；
- 失败处理：外部 agent 连续 3 次启动/执行失败则中止循环（退出码 1）；
  用户主动停止或至少成功一轮时不计为整体失败。

**⑦ 退出与持久化**
- 所有状态都落在工作区文件里（`research.md` / `words.txt` / `write_section.py` /
  `rounds/`），中断后重跑自动续上；
- 退出码：`0` 正常结束；`1` 所有轮次均执行失败；`2` 配置/参数错误；`130` 被 Ctrl+C 中断。

## 轮次守卫：每轮快照、候选/最佳分离、自动验证与评分

（`xuen/rounds.py`，配置段 `rounds:`，默认启用，`--no-rounds` 可关闭）

外部 agent 每轮【整体覆盖】想法区/产物区，旧实现里下一轮无条件继承最新
状态——某轮产出更差方案时，更好的前一轮就被覆盖丢失。守卫在不改变循环
主体的前提下加了一道闸：

```
每轮结束
  │
  ├─ 无改动 → 记「心跳」，不产生候选
  ├─ 区块标记损坏 → 守卫直接拒绝，还原最佳
  ├─ 有改动 → 快照为候选 rounds/cand-<id>.md（候选 ≠ 最佳，绝不直接当最佳）
  │        │
  │        ├─ 能用测试验证的跑测试：pytest → make test → npm test → go test
  │        │   级联探测（rounds.repo 指向的目标仓库；空 = 自动探测工作区
  │        │   所在 git 根）。全绿 → 晋升；全红 → 拒绝并还原
  │        ├─ 不能用测试验证的，二选一（rounds.fallback / rounds.verify）：
  │        │   · 用户评分：在 rounds/verdicts.txt 追加「<候选id> <0-10分> [评语]」，
  │        │     守卫在每轮开始/结束时兑现；候选先按最佳还原，拿到高分后
  │        │     前进式翻案（内容写回 research.md，不改写任何历史记录）
  │        │   · AI 评分：复用外部 agent 当评审员（rounds.judge_command
  │        │     可单独配更便宜的模型），对比候选与当前最佳打 0-10 分
  │        │
  │        ├─ 通过（测试全绿 / 评分 >= rounds.adopt_score）→ 晋升为最佳
  │        │    rounds/best.md + best.json 更新（前进式，只增不改）
  │        └─ 失败 / 挂起 → research.md 还原为当前最佳
  │             —— 下一轮【永远从最佳出发】，更差的候选无法污染后续轮
  └─ 全部事件追加进 rounds/history.jsonl（审计用，只增不改）
```

要点：

- **每轮保存快照**：任何一轮的产物都落在 `rounds/cand-<id>.md`，永不丢失；
- **候选与最佳分离**：`best.md` / `best.json` 只保存「当前最佳」；候选
  必须通过验证（或拿到高分）才晋升；
- **避免下一轮覆盖更好方案**：被拒绝/待评分的候选立即还原最佳——即使
  agent 连续产出多轮更差的内容，循环状态也始终停在最佳上；
- **agent 失败轮次**同样不留候选（半截产物不可信）并还原最佳；
- **守卫自身异常一律降级**（目录不可写、评审员超时、评分解析不出……），
  绝不阻断研究循环；解析不出分数时按「挂起」处理，既不采纳也不丢弃；
- **用户异步翻案**：给旧候选补分达到阈值时，旧快照被前进式晋升为最佳
  并写回 `research.md`，等价于回滚到它，但 `history.jsonl` 不改写一行。

CLI 快捷参数：`--no-rounds`（关闭守卫）、`--rounds-verify auto|tests|user|ai|off`、
`--rounds-fallback user|ai`、`--rounds-score N`（采纳阈值）。

## 使用

```bash
pip install -r requirements.txt        # 或 pip install -e .
cp config.example.yaml config.yaml     # 编辑 agent.command 等

# 配置外部 agent（config.yaml）：
# agent:
#   command: 'opencode run "$prompt"'

python main.py "设计一个新的优化器"              # TUI 模式（默认）
python main.py "设计一个新的优化器" --no-tui     # 纯终端输出
python main.py "设计一个新的优化器" --iterations inf --pick 3
python main.py "设计一个新的优化器" --regen-words
python main.py "设计一个新的优化器" --rounds-verify ai --rounds-score 8
python main.py "设计一个新的优化器" --no-rounds   # 退回旧行为：无快照无最佳

# 循环打磨某个代码仓库：把 rounds.repo 指向它，候选改动会被该仓库的
# 测试套件自动验证（pytest/make/npm/go 级联探测）
```

## 目录结构

```
xuen/
├── main.py                    # 入口
├── requirements.txt
├── pyproject.toml
├── config.example.yaml        # 复制为 config.yaml 使用
├── tests/                     # pytest 测试（轮次守卫单元/集成 + shell 渲染回归 + 冒烟）
└── xuen/
    ├── cli.py                 # 命令行
    ├── config.py              # 配置（含 rounds 轮次守卫段）
    ├── tui.py                 # TUI（textual）：区块面板 + 日志 + 底部输入框
    ├── sink.py                # 输出通道抽象（控制台 / TUI 共用）
    ├── ui.py                  # 纯终端输出（--no-tui）
    ├── state.py               # research.md（想法区/产物区）+ 写入助手脚本
    ├── words.py               # 词库：外部 agent 生成 / 解析 / 抽样
    ├── procs.py               # 跨平台进程工具
    ├── agents.py              # ShellAgent（外部 agent 命令）
    ├── rounds.py              # 轮次守卫：快照 / 候选与最佳分离 / 验证与评分
    └── runner.py              # 主循环编排
```

## 需求对照

| 需求 | 实现 |
|---|---|
| 只调用外部 agent（如 opencode） | 仅剩 `ShellAgent`；词库也由外部 agent 生成；已删除直连 LLM / 内置工具 / MCP 代码 |
| 配置 shell 命令调用外部 agent | `agent.command`，`$prompt` / `$prompt_file` 占位符 |
| TUI | `textual` 实现，默认启用（`--no-tui` 关闭） |
| 修改想法区显示 `[修改想法区]<写入想法区的内容>` | 「修改想法区」面板：想法区被覆盖后显示标记 + 新内容 |
| 修改产物区显示 `[修改产物区]<写入产物区的内容>` | 「修改产物区」面板：产物区被覆盖后显示标记 + 新内容 |
| 底部输入框，内容下次调用 agent 时带给 agent | 输入入队 → 下一轮提示词中带「【用户输入】」段落 |
| 想法区+产物区持久化 | `research.md`（标记区块），重跑自动续上 |
| 每轮保存快照，区分候选与当前最佳 | `rounds/cand-<id>.md` 候选快照 + `rounds/best.md|best.json` 当前最佳 + `history.jsonl` 审计日志 |
| 能用测试验证的就运行测试 | `rounds.repo`（默认自动探测 git 根）：pytest → make → npm → go 级联 |
| 不能测试验证的：用户评分 / AI 评分 | `verdicts.txt` 异步补分（可翻案旧候选） / 复用外部 agent 当评审员打分 |
| 避免下一轮覆盖更好方案 | 候选失败/挂起即还原最佳；下一轮永远从最佳出发；采纳旧快照用前进式晋升、不改写历史 |

**注意事项**：所有状态都在工作区文件里（`research.md` / `words.txt`），中断后重跑自动继续；
`agent.timeout` 控制单次外部调用超时。
