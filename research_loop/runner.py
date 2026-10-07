"""主流程编排：词库 → （随机抽词 → 研究者思考）循环。"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import List, Optional

from . import state, words
from .agents import DirectAgent, ShellAgent
from .config import Config
from .llm import LLMClient, LLMError
from .mcp import MCPManager
from .tools import ToolBox
from .ui import ui


def run(cfg: Config, task: str, *, regen_words: bool = False, use_mcp: bool = True) -> None:
    workspace = Path(cfg.workspace).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    state_path = workspace / "research.md"
    words_path = workspace / "words.txt"

    ui.banner()
    ui.info(f"任务：{task}")
    ui.info(f"工作区：{workspace.resolve()}")
    ui.info(f"Agent 模式：{cfg.agent.mode}｜每轮灵感词 n={cfg.words.pick}"
            f"｜轮数：{'∞' if cfg.loop.iterations is None else cfg.loop.iterations}")

    word_mode = _word_mode(cfg)
    if (cfg.agent.mode == "shell" or word_mode == "shell") and not cfg.agent.command.strip():
        raise SystemExit(
            "配置错误：需要外部 agent 命令。请在配置文件设置，例如：\n"
            "  agent:\n    mode: shell\n    command: 'opencode run \"$prompt\"'"
        )

    # 1) 状态文件 + 区块写入助手
    state.ensure_state_file(state_path, task)
    helper = state.write_helper_script(workspace, state_path)
    ui.info(f"状态文件：{state_path}（外部写入助手：{helper.name}）")

    # 2) 领域词库（持久化到 words.txt；已存在则复用）
    word_list = [] if regen_words else words.load_words(words_path)
    if word_list and cfg.words.reuse and not regen_words:
        ui.ok(f"复用已有词库：{words_path}（{len(word_list)} 个词）")
    else:
        try:
            word_list = _build_word_bank(cfg, task, workspace, words_path, word_mode)
        except (LLMError, OSError) as e:
            raise SystemExit(f"词库生成失败：{e}")

    if not word_list:
        if cfg.words.pick > 0:
            raise SystemExit(f"词库为空，无法继续。文件：{words_path}")
        ui.warn("词库为空，但 n=0，继续无灵感词模式")

    # 3) Agent 与循环
    mcp = MCPManager()
    direct_agent: Optional[DirectAgent] = None
    shell_agent: Optional[ShellAgent] = None
    history: List[dict] = []
    try:
        if cfg.agent.mode == "direct":
            llm = LLMClient(cfg.model)
            if not llm.api_key:
                ui.warn(f"未检测到 API key（{cfg.model.api_key_env}），直连请求可能失败")
            if use_mcp and cfg.mcp_servers:
                ui.rule("启动 MCP 服务器")
                mcp.start_all(cfg.mcp_servers)
            toolbox = ToolBox(cfg, workspace, state_path, mcp)
            direct_agent = DirectAgent(llm, toolbox, cfg)
            history = [{"role": "system", "content": _system_prompt(cfg, task)}]
        else:
            shell_agent = ShellAgent(cfg.agent.command, workspace, cfg.agent.timeout)

        counter = (itertools.count(1) if cfg.loop.iterations is None
                   else range(1, cfg.loop.iterations + 1))
        try:
            for i in counter:
                # 第一步：纯随机抽词（不调用 LLM）
                inspiration = words.sample_words(word_list, cfg.words.pick)
                label = ("、".join(f"「{w}」" for w in inspiration)
                         if inspiration else "（无灵感词，自由发挥）")
                ui.rule(f"第 {i} 轮 · 灵感词：{label}")
                try:
                    if direct_agent is not None:
                        history = direct_agent.run_round(
                            history,
                            _round_message(i, inspiration, state_path if i == 1 else None),
                        )
                    else:
                        assert shell_agent is not None
                        shell_agent.run(_shell_prompt(cfg, task, i, inspiration,
                                                      state_path, helper))
                except (LLMError, OSError) as e:
                    ui.err(f"本轮失败：{e}")
                    continue
                _show_state(state_path)
        except KeyboardInterrupt:
            ui.warn("收到中断信号，结束循环（所有状态均已持久化）")
    finally:
        mcp.shutdown()

    ui.rule("研究循环结束 · 最终状态")
    _show_state(state_path)


# ----------------------------------------------------------------------
def _word_mode(cfg: Config) -> str:
    if cfg.words.via in ("direct", "shell"):
        return cfg.words.via
    if cfg.agent.mode == "shell" and not cfg.model.resolve_api_key():
        return "shell"
    return "direct"


def _build_word_bank(cfg, task, workspace, words_path, mode) -> List[str]:
    if mode == "direct":
        ui.rule(f"调用 LLM 生成领域词库（目标 {cfg.words.count} 个，每批 {cfg.words.batch} 个）")
        llm = LLMClient(cfg.model)
        bank = words.generate_words_direct(llm, task, cfg.words.count, cfg.words.batch)
    else:
        ui.rule(f"通过外部 agent 生成领域词库（目标 {cfg.words.count} 个）")
        agent = ShellAgent(cfg.agent.command, workspace, cfg.agent.timeout)
        bank = words.generate_words_shell(agent, task, cfg.words.count, cfg.words.batch)
    words.save_words(words_path, bank)
    ui.ok(f"词库已保存：{words_path}（{len(bank)} 个词）")
    if len(bank) < cfg.words.count:
        ui.warn(f"词库未达目标（{len(bank)}/{cfg.words.count}），先继续")
    return bank


def _show_state(state_path: Path) -> None:
    text = state_path.read_text(encoding="utf-8")
    idea = state.get_section(text, state.SECTION_IDEA) or "（空）"
    artifact = state.get_section(text, state.SECTION_ARTIFACT) or "（空）"
    ui.rule("💡 想法区（research.md 当前内容）")
    ui.raw(idea + "\n")
    ui.rule("📦 产物区（research.md 当前内容）")
    ui.raw(artifact + "\n")


def _system_prompt(cfg: Config, task: str) -> str:
    notes = cfg.extra_notes.strip() or "（无）"
    shell_part = ("\n- run_shell(command)：执行任意 shell 命令"
                  "（写代码、跑实验、安装依赖、调用本地工具均可）。"
                  if cfg.tools.shell else "")
    return f"""你是一场「灵感驱动研究循环」中的人类研究员模拟器。

# 任务
{task}

# 用户对你的额外备注（来自配置文件）
{notes}

# 机制说明
- 每一轮系统会从任务领域的词库中随机抽取灵感词给你（数量可能为 0，此时请自由发挥）。
- 请把灵感词当作思维触发器：联想、类比、迁移、质疑，像真实研究者那样一步步推进研究。
- 工作区文件 research.md 中有两个跨轮保留的区块：
  * 『想法区』：当前的研究想法、假设与思路；
  * 『产物区』：具体成果（方案、伪代码、公式推导、实验设计、实验结果等）。
- 内置工具（都会整体覆盖对应区块）：
  * generate_idea(content)：覆盖『想法区』；
  * generate_artifact(content)：覆盖『产物区』。{shell_part}
- 你可以在同一条消息里并行调用多个工具。
- 你的全部思考、工具调用与工具输出都会实时展示在用户屏幕上，请自然地展示推理过程。
- 每一轮请至少更新一次想法区或产物区（可以只更新其一）。"""


def _round_message(i: int, inspiration: List[str], state_path: Optional[Path]) -> str:
    parts = [f"【第 {i} 轮】"]
    if inspiration:
        parts.append("随机灵感词：" + "、".join(f"「{w}」" for w in inspiration))
    else:
        parts.append("本轮没有随机灵感词，请自由发挥。")
    if state_path is not None:  # 第一轮（或断点续跑）附带当前状态
        text = state_path.read_text(encoding="utf-8")
        idea = state.get_section(text, state.SECTION_IDEA) or "（空）"
        artifact = state.get_section(text, state.SECTION_ARTIFACT) or "（空）"
        parts.append("当前状态文件内容（跨轮保留）：\n"
                     f"--- 想法区 ---\n{idea}\n--- 产物区 ---\n{artifact}")
    parts.append("请基于灵感词继续思考并推进研究；形成阶段性结论时，用工具更新想法区/产物区。")
    return "\n\n".join(parts)


def _shell_prompt(cfg, task, i, inspiration, state_path, helper) -> str:
    notes = cfg.extra_notes.strip()
    text = state_path.read_text(encoding="utf-8")
    idea = state.get_section(text, state.SECTION_IDEA) or "（空）"
    artifact = state.get_section(text, state.SECTION_ARTIFACT) or "（空）"
    ins = ("、".join(f"「{w}」" for w in inspiration)
           if inspiration else "（本轮没有随机灵感词，请自由发挥）")
    return f"""{notes}

【任务】{task}

你正在参加一场「灵感驱动研究循环」的第 {i} 轮，请模拟一位人类研究者的思考过程。
本轮随机灵感词：{ins}

状态文件 {state_path} 中有两个跨轮保留的区块，当前内容：

--- 想法区 ---
{idea}

--- 产物区 ---
{artifact}

【本轮要做的事】
1. 把你的思考过程直接输出（用户在屏幕前看）；
2. 用新的研究想法【整体覆盖】想法区；
3. 用本轮的具体产物【整体覆盖】产物区（方案 / 伪代码 / 推导 / 实验设计 / 实验结果等）。

【覆盖区块的方式】（推荐：用 shell 执行，内容经 stdin 传入）：
  cat <<'EOF' | python "{helper}" idea
  这里是新的想法区内容……
  EOF

  cat <<'EOF' | python "{helper}" artifact
  这里是新的产物区内容……
  EOF

也可以先写入临时文件再 `python "{helper}" idea < tmp.md`，
或用你自己的文件编辑能力直接修改 {state_path}——
但必须完整保留 IDEA / ARTIFACT 的 START / END 标记行。

完成后，用一两句话总结本轮的结论。"""
