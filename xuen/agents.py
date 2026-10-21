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
from typing import Callable, List, Optional, Set

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


def _cmd_double_quotes_after(text: str, in_quotes: bool) -> bool:
    """cmd.exe 中扫描 text 后的「是否仍在双引号内」状态。

    只跟踪双引号：cmd 的引号状态由未转义的 " 翻转；引号外的 ^ 转义下一个
    字符（^" 是字面引号、不翻转）。%VAR% 展开也可能带来引号，但模板无法
    预知展开结果，不在跟踪范围内（$prompt_file 路径本身不含 %，含 cmd
    元字符的工作区会在配置校验被拒绝，见 config._validate）。
    """
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "^" and not in_quotes:
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
        i += 1
    return in_quotes


# 占位符边界：与 config._validate 的正则一致，A-Za-z0-9_ 是「单词字符」
_WORD_CHAR = re.compile(r"[A-Za-z0-9_]")


def _windows_placeholder_starts(tpl: str, ph: str):
    """Windows 模板中会兑现的占位符起点（按 $$ 两两配对、cmd ^ 转义判断）。"""
    i = 0
    in_quotes = False
    n = len(tpl)
    while i < n:
        c = tpl[i]
        if c == "^" and not in_quotes:
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if not tpl.startswith(ph, i):
            i += 1
            continue
        end = i + len(ph)
        if end < n and _WORD_CHAR.match(tpl[end]):
            i += 1
            continue
        k = i - 1
        dollars = 0
        while k >= 0 and tpl[k] == "$":
            dollars += 1
            k -= 1
        if dollars:
            if dollars % 2 == 0:
                yield i
        elif k < 0 or not _WORD_CHAR.match(tpl[k]):
            yield i
        i = end


def _prev_effective_pos(tpl: str, i: int,
                        commented_backslashes: Optional[Set[int]] = None) -> int:
    """返回 i 左侧「shell 分词时真正相邻」字符的下标；无则为 -1。

    分词前 shell 会先删掉续行（未转义反斜杠 + 换行）：`a\\<换行>b` 的 b
    左侧真正相邻的是 a，`a\\<换行>#` 的 # 是词中字符而不是注释。续行判定
    按反斜杠奇偶：`a\\\\<换行>#`（两个）里换行不是续行、仍是词边界；三个
    反斜杠时删掉换行与最后一个反斜杠，紧邻 # 的是剩下的字面反斜杠。
    单引号语境不删续行，调用方不要在那里使用本函数。

    commented_backslashes：渲染器已消费的注释里紧贴换行（直接位于换行
    左侧）的反斜杠位置集合。注释里的反斜杠不被 shell 当续行——注释在
    物理换行处结束（bash/dash 实测 `#x\\<换行>echo y` 会执行 echo y），
    反斜杠只是被注释吞掉的普通字符。这种换行是硬换行：跨过去会把注释
    内的字符当成「相邻字符」，渲染器据此误判注释起点（`#\\<换行>#$prompt`
    里第二个 # 被当成词中字符，$prompt 被替换进 shell 的注释里，提示词的
    换行逃出注释成为命令——注入），或误判占位符的词边界。命中即返回换行
    位置（词边界），与实际 shell 一致。
    """
    k = i - 1
    while k >= 0 and tpl[k] == "\n":
        if commented_backslashes and (k - 1) in commented_backslashes:
            return k  # 注释吞掉了反斜杠：硬换行，是词边界
        j = k - 1
        n = 0
        while j >= 0 and tpl[j] == "\\":
            n += 1
            j -= 1
        if n % 2 == 0:
            return k  # 真换行：词边界
        if n >= 3:
            return k - 2  # 续行只删掉换行与最后一个反斜杠
        k = j
    return k


def _directly_after_placeholder(tpl: str, i: int, prev_ph_end: int) -> bool:
    """i 是否紧跟在上一个被兑现的占位符之后（中间只隔着续行）。

    「完整词」边界检查挡住的是模板里紧贴占位符的字面单词字符
    （`x$prompt` 不替换，见 _placeholder_at）；但上一个占位符的替换结果
    不是模板字面量：`$prompt$prompt` 里第二个占位符紧贴的是第一个的兑现
    结果，shell 会把两段展开拼成同一个词，第二个必须照常替换，否则会以
    字面量留在命令里被 shell 当空变量展开（提示词被静默丢弃一半）。
    续行（反斜杠-换行）在分词前被删除，`$prompt\\<换行>$prompt` 与紧邻
    写法等价，同样按相邻处理。
    """
    if prev_ph_end < 0 or prev_ph_end > i:
        return False
    k = prev_ph_end
    while k + 1 < len(tpl) and tpl[k] == "\\" and tpl[k + 1] == "\n":
        k += 2
    return k == i


def _dollar_starts_expansion(tpl: str, i: int,
                             commented_backslashes: Optional[Set[int]] = None
                             ) -> bool:
    """位置 i 处的 $ 是否开启新展开（紧邻的 $ 会被 shell 两两配成 $$）。

    shell 从左到右扫描连续未转义的 $：前两个配成一个 $$（PID），落单的
    那个才是 `$名字` 展开的开始——`$$prompt` 里 `prompt` 只是字面量，
    `$$$prompt` 才是 `$$` 加真正的 `$prompt` 展开（bash/dash 行为一致）。
    被反斜杠转义的 $ 是字面量、不参与配对：连续 $ 段的首个 $ 前有奇数个
    反斜杠时，未转义段从第二个 $ 起算（`\\$$prompt` 里 $$ 仍是 PID）。
    续行在分词前被删掉，跨行相邻关系按删除后的文本判断：`$\\<换行>
    $prompt` 就是 `$$prompt`，第二个 $ 只是前一个 $$ 的后半、不是展开。
    返回 False 表示 i 处的 $ 只是前一个 $$ 的后半，不是展开的开始。
    commented_backslashes 透传给 _prev_effective_pos：注释吞掉的反斜杠
    不续行，注释里的 $ 段不参与跨行配对（`#\\<换行>$prompt` 的 $ 是
    新展开，按注释内相邻关系会误算成 $$ 的后半）。
    """
    run = 0  # i 左侧紧邻的连续 $ 个数（按删除续行后的相邻关系）
    k = i
    while True:
        k = _prev_effective_pos(tpl, k, commented_backslashes)
        if k < 0 or tpl[k] != "$":
            break
        run += 1
    n = 0  # $ 段之前紧邻的连续反斜杠个数（同样按删除续行后的相邻关系）
    while k >= 0 and tpl[k] == "\\":
        n += 1
        k = _prev_effective_pos(tpl, k, commented_backslashes)
    if n % 2:
        run -= 1
    return run % 2 == 0


def _escaped_at(tpl: str, pos: int) -> bool:
    """pos 处字符是否被紧邻的奇数个反斜杠转义（不跨续行判断）。

    续行（反斜杠-换行）在分词前被删除，`\\>\\<换行>&` 里 `>` 紧跟的
    换行不是转义、`>` 是字面量；直接数物理相邻的反斜杠即可。
    """
    k = pos - 1
    cnt = 0
    while k >= 0 and tpl[k] == "\\":
        cnt += 1
        k -= 1
    return cnt % 2 == 1


# 续行（反斜杠-换行）在 shell 分词前会被删除，两侧的字符会被拼到一起：
# `>`+续行+`&` 拼成 `>&`、`<`+续行+`<` 拼成 heredoc `<<`、`$`+续行+`(`
# 拼成命令替换、`(`+续行+`(` 拼成算术命令、`>`/`<`+续行+`(` 拼成进程
# 替换……这些头部（及其 `$[`/`${`/`$'`/`$"` 变体）的引号与展开规则都与
# 普通文本不同：`>&` 的重定向词无视引号执行提示词里的 $(...)、`<<` 正文
# 不认引号（实测 bash 下这些模板都会执行提示词里的命令替换）。渲染器按
# 续行两侧字符独立解析会与实际 shell 脱节，因此这类模板整体拒绝、由配置
# 校验拦下（与 $'...' 的处理口径一致），而不是替换。
# `\\$$<续行>(` 里 $$ 是 PID、`(` 只是普通括号，`\\`+`>`+续行+`&` 里
# `>` 是字面量，都不构成头部（见 _continuation_split_head）。
_CONTINUATION_SPLIT_HEADS = frozenset((
    ">&",   # 裸 >&word 重定向词：展开不遵守引号规则
    "<<",   # heredoc：正文是数据/可被展开，不认引号
    "$(",   # 命令替换 / $(( 算术展开
    "$[",   # 旧式算术展开
    "${",   # 参数展开
    "$'",   # ANSI-C 引用：解释随 /bin/sh 方言而变
    '$"',   # 本地化引用（bash 做 gettext、dash 把 $ 当字面量）：同理
    "((",   # 算术命令
    ">(",   # 进程替换
    "<(",   # 进程替换
))


def _continuation_split_head(tpl: str, i: int,
                             commented_backslashes: Optional[Set[int]] = None
                             ) -> Optional[str]:
    """续行位置 i 两侧的有效字符是否拼成需特殊解析的操作符/展开头。

    返回拼成的头部文本（如 ">&"）；不构成时返回 None。
    `$` 开头的组合必须先确认是真正的展开（_dollar_starts_expansion，
    `\\$$<续行>(` 里的 $$ 是 PID，`(` 不是命令替换的起点）；其他字符
    先确认未被反斜杠转义（`\\>`+续行+`&` 里 `>` 是字面量、不是 `>&`）。
    commented_backslashes 透传给 _prev_effective_pos / _dollar_starts_
    expansion：注释吞掉的反斜杠不续行，跨过它会把注释内字符当成续行
    左侧的相邻字符（如把注释里的 > 与后续 & 误拼成 >& 而整体拒绝）。
    """
    n = len(tpl)
    prev = _prev_effective_pos(tpl, i, commented_backslashes)
    if prev < 0:
        return None
    k = i
    while k + 1 < n and tpl[k] == "\\" and tpl[k + 1] == "\n":
        k += 2
    if k >= n:
        return None
    head = tpl[prev] + tpl[k]
    if head not in _CONTINUATION_SPLIT_HEADS:
        return None
    if tpl[prev] == "$":
        if not _dollar_starts_expansion(tpl, prev, commented_backslashes):
            return None
    elif _escaped_at(tpl, prev):
        return None
    return head


def _continuation_split_error(head: str) -> ValueError:
    return ValueError(
        f"agent.command 不支持用续行（反斜杠-换行）拆分操作符/展开："
        f"续行在 shell 分词前被删除，两侧字符拼成了 `{head}`。"
        "该语境的引号/展开规则与普通文本不同（如 >& 的重定向词会无视"
        "引号执行提示词里的 $(...)，<< 正文不认引号），按续行两侧独立"
        "解析会与实际 shell 脱节、无法安全传递提示词；请把操作符写在"
        "同一行（行尾的普通续行不受影响）"
    )


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
        # 续行必须真的生效才能跨过：反斜杠所在物理行若含 #，它可能落在
        # 注释里，反斜杠-换行并不续行（`#x\<换行>case` 里 case 仍是新行
        # 行首的关键字）。误当续行会把单词边界判反、漏认 case（见
        # _render_posix 的 case 说明，漏认会让 pattern ) 破坏括号配对）。
        # 无法确定时按硬换行处理：宁可误认关键字（整体跳过/拒绝），
        # 不可漏认
        line_start = tpl.rfind("\n", 0, k - 1) + 1
        if "#" in tpl[line_start:k - 2]:
            break
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
    词首的 # 同理：dash 等不支持 $[...] 的 /bin/sh 把 $[ 当普通词、
    区域内容按普通词语境解析，词首 # 会开启注释，把结束符 ] 与同行
    后续（可能是替换所依赖的引号语境）一起吞到行尾——实测
    `$[ #c elif local ] for[declare[ (echo $prompt)` 渲染后，提示词的
    后续行在 dash 下成为裸命令、$(...)/`...` 被真正执行（注入）；
    bash 则在算术区解析 # 报错、不执行。遇到即整体吞到模板结尾
    （与引号等构造同口径），宁可拒绝模板也不让 $prompt 留在与实际
    shell 脱节的语境里。
    区域里的 << 同理：dash 把 << 当 heredoc 起点（bash 是左移），
    heredoc 正文会吞掉后续行并展开其中的命令替换，实测可注入；遇到
    即整体吞到模板结尾。
    找不到匹配的 ] 时同样吞到模板结尾。
    """
    n = len(tpl)
    depth = 1
    j = i + 2
    while j < n:
        if _has_unsafe_construct(tpl, j):
            return n
        c = tpl[j]
        if c == "#" and tpl[j - 1] in " \t\n;&|()<>":
            # 词首 #（dash 里是注释起点；$[ 紧跟的 [ 后不算词首，如
            # $[#x] 是单个词；bash 基数写法 $[16#ff] 的 # 前是数字，
            # 也不触发）
            return n
        if c == "<" and tpl.startswith("<<", j):
            # 不支持 $[...] 的 /bin/sh（dash）把区域内容按普通词语境
            # 解析，<< 是 heredoc 起点：正文会吞掉后续行并展开/执行
            # 其中的 $(...)/`...`——实测模板 `echo $[x<<EOF` 换行
            # `]$prompt` 渲染后，$prompt 被替换进 dash 的 heredoc 正文、
            # 提示词里的命令替换被真正执行（注入）；bash 则在算术区按
            # 左移解析、不执行。遇到即整体吞到模板结尾（与词首 # 同
            # 口径），宁可拒绝模板
            return n
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
    dash 不支持算术命令：(( 被当作两个嵌套子 shell、区域内容按普通
    命令解析，<< 是 heredoc 起点，正文会吞掉后续行并展开其中的命令
    替换。渲染器按括号深度算出的结束位置会落在 dash 的正文之内，其
    后的占位符被替换进正文并在执行时展开——实测模板 `true;
    ((x<<EOF` 换行 `))$prompt` 换行 `EOF` 换行 `))` 下 dash 执行了
    提示词里的 $(...)（bash 因语法错误不执行）。遇到 << 即整体吞到
    模板结尾（与 $[...] 内的词首 # 同口径），宁可拒绝模板。
    """
    n = len(tpl)
    depth = 2
    j = i + 2
    while j < n:
        if _has_unsafe_construct(tpl, j):
            return n
        c = tpl[j]
        if c == "<" and tpl.startswith("<<", j):
            # 见 docstring：dash 下这里是 heredoc 起点，正文会吞掉
            # 后续行并展开其中的命令替换，遇到即整体吞到模板结尾
            return n
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


def _command_substitution_end(tpl: str, i: int) -> int:
    """返回位置 i（$() 处命令替换结束后的保守下标；不确定时返回模板结尾。

    专用于 heredoc 正文边界判定：不加引号的正文里 $(...) 若不在正文区域内
    闭合，dash 会把后续行（包括与终止符相同的行）当作替换内容继续解析
    （实测 `cat <<A` 正文里的 `$(` 会吞掉 A 终止符行、在 `)` 之后才恢复
    终止符匹配；bash 则直接报错）。渲染器按行找终止符会以为正文已结束、
    把 $prompt 插进 shell 仍是正文的区域——提示词里的 $(...)/`...` 被真正
    执行（注入）。
    只做括号深度配对；引号、反斜杠、注释、嵌套展开/引用（$( ${ $[ $' $"）、
    正文内嵌 heredoc、case 等无法简单可靠配对的内容一律返回模板结尾
    （视为未闭合），宁可多吞（不替换）也不把提示词插进无法确保安全的
    位置（与 heredoc / 反引号 / 参数展开的处理口径一致）。
    """
    n = len(tpl)
    depth = 1
    j = i + 2
    while j < n:
        c = tpl[j]
        if c in "'\"\\`#":
            # 引号/转义/反引号/注释都可能藏着 )，按未闭合处理
            return n
        if c == "$":
            if j + 1 < n and tpl[j + 1] in "({['\"":
                # 嵌套 $( ${ $[ $' $"：内层解析边界不可靠
                return n
            j += 1
            continue
        if c == "<" and tpl.startswith("<<", j):
            # 正文内嵌 heredoc：其中的 ) 可能只是正文
            return n
        if _is_case_keyword(tpl, j):
            # case pattern 的 ) 不配对任何 (（见 _render_posix 说明）
            return n
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _pid_bracket_quote_region(tpl: str, i: int,
                              commented_backslashes: Optional[Set[int]] = None
                              ) -> bool:
    """位置 i（`(` 或 `{`）处是否为「$$ 后区域含引号切换」的写法。

    shell 把 `$$(` / `$${` 的 $$ 当 PID、后面的括号/花括号当字面量
    （bash/dash 都继续解析后续文本），但 bash 会对 `(` 到配对 `)`（以及
    `{` 到配对 `}`）的区域做一次命令替换式的配对扫描：区域里的引号只是
    字面量、不切换外层双引号状态（实测 `v="$$(a"b"c)d"` 在 bash 下 v 是
    `PID(a"b"c)d`、dash 是 `PID(abc)d`；`$${x:-"b"}` 同理 bash 保留引号）。
    渲染器（与 dash 一致）在 `"` 处切换语境：区域里的 `"` 之后插入的
    $prompt 会按裸语境用 shlex.quote 单引号包裹，而 bash 仍把它当双引号
    内文本——单引号只是字面量，提示词里的 $(...)/`...` 逃出引用被真正
    执行（注入，实测 `printf %s "$$<续行>( "$prompt" )"` 与
    `printf "%s $${x:-"}$prompt"}"` 渲染后 bash 创建文件、dash 安全）。
    区域里出现会切换引号的 `"` 且能配到结束的 `)` / `}` 时返回 True
    （调用方整体拒绝）。
    区域没有配对的结束符时 bash 报解析错误、不会继续执行，按安全处理；
    区域里的嵌套命令替换/参数展开/旧式算术/反引号按与渲染器相同的跳过
    程序跨过（bash 同样把它们视为配对内部），无法可靠跳过的一律按不安全
    处理。只在双引号语境调用：单引号里 `$$(`/`$${` 是纯字面量，裸语境下
    bash/dash 的解析一致或直接报语法错误。
    """
    opener = tpl[i]
    closer = ")" if opener == "(" else "}"
    prev = _prev_effective_pos(tpl, i, commented_backslashes)
    if prev < 0 or tpl[prev] != "$":
        return False
    prev2 = _prev_effective_pos(tpl, prev, commented_backslashes)
    if prev2 < 0 or tpl[prev2] != "$":
        return False
    if not _dollar_starts_expansion(tpl, prev2, commented_backslashes):
        return False
    n = len(tpl)
    depth = 1
    quote = False
    j = i + 1
    while j < n:
        c = tpl[j]
        if c == "\\":
            # 与双引号内的转义规则一致：\ + $ ` " \ 换行 成对复制
            if j + 1 < n and tpl[j + 1] in ("\\", '"', "$", "`", "\n"):
                j += 2
            else:
                j += 1
            continue
        if c == '"':
            k = j - 1
            backslashes = 0
            while k > i and tpl[k] == "\\":
                backslashes += 1
                k -= 1
            if backslashes % 2 == 0:
                # 渲染器会在这个 " 处切换引号状态（bash 不会）
                quote = True
            j += 1
            continue
        if c == "`":
            j = _backquote_end(tpl, j)
            if j >= n:
                # 反引号未闭合：bash 报解析错误，不会执行
                return False
            continue
        if c == "$" and j + 1 < n and tpl[j + 1] in ("(", "{", "["):
            if not _dollar_starts_expansion(tpl, j, commented_backslashes):
                j += 1
                continue
            if tpl.startswith("$(", j):
                j = _command_substitution_end(tpl, j)
                if j >= n:
                    # 嵌套命令替换的边界无法可靠确定：宁可拒绝
                    return True
            elif tpl.startswith("${", j):
                j = _parameter_expansion_end(tpl, j)
                if j >= n:
                    # 渲染器会整段跳过剩余模板、不再替换，按安全处理
                    return False
            else:
                j = _legacy_arithmetic_end(tpl, j)
                if j >= n:
                    return False
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return quote
        j += 1
    return False


def _heredoc_body_open_substitution(tpl: str, start: int, end: int) -> bool:
    """未加引号的 heredoc 正文 [start,end) 结束处是否仍有未闭合的展开。

    返回 True 表示无法证明结束处没有横跨终止符行的命令替换/展开：
    调用方不能在这里结束正文（dash 会把终止符行吞进未闭合的 $()/``，
    正文继续；渲染器若恢复替换会把 $prompt 插进 shell 的正文区域，
    注入）。返回 False 表示所有展开都在区域内闭合（含 ${}/$[]/$((…))
    这类边界一开口就确定的展开），按行匹配终止符与两种 shell 一致。
    反斜杠按转义跳过（与正文里反斜杠只对 $、反引号、反斜杠、换行生效
    相比略宽，只影响是否继续吞，安全方向）。
    """
    i = start
    while i < end:
        c = tpl[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            j = _backquote_end(tpl, i)
            if j > end:
                return True
            i = j
            continue
        if tpl.startswith("$((", i):
            j = _arithmetic_end(tpl, i)
            if j > end:
                return True
            i = j
            continue
        if tpl.startswith("$(", i):
            j = _command_substitution_end(tpl, i)
            if j > end:
                return True
            i = j
            continue
        if tpl.startswith("${", i):
            j = _parameter_expansion_end(tpl, i)
            if j > end:
                return True
            i = j
            continue
        if tpl.startswith("$[", i):
            j = _legacy_arithmetic_end(tpl, i)
            if j > end:
                return True
            i = j
            continue
        i += 1
    return False


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
    续行（反斜杠-换行）在分词前被删除，要与空白一样先跳过：`>&\\<换行>
     word` 等同于 `>& word`，重定向词是续行之后的那个词；不跳会把词
    判成空、把后面的 $prompt 当普通参数替换，而 bash 对 `>&word` 的
    展开不遵守引号规则，提示词里的 $(...) 就会被真正执行（注入）。
    """
    n = len(tpl)
    while j < n:
        if tpl[j] in " \t":
            j += 1
            continue
        if tpl[j] == "\\" and j + 1 < n and tpl[j + 1] == "\n":
            j += 2
            continue
        break
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
        # 上一次 run() 是否已完整收尾（进程已回收、_proc 已清空）。
        # kill() 在空闲期不能把请求留成「待下一次 run 补杀」：正常跑完
        # 一轮后到达的晚到 kill 不应让下一轮刚拉起的 agent 被误杀。
        # run() 一开始就清掉它，因此「本轮起跑后、Popen 前」的 kill
        # 仍会记成待处理请求，由 Popen 后补杀。
        self._idle_after_run = False
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
    # 单词字符的也只是普通 shell 变量拼接，同样不能误替换；$$prompt 里
    # shell 把 $$ 当 PID、prompt 只是字面量，也不算完整占位符（见
    # _placeholder_at）。
    # Windows 分支同样按连续 $ 两两配对（_windows_placeholder_starts）：
    # `$$prompt_file` 的第二个 $ 只是字面量，`$$$prompt_file` 的第三个
    # 才是占位符；否则会把字面量当路径替换、或在奇数个 $ 时漏掉真正的
    # 占位符（与 POSIX 侧口径一致）。

    def render_command(self, prompt: str, *, dry_run: bool = False,
                       probe: str = _PLACEHOLDER_PROBE) -> str:
        # 同一实例可能被连续渲染多次（直接 API 调用，或上一次渲染后未走
        # run() 收尾）：先把上一次留下的提示词文件删掉，否则直接把
        # _prompt_file 置 None 会让旧文件失去引用、永久残留在工作区
        # （run() 的兜底清理只能删掉最后一个）
        self._cleanup_prompt_file()
        try:
            if os.name == "nt":
                return self._render_windows(self.template, prompt, dry_run,
                                            probe)
            return self._render_posix(self.template, prompt, dry_run, probe)
        except BaseException:
            # 渲染中途失败（如模板含无法安全替换的 $'...' 或用户按
            # Ctrl+C）时，$prompt_file 可能已落盘：必须清掉，否则工作区
            # 会留下无消费者的 .prompt.*.md（内含研究状态）
            self._cleanup_prompt_file()
            raise

    def _placeholder_at(self, tpl: str, i: int,
                        state: str = "bare",
                        prev_ph_end: int = -1,
                        commented_backslashes: Optional[Set[int]] = None
                        ) -> Optional[str]:
        """位置 i 处是否为完整占位符（含 $prompt_file 前缀关系保护）。

        除单词字符边界外还要挡住紧跟在未转义 $ 后面的情况：shell 把
        `$$prompt` 的 $$ 当 PID（bash/dash 一致）、`prompt` 只是字面量，
        替换提示词会与模板原语义错位——双引号语境下拼成 `"$"+提示词`，
        提示词以 ( 开头就构成命令替换（注入），以字母开头则被当成变量名
        （提示词被吞）；裸语境下拼成 `$'...'` ANSI-C 引用，bash 解释
        反斜杠转义而 dash 原样保留（提示词被篡改且两 shell 行为不一）；
        `$$prompt_file` 还会把路径前缀上一个 $、agent 拿到坏路径。
        单引号语境没有 $ 展开（$ 只是字面量），'$prompt' / '$$prompt'
        仍是合法占位符，按 state 放行。
        单引号之外的语境分词前会删掉续行：左侧相邻字符要按
        _prev_effective_pos 跨行判断，否则 `x\\<换行>$prompt`（拼成
        `x$prompt`）会被当成词首占位符替换，而 `$\\<换行>$prompt`
        （拼成 `$$prompt`）会被当成真正的展开替换成 `$'提示词'`——
        bash 解释反斜杠转义而 dash 原样保留，提示词被篡改且行为随
        /bin/sh 方言而变（见 _dollar_starts_expansion）。右侧边界同理：
        `$prompt\\<换行>x` 拼成 `$promptx`、`$prompt\\<换行>_file` 拼成
        `$prompt_file`，占位符后面还接着单词字符，只是普通变量名，不是
        完整占位符；替换会静默多拼出后缀、或把 $prompt_file 误当
        $prompt 用（单引号内续行不被删除，那里的反斜杠-换行本就终止
        变量名，不适用本条）。
        prev_ph_end：调用方最近一次兑现的占位符结束位置。紧贴它的字面
        单词字符不是模板字面量，而是上一个占位符的替换结果（如
        `$prompt$prompt`、`$prompt\\<换行>$prompt`）：shell 会把两段
        拼成同一个词，第二个占位符要照常兑现（见
        _directly_after_placeholder）；模板里字面紧贴的 `x$prompt`
        仍然不替换。
        commented_backslashes：透传给 _prev_effective_pos / _dollar_
        starts_expansion，注释吞掉的反斜杠不续行（否则会把注释内的字符
        当成占位符左侧的相邻字符，误判词边界或 $ 配对）。
        """
        if state == "single":
            # 单引号内续行不被删除，相邻要求物理紧邻（不能用跨续行的
            # _directly_after_placeholder）
            if (i > 0 and _WORD_CHAR.match(tpl[i - 1])
                    and prev_ph_end != i):
                return None
        else:
            prev = _prev_effective_pos(tpl, i, commented_backslashes)
            if (prev >= 0 and _WORD_CHAR.match(tpl[prev])
                    and not _directly_after_placeholder(tpl, i, prev_ph_end)):
                return None
            if (prev >= 0 and tpl[prev] == "$"
                    and not _dollar_starts_expansion(
                        tpl, i, commented_backslashes)):
                return None
        for ph in ("$prompt_file", "$prompt"):
            if not tpl.startswith(ph, i):
                continue
            j = i + len(ph)
            if state != "single":
                # 续行在分词前被删除：`$prompt\<换行>x` 拼成 `$promptx`，
                # 变量名仍在延续，不是完整占位符
                while (j + 1 < len(tpl) and tpl[j] == "\\"
                       and tpl[j + 1] == "\n"):
                    j += 2
            if j >= len(tpl) or not _WORD_CHAR.match(tpl[j]):
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
        # 先登记再写入：Ctrl+C 可能落在 with 退出与赋值之间；若此时才
        # 登记，外层 render_command 的清理看不到该文件。写入失败时下方
        # 清掉登记，避免调用方再次 unlink 一个已删除/半成品的路径。
        self._prompt_file = pfile
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
        except BaseException:
            # 写入失败（含 KeyboardInterrupt/SystemExit）时关掉 fd 并清掉
            # 半成品文件，避免内含研究状态的 .prompt.*.md 留在工作区
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                pfile.unlink(missing_ok=True)
            except OSError:
                pass
            self._prompt_file = None
            raise
        return pfile

    def _render_posix(self, tpl: str, prompt: str, dry_run: bool = False,
                      probe: str = _PLACEHOLDER_PROBE) -> str:
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
        正文从「命令行的换行」之后开始：注册在外层命令里的 heredoc，其
        正文不会因命令替换内部的换行而开始（bash/dash 一致，实测替换内部
        与终止符相同的行仍作为替换内命令执行），必须等替换闭合后的外层
        换行再收（见 consume_heredoc_bodies；按注册深度区分）。

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

        ANSI-C 引用（$'...'）与本地化引用（$"..."）的语义取决于实际执行
        命令的 /bin/sh 方言：bash 支持它们（前者解释反斜杠转义，后者做
        gettext 翻译），dash/POSIX sh 不支持（$ 是字面量、后面只是普通
        单/双引号串）。xuen 用 shell=True 执行命令，/bin/sh 在不同系统上
        可能是 bash 也可能是 dash：按任一方言转义都会在另一方言下打乱
        引号边界，使提示词里的 $(...)/`...` 逃出引用被真正执行（注入），
        或让送达的提示词被多拼出一个 $。这种无法确定语义的语境整体拒绝
        （抛 ValueError），由配置校验拦下，而不是替换。

        裸 `>&word`（无 fd 号）重定向词也无法安全替换：bash 把它当
        `&>word` 的别名，但对 word 的展开不遵守引号规则——单引号里的
        $(...)/`...`/参数展开仍会被执行（`>&'$(cmd)'` 真的会跑 cmd），
        双引号里的 \\$ / \\` 也拦不住。与 heredoc 正文/反引号一致整词
        原样跳过（command_receives_prompt 据此拒绝这类模板）。

        续行（反斜杠-换行）在分词前被删除，也会把两侧字符拼成一个新的
        操作符/展开头：`>`+续行+`&` 拼成 `>&`、`<`+续行+`<` 拼成 heredoc
        `<<`、`$`+续行+`(`/`[`/`{`/`'`/`"` 拼成命令替换/旧式算术/参数
        展开/ANSI-C 引用/本地化引用、`(`+续行+`(` 拼成算术命令、`>`/`<`+
        续行+`(` 拼成进程替换。按续行两侧字符独立解析会让引号状态与实际
        shell 脱节：实测 bash 下 `printf %s >\\<换行>&"$prompt"`、`cat
        \\<换行><EOF...`、`printf %s $\\<换行>[$prompt]` 都会执行提示词里的
        命令 $(...)，双引号内的 `"$\\<换行>(` 在 bash 与 dash 下同样可注入。
        这类模板与 $'...' 同口径：整体拒绝（抛 ValueError），由配置
        校验拦下（见 _continuation_split_head）。

        紧跟在未转义 $ 后面的占位符（`$$prompt`）也不是完整占位符：
        shell 把 $$ 当 PID、`prompt` 只是字面量。替换会让提示词与模板
        原语义错位——双引号语境下拼成 `"$"+提示词`，提示词以 ( 开头就
        被当成命令替换执行（注入）、以字母开头则被当成变量名（提示词被
        吞掉）；裸语境下拼成 `$'...'` ANSI-C 引用（bash 解释反斜杠、
        dash 原样保留，提示词被篡改）；`$$prompt_file` 会把文件路径
        前缀上一个 $。与上述跳过区同理：不替换（command_receives_prompt
        据此拒绝这类模板）；`\\$$prompt`（$ 被转义、$prompt 是新展开）
        与 `$$$prompt`（落单的 $ 开启新展开）照常替换，单引号语境里
        $ 只是字面量、也不受影响（见 _placeholder_at）。

        双引号内的 `$$(` / `$${`（PID + 字面括号/花括号）还有一层
        bash/dash 差异：bash 会对 `(` 到配对 `)`（以及 `{` 到配对 `}`）
        的区域做命令替换式配对扫描——区域里的引号只是字面量、不切换
        外层双引号状态；dash 与渲染器按普通规则在引号处切换。区域里
        出现引号时后续 $prompt 会按错误语境插入（双引号里插入单引号
        没有保护作用），提示词里的 $(...)/`...` 被真正执行（注入）。
        这类模板整体拒绝（见 _pid_bracket_quote_region）。

        注释（词首的 # 到行尾）里的引号只是普通字符：渲染器若把注释里的
        ' 当引号开启，与实际 shell 的引号状态脱节，后续 $prompt 按错误
        语境插入（注入）。判断「词首」必须区分词边界 ) 与词内 )：
        $()/$((...))/>(...)/<(...) 的结束 ) 仍是同一个词的一部分，其后
        紧挨的 # 不是注释（echo $(echo hi)#there 输出 hi#there），误判成
        注释同样会跳过引号、让状态脱节；子 shell/case pattern 的 ) 才是
        词边界，其后的 # 仍是注释。

        dry_run=True：只探测哪些占位符会被兑现，$prompt_file 不落盘，
        替换成带探测令牌的假路径（供 command_receives_prompt 使用）。"""
        def file_value() -> str:
            if dry_run:
                return f"/xuen-dry-run/{probe}"
            if self._prompt_file is None:
                return str(self._write_prompt_file(prompt).resolve())
            return str(self._prompt_file.resolve())

        def read_heredoc_delim(pos: int) -> tuple:
            """读取 << 之后的终止符词，返回 (终止符, 词结束位置, 是否带引号)。

            按 shell 的引号移除规则拼出终止符（'EOF' / "EOF" / E\\OF / EOF
            等价）；是否加引号不影响这里的占位符处理——两种正文都不替换
            占位符——但影响正文边界判定：加引号的正文是纯字面量、终止符行
            按行精确匹配；不加引号的正文会做参数/命令替换，dash 会把跨行的
            $(...)/`...` 一直解析下去、连终止符行一起吞进替换（见
            _heredoc_body_open_substitution），必须用第三个返回值区分。

            引号移除还要处理续行与双引号内的转义：反斜杠-换行在单引号外
            会被整对删除、词跨行继续拼接（`<<E\\<换行>OF` 的终止符是
            EOF），删除本身不产生引用字符；单引号内不删续行；双引号内
            \\" \\\\ \\$ \\` 去掉反斜杠只留被转义字符（`<<"E\\$OF"` 的
            终止符是 E$OF）。按普通字符原样拼接会把终止符算错（多出
            换行/反斜杠）：这类合法模板的正文被整体吞到模板结尾、$prompt
            被静默丢弃，配置校验误报「缺少占位符」。

            续行删除后两侧字符同样会拼成新的展开头（`$`+续行+`(` 是
            命令替换、`$`+续行+`"` 是本地化引用……，与 _continuation_
            split_head 同一套判断）：实测 bash 下 `cat <<$\\<换行>
            (echo X) > /dev/null` + 正文行 `$` + `printf %s $prompt`
            里，shell 的终止符是字面量 `$(echo X)`，渲染器若在 ( 处把
            词截成 `$`，正文就会提前结束、把 $prompt 替换进 shell 仍当作
            正文的区域——不加引号的正文会执行提示词里的 $(...)/`...`
            （注入，实测创建文件）。拼接出的展开头/引用头与紧邻写法
            同口径：整体拒绝（quoted 语义与边界都无法安全确定）。

            终止符词里的 $(、${、$[、$'、$"、` 是展开/引用语法：词边界
            由展开内部的解析决定（内部的空白、括号、引号都不会结束词），
            简单扫描会提前截断终止符——渲染器以为正文已结束、把 $prompt
            替换进后面，而 shell 的正文一直延伸到真正的终止符。不加引号的
            正文会展开其中的 $(...)/`...`：实测 bash 下 `cat <<$(echo X)`
            的终止符是字面量 $(echo X)（词不展开、只做引号移除），提示词
            因此被当成正文执行（注入）；$((...))、含空白的 ${...}/$[...]、
            含空白的反引号同理。
            进程替换 <(...)/>(...) 也属于同一个词（`echo a<(cmd)` 输出
            a/dev/fd/63；实测 `cat <<EOF<(cmd)` 的终止符是字面量
            `EOF<(cmd)`，进程替换本身不执行、只留字面文本）：渲染器在
            < 处把词截断，正文提前结束、$prompt 被替换进 shell 仍当作
            正文的区域——不加引号的正文会执行提示词里的 $(...)/`...`
            （注入，实测 bash 创建文件；dash 对 <( 直接报语法错误）；
            带引号的终止符词虽不展开，提示词也会被静默吞掉。这类词返回
            (None, n)，调用方把剩余模板整体吞掉、不做替换
            （command_receives_prompt 据此拒绝）。
            """
            buf: List[str] = []
            quoted = False
            while pos < n:
                c = tpl[pos]
                if c == "\\" and pos + 1 < n:
                    if tpl[pos + 1] == "\n":
                        # 续行：分词前整对删除、词在下一行继续拼接。
                        # 删除不产生引用字符（不算引号），故不置 quoted。
                        # 拼接可能把两侧字符拼成展开头/引用头（`$`+续行+
                        # `(` 拼成命令替换、+`"` 拼成本地化引用）：与紧邻
                        # 写法同口径，整体拒绝（见方法说明；否则终止符词被
                        # 截短、正文提前结束，提示词被替换进 shell 仍当作
                        # 正文的区域，可注入）
                        head = _continuation_split_head(tpl, pos)
                        if head is not None:
                            return None, n, False
                        pos += 2
                        continue
                    buf.append(tpl[pos + 1])
                    pos += 2
                    quoted = True
                    continue
                if c == "'":
                    end = tpl.find("'", pos + 1)
                    if end < 0:
                        buf.append(tpl[pos + 1:])
                        return "".join(buf), n, True
                    buf.append(tpl[pos + 1:end])
                    pos = end + 1
                    quoted = True
                    continue
                if c == '"':
                    # 双引号内做引号移除：续行整对删除；\\" \\\\ \\$ \\` 去掉
                    # 反斜杠只留被转义字符；其他 \\x 的反斜杠是字面量。原样
                    # 拼接会把终止符算错（多出反斜杠/换行）、合法模板被整体
                    # 吞掉（见方法说明）
                    chunk: List[str] = []
                    end = pos + 1
                    while end < n:
                        if tpl[end] == '"':
                            end += 1
                            break
                        if tpl[end] == "\\" and end + 1 < n:
                            nxt = tpl[end + 1]
                            if nxt == "\n":
                                # 双引号内的续行同样在分词前整对删除：
                                # `"$`+续行+`(` 拼成 `"$(`，与紧邻写法
                                # 同口径（嵌套展开内部按自己的规则处理
                                # 引号，字面找 " 会截错词边界、正文范围
                                # 失控）：拼出 $(/${/$[ 时整体拒绝
                                head = _continuation_split_head(tpl, end)
                                if head in ("$(", "${", "$["):
                                    return None, n, False
                                end += 2
                                continue
                            if nxt in '"\\$`':
                                chunk.append(nxt)
                                end += 2
                                continue
                            chunk.append("\\")
                            end += 1
                            continue
                        if (tpl[end] == "`" or tpl.startswith("$(", end)
                                or tpl.startswith("${", end)
                                or tpl.startswith("$[", end)):
                            # 双引号内同样是嵌套解析：展开内部按自己的
                            # 规则处理引号，字面找 " 会截错词边界
                            return None, n, False
                        chunk.append(tpl[end])
                        end += 1
                    buf.append("".join(chunk))
                    pos = min(end, n)
                    quoted = True
                    continue
                if (c == "`" or tpl.startswith("$(", pos)
                        or tpl.startswith("${", pos)
                        or tpl.startswith("$[", pos)
                        or tpl.startswith("$'", pos)
                        or tpl.startswith('$"', pos)):
                    return None, n, False
                if c in "<>" and pos + 1 < n and tpl[pos + 1] == "(":
                    # 进程替换 <(...)/>(...) 与前面的字符同属一个词（见
                    # 方法说明）：内部是任意命令文本，词边界无法简单
                    # 确定——与 ${/反引号 等同类，整体拒绝
                    return None, n, False
                # shell 词在空白与控制运算符处结束
                if c in " \t\n;&|<>()":
                    break
                buf.append(c)
                pos += 1
            return "".join(buf), pos, quoted

        # [(终止符, 是否 <<-, 登记时的命令替换深度, 终止符词是否带引号)]
        pending_heredocs: List[tuple] = []

        def consume_heredoc_bodies(pos: int) -> int:
            """把已登记 heredoc 的正文原样吞掉（不做任何占位符替换）。

            正文按 shell 语义处理：不加引号的终止符下正文会做参数/命令替换，
            加引号时正文是纯字面量——两种情况下 shlex.quote 加的引号在正文里
            都只是普通字符，起不到保护作用。因此绝不能替换正文里的
            $prompt，否则提示词里的 $(...)/`...` 会被 shell 执行。
            找不到终止符时与 shell 一致：一直吞到模板结尾。

            只收注册深度 >= 当前替换深度的 heredoc：命令替换内部的换行
            不会让「外层命令的 heredoc」开始收正文（bash/dash 一致，实测
            换行后与该终止符相同的行仍作为替换内部命令执行），外层 heredoc
            要等替换闭合后的外层换行再收；若在这里提前收，会把替换内部的
            命令行当成正文吞掉、随后又在外层正文位置恢复替换——正好把
            $prompt 插进 shell 真正当正文处理的区域（注入）。
            反之，注册在更深层替换里的 heredoc 若其替换已闭合仍未收正文
            （`echo $(cat <<B)`），bash 会在下一个换行处补收（带 warning），
            深度条件 >= 当前深度会把它一并收掉；但 dash 对这类 heredoc
            的处理随命令形态而变：实测 `x=$(cat <<B)` 静默丢弃（后续行被
            当命令执行，其中的 `<<x` 会另外开启一个吞到模板结尾的正文），
            `x=$(exec 3<<B; :)` 又照常收正文——丢弃时渲染器多吞掉的区域
            正是 shell 当命令解析的区域，若正文终点不一致就可能在 dash
            仍当作正文的区域恢复替换（提示词里的 $(...)/`` 被真正执行，
            注入，实测创建文件）。因此存在这种「比当前深度更深」的
            heredoc 时，只有 dash 口径（只收深度 == 当前深度的正文，从
            换行处按登记顺序）与 bash 口径（深度降序收全部）的正文终点
            完全一致，才恢复替换；不一致时与其它无法安全替换的语境一致，
            剩余模板整体吞掉、不做替换（command_receives_prompt 据此
            拒绝这类模板）。

            待收正文的读取顺序必须与 shell 一致：登记深度更深（嵌套在
            命令替换里）的 heredoc 先读，同深度按登记顺序。bash 实测
            `cat <<A $(cat <<B)` 先读 B 的正文再读 A 的（probe 验证嵌套
            深度优先、同深度按登记顺序；相邻探测如
            `3<<T1 5<<T3 $(cat <<T2) $(cat <<T4)` 的读取顺序是
            T2,T4,T1,T3）。按登记顺序收会把两个 heredoc 的正文边界张冠
            李戴：`cat <<A $(cat <<B)\\nBODY\\nB\\nA\\n$prompt` 里按登记
            顺序先收 A（把 B 行当 A 的终止符、正文提前结束），随后在
            shell 仍当作 A 正文的区域恢复替换——bash 实际先收 B 的正文
            （BODY、B）、A 的正文从 `$prompt` 行延伸下去，提示词里的
            $(...)/`` 在该区域被真正执行（注入，实测创建文件）。
            dash 对已闭合替换里的 heredoc 按空正文处理、外层正文按登记
            顺序读：其正文区域都落在深度优先所吞掉的范围之内，恢复替换
            的位置只会更晚，同样是安全方向。

            不加引号的正文会做展开，反斜杠-换行在展开时被删除、终止符
            匹配发生在「逻辑行」上：行尾奇数个反斜杠要把下一物理行拼进
            同一个逻辑行再比较（bash 实测 `foo\\`+换行+`EOF` 拼成 fooEOF、
            不是终止符，正文继续到下一个 EOF 行；`\\`+换行+`EOF` 拼成
            EOF 则终止）。dash 也先吃掉续行再找终止符，但只在「检查点」
            （正文开头、真实换行之后、整行反斜杠的续行之后）逐字比较
            物理行，行内续行拼出的终止符不算数（实测 `EO\\`+换行+`F` 只有
            bash 终止）。按物理行匹配会让渲染器提前结束正文、把 $prompt
            替换进 shell 仍当作正文的续行区域——不加引号的正文会执行
            提示词里的 $(...)/``，bash 与 dash 均可注入（实测创建文件）。
            这里按 dash 的检查点口径匹配（终止符行要求此前没有非空续行
            前缀、且自身不以反斜杠续行结尾）：dash 的正文边界与它完全
            一致，bash 的边界只会相同或更早，恢复替换的位置对两种 shell
            都安全（bash 更早结束的行宁可多吞、不替换）。加引号的正文
            不展开、没有续行语义，仍按物理行精确匹配。

            不带引号的正文里出现横跨终止符行仍未闭合的 $()/`` 等展开时，
            这一行不是真正的正文结束：dash 会把它吞进展开、正文继续
            （见 _heredoc_body_open_substitution），此处继续按正文往后吞，
            直到某个终止符行处所有展开都已闭合（或吞到模板结尾）。
            """
            def scan_body(pos: int, delim: str, strip_tabs: bool,
                          quoted: bool) -> int:
                """从 pos 起收一个 heredoc 的正文，返回正文（含终止符行）后的下标。

                不加引号的正文按续行语义找终止符（见 consume_heredoc_bodies
                说明）：logical_prefix 非空 = 当前处于逻辑行中间，不是 dash
                的终止符检查点，与行尾反斜杠一起决定本行能否结束正文。
                """
                body_start = pos
                logical_prefix = ""
                while pos < n:
                    j = tpl.find("\n", pos)
                    end = n if j < 0 else j + 1
                    line = tpl[pos:] if j < 0 else tpl[pos:j]
                    pos = end
                    if quoted:
                        if (line.lstrip("\t") if strip_tabs
                                else line) == delim:
                            break
                        continue
                    # 行尾奇数个反斜杠 = 续行：删除末尾反斜杠与换行，
                    # 与下一物理行拼成同一个逻辑行
                    k = len(line)
                    while k > 0 and line[k - 1] == "\\":
                        k -= 1
                    if (len(line) - k) % 2:
                        logical_prefix += line[:-1]
                        continue
                    if (not logical_prefix
                            and (line.lstrip("\t") if strip_tabs
                                 else line) == delim):
                        # 不加引号的正文里若有横跨终止符行仍未闭合的
                        # $()/`` 等展开：dash 会把这一行也吞进展开、正文
                        # 继续（见 _heredoc_body_open_substitution），
                        # 此处不是真正的正文结束，继续按正文往后吞
                        if not _heredoc_body_open_substitution(
                                tpl, body_start, pos):
                            break
                    logical_prefix = ""
                return pos

            depth = len(subst_stack)
            kept = []
            consume = []
            for entry in pending_heredocs:
                if entry[2] < depth:
                    kept.append(entry)
                else:
                    consume.append(entry)
            # sorted 是稳定排序：同深度保持登记顺序，深度优先与 bash 一致
            consume.sort(key=lambda e: -e[2])
            if any(e[2] > depth for e in consume):
                # 注册在「已闭合的更深替换」里的 heredoc：bash 会在下一个
                # 换行处补收正文（带 warning），dash 的处理却随命令形态而
                # 变（见方法说明），只有两 shell 的正文终点完全一致时才
                # 能恢复替换。dash 只收「登记深度 == 当前深度」的正文
                # （从换行处开始、按登记顺序），bash 按深度降序收全部；
                # 终点不一致时渲染器多吞的区域会被 dash 当命令解析
                # （其中的 `<<x` 会开启吞到模板结尾的正文），继续替换
                # 可注入，必须整体吞到模板结尾、不做替换。
                active = [e for e in consume if e[2] == depth]
                dash_end = pos
                for delim, strip_tabs, _d, quoted in active:
                    dash_end = scan_body(dash_end, delim, strip_tabs, quoted)
                bash_end = pos
                for delim, strip_tabs, _d, quoted in consume:
                    bash_end = scan_body(bash_end, delim, strip_tabs, quoted)
                if dash_end != bash_end:
                    out.append(tpl[pos:])
                    pending_heredocs[:] = kept
                    return n
            for delim, strip_tabs, _reg_depth, quoted in consume:
                end = scan_body(pos, delim, strip_tabs, quoted)
                out.append(tpl[pos:end])
                pos = end
            pending_heredocs[:] = kept
            return pos

        out: List[str] = []
        # 进入 $( 时的解析上下文栈：[外层引号状态, 括号深度]。
        # 深度用于区分「子 shell 的 )」与「$( 的 )」：前者只减深度，
        # 后者（深度归零）才恢复外层引号状态
        subst_stack: List[list] = []
        # 最近一次「词内 )」在模板中的位置（$()/$((...))/>(...)/<(...)
        # 的结束括号）：紧跟其后的 # 仍是同一个词的一部分，不是注释
        # （echo $(echo hi)#there 输出 hi#there）。子 shell/case pattern
        # 的 ) 是词边界，其后的 # 才是注释，必须区分（见下面的 # 分支）
        word_internal_paren_end = -1
        # 已消费注释里紧贴换行的反斜杠位置集合（注释吞掉的反斜杠不构
        # 成续行：换行仍是硬换行、结束注释；`#a\\<换行>#$prompt` 里第二
        # 个 # 仍开注释）。不记录的话 _prev_effective_pos 会把跨过它的
        # 换行当续行删除、把注释内的字符当成相邻字符，误判 # 不是注释
        # 起点，$prompt 被替换进 shell 的注释里——提示词的换行逃出注释
        # 成为被执行的命令（注入，见 _prev_effective_pos）
        commented_backslashes: Set[int] = set()
        # 最近一次兑现的占位符在模板中的结束位置：紧贴它的单词字符是
        # 替换结果的结尾、不是模板字面量（`$prompt$prompt` 的第二个
        # 占位符要照常替换，见 _placeholder_at / _directly_after_placeholder）
        last_ph_end = -1
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
                ph = self._placeholder_at(tpl, i, state="single",
                                          prev_ph_end=last_ph_end,
                                          commented_backslashes=commented_backslashes)
                if ph == "$prompt":
                    out.append(_escape_in_single_quotes(prompt))
                    last_ph_end = i + len(ph)
                    i += len(ph)
                    continue
                if ph == "$prompt_file":
                    out.append(_escape_in_single_quotes(file_value()))
                    last_ph_end = i + len(ph)
                    i += len(ph)
                    continue
                out.append(ch)
                i += 1
                continue
            if state == "double":
                # 双引号内反斜杠仅对 $ ` " \ 换行有转义作用，遇到这类组合
                # 原样成对复制，避免把 \x 的转义状态算错导致引号误判
                if ch == "\\" and i + 1 < n and tpl[i + 1] in ("\\", '"', "$", "`", "\n"):
                    if tpl[i + 1] == "\n":
                        # 双引号内的续行同样在分词前被删除：`"$\<换行>(`
                        # 拼成 `"$(`，引号内的命令替换照常生效；按普通
                        # 字符解析会让状态与实际 shell 脱节（注入）
                        head = _continuation_split_head(tpl, i, commented_backslashes)
                        if head is not None:
                            raise _continuation_split_error(head)
                    out.append(tpl[i:i + 2])
                    i += 2
                    continue
                if (tpl.startswith("$(", i)
                        and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                    # 双引号内的命令替换/算术展开同样开启独立上下文。
                    # 必须确认这个 $ 真的开启展开：`$$(` 里第二个 $ 只是
                    # PID（$$）的后半，双引号内的 ( 是字面量（bash/dash
                    # 一致）；若按 $( 切到独立上下文，后续 $prompt 会按裸
                    # 语境插入（shlex.quote 的单引号），而实际 shell 仍在
                    # 双引号里——单引号只是字面量，提示词里的 $(...)/`...`
                    # 逃出引用被真正执行（注入）
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
                if (tpl.startswith("${", i)
                        and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                    # ${...} 参数展开（算术语境的数组下标/子串展开与词语境
                    # 的 ${x:-word} 等）都是无法安全替换的数据区
                    # （见方法说明），整段原样跳过、不替换。
                    # `$${...` 同理不是参数展开（$$ 是 PID，{ 是字面量），
                    # 不能按 ${ 跳掉实际会被 shell 正常解析的文本
                    j = _parameter_expansion_end(tpl, i)
                    out.append(tpl[i:j])
                    i = j
                    continue
                if (tpl.startswith("$[", i)
                        and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                    # 双引号内的旧式算术展开 $[...] 同样是表达式语境，
                    # 整体原样跳过、不替换；`$$[...` 的 $[ 同理不是展开
                    j = _legacy_arithmetic_end(tpl, i)
                    out.append(tpl[i:j])
                    i = j
                    continue
                if ch in "({" and _pid_bracket_quote_region(
                        tpl, i, commented_backslashes):
                    # `$$(` / `$${` 的区域里有会切换引号状态的 "：bash 对
                    # 区域做命令替换式配对扫描、区域内的引号只是字面量、
                    # 不切换外层双引号，而渲染器（与 dash 一致）在这里切到
                    # 裸语境——区域内的 $prompt 会按裸语境插入单引号，
                    # bash 却仍在双引号里，单引号只是字面量，提示词里的
                    # $(...)/`...` 逃出引用被真正执行（注入）。与 $'...'
                    # 同口径：整体拒绝、绝不替换（command_receives_prompt
                    # 据此让配置校验拒绝），见 _pid_bracket_quote_region
                    raise ValueError(
                        "agent.command 不支持 `$$(` / `$${` 后括号区域里"
                        "出现引号的写法：shell 把 $$ 当 PID、括号当字面量，"
                        " bash 会对括号到配对结束符的区域做命令替换式扫描"
                        "（区域里的引号只是字面量、不切换外层引号），而实"
                        "际解析会按引号状态把提示词放错语境——提示词里的 "
                        "$(...)/`...` 被真正执行（注入）。请改用普通写法，"
                        '例如 "$prompt"'
                    )
                if ch == '"':
                    state = "bare"
                    out.append(ch)
                    i += 1
                    continue
                ph = self._placeholder_at(tpl, i, state="double",
                                          prev_ph_end=last_ph_end,
                                          commented_backslashes=commented_backslashes)
                if ph == "$prompt":
                    out.append(_escape_in_double_quotes(prompt))
                    last_ph_end = i + len(ph)
                    i += len(ph)
                    continue
                if ph == "$prompt_file":
                    out.append(_escape_in_double_quotes(file_value()))
                    last_ph_end = i + len(ph)
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
                if tpl[i + 1] == "\n":
                    # 续行在分词前被删除：两侧字符会拼成新 token/操作符
                    # （`>\<换行>&` 是 >&、`$\<换行>(` 是命令替换……），
                    # 按续行两侧独立解析会与实际 shell 脱节（注入），
                    # 这类模板整体拒绝（与 $'...' 同口径）
                    head = _continuation_split_head(tpl, i, commented_backslashes)
                    if head is not None:
                        raise _continuation_split_error(head)
                out.append(tpl[i:i + 2])
                i += 2
                continue
            if ch == "#":
                # shell 注释：词首的 # 之后直到行尾都原样保留、不参与解析。
                # 注释里的不成对引号若被当成引号状态，会让后续占位符按
                # 错误的引号语境转义（转义过弱 = 提示词可被 shell 解释执行，
                # 转义过强 = 参数被拆错）；注释里的 $prompt 也不会真正送到
                # agent，command_receives_prompt 不能把它当作有效占位符。
                # 词中的 #（如 foo#bar、=$#）不是注释，照常按字符处理；
                # 紧跟 $()/$((...))/>(...)/<(...) 结束 ) 的 # 同样是词中
                # 字符（echo $(echo hi)#there 输出 hi#there），不算注释——
                # 若误判成注释会跳过引号、与实际 shell 的引号状态脱节，
                # 后续 $prompt 会按错误语境插入（注入）。
                # 「词首」判定必须按删除续行后的相邻字符：`a\<换行># x`
                # 拼成 `a# x`，# 是词中字符而不是注释，按裸换行误判成
                # 注释会跳过整行、$prompt 原样保留（提示词被静默丢弃）
                # 且必须排除被反斜杠转义的边界字符：`echo \ #x` 里 `\ `
                # 是转义空格、属于词的一部分（bash 与 dash 都输出 ` #x`），
                # 其后的 # 不是注释。若误判成注释会跳过该行剩余部分（含
                # 不成对引号），与实际 shell 的引号状态脱节，后续 $prompt
                # 按错误语境插入、提示词里的 $(...)/`...` 被真正执行
                # （注入，见 test_render_command_escaped_delimiter_hash）。
                # 注释行尾的反斜杠不续行（被注释吞掉）：`#a\<换行>#x` 里
                # 第二个 # 仍是词首注释，不能因为反斜杠奇偶判定成续行、
                # 把 # 当成上一行注释的词中字符——那会把 $prompt 替换进
                # shell 的注释里，提示词的换行逃出注释成为被执行的命令
                # （注入）。_prev_effective_pos 按 commented_backslashes
                # 返回硬换行的位置，此时该换行前的反斜杠不构成转义
                prev = _prev_effective_pos(tpl, i, commented_backslashes)
                if prev < 0 or (
                        tpl[prev] in " \t\n;&|()<>"
                        and prev != word_internal_paren_end
                        and not (_escaped_at(tpl, prev)
                                 and (prev - 1) not in
                                 commented_backslashes)):
                    j = tpl.find("\n", i)
                    if j < 0:
                        out.append(tpl[i:])
                        i = n
                    else:
                        if tpl[j - 1] == "\\":
                            # 注释在换行处结束，行尾反斜杠被注释吞掉、
                            # 不构成续行：记录位置供 _prev_effective_pos
                            commented_backslashes.add(j - 1)
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
            if (tpl.startswith("$((", i)
                    and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                # 算术展开内部是表达式，整体原样跳过：既不替换占位符
                # （shell 会把那里的 $prompt 当普通变量展开，送不到
                # agent），也避免位移运算符 << 被误登记成 heredoc。
                # `$$((` 不是算术展开（$$ 是 PID），不能按 $(( 跳过
                j = _arithmetic_end(tpl, i)
                out.append(tpl[i:j])
                if j > i and tpl[j - 1] == ")":
                    # $((...)) 的结束 )) 是词内字符：紧随其后的 #
                    # 不是注释（echo $((1+1))#there 输出 2#there）
                    word_internal_paren_end = j - 1
                i = j
                continue
            if (tpl.startswith("${", i)
                    and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                # ${...} 参数展开（数组下标/子串展开等算术语境与
                # ${x:-word} 等词语境）内部都无法安全替换占位符
                # （见方法说明），整段原样跳过（command_receives_prompt
                # 据此拒绝这类模板）。`$${...` 不是参数展开（$$ 是 PID、
                # { 是字面量），不能按 ${ 跳过后面实际正常解析的文本
                j = _parameter_expansion_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if (tpl.startswith("$[", i)
                    and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                # 旧式算术展开 $[...]：内部是表达式，与 $((...)) 同理，
                # 插入的引号不构成保护，整体原样跳过、不替换；
                # `$$[...` 的 $[ 同理不是展开
                j = _legacy_arithmetic_end(tpl, i)
                out.append(tpl[i:j])
                i = j
                continue
            if ((tpl.startswith("$'", i) or tpl.startswith('$"', i))
                    and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                # ANSI-C 引用（$'...'）与本地化引用（$"..."）的解释随
                # /bin/sh 方言而变：bash 按引用处理（前者解释反斜杠转义，
                # 后者做 gettext 翻译），dash 则把 $ 当字面量、后面当普通
                # 单/双引号串。xuen 用 shell=True 执行（Linux 上通常是
                # dash，macOS/RHEL 上是 bash），无法预知方言：按 bash 规则
                # 转义插入提示词，在 dash 下引号边界会被打乱——$' 语境下
                # 提示词里的 `; cmd` / $(cmd) 逃出引用被真正执行（注入）；
                # $" 语境下提示词被静默多拼出一个 $（两 shell 送达的内容
                # 不一致）。与其他不安全语境一致：整体拒绝这类模板，
                # 绝不替换（command_receives_prompt 据此让配置校验拒绝）。
                # `$$'...` / `$$"...` 不是引用（$$ 是 PID、引号只是普通
                # 引号开头），照下面的分支按引号语境处理
                form = "$'...'" if tpl[i + 1] == "'" else '$"...'
                raise ValueError(
                    f"agent.command 不支持方言相关的引用（{form}）：不同"
                    "系统的 /bin/sh（bash 支持、dash 把 $ 当字面量）对它"
                    "的解释不同，无法安全传递提示词；请改用普通引号，"
                    '例如 "$prompt" 或 \'$prompt\''
                )
            if ch == "(":
                # 数组赋值 NAME=(...) / NAME+=(...)：`(` 紧跟在赋值等号后
                # （按删除续行后的相邻字符判断，`NAME=\\<换行>(` 同样是
                # 数组赋值）。这是非 POSIX 的 bash 语法：dash 下在 ( 处
                # 直接报语法错误、命令无法运行；更危险的是 bash 对数组内
                # 语法错误的恢复行为——`NAME=(;` 会放弃当前命令并把后续
                # 行当命令执行（实测 `v=(; $prompt` 渲染后，提示词里的
                # $(touch x)/`touch x` 被真正执行、创建文件），`NAME=((`
                # 这类非法数组整型写法同样触发。提示词一旦按跨行引号串
                # 落进这种模板，其后的提示词行就会成为被执行的命令。
                # /bin/sh 方言无法预知，与 $'...' 同口径：整体拒绝、绝不
                # 替换（command_receives_prompt 据此让配置校验拒绝），
                # 也避免合法数组模板在 dash 下「能通过校验却永远跑不了」
                prev = _prev_effective_pos(tpl, i, commented_backslashes)
                if (prev >= 0 and tpl[prev] == "="
                        and not _escaped_at(tpl, prev)):
                    raise ValueError(
                        "agent.command 不支持数组赋值（NAME=(...)）：这是"
                        "非 POSIX 的 bash 语法，dash 下命令无法运行；且 "
                        "bash 在数组内出现语法错误时会把后续行当命令执行，"
                        "提示词里的 $(...)/`...` 会被真正执行（注入）。"
                        '请改用普通参数传递，例如 "$prompt"'
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
            if (tpl.startswith("$(", i)
                    and _dollar_starts_expansion(tpl, i, commented_backslashes)):
                # 命令替换开启独立解析上下文（见方法说明）。
                # 必须确认这个 $ 真的开启展开：`$$(` 里第二个 $ 是 PID
                # （$$）的后半，( 只是普通字符（另一层含义见
                # _placeholder_at：$$prompt 也不是占位符）；误按 $( 处理
                # 会让后续 $prompt 按错误引号语境插入（注入）
                out.append(tpl[i:i + 2])
                subst_stack.append([state, 1])
                state = "bare"
                i += 2
                continue
            if tpl.startswith(">(", i) or tpl.startswith("<(", i):
                # 进程替换 >(...) / <(...)（bash 等支持）：内部是命令列表，
                # 与 $( 一样开启独立解析上下文（进程替换也可嵌套在 $( 内）。
                # 结束的 ) 仍是同一个词的一部分，其后紧挨的 # 不是注释
                # （echo <(echo hi)#there 在 bash 下输出 /dev/fd/63#there）；
                # 不跟踪的话 # 会被误当注释、引号状态与实际 shell 脱节，
                # 后续 $prompt 会按错误语境插入（注入）。dash 等不支持
                # 进程替换的 shell 会直接报语法错误，此时按命令替换解析
                # 不影响实际执行
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
                    # $()/>(...)/<(...) 的结束括号是词内字符：紧随其后的
                    # # 不是注释，记录位置供 # 分支判断
                    word_internal_paren_end = i
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
                delim, j, delim_quoted = read_heredoc_delim(j)
                if delim is None:
                    # 终止符词含无法安全确定边界的展开（$(、${、$[...、$'、
                    # $"、` 等）：与实际 shell 的词边界可能不一致，正文
                    # 范围无法判断。与 heredoc 正文同口径：整体吞到模板
                    # 结尾、不做替换
                    out.append(tpl[i:])
                    i = n
                    continue
                out.append(tpl[i:j])
                pending_heredocs.append(
                    (delim, strip_tabs, len(subst_stack), delim_quoted))
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
            ph = self._placeholder_at(tpl, i, state="bare",
                                      prev_ph_end=last_ph_end,
                                      commented_backslashes=commented_backslashes)
            if ph == "$prompt":
                out.append(_quote(prompt))
                last_ph_end = i + len(ph)
                i += len(ph)
                continue
            if ph == "$prompt_file":
                out.append(_quote(file_value()))
                last_ph_end = i + len(ph)
                i += len(ph)
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _render_windows(self, tpl: str, prompt: str, dry_run: bool = False,
                        probe: str = _PLACEHOLDER_PROBE) -> str:
        f_sentinel = "\0XUEN_PROMPT_FILE\0"
        # 引号内的占位符单独用一个哨兵：外层引号已经把路径归组，插入
        # list2cmdline 生成的引号会变成嵌套引号（"pre "C:\Users\John
        # Doe\p.md" suf"），cmd 把参数拆错、外部 agent 拿到坏路径
        f_inq_sentinel = "\0XUEN_PROMPT_FILE_INQ\0"
        p_sentinel = "\0XUEN_PROMPT\0"
        # 与 POSIX 侧同口径：$'...' / $"..." 是方言相关的引用语法（bash
        # 按 ANSI-C/本地化字符串解释、dash 把 $ 当字面量），xuen 无法预知
        # 最终 shell。Windows 上 cmd 虽不展开 $，但这类写法几乎总是按
        # POSIX 语义书写的模板（同一份配置应两端一致）：`$"$prompt_file"`
        # 会把字面 $ 粘在替换出的路径前（先替换引号内占位符、外层 $ 与
        # 引号里的路径在 cmd 下拼接），外部 agent 拿到 `$C:\...` 的坏路径，
        # 而 POSIX 侧对同一模板报错拒绝。整体拒绝、由配置校验拦下。
        # 扫描按 cmd 引号状态：双引号内的 $" 只是字面 $ 紧邻引号
        # （如 "x$"y"$prompt_file"）、^" 是字面引号、\$" 的 $ 前有反斜杠
        # ——都不是方言引用，照常兑现（与 _cmd_double_quotes_after 同规则）
        i = 0
        tpl_n = len(tpl)
        in_quotes = False
        while i + 1 < tpl_n:
            c = tpl[i]
            if c == "^" and not in_quotes:
                i += 2
                continue
            if c == '"':
                in_quotes = not in_quotes
                i += 1
                continue
            if (not in_quotes
                    and (tpl.startswith("$'", i) or tpl.startswith('$"', i))
                    and _dollar_starts_expansion(tpl, i)):
                form = "$'...'" if tpl[i + 1] == "'" else '$"...'
                raise ValueError(
                    f"agent.command 不支持方言相关的引用（{form}）：不同"
                    "系统的 shell 对它解释不同，xuen 无法安全传递提示词"
                    "（Windows 的 cmd 会把字面 $ 粘在替换出的路径前）；"
                    '请改用普通引号，例如 "$prompt_file"'
                )
            i += 1
        # 先把两处占位符统一换成哨兵，最后才一次性替换成实际内容。
        # 若先插入内容再做另一处替换，后插入的内容（转义后的提示词 /
        # 提示词文件路径）里恰好含有占位符字面量时会被二次替换、破坏命令
        # （占位符被模板自带引号包住时，连引号一起换成哨兵，否则转义结果
        # 嵌在引号里会被当作字面值）
        for ph in ('"$prompt_file"',):
            tpl = tpl.replace(ph, f_sentinel)
        # 单引号在 cmd 中只是普通字符：只有整对单引号位于双引号外时，才按
        # 「整词占位符」处理（保持既有行为）。位于双引号内时保留单引号
        # 字面量，只把内部占位符按「引号内」插入裸路径——否则
        # `tool "'$prompt_file'"` 会被替换成 `tool ""C:\path""`，嵌套引号
        # 让 cmd 拆错参数，外部 agent 拿到坏路径。
        sq_pattern = re.compile(r"'\$prompt_file'")
        sq_parts = []
        sq_last = 0
        sq_in_quotes = False
        for match in sq_pattern.finditer(tpl):
            sq_in_quotes = _cmd_double_quotes_after(
                tpl[sq_last:match.start()], sq_in_quotes)
            sq_parts.append(tpl[sq_last:match.start()])
            if sq_in_quotes:
                sq_parts.append("'" + f_inq_sentinel + "'")
            else:
                sq_parts.append(f_sentinel)
            sq_last = match.end()
        sq_parts.append(tpl[sq_last:])
        tpl = "".join(sq_parts)
        # 剩余占位符要按所在的 cmd 引号状态区分：引号内插裸路径、引号外
        # 插转义路径（Windows 上 $prompt 已被配置校验整体拒绝，只有
        # $prompt_file 需要区分；见 config._validate）
        parts = []
        last = 0
        in_quotes = False
        for i in _windows_placeholder_starts(tpl, "$prompt_file"):
            in_quotes = _cmd_double_quotes_after(tpl[last:i], in_quotes)
            parts.append(tpl[last:i])
            parts.append(f_inq_sentinel if in_quotes else f_sentinel)
            last = i + len("$prompt_file")
        parts.append(tpl[last:])
        tpl = "".join(parts)
        for ph in ('"$prompt"', "'$prompt'"):
            tpl = tpl.replace(ph, p_sentinel)
        parts = []
        last = 0
        for i in _windows_placeholder_starts(tpl, "$prompt"):
            parts.append(tpl[last:i])
            parts.append(p_sentinel)
            last = i + len("$prompt")
        parts.append(tpl[last:])
        tpl = "".join(parts)

        if f_sentinel in tpl or f_inq_sentinel in tpl:
            if dry_run:
                # 只探测占位符是否会被兑现：不落盘提示词文件
                path = f"/xuen-dry-run/{probe}"
            else:
                pfile = self._write_prompt_file(prompt)
                path = str(pfile.resolve())
            # 引号内直接插裸路径（文件名不可能含 "，且含 cmd 元字符的
            # 工作区在配置校验已拒绝）；引号外按 cmd 规则加引号
            tpl = tpl.replace(f_inq_sentinel, path)
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
        _user_killed 只在确实杀掉一个存活进程时置位：进程已退出的收尾
        窗口里到达的 kill（如 TUI 按 q 恰好落在进程退出与 run() 收尾
        之间）什么都杀不到，若也置位，刚完整跑完（rc=0）的轮次会被
        runner 当作「被用户终止，轮次未完成」丢弃并还原最佳。同理，
        proc 已存在但 poll() 非 None 时只忽略请求、不记待处理，否则会
        误杀下一轮。run() 已起跑但进程尚未拉起时杀不到，会记 _killed，
        由本次 run 在 Popen 后立即补杀并自行补置位 _user_killed；上一轮
        已收尾后的空闲期则不记，避免晚到请求把下一轮刚拉起的 agent
        误杀。
        """
        with self._kill_lock:
            proc = self._proc
            if proc is not None:
                # 进程对象还在（本轮 run() 已起跑）：只有仍存活时才需要
                # 终止。poll() 非 None 表示进程已经自行退出、只是 run()
                # 尚未 wait()/收尾——此时 kill 什么都杀不到，当前轮内容
                # 已完整；绝不能记成待处理请求，否则会误杀下一轮。
                if proc.poll() is None:
                    self._user_killed = True
            elif not self._idle_after_run:
                # 本轮尚未拉起进程（run() 已起跑）或从未 run 过：记成
                # 待处理请求。上一轮已完整收尾后的空闲期不能再记——
                # 那会把晚到的停止请求错误地兑现到下一轮。
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
            self._idle_after_run = False
            killed_before = self._killed
            self._killed = False
            # killed_before 本身就是一次用户停止请求（kill 到达时尚无进程可杀），
            # 不能在这里降级成普通的 start→rc=-9 失败轮次。
            self._user_killed = killed_before
        proc = None
        try:
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
        except Exception as e:
            # 启动失败（如提示词含 NUL 字节）时提示词文件已无消费者，
            # 必须清理，否则每次启动失败都在工作区留一个 .prompt.*.md
            self._cleanup_prompt_file()
            with self._kill_lock:
                self._idle_after_run = True
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
        except BaseException:
            # KeyboardInterrupt / SystemExit 落在渲染或 Popen 之间（Ctrl+C
            # 的常见窗口）时同样清理：提示词文件已无消费者，内含研究状态，
            # 不能留在工作区。Popen 已返回但还没进入 wait 收尾时进程可能
            # 已在运行：先杀掉再清理，不要留下孤儿进程去读已删除的文件
            if proc is not None:
                kill_process_tree(proc)
            self._cleanup_prompt_file()
            with self._kill_lock:
                self._idle_after_run = True
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
            # 杀进程，不会再置位 _killed，故此处清除不会丢任何请求。
            # kill() 杀不到进程时只记 _killed、不再直接置位 _user_killed
            # （见 kill() 注释），所以这里发现待处理请求（进程马上会被
            # 补杀）时要补置 _user_killed：本轮的 rc=-9 是用户终止，不能
            # 被计成 agent 执行失败
            pending_kill = killed_before or self._killed
            self._killed = False
            if pending_kill:
                self._user_killed = True
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

        t_out: Optional[threading.Thread] = None
        # stderr 不回读、仅回调：丢弃列表避免长会话无界内存增长
        t_err: Optional[threading.Thread] = None
        timer: Optional[threading.Timer] = None
        reaped = False
        try:
            t_out = threading.Thread(target=pump, args=(proc.stdout, out, self.on_output), daemon=True)
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
                reaped = True
                # 进程已回收即本轮已完整结束：收尾还要 join 输出线程、
                # 等待超时回调结束，可能持续数秒。这个窗口里到达的 kill
                # 已没有任何进程可终止，不能记成待处理请求——否则会在
                # 下一轮 Popen 后立即补杀，把完整的下一轮误报成用户终止。
                # 必须在这里就标记空闲，不能等到整个 finally 结束。
                with self._kill_lock:
                    self._idle_after_run = True
            except KeyboardInterrupt:
                kill_process_tree(proc)
                raise
        finally:
            # 线程创建 / 启动 / 定时器设置期间也可能被 Ctrl+C 或
            # SystemExit 打断（这些步骤都在 proc.wait 的 try 之外）。
            # 此时子进程已在运行、提示词文件也已落盘：必须先终止并
            # 回收进程，否则 start_new_session 的子进程会成为孤儿。
            if timer is not None:
                timer.cancel()
            if not reaped:
                try:
                    if proc.poll() is None:
                        kill_process_tree(proc)
                    proc.wait(timeout=5)
                except (subprocess.TimeoutExpired, OSError, ValueError):
                    pass
            if timer is not None:
                # 超时回调可能已开始执行（正在 kill/复查退出码）：
                # 必须等它执行完，否则主线程读到的 killed 标志可能不是最终值，
                # 导致「真超时被报成异常退出」或反之。Timer 可能尚未成功启动
                # （启动瞬间被中断），此时 join 会抛 RuntimeError，忽略即可。
                try:
                    timer.join()
                except RuntimeError:
                    pass
            for thread in (t_out, t_err):
                if thread is not None:
                    try:
                        thread.join(timeout=5)
                    except RuntimeError:
                        pass
            with self._kill_lock:
                self._proc = None
                self._idle_after_run = True
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
    （如方言相关的引用 $'...' / $"..."）同样按「提示词无法送达」处理。"""
    probe = _PLACEHOLDER_PROBE
    while probe in template:
        probe += "Z"
    probe_agent = ShellAgent(template, Path("."), timeout=1.0)
    try:
        rendered = probe_agent.render_command(probe, dry_run=True, probe=probe)
    except ValueError:
        return False
    return probe in rendered
