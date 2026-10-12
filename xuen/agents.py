"""外部 agent 执行器：通过 shell 命令调用 opencode / claude / aider 等外部 agent。

xuen 不再内置直连 LLM 的模式 —— 所有的"研究者思考"都由外部 agent 完成：
程序把任务/灵感词/当前状态拼成提示词交给外部 agent，agent 通过
workspace/write_section.py 直接写文件来"覆盖想法区 / 产物区"。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

from .procs import kill_process_tree, popen_kwargs
from .ui import ui

OutputCallback = Callable[[str], None]


def _default_on_output(line: str) -> None:
    ui.raw(line)


def _default_on_stderr(line: str) -> None:
    ui.dim("│ " + line.rstrip("\n"))


def _quote(prompt: str) -> str:
    if os.name == "nt":  # Windows cmd 的引号规则
        return subprocess.list2cmdline([prompt])
    return shlex.quote(prompt)


class ShellAgent:
    """通过 shell 命令调用外部 agent（opencode / claude / aider …）。

    命令模板占位符：
      "$prompt" / $prompt   —— 替换为 shell 转义后的整段提示词
      $prompt_file          —— 提示词写入 工作区/.prompt.md，替换为该文件路径

    on_output / on_stderr：每行输出的回调（默认打到终端；TUI 模式下注入到界面）。
    """

    def __init__(
        self,
        command: str,
        workspace: Path,
        timeout: float = 1800.0,
        on_output: Optional[OutputCallback] = None,
        on_stderr: Optional[OutputCallback] = None,
    ):
        self.template = command
        self.workspace = workspace
        self.timeout = timeout
        self.on_output = on_output or _default_on_output
        self.on_stderr = on_stderr or _default_on_stderr
        self._proc: Optional[subprocess.Popen] = None
        self._killed = False
        # 记录「本轮运行期间用户发起过 kill」：超时定时器与用户 kill 几乎
        # 同时到达时，被用户杀掉的进程（rc=-9）会被误判成超时，需要靠
        # 这个标志甄别（_killed 是跨轮次的待处理请求标志，run() 读到即清，
        # 不能承担此职）
        self._user_killed = False
        # 保护 _killed/_proc：「run() 读取并清掉待处理 kill 请求」与
        # 「kill() 置位并取当前进程」必须各自原子完成，否则 kill()
        # 若恰好落在 run() 的读取与清除之间，这次停止请求会被静默丢弃
        # （详见 run() 中注释），刚拉起的 agent 会一直跑到超时
        self._kill_lock = threading.Lock()
        self.returncode: Optional[int] = None
        self.timed_out = False

    # 占位符必须是“完整词”：$prompt_out / $prompt_filex 之类只是以
    # 占位符为前缀的普通变量，不能被子串替换误伤；x$prompt 这类前面紧贴
    # 单词字符的也只是普通 shell 变量拼接，同样不能误替换
    _PLACEHOLDER_HEAD = r"(?<![A-Za-z0-9_])"
    _PLACEHOLDER_BOUNDARY = r"(?![A-Za-z0-9_])"

    def render_command(self, prompt: str) -> str:
        tpl = self.template
        f_sentinel = "\0XUEN_PROMPT_FILE\0"
        p_sentinel = "\0XUEN_PROMPT\0"
        # 先把两处占位符统一换成哨兵，最后才一次性替换成实际内容。
        # 若先插入内容再做另一处替换，后插入的内容（转义后的提示词 /
        # 提示词文件路径）里恰好含有占位符字面量时会被二次替换、破坏命令
        # （占位符被模板自带引号包住时，连引号一起换成哨兵，否则转义结果
        # 嵌在引号里会被当作字面值）
        for ph in ('"$prompt_file"', "'$prompt_file'"):
            tpl = tpl.replace(ph, f_sentinel)
        tpl = re.sub(self._PLACEHOLDER_HEAD + r"\$prompt_file"
                     + self._PLACEHOLDER_BOUNDARY, f_sentinel, tpl)
        for ph in ('"$prompt"', "'$prompt'"):
            tpl = tpl.replace(ph, p_sentinel)
        tpl = re.sub(self._PLACEHOLDER_HEAD + r"\$prompt"
                     + self._PLACEHOLDER_BOUNDARY, p_sentinel, tpl)

        if f_sentinel in tpl:
            pfile = self.workspace / ".prompt.md"
            pfile.write_text(prompt, encoding="utf-8")
            # 路径可能含空格：与 $prompt 一样做 shell 转义后再替换
            tpl = tpl.replace(f_sentinel, _quote(str(pfile.resolve())))
        return tpl.replace(p_sentinel, _quote(prompt))

    def kill(self) -> None:
        """强制终止当前正在运行的外部 agent（TUI 退出 / 中断时使用）。

        记 _killed 标志以覆盖竞态：kill 与 run() 起跑（Popen 到
        self._proc 赋值之间）并发时 proc 读到 None，若不记标志，
        刚拉起的外部 agent 会因 start_new_session 脱离终端会话而
        成为孤儿继续运行。注意只在杀不到进程时置位：若已把当前进程
        杀死，本次停止请求就已兑现，残留的 _killed 会被下一轮 run()
        读成「待处理请求」，把新拉起的 agent 立即误杀。
        """
        with self._kill_lock:
            proc = self._proc
            self._user_killed = True
            if proc is None:
                self._killed = True
        if proc is not None and proc.poll() is None:
            kill_process_tree(proc)

    def run(self, prompt: str) -> str:
        # 先复位上一轮的结果：若 Popen 抛 OSError，调用方看到的
        # returncode/timed_out 不能是上一次运行的残留值
        self.returncode = None
        self.timed_out = False
        # 注意：绝不能简单在此复位 self._killed —— kill() 可能在上一轮
        # should_stop() 检查通过之后、本轮 Popen 之前到达（kill 先到达、
        # self._proc 仍为 None，杀不到任何进程）；若丢弃这次停止请求，
        # 刚拉起的外部 agent（start_new_session 脱离终端会话）就成孤儿
        # 一直跑到超时。正确做法：读取并清掉旗标，把「待处理的 kill 请求」
        # 传到 Popen 后的补杀一并兑现；否则 _killed 一旦置位便永不复位，
        # 之后每次 run() 都会拉起进程又立刻误杀（返回 -9 且 timed_out=False，
        # 还会被误报为「异常退出」），agent 实例就此失效。
        with self._kill_lock:
            killed_before = self._killed
            self._killed = False
            self._user_killed = False
        command = self.render_command(prompt)
        shown = command if len(command) <= 300 else command[:300] + " …"
        self.on_stderr(f"$ {shown}\n")

        proc = subprocess.Popen(
            command, shell=True,
            stdin=subprocess.DEVNULL,  # 防止外部 agent 继承 stdin 与 TUI 争抢键盘/挂起
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            **popen_kwargs(),
        )
        self._proc = proc
        # kill 请求在 Popen 前（killed_before）或 Popen 与本赋值之间
        # （self._killed）到达：进程刚拉起，立即补杀
        if killed_before or self._killed:
            kill_process_tree(proc)
        out: List[str] = []
        killed = {"flag": False}

        def pump(pipe, sink: Optional[List[str]], cb: OutputCallback) -> None:
            try:
                for line in pipe:
                    if sink is not None:
                        sink.append(line)
                    try:
                        cb(line)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=pump, args=(proc.stdout, out, self.on_output), daemon=True)
        # stderr 不回读、仅回调：丢弃列表避免长会话无界内存增长
        t_err = threading.Thread(target=pump, args=(proc.stderr, None, self.on_stderr), daemon=True)
        t_out.start()
        t_err.start()

        def _on_timeout() -> None:
            if proc.poll() is not None:
                return  # 进程已正常退出，避免竞态误报超时/误杀
            kill_process_tree(proc)
            # 复查回收结果：kill 送达前进程可能已自然退出（退出码 >= 0），
            # 此时不算超时；主线程在 timer.join() 之后才读取 killed，
            # 因此这里的置位/不置位对主线程可见且无竞态。
            # 注意：该「自然退出」判定仅在 POSIX 下成立 —— POSIX 下被
            # SIGKILL 终止的进程退出码为负（-9），而 Windows 上 taskkill
            # 杀掉的进程退出码是正数（通常 1），若不做区分会把 Windows 上
            # 的真实超时误报成「异常退出」
            try:
                rc = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # kill 未能终结进程（kill_process_tree 内部吞掉了失败）：
                # 不能无限阻塞，否则主线程 timer.join() 会把整个运行卡死
                rc = None
            if rc is not None and rc >= 0 and (os.name != "nt" or rc == 0):
                # Windows 补充：taskkill 杀掉的进程退出码为正（通常 1），无法
                # 与自然失败（rc=1）区分；但 rc=0（干净成功）几乎不可能来自
                # taskkill，此时输出已完整写出，应算自然退出而非超时，
                # 否则完整结果会被当作超时截断内容丢弃
                return
            with self._kill_lock:
                # 用户主动 kill（TUI 按 q / Ctrl+C）与超时定时器几乎同时到达时，
                # 进程是被用户请求杀掉的，不能误报成超时
                if self._user_killed:
                    return
            killed["flag"] = True

        timer = threading.Timer(self.timeout, _on_timeout)
        timer.daemon = True
        timer.start()
        try:
            proc.wait()
        except KeyboardInterrupt:
            kill_process_tree(proc)
            raise
        finally:
            timer.cancel()
            # 超时回调可能已开始执行（正在 kill/复查退出码）：
            # 必须等它执行完，否则主线程读到的 killed 标志可能不是最终值，
            # 导致「真超时被报成异常退出」或反之
            timer.join()
            t_out.join(timeout=5)
            t_err.join(timeout=5)
            self._proc = None
        self.returncode = proc.returncode
        self.timed_out = killed["flag"]
        if self.timed_out:
            # :g 避免小数秒（如 0.5）被 :.0f 四舍五入成「0s」
            self.on_stderr(f"外部 agent 超时（{self.timeout:g}s），已强制终止\n")
        elif proc.returncode:
            self.on_stderr(f"外部 agent 异常退出（退出码 {proc.returncode}），"
                           "本轮可能未更新区块\n")
        return "".join(out)
