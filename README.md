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
- `agent.command` 命令模板支持两种占位符：`$prompt`（整段提示词 shell 转义后替换）、
  `$prompt_file`（提示词写入工作区内唯一临时文件后替换为路径，跨平台推荐）；
- `agent.timeout` 超时后强制终止整个进程树；TUI 中 `q` / `Ctrl+C` 也会先终止正在运行的 agent。

**⑤ 词库生成**（`xuen/words.py`）
- 分批向外部 agent 请求「为研究方向列出 N 个术语/关键词」，程序只负责解析、清洗、去重
  （剥序号/引号/冒号解释等），原子写入 `words.txt`；
- 词表不再增长则提前结束；生成失败时回退复用磁盘上的旧词库；
  `words.pick=0` 时跳过词库，循环中不给灵感词。

**⑥ 研究循环**（`xuen/runner.py`）
- 每轮顺序执行：纯随机抽词 → 收集用户输入 → 拼提示词 → 运行外部 agent → diff 区块变化；
- 提示词要求 agent：输出思考过程（供用户在屏幕前看），并完整保留区块标记行的前提下
  整体覆盖想法区 / 产物区；
- 失败处理：外部 agent 连续 3 次启动/执行失败则中止循环（退出码 1）；
  用户主动停止或至少成功一轮时不计为整体失败。

**⑦ 退出与持久化**
- 所有状态都落在工作区文件里（`research.md` / `words.txt` / `write_section.py`），
  中断后重跑自动续上；
- 退出码：`0` 正常结束；`1` 所有轮次均执行失败；`2` 配置/参数错误；`130` 被 Ctrl+C 中断。

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
```

## 目录结构

```
xuen/
├── main.py                    # 入口
├── requirements.txt
├── pyproject.toml
├── config.example.yaml        # 复制为 config.yaml 使用
└── xuen/
    ├── cli.py                 # 命令行
    ├── config.py              # 配置
    ├── tui.py                 # TUI（textual）：区块面板 + 日志 + 底部输入框
    ├── sink.py                # 输出通道抽象（控制台 / TUI 共用）
    ├── ui.py                  # 纯终端输出（--no-tui）
    ├── state.py               # research.md（想法区/产物区）+ 写入助手脚本
    ├── words.py               # 词库：外部 agent 生成 / 解析 / 抽样
    ├── procs.py               # 跨平台进程工具
    ├── agents.py              # ShellAgent（外部 agent 命令）
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

**注意事项**：所有状态都在工作区文件里（`research.md` / `words.txt`），中断后重跑自动继续；
`agent.timeout` 控制单次外部调用超时。

## Continuous Loop（自动修 bug）的轮次保护机制

本仓库由 `.github/workflows/continuous-loop.yml` 驱动：opencode 反复
「判断是否有 bug，如果有就修复」。为避免**下一轮直接覆盖掉更好的方案**，
每轮结束后都经过轮次守卫 `.github/scripts/round_guard.py`（详见 `.rounds/README.md`）：

1. **每轮保存快照**：本轮改动提交为 `snap/<时间>-r<轮次>` 标签并立即推送，
   无论验证结果如何，这一轮的产物都不会丢；
2. **候选 ≠ 最佳**：`master` 分支只保存「当前最佳」；候选只存在于快照标签
   与 `.rounds/` 的记录中，不会直接覆盖 master；
3. **能自动验证的就跑测试**：round_guard 自动探测并运行
   `pytest`（本仓库 `tests/`）→ Python 编译检查 → `main.py --help` → 包导入冒烟：
   - 候选通过 → 晋升为新的最佳；
   - 候选失败而最佳通过 → 拒绝候选、保留最佳，**下一轮从最佳重新出发**；
4. **不能自动验证的让用户评分**：在 `.rounds/verdicts.txt` 写一行
   `snap/<快照ID>: 8`（1-10 分，≥7 采纳）或 `accept` / `reject`；
   采纳旧快照即回滚到该方案。总览见 `.rounds/review.md`，
   每条候选的 diff 见 `.rounds/pending/`。
