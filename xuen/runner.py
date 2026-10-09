"""主流程编排：词库 → （随机抽词 → 外部 agent 思考）循环。

所有展示都经 sink 上报；TUI 底部输入框的内容会在下一轮调用 agent 时
拼进提示词带给 agent。
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import List, Optional

from . import state, words
from .agents import ShellAgent
from .config import Config
from .sink import SECTION_ARTIFACT, SECTION_IDEA, ConsoleSink, Sink


def run(cfg: Config, task: str, *, regen_words: bool = False,
        sink: Optional[Sink] = None) -> None:
    sink = sink or ConsoleSink()

    # resolve 成绝对路径：外部 agent 的工作目录不一定是 xuen 的 cwd，
    # 提示词里的 helper / state 路径必须对任何 cwd 都有效
    workspace = Path(cfg.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_path = workspace / "research.md"
    words_path = workspace / "words.txt"

    if not cfg.agent.command.strip():
        raise SystemExit(
            "配置错误：缺少外部 agent 命令。请在配置文件设置，例如：\n"
            "  agent:\n    command: 'opencode run \"$prompt\"'"
        )

    sink.info(f"任务：{task}")
    sink.info(f"工作区：{workspace.resolve()}")
    sink.info(f"外部 agent：{cfg.agent.command}"
              f"｜每轮灵感词 n={cfg.words.pick}"
              f"｜轮数：{'∞' if cfg.loop.iterations is None else cfg.loop.iterations}")

    # 1) 状态文件 + 区块写入助手
    try:
        state.ensure_state_file(state_path, task)
    except (OSError, UnicodeDecodeError) as e:
        # 状态文件损坏（含坏编码）时给出明确提示而不是 traceback
        raise SystemExit(f"状态文件读取失败：{e}（可备份后删除 {state_path} 重建）")
    helper = state.write_helper_script(workspace, state_path)
    sink.info(f"状态文件：{state_path}（外部写入助手：{helper.name}）")

    agent = ShellAgent(
        cfg.agent.command, workspace, cfg.agent.timeout,
        on_output=sink.agent_output, on_stderr=sink.agent_stderr,
    )
    sink.agent = agent  # 供 sink.stop_agent() 终止当前进程

    # 2) 领域词库（持久化到 words.txt；已存在则复用；一律由外部 agent 生成）
    try:
        disk_words = words.load_words(words_path)
    except (OSError, UnicodeDecodeError) as e:
        # 词库文件损坏（含坏编码）时给出明确提示而不是 traceback；
        # 但 --regen-words 模式下反正要重新生成，不应被旧文件阻塞
        if not regen_words:
            raise SystemExit(f"词库读取失败：{e}")
        sink.warn(f"已有词库读取失败（{e}），将重新生成")
        disk_words = []
    word_list = disk_words if not regen_words else []
    if word_list and cfg.words.reuse:
        sink.ok(f"复用已有词库：{words_path}（{len(word_list)} 个词）")
    elif cfg.words.pick == 0:
        sink.info("words.pick=0：本轮循环不使用灵感词，跳过词库生成")
    else:
        try:
            sink.info(f"通过外部 agent 生成领域词库（目标 {cfg.words.count} 个，"
                      f"每批 {cfg.words.batch} 个）")
            word_list = words.generate_words_shell(
                agent, task, cfg.words.count, cfg.words.batch,
                info=sink.info, warn=sink.warn,
            )
            # 生成结果为空时不落盘：避免空词库覆盖掉磁盘上已有的可用词库
            if word_list:
                words.save_words(words_path, word_list)
                sink.ok(f"词库已保存：{words_path}（{len(word_list)} 个词）")
            elif disk_words:
                # 生成失败但磁盘上已有可用词库：回退复用，而不是直接中止
                word_list = disk_words
                sink.warn(f"词库生成失败，回退复用已有词库（{len(disk_words)} 个词）")
        except OSError as e:
            raise SystemExit(f"词库生成失败：{e}")
        if len(word_list) < cfg.words.count:
            sink.warn(f"词库未达目标（{len(word_list)}/{cfg.words.count}），先继续")

    if not word_list and cfg.words.pick > 0:
        raise SystemExit(f"词库为空，无法继续。文件：{words_path}")

    # 3) 循环
    prev_idea, prev_artifact = _read_sections(state_path)
    sink.section(SECTION_IDEA, prev_idea or "（空）")
    sink.section(SECTION_ARTIFACT, prev_artifact or "（空）")

    counter = (itertools.count(1) if cfg.loop.iterations is None
               else range(1, cfg.loop.iterations + 1))
    rounds = failures = consecutive_failures = 0
    try:
        for i in counter:
            if sink.should_stop():
                break
            # 第一步：纯随机抽词（不调用任何 LLM）
            inspiration = words.sample_words(word_list, cfg.words.pick)
            label = ("、".join(f"「{w}」" for w in inspiration)
                     if inspiration else "（无灵感词，自由发挥）")
            sink.round_header(i, label)
            # 底部输入框的内容：在下次调用 agent 时带给 agent
            user_notes = sink.drain_user_input()
            rounds += 1
            try:
                agent.run(_shell_prompt(cfg, task, i, inspiration,
                                        state_path, helper, user_notes))
            except OSError as e:
                failures += 1
                consecutive_failures += 1
                sink.err(f"本轮失败：{e}")
                if consecutive_failures >= 3:
                    raise SystemExit("外部 agent 连续 3 次启动失败，已中止循环")
                continue
            if agent.timed_out or agent.returncode:
                failures += 1
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    raise SystemExit("外部 agent 连续 3 次执行失败，已中止循环")
            else:
                consecutive_failures = 0
            # 读取状态文件：哪个区块被覆盖了就上报哪个（屏幕显示 [修改xx区]<内容>）
            idea, artifact = _read_sections(state_path)
            if idea != prev_idea:
                prev_idea = idea
                sink.section(SECTION_IDEA, idea or "（空）")
            if artifact != prev_artifact:
                prev_artifact = artifact
                sink.section(SECTION_ARTIFACT, artifact or "（空）")
    except KeyboardInterrupt:
        sink.warn("收到中断信号，结束循环（所有状态均已持久化）")
        sink.finish(prev_idea or "（空）", prev_artifact or "（空）")
        # 向上传播中断，让 cli 以 130 退出；若在此吞掉，
        # 进程会以 0 退出且 cli 的 KeyboardInterrupt 分支成为死代码
        raise

    sink.finish(prev_idea or "（空）", prev_artifact or "（空）")
    # 外部 agent 每轮都失败，对自动化调用者必须体现为非零退出码；
    # 若只是用户提前停止（rounds == 0）或至少成功一轮，则不算整体失败。
    if rounds and failures == rounds:
        raise SystemExit("外部 agent 所有轮次均执行失败")


# ----------------------------------------------------------------------
def _read_sections(state_path: Path) -> tuple:
    try:
        text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # 文件缺失/读取失败/编码损坏：当作空区块，避免循环每轮 traceback 崩溃
        return "", ""
    return (state.get_section(text, state.SECTION_IDEA),
            state.get_section(text, state.SECTION_ARTIFACT))


def _shell_prompt(cfg: Config, task: str, i: int, inspiration: List[str],
                  state_path: Path, helper: Path,
                  user_notes: List[str]) -> str:
    notes = cfg.extra_notes.strip()
    idea, artifact = _read_sections(state_path)
    ins = ("、".join(f"「{w}」" for w in inspiration)
           if inspiration else "（本轮没有随机灵感词，请自由发挥）")

    user_part = ""
    if user_notes:
        joined = "\n".join(f"- {n}" for n in user_notes)
        user_part = f"""
【用户输入】（用户在底部输入框中给你的话，请认真对待并在本轮体现）：
{joined}
"""

    return f"""{notes}

【任务】{task}

你正在参加一场「灵感驱动研究循环」的第 {i} 轮，请模拟一位人类研究者的思考过程。
本轮随机灵感词：{ins}
{user_part}
状态文件 {state_path} 中有两个跨轮保留的区块，当前内容：

--- 想法区 ---
{idea or "（空）"}

--- 产物区 ---
{artifact or "（空）"}

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
