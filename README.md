# xuangen

一个"随机灵感词 × 外部 agent 模拟人类研究者"的 **TUI** 循环。

xuangen **只调用外部 agent**（如 opencode）来完成所有思考：首次运行让外部 agent
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
输入任务 ──► 首次运行：外部 agent 分批生成领域词 ──► words.txt
                        │
                        ▼
   ┌────────────── 循环（轮数可配，支持 inf）──────────────┐
   │ 1. 从词库纯随机抽 n 个词（n≥0，默认 2，不调任何模型）   │
   │ 2. 取底部输入框中积累的用户输入                         │
   │ 3. 拼提示词 → 调用外部 agent（如 opencode run "$prompt"）│
   │    agent 经 workspace/write_section.py 覆盖想法区/产物区 │
   │ 4. 哪个区块被改了，就在屏幕上显示 [修改xx区]<新内容>      │
   └────────────────────────────────────────────────────────┘
```

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
xuangen/
├── main.py                    # 入口
├── requirements.txt
├── pyproject.toml
├── config.example.yaml        # 复制为 config.yaml 使用
└── xuangen/
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
