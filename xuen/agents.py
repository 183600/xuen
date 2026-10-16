"""外部 agent 执行器：通过 shell 命令调用 opencode / claude / aider 等外部 agent。

xuen 不再内置直连 LLM 的模式 —— 所有的"研究者思考"都由外部 agent 完成：
程序把任务/灵感词/当前状态拼成提示词交给外部 agent，agent 通过
workspace/write_section.py 直接写文件来"覆盖想法区 / 产物区"。
"""
from __future__ import annotations

import errno
import os
import re
import shlex
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, List, Optional

from .procs import kill_process_tree, popen_kwargs
from .ui import ui

OutputCallback = Callable[[str], None]


class PromptTooLongError(ValueError):
    """提示词作为命令行参数超出系统长度上限（E2BIG）。

    继承 ValueError：调用方原有的 (OSError, ValueError) 失败处理仍适用。
    $prompt 模板把整段提示词塞进 sh -c 的单个参数（Linux 单参数上限约
    128KB），提示词会随想法区/产物区内容逐轮增长，最终必然触达上限；
    $prompt_file 模板只传文件路径，不受影响。
    """


def _default_on_output(line: str) -> None:
    ui.raw(line)


def _default_on_stderr(line: str) -> None:
    ui.dim("│ " + line.rstrip("\n"))


def _quote(prompt: str) -> str:
    if os.name == "nt":  # Windows cmd 的引号规则
        return subprocess.list2cmdline([prompt])
    return shlex.quote(prompt)


# 占位符边界：与 config._validate 的正则一致，A-Za-z0-9_ 是「单词字符」
_WORD_CHAR = re.compile(r"[A-Za-z0-9_]")

# 占位符探测令牌（供 command_receives_prompt 的 dry_run 渲染使用）：
# 全为单词字符，途经任意引号语境/转义后仍原样保留在渲染结果里
_PLACEHOLDER_PROBE = "XUENPROMPTPROBE7C4F1D"


def _escape_in_single_quotes(value: str) -> str:
    """把值安全地嵌进已打开的单引号内部（模板形如 '前缀 $prompt'）。

    单引号内无法用反斜杠转义单引号，只能用「闭合-转义-重开」写法：
    值中的 ' 输出为 '\\''，shell 解析后仍是原值。shlex.quote 生成的是
    带引号的完整 token，直接塞进已有引号会被当成字面值。
    """
    return value.replace("'", "'\\''")


def _escape_in_double_quotes(value: str) -> str:
    """把值安全地嵌进已打开的双引号内部（模板形如 "前缀 $prompt"）。

    双引号内 $ ` " \\ 仍有特殊含义：不转义的话，提示词里的 $(cmd)、`
    cmd`、$VAR 会被 shell 展开执行，引号会提前闭合导致参数被拆碎。
    反斜杠必须最先转义，避免把后续转义产生的反斜杠二次转义。
    """
    return (value.replace("\\", "\\\\").replace('"', '\\"')
                 .replace("$", "\\$").replace("`", "\\`"))


# 这些字符出现在「整体跳过」的语境内时，可能隐藏（或吞掉）配对的结束符：
# 引号里的 } / ] / ) 不终结展开，反斜杠会转义结束符，反引号与 $( 命令
# 替换内部还有自己的解析上下文。只用深度配对会提前停在假结束符上，余下
# 模板被按外层引号语境解析——占位符可能被插进错误语境（单引号落在双引号
# 里只是字面量），提示词里的 $(...)/`...` 会被真正执行（注入）。
# 与 heredoc 正文一致：遇到即整体吞到模板结尾（宁可拒绝模板，也不把
# 占位符插进无法确保安全的位置）。
_UNSAFE_IN_SKIPPED_CONTEXT = "'\"`\\"
# 算术/下标语境里嵌套的替换与展开可能含有引号或花括号，一律按无法
# 安全配对处理，整体吞到模板结尾
_UNSAFE_SUBSTITUTION_HEADS = ("$(", "$[", "${")
# ${...} 里的嵌套 ${（无引号等构造时）可以安全计深度，故不在此列
_UNSAFE_PARAMETER_HEADS = ("$(", "$[")


def _has_unsafe_construct(tpl: str, j: int,
                          heads: tuple = _UNSAFE_SUBSTITUTION_HEADS) -> bool:
    """位置 j 处的字符是否使「整体跳过」语境无法安全找结束符。"""
    return (tpl[j] in _UNSAFE_IN_SKIPPED_CONTEXT
            or tpl.startswith(heads, j))


def _is_case_keyword(tpl: str, i: int) -> bool:
    """位置 i 起是否为裸 case 保留字（允许 \\+换行 续行把单词拆开）。

    shell 在分词前会先删掉反斜杠-换行（续行），因此 `ca\\<换行>se`
    仍被识别为 case 保留字；扫描器若只按字面匹配 "case" 会漏掉这种
    写法，其后的 pattern ) 又会破坏括号配对（见 _render_posix 说明）。
    单词边界两侧同样先跨过续行再判断，且反斜杠转义其他字符、引号都
    会让单词不再是保留字（`c\\ase`、`c'a'se` 均不是 case）。
    """
    n = len(tpl)

    def skip_continuations(pos: int) -> int:
        while pos + 1 < n and tpl[pos] == "\\" and tpl[pos + 1] == "\n":
            pos += 2
        return pos

    k = i
    while k >= 2 and tpl[k - 1] == "\n" and tpl[k - 2] == "\\":
        k -= 2
    if k > 0 and _WORD_CHAR.match(tpl[k - 1]):
        return False
    j = i
    for letter in "case":
        j = skip_continuations(j)
        if j >= n or tpl[j] != letter:
            return False
        j += 1
    j = skip_continuations(j)
    return j >= n or not _WORD_CHAR.match(tpl[j])


def _arithmetic_end(tpl: str, i: int) -> int:
    """返回位置 i 处 $((...)) 算术展开结束后的下标（吞掉匹配的两个右括号）。

    算术表达式内部可以嵌套括号（如 $(( (1+2) * 3 ))），用括号深度配对。
    模板缺少匹配括号时按 shell 语法错误处理：一直算到模板结尾，剩余部分
    不再参与占位符替换（与 heredoc 找不到终止符时的策略一致）。
    引号/反引号/反斜杠/嵌套替换可能隐藏右括号（如 $(( $(echo ")") ))），
    使「第一个深度归零的 )」不再是真实结束位置；这些字符在表达式里的
    语义还随 shell 方言变化，遇到即整体吞到模板结尾（见
    _UNSAFE_IN_SKIPPED_CONTEXT 的说明）。
    """
    depth = 1
    j = i + 3
    n = len(tpl)
    while j < n:
        if _has_unsafe_construct(tpl, j):
            return n
        c = tpl[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                # 必须真的跟着第二个 )：$(()) 才是算术展开。$((")... 这类
                # 写法下 shell 会改按命令替换 + 子 shell 解析（与我们的
                # 括号计数不同），紧挨着的引号若被当成跳过区吞掉会错位
                # 引号状态、让后续 $prompt 以错误语境插入（注入），
                # 遇到即整体吞到模板结尾
                if j + 1 < n and tpl[j + 1] == ")":
                    return j + 2
                return n
        j += 1
    return n


def _backquote_end(tpl: str, i: int) -> int:
    """返回位置 i（`）处整个反引号命令替换结束后的下标。

    与 heredoc 正文同理，反引号内容是不能安全插入占位符的数据区：
    shell 对反引号的「第一遍」处理对引号不敏感——\\$ 会被还原成 $、
    引号里的裸反引号也会结束替换——插入的转义（如 \\\\\\$）在内层
    shell 中并不成立，提示词里的 $(...)/`...` 会被真正执行（注入）。
    因此这里整体跳过：结束位置按 shell 的配对规则取第一个未被反斜杠
    转义的反引号；找不到则一直吞到模板结尾（与 heredoc 一致）。
    """
    n = len(tpl)
    j = i + 1
    while j < n:
        c = tpl[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        j += 1
    return n


def _legacy_arithmetic_end(tpl: str, i: int) -> int:
    """返回位置 i（$[）处旧式算术展开结束后的下标（吞掉匹配的 ]）。

    与 $((...)) 同理：算术表达式内部不是普通词语境，插入的引号不被
    当作保护（bash 会对表达式里的 $(...)/`...` 求值执行），因此整体
    跳过、不替换占位符。下标可以嵌套（如 $[ ${a[0]} + 1 ]），按 [ ]
    深度配对；引号/反引号/反斜杠/嵌套替换可能隐藏 ]（bash 识别引号，
    如 $[ "]" ] 的 ] 不终结展开），遇到即整体吞到模板结尾——提前停在
    假结束符上会让余下模板按错误的引号语境解析（注入风险）。
    找不到匹配的 ] 时同样吞到模板结尾。
    """
    n = len(tpl)
    depth = 1
    j = i + 2
    while j < n:
        if _has_unsafe_construct(tpl, j):
            return n
        c = tpl[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _arithmetic_command_end(tpl: str, i: int) -> int:
    """返回位置 i（((）处算术命令结束后的下标（吞掉匹配的 ))。

    算术命令（bash/ksh 的 ((...))）内部是表达式：插入的引号不构成
    保护，表达式里的 $(...)/`...` 会被求值执行。按括号深度配对找
    匹配的 ))，整体跳过、不替换占位符；引号/反引号/反斜杠/嵌套替换
    可能隐藏右括号，遇到即整体吞到模板结尾（见
    _UNSAFE_IN_SKIPPED_CONTEXT），找不到则同样吞到模板结尾。
    """
    n = len(tpl)
    depth = 2
    j = i + 2
    while j < n:
        if _has_unsafe_construct(tpl, j):
            return n
        c = tpl[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _parameter_expansion_end(tpl: str, i: int) -> int:
    """返回位置 i（${）处参数展开结束后的下标（吞掉匹配的 }）。

    整个 ${...} 展开都是无法安全替换的数据区（见 _render_posix 说明），
    调用方据此整段跳过、不做占位符替换。配对必须保守：引号里的 } 不
    终结展开（${x:-"}"}）、反斜杠会转义 }、$( 与反引号内部还有自己的
    解析上下文——提前停在假结束符上会让余下模板按错误的引号语境解析
    （如 ${x:-"}$prompt"}：$prompt 会按裸语境插入单引号，而 shell 仍在
    双引号内，提示词里的 $(...)/`...` 被真正执行）。
    嵌套 ${（无引号等构造时）计深度；遇到引号/反引号/反斜杠/嵌套替换
    （可能隐藏 }）或找不到匹配的 } 时，返回模板结尾、整体跳过——宁可
    拒绝模板，也不把占位符插进无法确保安全的位置（与 heredoc / 反引号
    的处理口径一致）。
    """
    n = len(tpl)
    depth = 1
    j = i + 2
    while j < n:
        if _has_unsafe_construct(tpl, j, _UNSAFE_PARAMETER_HEADS):
            return n
        if tpl.startswith("${", j):
            depth += 1
            j += 2
            continue
        if tpl[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _redirect_word_end(tpl: str, j: int) -> int:
    """返回裸上下文 `>&` 后重定向词结束处的下标；无法安全扫描时返回模板结尾。

    bash 把无 fd 号的 `>&word` 当作 `&>word` 的别名，但对 word 的展开
    不遵守引号规则：单引号里的 $(...)/`...`/参数展开仍会被执行
    （`bash -c "printf x >&'$(touch pwned)'"` 会真的执行 touch），
    双引号里的 \\$ / \\` 也拦不住。因此该词内无法安全插入提示词：
    调用方据返回值整词原样跳过、不做替换（command_receives_prompt
    据此拒绝只在该词里使用占位符的模板）。
    词里出现嵌套替换/展开（$( ${ $[ 反引号）或进程替换（>( / <(）
    时无法可靠找出词尾边界，整体吞到模板结尾——宁可多跳过，也不把
    提示词插进无法确保安全的位置（与 heredoc / 反引号 / 参数展开的
    处理口径一致）。
    """
    n = len(tpl)
    while j < n and tpl[j] in " \t":
        j += 1
    if j < n and tpl[j] == "\n":
        # 重定向词跨行（`>&` 后换行再给词）：无法安全确定边界，整体跳过
        return n
    while j < n:
        c = tpl[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            end = tpl.find("'", j + 1)
            if end < 0:
                return n
            j = end + 1
            continue
        if c == '"':
            j += 1
            while j < n:
                if tpl[j] == "\\":
                    j += 2
                    continue
                if tpl[j] == '"':
                    j += 1
                    break
                if tpl[j] in "`$":
                    return n
                j += 1
            continue
        if c in "`$":
            return n
        if c in "<>" and j + 1 < n and tpl[j + 1] == "(":
            # `>(...)`/`<(...)` 进程替换是词的一部分且有自己的解析上下文，
            # 无法安全找出词尾：整体吞到模板结尾。注意 `>` 后不跟 `(`
            # 时是重定向操作符（`>&x>y` 的词是 `x`），按词尾处理
            return n
        if c in " \t\n;&|<>()":
            return j
        j += 1
    return j


class ShellAgent:
    """通过 shell 命令调用外部 agent（opencode / claude / aider …）。

    命令模板占位符：
      "$prompt" / $prompt   —— 替换为 shell 转义后的整段提示词
      $prompt_file          —— 提示词写入工作区内本次运行唯一的
                              .prompt.XXXXXX.md 文件，替换为该文件路径
                              （run() 结束后文件会被清理）

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
        # 本次 run() 经 render_command 创建的提示词文件（$prompt_file 模式），
        # run() 结束后清理；None 表示未使用 $prompt_file
        self._prompt_file: Optional[Path] = None

    @property
    def user_killed(self) -> bool:
        """本轮退出是否由用户的停止请求触发。"""
        with self._kill_lock:
            return self._user_killed

    # 占位符必须是“完整词”：$prompt_out / $prompt_filex 之类只是以
    # 占位符为前缀的普通变量，不能被子串替换误伤；x$prompt 这类前面紧贴
    # 单词字符的也只是普通 shell 变量拼接，同样不能误替换。
    # Windows 分支仍用正则哨兵替换，边界类与之配套
    _PLACEHOLDER_HEAD = r"(?<![A-Za-z0-9_])"
    _PLACEHOLDER_BOUNDARY = r"(?![A-Za-z0-9_])"

    def render_command(self, prompt: str, *, dry_run: bool = False) -> str:
        self._prompt_file = None
        try:
            if os.name == "nt":
                return self._render_windows(self.template, prompt, dry_run)
            return self._render_posix(self.template, prompt, dry_run)
        except Exception:
            # 渲染中途失败（如模板含无法安全替换的 $'...'）时，$prompt_file
            # 可能已落盘：必须清掉，否则工作区会留下无消费者的 .prompt.*.md
            self._cleanup_prompt_file()
            raise

    def _placeholder_at(self, tpl: str, i: int) -> Optional[str]:
        """位置 i 处是否为完整占位符（含 $prompt_file 前缀关系保护）。"""
        if i > 0 and _WORD_CHAR.match(tpl[i - 1]):
            return None
        for ph in ("$prompt_file", "$prompt"):
            j = i + len(ph)
            if tpl.startswith(ph, i) and (
                    j >= len(tpl) or not _WORD_CHAR.match(tpl[j])):
                return ph
        return None

    def _write_prompt_file(self, prompt: str) -> Path:
        # mkstemp 原子创建唯一文件名：同进程多实例或多进程并发共用同一
        # workspace 时，固定名（如 .prompt.md）会互相覆盖提示词，
        # agent 读到的是另一实例的内容（state/words 均已做并发防护，
        # 提示词文件同理）
        fd, fname = tempfile.mkstemp(
            prefix=".prompt.", suffix=".md", dir=self.workspace)
        pfile = Path(fname)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
        except Exception:
            # 写入失败时关掉 fd 并清掉半成品文件，避免工作区堆积
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                pfile.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self._prompt_file = pfile
        return pfile

    def _render_posix(self, tpl: str, prompt: str, dry_run: bool = False) -> str:
        """按占位符所在的 shell 引号语境分别转义后替换。

        不能把 shlex.quote 生成的「带引号完整 token」直接塞进模板：模板里
        占位符可能位于自己打开的引号内部（如 "方向: $prompt"），插入的引号
        会被当成字面值，参数里多出引号；双引号内还不拦住 $ ` 展开，提示词
        中的 $(cmd)/`cmd` 会被 shell 执行（注入）。这里逐字符扫描模板跟踪
        引号状态，裸上下文用 shlex.quote，单引号内用 '\\'' 闭合重开写法，
        双引号内反斜杠转义 $ ` " \\。

        $(...) 命令替换与 $((...)) 算术展开是独立的解析上下文：内部的
        引号自成一体、不能影响外层引号状态。必须用栈记录进入时的外层
        引号状态并在配对的 ) 处恢复，否则 "$(cmd "$prompt")" 这类模板
        会把内层 " 误当成外层引号闭合，$prompt 按裸上下文插入——
        模板自己的双引号还在，shlex.quote 的单引号被当成字面值，提示词
        里的 $(cmd) 反而被 shell 执行（注入）。算术展开内部是表达式，
        整体跳过不替换（shell 会把那里的 $prompt 当变量展开）。

        命令替换内部还允许嵌套普通括号（子 shell、函数定义等），它们
        与 $( 共用同一个 ) 字符：必须按括号深度配对，只有深度归零的 )
        才是命令替换的结束。见到任意裸 ) 就恢复外层引号状态，会把
        子 shell 的 ) 误当成命令替换结束——之后的 $prompt 按错误语境
        插入（提示词被拆词、甚至分号等元字符被 shell 执行）。

        heredoc（<< / <<-）正文是数据而不是命令文本：正文里的引号只是普通
        字符，shlex.quote 的引号在正文中不起保护作用（不加引号的终止符下
        正文还会做参数/命令替换），因此在正文里替换 $prompt 会让提示词里的
        $(...)/`...` 被 shell 执行。与注释同理，正文里的 $prompt 本就只是
        shell 变量展开或字面量，不会把提示词送达 agent，这里原样跳过正文、
        不做替换（command_receives_prompt 据此拒绝这类模板）。

        反引号命令替换（`...`）同样是无法安全替换的数据区：shell 对反引号
        的「第一遍」处理对引号不敏感——\\$ 会被还原成 $（而不是保护 $），
        引号里的裸反引号也会结束替换——插入的任何转义在内层 shell 中都
        不成立，提示词里的 $(cmd)/`cmd` 会被真正执行（注入）。与 heredoc
        正文相同：整体原样跳过、不替换（command_receives_prompt 据此拒绝
        这类模板）。

        算术语境（$((...))、旧式 $[...]、算术命令 ((...))）里插入的引号
        不构成保护：表达式会对其中的 $(cmd)/`cmd` 求值执行（bash）。
        这些位置无法安全送达提示词，同样整体原样跳过、不替换。

        case 的 pattern 以裸 ) 结束、不配对任何 (（case x in x) ...;; esac）：
        在命令替换内部，括号深度配对会把这个 ) 误当成替换/子 shell 的结束，
        提前恢复外层引号状态——之后的 $prompt 按错误语境插入（模板外层是
        双引号时用单引号转义，单引号在双引号内只是字面量），提示词里的
        $(...)/`...` 被真正执行（注入）。与 heredoc 正文/反引号/算术语境
        同理：命令替换内的裸 case 之后无法安全配对，整体吞到模板结尾、
        不做替换（command_receives_prompt 据此拒绝这类模板）。

        ${...} 参数展开内部也是无法安全替换的数据区，整体跳过、不替换：
        - 算术语境（数组下标 ${name[...]}、子串展开 ${name:offset[:length]}）
          插入的引号只是表达式文本，$(...)/`...` 会被求值执行；
        - 词语境（${x:-word} / ${x:=word} / ${x:?word} / ${x:+word} 等）
          无法用一套转义同时适配 bash 与 dash：dash 需要把 ' 转义成 \\'，
          而 bash 在展开体内把 ' 当引号，落单的 ' 直接让整条命令解析失败
          （unexpected EOF）；} 在两种 shell 下都会提前结束参数展开、静默
          丢字符（"${x:-foo}barbaz}" 输出 foobarbaz} 而不是 foo}barbaz）；
          bash 还会把展开体内未配对的 >( / <( 当进程替换解析而报错。
        提示词内容运行时才能确定、模板无法预知，因此与 heredoc 正文/反引号
        一致整段跳过（command_receives_prompt 据此拒绝这类模板）。

        ANSI-C 引用（$'...'）的语义取决于实际执行命令的 /bin/sh 方言：
        bash 支持它（解释反斜杠转义），dash/POSIX sh 不支持（$ 是字面量、
        后面只是普通单引号串）。xuen 用 shell=True 执行命令，/bin/sh 在
        不同系统上可能是 bash 也可能是 dash：按任一方言转义都会在另一方言
        下打乱引号边界，使提示词里的 $(...)/`...` 逃出引用被真正执行
        （注入）。这种无法确定语义的语境整体拒绝（抛 ValueError），由
        配置校验拦下，而不是替换。

        裸 `>&word`（无 fd 号）重定向词也无法安全替换：bash 把它当
        `&>word` 的别名，但对 word 的展开不遵守引号规则——单引号里的
        $(...)/`...`/参数展开仍会被执行（`>&'$(cmd)'` 真的会跑 cmd），
        双引号里的 \\$ / \\` 也拦不住。与 heredoc 正文/反引号一致整词
        原样跳过（command_receives_prompt 据此拒绝这类模板）。

        dry_run=True：只探测哪些占位符会被兑现，$prompt_file 不落盘，
        替换成带探测令牌的假路径（供 command_receives_prompt 使用）。"""
        def file_value() -> str:
            if dry_run:
                return f"/xuen-dry-run/{_PLACEHOLDER_PROBE}"
            if self._prompt_file is None:
                return str(self._write_prompt_file(prompt).resolve())
            return str(self._prompt_file.resolve())

        def read_heredoc_delim(pos: int) -> tuple:
            """读取 << 之后的终止符词，返回 (终止符, 词结束位置)。

            按 shell 的引号移除规则拼出终止符（'EOF' / "EOF" / E\\OF / EOF
            等价）；是否加引号不影响这里的处理——两种正文都不替换占位符。
            """
            buf: List[str] = []
            while pos < n:
                c = tpl[pos]
                if c == "\\" and pos + 1 < n:
                    buf.append(tpl[pos + 1])
                    pos += 2
                    continue
                if c == "'":
                    end = tpl.find("'", pos + 1)
                    if end < 0:
                        buf.append(tpl[pos + 1:])
                        return "".join(buf), n
                    buf.append(tpl[pos + 1:end])
                    pos = end + 1
                    continue
                if c == '"':
                    end = pos + 1
                    while end < n and tpl[end] != '"':
                        if (tpl[end] == "\\" and end + 1 < n
                                and tpl[end + 1] in '"\\$`'):
                            end += 2
                            continue
                        end += 1
                    buf.append(tpl[pos + 1:end])
                    pos = min(end + 1, n)
                    continue
                # shell 词在空白与控制运算符处结束
                if c in " \t\n;&|<>()":
                    break
                buf.append(c)
                pos += 1
            return "".join(buf), pos

        pending_heredocs: List[tuple] = []  # [(终止符, 是否 <<-)]

        def consume_heredoc_bodies(pos: int) -> int:
            """把已登记 heredoc 的正文原样吞掉（不做任何占位符替换）。

            正文按 shell 语义处理：不加引号的终止符下正文会做参数/命令替换，
            加引号时正文是纯字面量——两种情况下 shlex.quote 加的引号在正文里
            都只是普通字符，起不到保护作用。因此绝不能替换正文里的
            $prompt，否则提示词里的 $(...)/`...` 会被 shell 执行。
            找不到终止符时与 shell 一致：一直吞到模板结尾。
            """
            for delim, strip_tabs in pending_heredocs:
                while pos < n:
                    j = tpl.find("\n", pos)
                    end = n if j < 0 else j + 1
                    line = tpl[pos:] if j < 0 else tpl[pos:j]
                    out.append(tpl[pos:end])
                    pos = end
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        break
            pending_heredocs.clear()
            return pos

        out: List[str] = []
        # 进入 $( 时的解析上下文栈：[外层引号状态, 括号深度]。
        # 深度用于区分「子 shell 的 )」与「$( 的 )」：前者只减深度，
        # 后者（深度归零）才恢复外层引号状态
        subst_stack: List[list] = []
        state = "bare"  # bare / single / double
        i = 0
        n = len(tpl)
        while i < n:
            ch = tpl[i]
            if state == "single":
                if ch == "'":
                    state = "bare"
                    out.append(ch)
                    i += 1
                    continue
                ph = self._placeholder_at(tpl, i)
                if ph == "$prompt":
                    out.append(_escape_in_single_quotes(prompt))
                    i += len(ph)
                    continue
                if ph == "$prompt_file":
                    out.append(_escape_in_single_quotes(file_value()))
                    i += len(ph)
                    continue
                out.append(ch)
                i += 1
                continue
            if state == "double":
                # 双引号内反斜杠仅对 $ ` " \ 换行有转义作用，遇到这类组合
                # 原样成对复制，避免把 \x 的转义状态算错导致引号误判
                if ch == "\\" and i + 1 < n and tpl[i + 1] in ("\\", '"', "$", "`", "\n"):
                    out.append(tpl[i:i + 2])
                    i += 2
                    continue
                if tpl.startswith("$(", i):
                    # 双引号内的命令替换/算术展开同样开启独立上下文
                    if tpl.startswith("$((", i):
                        j = _arithmetic_end(tpl, i)
                        out.append(tpl[i:j])
                        i = j
                        continue
                    out.append(tpl[i:i + 2])
                    subst_stack.append([state, 1])
                    state = "bare"
                    i += 2
                    continue
                if ch == "`":
                    # 反引号命令替换（双引号内也是独立的一次「第一遍」处理）：
                    # 与 heredoc 正文同理不能安全插入转义，整体跳过不替换
                    j = _backquote_end(tpl, i)
                    out.append(tpl[i:j])
                    i = j
                    continue
                if tpl.startswith("${", i):
                    # ${...} 参数展开（算术语境的数组下标/子串展开与词语境
                    # 的 ${x:-word} 等）都是无法安全替换的数据区
                    # （见方法说明），整段原样跳过、不替换
                    j = _parameter_expansion_end(tpl, i)
                    out.append(tpl[i:j])
                    i = j
                    continue
                if tpl.startswith("$[", i):
                    # 双引号内的旧式算术展开 $[...] 同样是表达式语境，
                    # 整体原样跳过、不替换
                    j = _legacy_arithmetic_end(tpl, i)
                    out.append(tpl[i:j])
                    i = j
                    continue
                if ch == '"':
                    state = "bare"
                    out.append(ch)
                    i += 1
                    continue
                ph = self._placeholder_at(tpl, i)
                if ph == "$prompt":
                    out.append(_escape_in_double_quotes(prompt))
                    i += len(ph)
                    continue
                if ph == "$prompt_file":
                    out.append(_escape_in_double_quotes(file_value()))
                    i += len(ph)
                    continue
                out.append(ch)
                i += 1
                continue
            # 裸上下文
            if ch == "\n" and pending_heredocs:
                # 命令行结束：其后的正文属于 heredoc，原样跳过
                out.append(ch)
                i = consume_heredoc_bodies(i + 1)
                continue
            if ch == "\\" and i + 1 < n:
                out.append(tpl[i:i + 2])
                i += 2
                continue
            if ch == "#" and (i == 0 or tpl[i - 1] in " \t\n;&|()<>"):
                # shell 注释：词首的 # 之后直到行尾都原样保留、不参与解析。
                # 注释里的不成对引号若被当成引号状态，会让后续占位符按
                # 错误的引号语境转义（转义过弱 = 提示词可被 shell 解释执行，
                # 转义过强 = 参数被拆错）；注释里的 $prompt 也不会真正送到
                # agent，command_receives_prompt 不能把它当作有效占位符。
                # 词中的 #（如 foo#bar、=$#）不是注释，照常按字符处理。
                j = tpl.find("\n", i)
                if j < 0:
                    out.append(tpl[i:])
                    i = n
                else:
                    out.append(tpl[i:j + 1])
                    i = j + 1
                    if pending_heredocs:
                        # 本行以注释结尾，但行内的 << 仍开启了正文
                        i = consume_heredoc_bodies(i)
                continue
            if ch == "`":
                # 反引号命令替换：shell 对它的「第一遍」处理对引号不敏感
                # （\$ 会被还原成 $、引号里的裸反引号也会结束替换），插入
                # 的转义在内层 shell 中并不成立，替换 $prompt 会让提示词里的
                # $(...)/`...` 被真正执行（注入）。与 heredoc 正文同理整体
                # 跳过、不替换（command_receives_prompt 据此拒绝这类模板）
                j = _backquote_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if subst_stack and _is_case_keyword(tpl, i):
                # 命令替换内的裸 case 关键字：pattern 结束的 ) 不配对任何 (，
                # 括号深度配对会提前把替换错误闭合、恢复错误的引号状态，
                # 之后的 $prompt 会按错误语境插入（见方法说明）。无法安全
                # 配对时与其他跳过区一致：整段原样保留、不替换
                out.append(tpl[i:])
                i = n
                continue
            if tpl.startswith("$((", i):
                # 算术展开内部是表达式，整体原样跳过：既不替换占位符
                # （shell 会把那里的 $prompt 当普通变量展开，送不到
                # agent），也避免位移运算符 << 被误登记成 heredoc
                j = _arithmetic_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if tpl.startswith("${", i):
                # ${...} 参数展开（数组下标/子串展开等算术语境与
                # ${x:-word} 等词语境）内部都无法安全替换占位符
                # （见方法说明），整段原样跳过（command_receives_prompt
                # 据此拒绝这类模板）
                j = _parameter_expansion_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if tpl.startswith("$[", i):
                # 旧式算术展开 $[...]：内部是表达式，与 $((...)) 同理，
                # 插入的引号不构成保护，整体原样跳过、不替换
                j = _legacy_arithmetic_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if tpl.startswith("$'", i):
                # ANSI-C 引用（$'...'）的解释随 /bin/sh 方言而变：bash 按
                # 反斜杠转义处理，dash 则把 $ 当字面量、后面当普通单引号串。
                # xuen 用 shell=True 执行（Linux 上通常是 dash，macOS/RHEL
                # 上是 bash），无法预知方言：按 bash 规则转义插入提示词，
                # 在 dash 下引号边界会被打乱——提示词里的 `; cmd` / $(cmd)
                # 逃出引用被真正执行（注入）；按 POSIX 规则插入，则会在
                # bash 下注入。与其他不安全语境一致：整体拒绝这类模板，
                # 绝不替换（command_receives_prompt 据此让配置校验拒绝）
                raise ValueError(
                    "agent.command 不支持 ANSI-C 引用（$'...'）：不同系统"
                    "的 /bin/sh（bash 支持、dash 不支持）对它的解释不同，"
                    "无法安全传递提示词；请改用普通引号，例如 "
                    '"$prompt" 或 \'$prompt\''
                )
            if tpl.startswith("((", i):
                # 算术命令 ((...))：内部是表达式，插入的引号不构成保护，
                # 表达式里的 $(...)/`...` 会被求值执行。整体原样跳过、
                # 不替换（不做完整 shell 语法分析：裸上下文里的 (( 一律
                # 按算术命令对待，无法兑现的占位符由配置校验拒绝）
                j = _arithmetic_command_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if tpl.startswith("$(", i):
                # 命令替换开启独立解析上下文（见方法说明）
                out.append(tpl[i:i + 2])
                subst_stack.append([state, 1])
                state = "bare"
                i += 2
                continue
            if ch == "(" and subst_stack:
                # 命令替换内部的普通左括号（子 shell、函数定义等）：
                # 记入当前替换的括号深度，避免其配对的 ) 被误当成
                # 命令替换的结束
                subst_stack[-1][1] += 1
                out.append(ch)
                i += 1
                continue
            if ch == ")" and subst_stack:
                # 只有深度归零的 ) 才与 $( 配对：恢复进入替换前的外层
                # 引号状态；子 shell 的 ) 只减深度、不改变外层语境
                frame = subst_stack[-1]
                frame[1] -= 1
                if frame[1] <= 0:
                    subst_stack.pop()
                    state = frame[0]
                out.append(ch)
                i += 1
                continue
            if tpl.startswith(">&", i):
                # 裸 `>&word`（无 fd 号）是 `&>word` 的别名，但 bash 对
                # word 的展开不遵守引号规则：单引号里的 $(...)/`...` 与
                # 参数展开仍会被执行，双引号里的 \$ / \` 也拦不住——按
                # 普通引号语境插入提示词会让提示词里的 $(...)/`...` 被
                # 真正执行（注入）。与 heredoc 正文/反引号/算术语境同理：
                # 整词原样跳过、不做替换（command_receives_prompt 据此
                # 拒绝这类模板）。`&>`/`<>`/`>|` 等写法遵守引号规则，
                # 不在此列
                j = _redirect_word_end(tpl, i + 2)
                out.append(tpl[i:j])
                i = j
                continue
            if tpl.startswith("<<<", i):
                # here-string（<<<）没有正文，整段按普通文本处理
                out.append("<<<")
                i += 3
                continue
            if ch == "<" and tpl.startswith("<<", i):
                # heredoc 重定向：登记终止符，正文里的占位符一律不替换
                # （见 consume_heredoc_bodies）。不做完整 shell 语法分析：
                # 裸上下文里的 << 一律按重定向处理，无法兑现的占位符由
                # 配置校验拒绝，而不是替换
                j = i + 2
                strip_tabs = False
                if j < n and tpl[j] == "-":
                    strip_tabs = True
                    j += 1
                while j < n and tpl[j] in " \t":
                    j += 1
                delim, j = read_heredoc_delim(j)
                out.append(tpl[i:j])
                pending_heredocs.append((delim, strip_tabs))
                i = j
                continue
            if ch == "'":
                state = "single"
                out.append(ch)
                i += 1
                continue
            if ch == '"':
                state = "double"
                out.append(ch)
                i += 1
                continue
            ph = self._placeholder_at(tpl, i)
            if ph == "$prompt":
                out.append(_quote(prompt))
                i += len(ph)
                continue
            if ph == "$prompt_file":
                out.append(_quote(file_value()))
                i += len(ph)
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _render_windows(self, tpl: str, prompt: str, dry_run: bool = False) -> str:
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
            if dry_run:
                # 只探测占位符是否会被兑现：不落盘提示词文件
                path = f"/xuen-dry-run/{_PLACEHOLDER_PROBE}"
            else:
                pfile = self._write_prompt_file(prompt)
                path = str(pfile.resolve())
            # 路径可能含空格：与 $prompt 一样做 shell 转义后再替换
            tpl = tpl.replace(f_sentinel, _quote(path))
        return tpl.replace(p_sentinel, _quote(prompt))

    def _cleanup_prompt_file(self) -> None:
        pfile = self._prompt_file
        self._prompt_file = None
        if pfile is not None:
            try:
                pfile.unlink(missing_ok=True)
            except OSError:
                pass

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
            # killed_before 本身就是一次用户停止请求（kill 到达时尚无进程可杀），
            # 不能在这里降级成普通的 start→rc=-9 失败轮次。
            self._user_killed = killed_before
        command = self.render_command(prompt)
        shown = command if len(command) <= 300 else command[:300] + " …"
        self.on_stderr(f"$ {shown}\n")

        try:
            proc = subprocess.Popen(
                command, shell=True,
                stdin=subprocess.DEVNULL,  # 防止外部 agent 继承 stdin 与 TUI 争抢键盘/挂起
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                **popen_kwargs(),
            )
        except Exception as e:
            # 启动失败（如提示词含 NUL 字节）时提示词文件已无消费者，
            # 必须清理，否则每次启动失败都在工作区留一个 .prompt.*.md
            self._cleanup_prompt_file()
            if isinstance(e, OSError) and e.errno == errno.E2BIG:
                # 命令行参数过长（提示词太大）：把裸 [Errno 7] 换成可操作
                # 的错误并附上解法（改用 $prompt_file，只传文件路径）。
                # 区块内容只增不减，同模板重试必然同样失败
                raise PromptTooLongError(
                    "外部 agent 调用命令过长：提示词经 $prompt 作为命令行"
                    "参数传递，超出了系统对单个参数的长度上限（Linux 约 "
                    "128KB），且提示词会随想法区/产物区内容增长而变长。"
                    "请在 agent.command 中改用 $prompt_file（提示词写入"
                    "工作区文件、命令只传路径，例如 "
                    "'opencode run \"$prompt_file\"'）后重跑，"
                    "研究状态会从 research.md 继续。"
                ) from e
            raise
        # _proc/_killed 归属 _kill_lock 保护：赋值与检查必须在锁内完成，
        # 否则与 kill() 的竞态依赖 GIL 语义，与锁不变式不符
        with self._kill_lock:
            self._proc = proc
            # kill 请求在 Popen 前（killed_before）或 Popen 与本赋值之间
            # （self._killed）到达：进程刚拉起，立即补杀。
            # 补杀后必须清掉 _killed：这次停止请求已在下面兑现，若残留，
            # 下一轮 run() 会把它当作新的待处理 kill，把新拉起的进程再次
            # 误杀（rc=-9）。此后 kill() 读到的 _proc 已非 None，只会直接
            # 杀进程，不会再置位 _killed，故此处清除不会丢任何请求
            pending_kill = killed_before or self._killed
            self._killed = False
        if pending_kill:
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
            with self._kill_lock:
                self._proc = None
            # 清理本次的提示词文件（子进程已退出，不再需要；
            # 循环长跑时避免工作区堆积 .prompt.*.md）
            self._cleanup_prompt_file()
        self.returncode = proc.returncode
        self.timed_out = killed["flag"]
        if self.timed_out:
            # :g 避免小数秒（如 0.5）被 :.0f 四舍五入成「0s」
            self.on_stderr(f"外部 agent 超时（{self.timeout:g}s），已强制终止\n")
        elif proc.returncode and self.user_killed:
            # 用户按 q / Ctrl+C 触发的终止不是 agent 执行失败：被 SIGKILL
            # 杀掉的进程退出码为 -9，不能按「异常退出」计入失败统计。
            self.on_stderr("已按请求终止外部 agent\n")
        elif proc.returncode:
            self.on_stderr(f"外部 agent 异常退出（退出码 {proc.returncode}），"
                           "本轮可能未更新区块\n")
        return "".join(out)


def command_receives_prompt(template: str) -> bool:
    """命令模板是否会把提示词真正传给外部 agent。

    直接复用 ShellAgent 的实际渲染逻辑（dry_run 不落盘 $prompt_file
    文件）判断，而不是用正则近似匹配 "$prompt" 子串：被 shell 转义的
    \\$prompt 虽然包含 "$prompt" 子串，渲染时并不会替换，提示词会被
    静默丢弃——这正是配置校验要拦下的场景。渲染直接拒绝的模板
    （如 ANSI-C 引用 $'...'）同样按「提示词无法送达」处理。"""
    probe_agent = ShellAgent(template, Path("."), timeout=1.0)
    try:
        rendered = probe_agent.render_command(_PLACEHOLDER_PROBE, dry_run=True)
    except ValueError:
        return False
    return _PLACEHOLDER_PROBE in rendered
