"""主流程编排：词库 → （随机抽词 → 外部 agent 思考）循环。

所有展示都经 sink 上报；TUI 底部输入框的内容会在下一轮调用 agent 时
拼进提示词带给 agent。
"""
from __future__ import annotations

import itertools
import os
import shlex
from pathlib import Path
from typing import List, Optional

from . import state, words
from .agents import PromptTooLongError, ShellAgent
from .config import Config
from .rounds import RoundGuard
from .sink import SECTION_ARTIFACT, SECTION_IDEA, ConsoleSink, Sink


def run(cfg: Config, task: str, *, regen_words: bool = False,
        sink: Optional[Sink] = None) -> None:
    sink = sink or ConsoleSink()

    # resolve 成绝对路径：外部 agent 的工作目录不一定是 xuen 的 cwd，
    # 提示词里的 helper / state 路径必须对任何 cwd 都有效
    workspace = Path(cfg.workspace).expanduser().resolve()
    state_path = workspace / "research.md"
    words_path = workspace / "words.txt"

    # 先校验配置再建目录：配置错误退出时不应留下空的 workspace
    if not cfg.agent.command.strip():
        raise SystemExit(
            "配置错误：缺少外部 agent 命令。请在配置文件设置，例如：\n"
            "  agent:\n    command: 'opencode run \"$prompt\"'"
        )
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"工作区不可用：{workspace}（{e}）")

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
    try:
        helper = state.write_helper_script(workspace, state_path)
    except OSError as e:
        raise SystemExit(f"写入助手创建失败：{workspace / state.HELPER_NAME}（{e}）")
    sink.info(f"状态文件：{state_path}（外部写入助手：{helper.name}）")

    agent = ShellAgent(
        cfg.agent.command, workspace, cfg.agent.timeout,
        on_output=sink.agent_output, on_stderr=sink.agent_stderr,
    )
    sink.agent = agent  # 供 sink.stop_agent() 终止当前进程
    # 若用户在 agent 引用注入前就请求退出，注入后补做一次，避免慢速磁盘 IO
    # 造成的竞态窗口里继续启动外部 agent
    if sink.should_stop():
        sink.stop_agent()

    # 4) 轮次守卫：每轮快照、候选/最佳分离、自动验证与评分。
    #    启用失败（目录不可写等）一律降级为无守卫模式，不阻断研究循环
    guard: Optional[RoundGuard] = None
    if cfg.rounds.enabled:
        try:
            guard = RoundGuard(cfg, task, state_path, workspace, sink)
            guard.start()
        except OSError as e:
            sink.warn(f"轮次守卫启用失败，本轮循环降级为无守卫模式：{e}")
            guard = None

    # 2) 领域词库（持久化到 words.txt；已存在则复用；一律由外部 agent 生成）
    disk_words: List[str] = []
    if cfg.words.pick > 0:
        try:
            disk_words = words.load_words(words_path)
        except (OSError, UnicodeDecodeError) as e:
            # 词库文件损坏（含坏编码）时给出明确提示而不是 traceback；
            # 但 --regen-words 或 words.reuse=false 时反正要重新生成、
            # 旧词库不会被使用，不应被坏文件阻塞
            if not regen_words and cfg.words.reuse:
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
                info=sink.info, warn=sink.warn, stop=sink.should_stop,
            )
            # 生成结果为空时不落盘：避免空词库覆盖掉磁盘上已有的可用词库。
            # 生成未达目标（用户停止 / 批次失败 / 词表不再增长）时拿到的可能
            # 只是半截词表，若比磁盘上已有的词还少同样不能落盘：否则下次
            # reuse 会把完整旧词库永久换成残缺词表（词汇静默丢失）
            if word_list and len(word_list) < cfg.words.count \
                    and disk_words and len(word_list) < len(disk_words):
                if cfg.words.reuse and not regen_words:
                    sink.warn(f"词库生成未完成（{len(word_list)} 个），"
                              f"保留并复用磁盘上更完整的旧词库"
                              f"（{len(disk_words)} 个词）")
                    word_list = disk_words
                else:
                    # words.reuse=false 与 --regen-words 都是显式拒绝复用
                    # 旧词库，不能绕回旧词库；但也不能用残缺词表覆盖它，
                    # 本次循环临时使用生成结果
                    sink.warn(f"词库生成未完成（{len(word_list)}/{cfg.words.count}），"
                              "本次临时使用，不覆盖磁盘上更完整的旧词库")
            elif word_list:
                words.save_words(words_path, word_list)
                sink.ok(f"词库已保存：{words_path}（{len(word_list)} 个词）")
            elif disk_words and not regen_words and cfg.words.reuse:
                # 生成失败但磁盘上已有可用词库：回退复用，而不是直接中止。
                # words.reuse=false 是显式禁用复用，不能绕回旧词库。
                word_list = disk_words
                sink.warn(f"词库生成失败，回退复用已有词库（{len(disk_words)} 个词）")
            elif disk_words and regen_words:
                # --regen-words 明确要求忽略已有词库：生成失败时不能悄悄
                # 绕回旧词库（用户可能正是因为旧词库不可用才要求重建），
                # 保持空词库，由下面的「词库为空」检查给出明确失败
                sink.warn("词库生成失败；--regen-words 已按请求忽略磁盘上的"
                          f"旧词库（{len(disk_words)} 个词）")
        except (OSError, ValueError) as e:
            # ValueError：提示词含 NUL 字节时 Popen 抛 embedded null byte
            #（如 --task-file 读入二进制文件）；与启动失败同等对待
            raise SystemExit(f"词库生成失败：{e}")
        # 空词库不再谎报「先继续」：下面会以「词库为空」正式中止
        if word_list and len(word_list) < cfg.words.count:
            sink.warn(f"词库未达目标（{len(word_list)}/{cfg.words.count}），先继续")

    # 用户主动停止（如 TUI 按 q 中断词库生成）导致的空词库不算失败，
    # 否则正常退出会被记成非零退出码的「词库为空」错误
    if not word_list and cfg.words.pick > 0 and not sink.should_stop():
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
            except PromptTooLongError as e:
                # 提示词随区块内容只增不减，同模板重试必然同样失败：
                # 不再空转 3 轮，立即中止并给出可操作的建议
                sink.err(str(e))
                sink.err("重试不会成功，已中止循环")
                raise SystemExit(1)
            except (OSError, ValueError) as e:
                # ValueError：提示词含 NUL 字节时 Popen 抛 embedded null byte，
                # 属「启动失败」，计入轮次失败而非让 traceback 崩溃整个循环
                failures += 1
                consecutive_failures += 1
                sink.err(f"本轮失败：{e}")
                _guard_round_failed(guard, i, f"启动失败：{e}")
                if consecutive_failures >= 3 and not sink.should_stop():
                    # 运行期失败用退出码 1（消息走 sink.err），与预检错误的
                    # 字符串 SystemExit（退出码 2）区分，见 cli.main 注释
                    sink.err("外部 agent 连续 3 次启动失败，已中止循环")
                    raise SystemExit(1)
                continue
            if (agent.timed_out or agent.returncode) and not agent.user_killed:
                failures += 1
                consecutive_failures += 1
                _guard_round_failed(
                    guard, i,
                    "超时" if agent.timed_out
                    else f"退出码 {agent.returncode}")
                if consecutive_failures >= 3 and not sink.should_stop():
                    sink.err("外部 agent 连续 3 次执行失败，已中止循环")
                    raise SystemExit(1)
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
            # 轮次守卫：快照 → 验证 → 晋升/还原。守卫自身异常一律降级跳过，
            # 绝不阻断研究循环（但还原后的区块变化要重读并上报给用户）
            if guard is not None and not (
                    agent.timed_out or (agent.returncode not in (0, None))) \
                    and not agent.user_killed:
                try:
                    guard.on_round_end(i)
                    idea, artifact = _read_sections(state_path)
                except Exception as e:  # noqa: BLE001 —— 守卫降级原则
                    sink.warn(f"轮次守卫本轮异常（已降级跳过）：{e}")
                if idea != prev_idea:
                    prev_idea = idea
                    sink.section(SECTION_IDEA, idea or "（空）")
                if artifact != prev_artifact:
                    prev_artifact = artifact
                    sink.section(SECTION_ARTIFACT, artifact or "（空）")
    except SystemExit:
        # 连续失败等「提前中止」路径也要先收尾（打印最终区块状态 /
        # 通知 TUI 循环结束），与正常结束、键盘中断路径保持一致
        _guard_finish(guard)
        prev_idea, prev_artifact = _read_sections(state_path)
        sink.finish(prev_idea or "（空）", prev_artifact or "（空）")
        raise
    except KeyboardInterrupt:
        sink.warn("收到中断信号，结束循环（所有状态均已持久化）")
        _guard_finish(guard)
        prev_idea, prev_artifact = _read_sections(state_path)
        sink.finish(prev_idea or "（空）", prev_artifact or "（空）")
        # 向上传播中断，让 cli 以 130 退出；若在此吞掉，
        # 进程会以 0 退出且 cli 的 KeyboardInterrupt 分支成为死代码
        raise

    _guard_finish(guard)
    # guard.finish() 可能兑现循环期间补交的用户评分并写回区块：
    # 最终展示必须重读状态文件，否则屏幕会停在已被替换的旧内容上
    prev_idea, prev_artifact = _read_sections(state_path)
    sink.finish(prev_idea or "（空）", prev_artifact or "（空）")
    # 外部 agent 每轮都失败，对自动化调用者必须体现为非零退出码；
    # 若只是用户提前停止（rounds == 0）或至少成功一轮，则不算整体失败。
    if rounds and failures == rounds and not sink.should_stop():
        # sink.should_stop() 为真 = 用户主动请求停止（TUI 按 q 会先杀掉
        # 正在运行的 agent，该轮计入 failures）：这是正常退出，不能误报
        # 为「所有轮次均执行失败」，否则 TUI 会把用户退出记成失败退出码
        sink.err("外部 agent 所有轮次均执行失败")
        raise SystemExit(1)


# ----------------------------------------------------------------------
def _guard_finish(guard: Optional[RoundGuard]) -> None:
    """守卫收尾（应用待决用户评分 + 汇总）；守卫自身异常不外溅。"""
    if guard is None:
        return
    try:
        guard.finish()
    except Exception as e:  # noqa: BLE001 —— 守卫降级原则
        try:
            guard.sink.warn(f"轮次守卫收尾异常（忽略）：{e}")
        except Exception:
            pass


def _guard_round_failed(guard: Optional[RoundGuard], i: int, reason: str) -> None:
    """agent 失败的轮次：不留候选（半截产物不可信），仅记账。"""
    if guard is None:
        return
    try:
        guard.on_round_failed(i, reason)
    except Exception as e:  # noqa: BLE001 —— 守卫降级原则
        try:
            guard.sink.warn(f"轮次守卫记账异常（忽略）：{e}")
        except Exception:
            pass


def _read_sections(state_path: Path) -> tuple:
    try:
        text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # 文件缺失/读取失败/编码损坏：当作空区块，避免循环每轮 traceback 崩溃
        return "", ""
    return (state.get_section(text, state.SECTION_IDEA),
            state.get_section(text, state.SECTION_ARTIFACT))


def _shell_path(path: Path) -> str:
    """把路径安全地嵌入提示词，供外部 agent 的 shell 直接执行。

    POSIX 下不能用双引号包裹路径：shell 在双引号内仍会展开 $ 与反引号
    （工作区名为 "ws$x`id`" 时，外部 agent 按提示词执行会拿到错误路径、
    区块永远写不进去），必须用 shlex.quote 单引号保护；Windows cmd 不
    展开 $/反引号，双引号（含空格路径）即可，文件名也不可能含双引号。
    """
    text = str(path)
    if os.name == "nt":
        return f'"{text}"'
    return shlex.quote(text)


def _shell_prompt(cfg: Config, task: str, i: int, inspiration: List[str],
                  state_path: Path, helper: Path,
                  user_notes: List[str]) -> str:
    notes = cfg.extra_notes.strip()
    idea, artifact = _read_sections(state_path)
    ins = ("、".join(f"「{w}」" for w in inspiration)
           if inspiration else "（本轮没有随机灵感词，请自由发挥）")
    # 提示词会被外部 agent 按 shell 复制执行：路径必须按当前平台的 shell
    # 规则转义后再拼进去（简单路径下 shlex.quote 原样返回、不影响可读性）
    state_q, helper_q = _shell_path(state_path), _shell_path(helper)

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
状态文件 {state_q} 中有两个跨轮保留的区块，当前内容：

--- 想法区 ---
{idea or "（空）"}

--- 产物区 ---
{artifact or "（空）"}

【本轮要做的事】
1. 把你的思考过程直接输出（用户在屏幕前看）；
2. 用新的研究想法【整体覆盖】想法区；
3. 用本轮的具体产物【整体覆盖】产物区（方案 / 伪代码 / 推导 / 实验设计 / 实验结果等）。

【覆盖区块的方式】（推荐：用 shell 执行，内容经 stdin 传入）：
注意：下面的命令与结束标记都必须【顶格】（行首不能有空格）。
结束标记 XUEN_EOF 必须独占一行，否则 shell 会把后续内容一并
吞进区块内容里。

cat <<'XUEN_EOF' | python {helper_q} idea
这里是新的想法区内容……
XUEN_EOF

cat <<'XUEN_EOF' | python {helper_q} artifact
这里是新的产物区内容……
XUEN_EOF

也可以先写入临时文件再 `python {helper_q} idea < tmp.md`，
或用你自己的文件编辑能力直接修改 {state_q}——
但必须完整保留 IDEA / ARTIFACT 的 START / END 标记行。

完成后，用一两句话总结本轮的结论。"""
