"""ShellAgent 命令渲染回归：Windows 引号规则与提示词文件生命周期。

本文件从 test_agents_render.py 按被测功能物理拆分而来，只移动测试、
不改任何断言；覆盖 cmd 的 ^ 转义/引号语境与 $prompt_file 的清理。
"""
from __future__ import annotations


def _posix_shell_available():
    import os
    import shutil
    return os.name == "posix" and shutil.which("bash") and shutil.which("sh")


def test_render_windows_prompt_file_inside_quotes_is_not_double_quoted(
        tmp_path, monkeypatch):
    """Windows 下 $prompt_file 嵌在双引号串中间时不能再套一层引号。

    回归：模板 `tool "pre $prompt_file suf"`（占位符前后还有字面量，
    不匹配整词的 "$prompt_file" 预处理）在渲染时被替换成
    subprocess.list2cmdline 生成、带引号的路径，而它本身已在一对双引号
    内，结果得到 `tool "pre "C:\\Users\\John Doe\\p.md" suf"` 这类嵌套
    引号：cmd.exe 会把参数拆成多段，外部 agent 拿到坏路径（工作区含
    空格时必现，Windows 用户目录常含空格）。修复：按 cmd 的引号状态
    决定插入裸路径（引号内）还是 list2cmdline 转义后的路径（引号外）。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    ws = tmp_path / "ws with space"
    ws.mkdir()

    def render(tpl):
        agent = agents.ShellAgent(tpl, ws, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None
            path = str(agent._prompt_file.resolve())
            assert " " in path
            return rendered, path
        finally:
            agent._cleanup_prompt_file()

    # 引号内有前后缀：路径直接插入引号内，不能再生成嵌套引号
    rendered, path = render('tool "pre $prompt_file suf"')
    assert rendered == f'tool "pre {path} suf"', rendered
    rendered, path = render('tool "a $prompt_file"')
    assert rendered == f'tool "a {path}"', rendered
    # 引号外：仍按 cmd 规则给含空格的路径加引号
    rendered, path = render('tool pre $prompt_file')
    assert rendered == f'tool pre "{path}"', rendered
    rendered, path = render('tool --file=$prompt_file')
    assert rendered == f'tool --file="{path}"', rendered
    # 引号外的 ^" 是字面引号、不开启引号语境：路径仍按 cmd 规则加引号
    rendered, path = render('tool ^"pre $prompt_file suf^"')
    assert rendered == f'tool ^"pre "{path}" suf^"', rendered
    # 整词被引号包住的既有写法（预处理路径）不受影响
    rendered, path = render('tool "$prompt_file"')
    assert rendered == f'tool "{path}"', rendered
    rendered, path = render('tool "$prompt_file" --end')
    assert rendered == f'tool "{path}" --end', rendered
    # 死活：任何位置都不能出现引用路径的嵌套引号（"" 视作异常）
    for tpl in ('tool "pre $prompt_file suf"', 'tool "a $prompt_file"'):
        rendered, _ = render(tpl)
        assert '""' not in rendered, rendered


def test_render_windows_quoted_prompt_file_between_quoted_segments(
        tmp_path, monkeypatch):
    """占位符夹在「已闭合引号」与「新开引号」之间时不能被整词预处理吞引号。

    回归：`tool "x"$prompt_file"y"` 里的 `"$prompt_file"` 前一个引号其实是
    x 的收尾引号、后一个引号是 y 的起始引号。整词预处理把它们一起换成
    哨兵后，路径按「引号外」规则插入，但两侧引号已被消费，最终变成
    `tool "x"{path}"y"`：含空格的工作区路径没有引号保护，cmd 会把参数
    拆成多段。这里占位符实际位于引号外，必须按扫描到的引号状态加引号，
    与两侧引号串拼接成同一个参数。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    ws = tmp_path / "ws with space"
    ws.mkdir()

    for tpl, expected in (
            ('tool "x"$prompt_file"y"', 'tool "x""{path}""y"'),
            ('tool "a-"$prompt_file"x"', 'tool "a-""{path}""x"'),
            ('tool a"$prompt_file"b', 'tool a"{path}"b'),
            ('tool x"$prompt_file"', 'tool x"{path}"'),
    ):
        agent = agents.ShellAgent(tpl, ws, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None
            path = str(agent._prompt_file.resolve())
            assert rendered == expected.format(path=path), (tpl, rendered)
        finally:
            agent._cleanup_prompt_file()


def test_render_windows_double_dollar_prompt_file_not_substituted(
        tmp_path, monkeypatch):
    """Windows 下 $$prompt_file 里的 $prompt_file 同样不能替换。

    回归：Windows 侧正则的前置边界允许 `$`，第二个 $prompt_file 被替换
    后命令里残留 `$` 前缀（cmd 不展开 $，外部 agent 拿到 `$C:\\...` 的
    坏路径），而 POSIX 侧整段不替换、配置校验据此拒绝；修复后两侧口径
    一致：$$prompt_file 不被兑现（command_receives_prompt 返回 False），
    真正落单的 $prompt_file 照常兑现。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    for tpl in ('tool $$prompt_file', 'tool "$$prompt_file"',
                "tool '$$prompt_file'"):
        assert agents.command_receives_prompt(tpl) is False, tpl
        agent = agents.ShellAgent(tpl, tmp_path, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert "$prompt_file" in rendered, rendered
            assert agent._prompt_file is None
        finally:
            agent._cleanup_prompt_file()
    # 对照：落单的占位符仍被识别并兑现
    assert agents.command_receives_prompt('tool "$prompt_file"') is True


def test_render_windows_dollar_run_parity_for_prompt_file(
        tmp_path, monkeypatch):
    """Windows 下 $$$prompt_file 的第三个 $ 才是占位符（与 POSIX 配对一致）。

    回归：前置边界 `(?<![A-Za-z0-9_$])` 把任何紧跟在 $ 后的占位符都排除，
    `$$$prompt_file` 因此整段不替换；POSIX 侧把前两个 $ 配成 $$、第三个
    才开启真实占位符，同一配置在 Windows 上静默丢掉提示词路径。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    for tpl in ('tool $$$prompt_file', 'tool "$$$prompt_file"',
                "tool '$$$prompt_file'", 'tool $$$$$prompt_file'):
        assert agents.command_receives_prompt(tpl) is True, tpl
        agent = agents.ShellAgent(tpl, tmp_path, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None, tpl
            path = str(agent._prompt_file.resolve())
            assert rendered == tpl.replace("$prompt_file", path), rendered
        finally:
            agent._cleanup_prompt_file()
    # 偶数个连续 $ 仍按字面量处理，不能凭空替换出坏路径
    for tpl in ('tool $$prompt_file', 'tool $$$$prompt_file'):
        assert agents.command_receives_prompt(tpl) is False, tpl
        agent = agents.ShellAgent(tpl, tmp_path, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert "$prompt_file" in rendered, rendered
            assert agent._prompt_file is None
        finally:
            agent._cleanup_prompt_file()


def test_render_windows_rejects_dialect_quotes(tmp_path, monkeypatch):
    """Windows 下 $'...' / $"..." 也要整体拒绝，与 POSIX 侧同口径。

    回归：cmd 不展开 $，但这类写法几乎总是按 POSIX 语义书写的模板——
    `tool $"$prompt_file"` 会把字面 $ 粘在替换出的路径前（引号内的
    占位符被替换、外层 $ 与路径在 cmd 下拼接），外部 agent 拿到
    `$C:\\...` 的坏路径，而 POSIX 侧对同一模板报错拒绝：同一份配置在
    Windows 上静默跑坏、在 Linux 上直接拒绝。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    for tpl in ('tool $"$prompt_file"', "tool $'$prompt_file'",
                'tool $"pre $prompt_file suf"'):
        assert agents.command_receives_prompt(tpl) is False, tpl
        agent = agents.ShellAgent(tpl, tmp_path, timeout=1)
        try:
            agent.render_command("PROMPT")
        except ValueError:
            pass
        else:
            raise AssertionError(f"含方言相关引用的模板应被拒绝: {tpl}")
        finally:
            agent._cleanup_prompt_file()
        # 拒绝路径不能残留无消费者的提示词文件
        assert [p.name for p in tmp_path.iterdir()] == []
    # 对照：$$" 是字面 $$ + 普通双引号、\$" 的 $ 前有反斜杠、
    # 双引号内紧跟结束引号的 $ 都不是方言引用，占位符照常兑现
    for tpl in ('tool $$"$prompt_file"', 'tool \\$"$prompt_file"',
                'tool "x$"y"$prompt_file"'):
        assert agents.command_receives_prompt(tpl) is True, tpl


def test_render_command_repeated_calls_do_not_leak_prompt_files(tmp_path):
    """同一实例连续 render_command 时旧提示词文件不能残留。

    回归：render_command 开头直接 self._prompt_file = None，只渲染不
    run()（或渲染后再次渲染）时，前一个 .prompt.*.md 失去引用、永久残留
    在工作区；run() 的兜底清理只能删掉最后一个。修复：渲染新命令前先走
    _cleanup_prompt_file()。
    """
    from xuen.agents import ShellAgent

    agent = ShellAgent("tool $prompt_file", tmp_path, timeout=5)
    agent.render_command("one")
    first = agent._prompt_file
    assert first is not None and first.exists()

    agent.render_command("two")
    second = agent._prompt_file
    assert second is not None and second.exists()
    assert second != first
    # 第二次渲染必须清掉第一个文件，工作区只留当前提示词文件
    assert not first.exists()
    assert sorted(p.name for p in tmp_path.glob(".prompt.*.md")) == [second.name]

    # dry_run 不落盘，但也不能把上一次的真实文件留在工作区
    agent.render_command("three", dry_run=True)
    assert agent._prompt_file is None
    assert list(tmp_path.glob(".prompt.*.md")) == []


def test_render_command_keyboard_interrupt_cleans_prompt_file(tmp_path,
                                                              monkeypatch):
    """渲染中途被 KeyboardInterrupt 打断时也要清掉已落盘的提示词文件。

    回归：render_command 只捕获 Exception，Ctrl+C 落在 $prompt_file
    落盘与渲染完成之间时文件失去消费者，.prompt.*.md（内含研究状态）
    永久残留在工作区。"""
    from xuen.agents import ShellAgent

    agent = ShellAgent("tool $prompt_file", tmp_path, timeout=5)
    real_write = agent._write_prompt_file

    def interrupted(prompt):
        real_write(prompt)
        raise KeyboardInterrupt

    monkeypatch.setattr(agent, "_write_prompt_file", interrupted)
    try:
        agent.render_command("中途被打断")
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("KeyboardInterrupt 应向上传播")
    assert agent._prompt_file is None
    assert list(tmp_path.glob(".prompt.*.md")) == []


def test_write_prompt_file_interrupt_closes_and_cleans_temp(tmp_path,
                                                            monkeypatch):
    """_write_prompt_file 自身被 Ctrl+C 打断时也不能留下半成品文件。

    回归：该函数只捕获 Exception，KeyboardInterrupt 会绕过清理；且
    _prompt_file 直到写入成功后才登记，render_command 的外层清理也看不到
    这个已创建的 .prompt.*.md（内含研究状态），文件永久残留。"""
    from xuen import agents

    agent = agents.ShellAgent("tool $prompt_file", tmp_path, timeout=5)

    def interrupted(fd, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(agents.os, "fdopen", interrupted)
    try:
        agent._write_prompt_file("机密提示词")
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("KeyboardInterrupt 应向上传播")
    assert agent._prompt_file is None
    assert list(tmp_path.glob(".prompt.*.md")) == []


def test_render_command_rejects_array_assignment(tmp_path):
    """裸上下文中的 bash 数组赋值（NAME=(...)）模板必须整体拒绝。

    回归：`v=(; $prompt` 这类模板此前能通过配置校验——`(` 在裸上下文按
    普通字符原样保留、$prompt 被替换成跨行单引号串。但 bash 对数组内语法
    错误（`;`）的恢复是「放弃当前命令、把后续行当命令执行」：渲染后提示词
    的第 2..n 行成了被执行的命令，实测其中 $(touch x)/`touch x` 创建文件
    （dash 则在 `(` 处直接报语法错误、什么也不执行，提示词也送不到）。
    数组是非 POSIX 语法（dash 下命令永远跑不了），`NAME=((` 这类非法写法
    同样触发恢复，合法数组在 dash 下也无法运行；方言无法预知——与
    $'...' 同口径整体拒绝、绝不替换。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    exploits = (
        "v=(; $prompt",
        'v=("x"; v="$v"$prompt"; echo "$v"',
        "v+=($prompt)",
        "v=((1+1)); $prompt",
        "v[$i]=($prompt)",
        "declare -a v=(x $prompt)",
        "local v=(; $prompt",
        # 续行拼接成 v=(：分词前反斜杠-换行被删除
        "v=\\\n(; $prompt",
        # 合法 bash 数组同样拒绝：dash 下无法运行、无方言安全的支持方式
        "v=($prompt)",
    )
    for tpl in exploits:
        assert command_receives_prompt(tpl) is False, tpl
        try:
            ShellAgent(tpl, tmp_path, timeout=5).render_command("x")
        except ValueError:
            pass
        else:
            raise AssertionError(f"含数组赋值的模板应被拒绝: {tpl}")
    # 拒绝发生后工作区不能残留无消费者的提示词文件（$prompt_file 先落盘、
    # 随后的数组赋值才触发拒绝）
    mixed = 'printf %s "$prompt_file" >/dev/null; v=(; $prompt'
    try:
        ShellAgent(mixed, tmp_path, timeout=5).render_command("x")
    except ValueError:
        pass
    else:
        raise AssertionError("含数组赋值的模板应被拒绝")
    assert [p.name for p in tmp_path.iterdir()] == []

    if not _posix_shell_available():
        return
    # 端到端：run() 必须在渲染阶段拒绝，绝不能把注入模板交给 shell 执行
    agent = ShellAgent("v=(; $prompt", tmp_path, timeout=5)
    try:
        agent.run("line1\n$(touch pwned1)\n`touch pwned2`")
    except ValueError:
        pass
    else:
        raise AssertionError("数组赋值模板必须在运行前被拒绝")
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    # 对照：`=` 之外位置的裸括号（子 shell 等）不是数组，照常送达且两
    # shell 一致（( 在 () 内被当普通括号，不触发拒绝）
    tpl2 = '(echo "$prompt")'
    assert command_receives_prompt(tpl2) is True
    prompt = "a'b \"c\" $HOME `id`"
    rendered = ShellAgent(tpl2, tmp_path, timeout=5).render_command(prompt)
    for argv in (["/bin/sh", "-c", rendered], ["bash", "-c", rendered]):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (argv, r.stderr)
        assert r.stdout == prompt + "\n", (argv, r.stdout)


def test_render_windows_single_quoted_prompt_file_inside_double_quotes(
        tmp_path, monkeypatch):
    """cmd 里单引号是字面字符：它位于双引号内时不能连同占位符一起
    被替换成带引号的路径，否则 `"'$prompt_file'"` 会生成 `""C:\\path""`
    的嵌套引号，cmd 拆错参数、外部 agent 拿到坏路径。"""
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    ws = tmp_path / "ws with space"
    ws.mkdir()
    for tpl in ('tool "\'$prompt_file\'"', 'tool "pre \'$prompt_file\' suf"',
                'tool "\'a $prompt_file b\'"'):
        agent = agents.ShellAgent(tpl, ws, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None
            path = str(agent._prompt_file.resolve())
            assert rendered == tpl.replace("$prompt_file", path), rendered
            assert '""' not in rendered, rendered
        finally:
            agent._cleanup_prompt_file()
    # 双引号外的整词单引号写法保持既有口径：去掉单引号并按 cmd 加引号
    agent = agents.ShellAgent("tool '$prompt_file'", ws, timeout=1)
    try:
        rendered = agent.render_command("PROMPT")
        path = str(agent._prompt_file.resolve())
        assert rendered == f'tool "{path}"', rendered
    finally:
        agent._cleanup_prompt_file()


def test_render_windows_caret_escaped_single_quote_still_quotes_path(
        tmp_path, monkeypatch):
    """cmd 的 ^ 转义只作用于单引号本身，不能连带吞掉路径两侧的引号保护。

    回归：模板 `tool ^'$prompt_file'` 里第一个单引号被 ^ 转义，整词单引号
    预处理却仍把 `'$prompt_file'` 一起换掉，得到 `tool ^"C:\\ws with
    space\\p.md"`：^" 在 cmd 中是字面引号，含空格路径没有分组引号。修复：
    第一个单引号被 ^ 转义时不做整词预处理，只替换占位符，保留两侧单引号
    字面量，并按引号外规则给路径加引号。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    ws = tmp_path / "ws with space"
    ws.mkdir()

    assert agents.command_receives_prompt("tool ^'$prompt_file'") is True
    for tpl in ("tool ^'$prompt_file'", "tool ^'$prompt_file' --end"):
        agent = agents.ShellAgent(tpl, ws, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None
            path = str(agent._prompt_file.resolve())
            expected = tpl.replace("$prompt_file", f'"{path}"')
            assert rendered == expected, rendered
            assert '""' not in rendered, rendered
        finally:
            agent._cleanup_prompt_file()


def test_render_windows_caret_escaped_prompt_file_not_substituted(
        tmp_path, monkeypatch):
    """cmd 的 ^ 转义：^$prompt_file 是字面量，不能被替换成未加引号的路径。

    回归：_windows_placeholder_starts 只查占位符/单词边界，不识别 cmd
    的 ^ 转义；`tool ^$prompt_file` 会被替换成 `tool ^"C:\\path"`，^" 在
    cmd 中是字面引号、不能给含空格路径分组。配置校验也会误放行这种
    永远不会送达提示词文件的模板。
    """
    import os as _os

    from xuen import agents

    class _NtOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(_os, key)

    monkeypatch.setattr(agents, "os", _NtOs())
    ws = tmp_path / "ws with space"
    ws.mkdir()

    assert agents.command_receives_prompt("tool ^$prompt_file") is False
    agent = agents.ShellAgent("tool ^$prompt_file", ws, timeout=1)
    try:
        rendered = agent.render_command("PROMPT")
        assert rendered == "tool ^$prompt_file"
        assert agent._prompt_file is None
    finally:
        agent._cleanup_prompt_file()

    # ^^ 只是字面 ^，占位符仍然有效；引号内的 ^ 不转义
    assert agents.command_receives_prompt("tool ^^$prompt_file") is True
    assert agents.command_receives_prompt('tool "^$prompt_file"') is True
    for tpl in ("tool ^^$prompt_file", 'tool "^$prompt_file"'):
        agent = agents.ShellAgent(tpl, ws, timeout=1)
        try:
            rendered = agent.render_command("PROMPT")
            assert agent._prompt_file is not None, tpl
            path = str(agent._prompt_file.resolve())
            assert path in rendered, (tpl, rendered)
        finally:
            agent._cleanup_prompt_file()

