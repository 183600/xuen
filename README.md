# 玄根

一个"随机灵感词 × 人类研究者模拟"的 CLI 循环。

输入任务后先调用 LLM 生成领域词库；每轮从词库**纯随机**抽取灵感词（不调 LLM），由 LLM 以词为灵感模拟人类研究者思考，产生并持久化「想法区 / 产物区」。

## 整体流程

```
输入任务 ──► 首次运行：调 LLM 分批生成 1000 个领域词 ──► words.txt
                         │
                         ▼
   ┌─────────────── 循环（轮数可配，支持 inf）───────────────┐
   │ 1. 从词库纯随机抽 n 个词（n≥0，默认 2，此步绝不调 LLM）  │
   │ 2. LLM 以词为灵感，模拟人类研究者思考：                  │
   │    • generate_idea     覆盖想法区                       │
   │    • generate_artifact 覆盖产物区                       │
   │    • run_shell         执行命令（可做实验）              │
   │    • （可注入任意 MCP 工具；同一消息多工具并行执行）      │
   │ 3. 想法区+产物区持久化到 research.md，并打印到 stdout    │
   └──────────────────────────────────────────────────────────┘

shell 模式（agent.mode=shell，如 opencode run "$prompt"）：
   内置工具循环被替换 —— 程序把任务/灵感词/当前状态拼成提示词交给外部 agent，
   agent 通过 workspace/write_section.py 直接写文件来"覆盖想法区/产物区"，
   其 stdout/stderr 原样打到屏幕上。
```

## 目录结构

```
xuangen/
├── main.py                    # 入口
├── requirements.txt
├── pyproject.toml
├── config.example.yaml        # 复制为 config.yaml 使用
└── xuangen/
    ├── __init__.py
    ├── __main__.py
    ├── cli.py                 # 命令行
    ├── config.py              # 配置
    ├── ui.py                  # 终端输出
    ├── state.py               # research.md（想法区/产物区）+ 写入助手脚本
    ├── words.py               # 词库：生成/解析/抽样
    ├── llm.py                 # OpenAI 兼容客户端（流式+工具调用）
    ├── mcp.py                 # 极简 MCP stdio 客户端
    ├── procs.py               # 跨平台进程工具
    ├── tools.py               # direct 模式内置工具
    ├── agents.py              # DirectAgent / ShellAgent
    └── runner.py              # 主循环编排
```

## 使用

```bash
pip install -r requirements.txt        # 或 pip install -e .
cp config.example.yaml config.yaml     # 编辑模型、extra_notes 等

export OPENAI_API_KEY=sk-...

# direct 模式
python main.py "设计一个新的优化器"

# 常用参数
python main.py "设计一个新的优化器" --iterations inf --pick 3
python main.py "设计一个新的优化器" --regen-words --no-mcp
```

**shell 模式（如 opencode）** —— 在 `config.yaml` 中：

```yaml
agent:
  mode: shell
  command: 'opencode run "$prompt"'
```

然后同样 `python main.py "设计一个新的优化器"`。此模式下：内置工具循环被忽略，程序每轮把「任务 + 灵感词 + 当前想法区/产物区 + 写入说明」拼成提示词交给外部 agent；agent 用 `cat <<'EOF' | python workspace/write_section.py idea` 这类命令**直接写文件**实现"生成想法/生成产物"，其全部输出实时打到屏幕；程序随后读取 `research.md` 把两个区块打印出来。

**运行效果示例：**

```
──────── 第 3 轮 · 灵感词：「momentum」「loss landscape」 ────────
──────── 研究者思考 · 第 1 步 ────────
这两个词让我想到：把冲量看作曲面上惯性的离散化……我先重写想法区。
⚙ generate_artifact({"content": "# Sharpness-Aware …"})
✍ 产物区 已覆盖（已持久化到 research.md）
# Sharpness-Aware …
$ python -c "print(2**10)"
1024
──────── 💡 想法区（research.md 当前内容） ────────
…
```

## 需求对照

| 需求 | 实现 |
|---|---|
| 配置文件设置模型 / 给 LLM 的额外备注 | `model:` + `extra_notes:` |
| 配置 shell 命令调用其他 agent（`opencode run "$prompt"`） | `agent.mode: shell` + `agent.command`，`$prompt` / `$prompt_file` 占位符，输出原样上屏 |
| 输入任务后先调 LLM 生成 1000 个领域词并持久化 | `workspace/words.txt`，分批生成、去重，可复用 |
| 每轮随机抽 n 个词（n≥0，配置，默认 2），**此步不调 LLM** | `random.sample`，`words.pick` |
| LLM 以词为灵感模拟人类研究者思考 | 流式输出 + 跨轮会话历史 + 状态文件 |
| 三个工具：生成想法（覆盖想法区）/ 生成产物（覆盖产物区）/ shell | `generate_idea` / `generate_artifact` / `run_shell` |
| shell-agent 模式下两工具改为直接写文件 | `write_section.py` 助手 + 标记行协议 |
| 可添加其他 MCP 工具 | `mcp_servers:`（内置 stdio MCP 客户端，自动注入） |
| 工具可同时调用 | 同一消息多个 tool_calls 用线程池并行执行 |
| 想法区+产物区持久化到一个文件并输出到 stdout | `research.md`（标记区块），写入即回显，每轮结束再整体打印 |

**注意事项**：Ctrl+C 可随时安全中断（状态都在文件里，重跑自动从上次的 `research.md` 继续）；上下文变长时可调小 `agent.max_steps` / `tools.max_tool_output`；`XUANGEN_DEBUG=1` 可查看 MCP 服务器日志。
