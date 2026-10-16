"""xuen 包的冒烟测试（只依赖标准库 + PyYAML，不依赖 textual）。

这些测试让 Continuous Loop 的每轮候选都有一道最基本的自动验证：
import 断了、CLI 参数解析坏了，都会被 round_guard 拦下（不晋升为最佳）。
"""
from __future__ import annotations

import importlib

from xuen.sink import Sink


def _import(name):
    return importlib.import_module(name)


def test_import_core_modules():
    for name in ("xuen", "xuen.config", "xuen.state", "xuen.words",
                 "xuen.agents", "xuen.procs", "xuen.sink", "xuen.runner"):
        assert _import(name) is not None, f"无法 import {name}"


def test_cli_parser():
    from xuen.cli import build_parser
    p = build_parser()
    args = p.parse_args(["设计一个新的优化器", "--no-tui"])
    assert args.task == ["设计一个新的优化器"]
    assert args.no_tui is True


def test_version():
    import xuen
    assert xuen.__version__


def _posix_shell_available():
    import os
    import shutil
    return os.name == "posix" and shutil.which("bash") and shutil.which("sh")


def test_shell_prompt_heredoc_snippet_is_executable(tmp_path):
    """提示词中「覆盖区块」的 shell 示例必须能原样执行。

    回归：示例曾整体带两格缩进，heredoc 结束标记不顶格 → shell 会一直
    读到输入结尾，把结束标记与后续内容一起写进区块（内容被污染）。
    """
    import subprocess
    import sys
    from xuen.config import Config
    from xuen.runner import _shell_prompt

    if not _posix_shell_available():
        return
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1] + '.out').write_bytes(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    prompt = _shell_prompt(Config(), "任务", 1, [], tmp_path / "research.md",
                           helper, [])
    lines = prompt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("cat <<'"))
    end = max(i for i, l in enumerate(lines) if l.startswith("XUEN_EOF"))
    snippet = "\n".join(lines[start:end + 1])
    # 测试环境不保证存在 `python` 命令，替换为当前解释器
    snippet = snippet.replace("python ", f'"{sys.executable}" ')
    r = subprocess.run(["bash", "-c", snippet], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stderr == "", r.stderr
    assert (tmp_path / "idea.out").read_text(encoding="utf-8").strip() \
        == "这里是新的想法区内容……"
    assert (tmp_path / "artifact.out").read_text(encoding="utf-8").strip() \
        == "这里是新的产物区内容……"


def test_shell_prompt_snippet_quotes_workspace_path(tmp_path):
    """工作区路径含 shell 元字符时，提示词中的写入片段必须仍可执行。

    回归：片段里的 helper 路径原先只用双引号包裹，而 POSIX shell 在双引号
    内仍会展开 $ 与反引号（工作区名为「ws $x `id`」时，外部 agent 按提示词
    执行会拿到错误路径、区块永远写不进去）。修复：路径经 _shell_path 按
    当前平台 shell 的规则转义后再拼进提示词。
    """
    import subprocess
    import sys
    from xuen.config import Config
    from xuen.runner import _shell_prompt

    if not _posix_shell_available():
        return
    ws = tmp_path / "ws $x `id` 'q'"
    ws.mkdir()
    helper = ws / "write_section.py"
    helper.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1] + '.out').write_bytes(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    prompt = _shell_prompt(Config(), "任务", 1, [], ws / "research.md",
                           helper, [])
    lines = prompt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("cat <<'"))
    end = max(i for i, l in enumerate(lines) if l.startswith("XUEN_EOF"))
    snippet = "\n".join(lines[start:end + 1])
    # 测试环境不保证存在 `python` 命令，替换为当前解释器
    snippet = snippet.replace("python ", f'"{sys.executable}" ')
    r = subprocess.run(["bash", "-c", snippet], cwd=ws,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stderr == "", r.stderr
    assert (ws / "idea.out").read_text(encoding="utf-8").strip() \
        == "这里是新的想法区内容……"
    assert (ws / "artifact.out").read_text(encoding="utf-8").strip() \
        == "这里是新的产物区内容……"


def test_render_command_ignores_shell_comments(tmp_path):
    """命令模板里 shell 注释中的不成对引号不能污染后续占位符的转义。

    回归：注释里的单引号会开启「单引号状态」，之后的 $prompt 被按单引号
    语境插入（缺少双引号转义），提示词中的反引号会被 shell 执行。
    """
    import subprocess
    from xuen.agents import ShellAgent

    if not _posix_shell_available():
        return
    agent = ShellAgent("# don't edit\nprintf '%s' $prompt", tmp_path, timeout=5)
    prompt = "a'b \"c\" $HOME `id`"
    rendered = agent.render_command(prompt)
    assert rendered.startswith("# don't edit\n")
    r = subprocess.run(rendered, shell=True, capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt


def test_command_receives_prompt_ignores_comments():
    from xuen.agents import command_receives_prompt

    assert command_receives_prompt('opencode run "$prompt"') is True
    assert command_receives_prompt('opencode run $prompt # 说明') is True
    # 注释里的 $prompt 不会送达 agent：必须判负，否则会放行一个
    # 「提示词被静默丢弃」的模板
    assert command_receives_prompt('opencode run # $prompt') is False


def test_render_command_does_not_substitute_in_heredoc(tmp_path):
    """heredoc 正文里绝不能替换 $prompt。

    回归：正文里的 shlex.quote 引号只是普通字符，不加引号的终止符下正文
    会做参数/命令替换——提示词里的 $(touch ...)/反引号会被 shell 执行
    （注入）；加引号的终止符下引号则原样进入 agent 输入。正文里的
    $prompt 本来也只是 shell 变量展开/字面量，不会把提示词送达 agent，
    必须判为未送达，由配置校验拦下。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    for tpl in (f"cat <<EOF\n$prompt\nEOF",
                f"cat <<'EOF'\n$prompt\nEOF",
                f"cat <<-EOF\n\t$prompt\n\tEOF"):
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词内容没有被塞进正文
        assert "$prompt" in rendered
        assert str(marker) not in rendered
        r = subprocess.run(rendered, shell=True, capture_output=True, text=True,
                           cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
        # 正文里的 $prompt 不会被替换：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False
    # here-string（<<<）没有正文，不按 heredoc 处理
    assert command_receives_prompt("cat <<< $prompt") is True


def test_render_command_after_heredoc_still_substitutes(tmp_path):
    """heredoc 正文中的不成对引号/井号不能污染终止符之后的 $prompt 渲染。

    回归：正文里的单引号会被当成「打开引号」，终止符之后的 $prompt 就会
    按错误的引号语境插入，参数被拆碎或提示词被注入执行。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    tpl = ("cat <<'EOF' > /dev/null\n"
           "it's # not a comment\n"
           "EOF\n"
           "printf '%s' $prompt")
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    prompt = "a'b \"c\" $HOME `id`"
    rendered = agent.render_command(prompt)
    r = subprocess.run(rendered, shell=True, capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt


def test_render_command_heredoc_delimiter_expansion_cannot_inject(tmp_path):
    """heredoc 终止符词里的展开语法不能按字面截断词边界。

    回归：shell 不对终止符词做展开、词边界由展开内部的解析决定
    （`cat <<$(echo X)` 的终止符是字面量 $(echo X)，含空白的
    ${...}/$[...] 与反引号同理）。渲染器若在 ( 或空白处截断终止符
    （把 $(echo X) 读成 $），就会以为正文在模板中途结束、把 $prompt
    替换进后面的文本；而 shell 的正文一直延伸到真正的终止符，不加引号
    的正文会展开替换文本里的 $(...)/`...`——提示词里的命令被真正执行
    （注入，实测 bash 下创建文件）。修复：终止符词含无法安全确定边界的
    展开时把剩余模板整体吞掉（与 heredoc 正文/反引号/算术语境同口径），
    配置校验据此拒绝这类模板。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        "cat <<$(echo X)\nX\n$\n$prompt\n",
        "cat <<$(echo X) > /dev/null\nX\n$\n$prompt\n",
        "cat <<$((1+1))\n$\n$prompt\n",
        "cat <<a${X:-b c}\na${X:-b\n$prompt\n}\na${X:-b c}\n",
        "cat <<a$[b c]d\na$[b\n$prompt\n]\na$[b c]d\n",
        "cat <<`echo a b`\n`echo\n$prompt\n`echo a b`\n",
    )
    for tpl in templates:
        assert command_receives_prompt(tpl) is False, tpl
        if not _posix_shell_available():
            continue
        marker = tmp_path / "pwned"
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(f"$(touch {marker}) `touch {marker}.bt`")
        # 占位符原样保留，提示词绝不进入终止符词之后的任何命令/正文
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    if not _posix_shell_available():
        return
    # 对照 1：单引号终止符里的 $(...) 是字面量，照常截断正文、正常送达
    tpl = "cat <<'$(echo X)' > /dev/null\n$(echo X)\nprintf %s $prompt"
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    prompt = "a b $HOME `id`"
    r = subprocess.run(agent.render_command(prompt), shell=True,
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt
    # 对照 2：终止符词之前的 $prompt 照常送达；危险区之后的整体吞掉，
    # 不会因为拒绝而丢掉已兑现的占位符（该写法 dash 直接语法错误，
    # 这里用 bash 验证）
    tpl = "printf %s $prompt\ncat <<$(echo X)\nX\n$(echo X)\n"
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([shutil.which("bash"), "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith(prompt)
    assert "X" in r.stdout


def test_render_command_heredoc_delimiter_word_continuation_and_escapes(tmp_path):
    """heredoc 终止符词要按 shell 的引号移除规则拼接（续行/双引号内转义）。

    回归：`cat <<E\\<换行>OF` 的终止符是 EOF（反斜杠-换行在分词前被整对
    删除、词跨行继续拼接，bash/dash 实测一致）；`cat <<"E\\$OF"` 的终止符
    是 E$OF（双引号内 \\$ 是引号移除后的字面 $）；`<<"A\\\\B"` 是 A\\B。
    渲染器原先把续行当普通字符（终止符里多出一个换行、永远匹配不到任何
    物理行），又把双引号内的反斜杠原样保留，正文因此被整体吞到模板结尾：
    合法模板的 $prompt 被静默丢弃、配置校验还会误报「缺少占位符」。
    修复：终止符词按同一套引号移除规则拼接（单引号外续行整对删除、
    双引号内 \\" \\\\ \\$ \\` 去掉反斜杠），正文边界与 shell 一致。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # 续行拆开的终止符词：shell 视为 EOF
        "cat <<E\\\nOF > /dev/null\nbody\nEOF\nprintf %s $prompt",
        # 双引号 + 续行：同样是 EOF
        'cat <<"E\\\nOF" > /dev/null\nbody\nEOF\nprintf %s $prompt',
        # 双引号内的 \$ 是引号移除后的字面 $
        'cat <<"E\\$OF" > /dev/null\nbody\nE$OF\nprintf %s $prompt',
        # 双引号内的 \\ 是单个字面反斜杠
        'cat <<"A\\\\B" > /dev/null\nbody\nA\\B\nprintf %s $prompt',
        # 裸露的 \$ 照常等价于字面 $
        "cat <<E\\$OF > /dev/null\nbody\nE$OF\nprintf %s $prompt",
    )
    prompt = "a'b $HOME `id` $(touch pwned)"
    for tpl in templates:
        assert command_receives_prompt(tpl) is True, tpl
        if not _posix_shell_available():
            continue
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert "$prompt" not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            if (tmp_path / "pwned").exists():
                (tmp_path / "pwned").unlink()
            r = subprocess.run([sh, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, sh, r.stderr)
            assert r.stdout == prompt, (tpl, sh, r.stdout)
            assert not (tmp_path / "pwned").exists(), (tpl, sh)
    if not _posix_shell_available():
        return
    # 对照：找不到闭合双引号时仍按原有保守口径整体吞掉、不替换
    tpl = 'cat <<"EOF > /dev/null\nbody\nprintf %s $prompt'
    assert command_receives_prompt(tpl) is False
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    assert "$prompt" in agent.render_command(prompt)


def test_render_command_heredoc_inside_command_substitution_cannot_inject(tmp_path):
    """命令替换内部的换行不能提前收「外层命令的 heredoc」正文。

    回归：`cat <<A $(echo hi\\nA\\n)\\n$prompt\\nA` 里替换内部有一行与
    终止符相同的 A。shell（bash/dash 一致，实测该行仍作为替换内部命令
    执行）在替换内部的换行处不会开始收外层 heredoc 的正文，正文从替换
    闭合后的外层换行才开始；渲染器原先一见换行就登记正文、把替换内部
    的 A 行当成终止符，随后又在外层正文位置恢复替换——$prompt 正好被
    插入 shell 当作不加引号 heredoc 正文的区域，正文会做参数/命令替换，
    提示词里的 $(touch ...)/反引号被真正执行（注入，实测创建文件）。
    修复：heredoc 记录登记时的替换深度，只在深度 >= 当前的换行处收正文；
    外层待收的 heredoc 留到替换闭合后的外层换行。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # 裸命令替换：替换内部出现与终止符相同的行
        "cat <<A $(echo hi\nA\n)\n$prompt\nA\n",
        # 注释分支：替换内部以注释结尾的换行同样不能触发正文
        "cat <<A $(echo x\n# note\nA\n)\n$prompt\nA\n",
        # 双引号内的命令替换
        'cat <<A "$(echo hi\nA\n)"\n$prompt\nA\n',
        # 嵌套替换（深度 2 的换行）
        "cat <<A $(echo $(echo hi\nA\n)\n)\n$prompt\nA\n",
        # <<- 与制表符缩进的终止符行
        "cat <<-A $(echo hi\n\tA\n)\n$prompt\nA\n",
    )
    prompt = f"$(touch {tmp_path / 'pwned'}) `touch {tmp_path / 'pwned.bt'}`"
    for tpl in templates:
        # 正文里的 $prompt 不会被替换：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
        if not _posix_shell_available():
            continue
        marker = tmp_path / "pwned"
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词绝不进入 shell 当作正文的区域
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    if not _posix_shell_available():
        return
    # 对照 1：命令替换内部有换行，但外层 heredoc 照常在外层换行收正文、
    # 终止符之后的 $prompt 正常送达
    tpl = ("cat <<A > /dev/null\n"
           "$(printf hi\n)\n"
           "A\n"
           "printf %s $prompt")
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    prompt2 = "a'b $HOME `id`"
    for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (sh, r.stderr)
        assert r.stdout == prompt2, sh
    # 对照 2：注册在命令替换内部的 heredoc 在替换内部的换行处收正文，
    # 正文里的行不得被当成命令替换的一部分替换占位符
    tpl = "x=$(cat <<B\ninner\nB\n)\nprintf %s $prompt"
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (sh, r.stderr)
        assert r.stdout == prompt2, sh


def test_render_command_closed_substitution_heredoc_read_before_outer(tmp_path):
    """多个待收 heredoc 的正文读取顺序必须与 shell 一致：深度优先。

    回归：`cat <<A $(cat <<B)` 里 B 的替换在同一行闭合，外层换行处 A 和
    B 都待收正文。渲染器按登记顺序先收 A，把 B 行当成 A 的终止符、在
    shell 仍当作 A 正文的区域恢复替换——bash 实际先收 B 的正文
    （REMBODY、B），A 的正文从 `$prompt` 行一直延伸到模板结尾，提示词
    里的 $(...)/`` 被 bash 当成不加引号正文执行（注入，实测创建文件）。
    修复：待收正文按登记深度降序（同深度按登记顺序）读取，与 bash
    实测行为一致；dash 对已闭合替换里的 heredoc 按空正文处理、外层正文
    按登记顺序读，其正文区域落在深度优先吞掉的范围之内，同样安全。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    # 注入模板：B 的正文吃掉 x、A 行后，bash 把 $prompt 行当作 A 的正文
    templates = (
        ("cat <<A > /dev/null $(cat <<B)\n"
         "x\n"
         "A\n"
         "B\n"
         "$prompt\n"),
        # 深度 2：C 最先读，然后 B，最后 A
        ("cat <<A > /dev/null $(cat <<B $(cat <<C))\n"
         "x\n"
         "A\n"
         "B\n"
         "C\n"
         "$prompt\n"),
    )
    prompt = f"$(touch {tmp_path / 'pwned'}) `touch {tmp_path / 'pwned.bt'}`"
    for tpl in templates:
        # 正文里的 $prompt 不会被替换：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
        if not _posix_shell_available():
            continue
        marker = tmp_path / "pwned"
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    if not _posix_shell_available():
        return
    # 对照 1：正文在终止符行前正常结束，深度优先收完后终止符之后的
    # $prompt 照常送达（bash/dash 都把提示词作为 printf 的参数输出）
    tpl = ("cat <<A > /dev/null $(cat <<B)\n"
           "y\n"
           "B\n"
           "A\n"
           "printf %s $prompt")
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    prompt2 = "a'b $HOME `id`"
    for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (sh, r.stderr)
        assert r.stdout == prompt2, sh
    # 对照 2：深度 2 的嵌套替换同理，先收 C 再收 B，A 空正文不吞占位符
    tpl = ("cat <<A > /dev/null $(cat <<B $(cat <<C))\n"
           "z\n"
           "C\n"
           "B\n"
           "A\n"
           "printf %s $prompt")
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (sh, r.stderr)
        assert r.stdout == prompt2, sh


def test_render_command_unquoted_heredoc_body_spanning_expansion_cannot_inject(tmp_path):
    """不加引号的 heredoc 正文里横跨终止符行的展开不能在正文外恢复替换。

    回归：dash 对正文里的 $(...)/`...` 会跨行从输入流继续解析——终止符行
    被吞进展开、正文继续，直到展开闭合后的下一个终止符行才收尾（实测
    `cat <<A >/dev/null\\n$(echo hi\\nA\\n)\\nA\\nprintf %s $prompt` 在 dash
    下第一个 A 行不终止正文；bash 在这类模板上直接报错）。渲染器若按行
    就此结束正文、把 $prompt 插进后面，就正好落进 shell 仍当作正文的
    区域：不加引号的正文会做参数/命令替换，提示词里的 $(touch ...)/
    反引号被真正执行（注入，实测 dash 创建文件）。修复：记录终止符词
    是否带引号；不加引号时用 _heredoc_body_open_substitution 检查区域内
    的展开是否都已闭合，未闭合则继续按正文吞（吞到模板结尾也不替换）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    # 展开在模板内不闭合：占位符留在正文里不替换、必须判为未送达
    swallowed = (
        "<<A\n$(\nA\n)$prompt",
        "<<A\n$('\nA\n$prompt')",
        "cat <<A >/dev/null\n$(echo hi\nA\nprintf %s $prompt\nA\n",
    )
    for tpl in swallowed:
        assert command_receives_prompt(tpl) is False, tpl
    # 展开在后续行闭合：第一个终止符行被吞、后续终止符行才是真终止符，
    # 之后的占位符照常送达
    spanning = (
        "cat <<A >/dev/null\n$(echo hi\nA\n)\nA\nprintf %s $prompt",
        "cat <<A >/dev/null\n`echo hi\nA\n`\nA\nprintf %s $prompt",
    )
    for tpl in spanning:
        assert command_receives_prompt(tpl) is True, tpl
    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    for tpl in swallowed:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    for tpl in spanning:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    # 对照：同一行/区域内在终止符行之前闭合的展开照常送达
    prompt2 = "a'b $HOME `id`"
    for tpl in ("cat <<A >/dev/null\n$(printf hi)\nA\nprintf %s $prompt",
                "cat <<A >/dev/null\n$(printf hi\n)\nA\nprintf %s $prompt"):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                               capture_output=True, text=True, cwd=tmp_path)
            assert r.returncode == 0, (sh, r.stderr)
            assert r.stdout == prompt2, sh


def test_render_command_heredoc_backslash_continuation_cannot_inject(tmp_path):
    """不加引号 heredoc 正文的行尾反斜杠续行不能按物理行提前收正文。

    回归：`cat <<EOF\\nfoo\\<换行>EOF\\n$prompt\\nEOF` 里 bash 与 dash 都把
    `foo\\`+换行+`EOF` 拼成逻辑行 fooEOF（不是终止符），正文继续到真正的
    EOF 行；渲染器按物理行匹配，以为正文在第一个 EOF 行结束，把 $prompt
    替换进 shell 仍当作不加引号正文的区域——正文会做命令替换，提示词里的
    $(touch ...)/反引号被真正执行（注入，实测两 shell 均创建文件）。
    `EO\\`+换行+`F` 更隐蔽：bash 拼出 EOF 会结束正文，dash 只在行首检查点
    逐字比较物理行、不结束，跨 shell 必须取更晚的边界。修复：不加引号的
    正文按反斜杠-换行先拼逻辑行、以 dash 的检查点口径匹配终止符
    （见 consume_heredoc_bodies），$prompt 因此留在正文里不替换，由配置
    校验拒绝这类模板；加引号的正文没有续行语义，仍按物理行精确匹配。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # 续行拼出的「终止符」行不是终止符：正文继续到下一个 EOF
        "cat <<EOF\nfoo\\\nEOF\n$prompt\nEOF\n",
        # <<- 与制表符缩进的续行
        "cat <<-EOF\nfoo\\\n\tEOF\n$prompt\n\tEOF\n",
        # bash 终止、dash 不终止：跨 shell 取更晚的正文边界
        "cat <<EOF\nEO\\\nF\n$prompt\nEOF\n",
    )
    prompt = f"$(touch {tmp_path / 'pwned'}) `touch {tmp_path / 'pwned.bt'}`"
    for tpl in templates:
        # 正文里的 $prompt 不会被替换：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
        if not _posix_shell_available():
            continue
        marker = tmp_path / "pwned"
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    if not _posix_shell_available():
        return
    # 对照：这些续行/终止符组合下两种 shell 的正文边界一致、都同意正文
    # 在终止符行结束——之后的 $prompt 必须照常送达（不被多吞误伤）
    deliver = (
        # 续行在真正的终止符行之前结束，正文照常收束
        "cat <<EOF > /dev/null\nfoo\\\nbar\nEOF\nprintf %s $prompt",
        # 偶数个反斜杠不续行，下一行 EOF 正常终止
        "cat <<EOF > /dev/null\nfoo\\\\\nEOF\nprintf %s $prompt",
        # 加引号的正文没有续行语义，物理行 EOF 即终止
        "cat <<'EOF' > /dev/null\nfoo\\\nEOF\nprintf %s $prompt",
        # 整行反斜杠的续行与终止符拼成终止符（两 shell 一致），正文为空
        "cat <<EOF > /dev/null\n\\\nEOF\nprintf %s $prompt",
    )
    prompt2 = "a'b $HOME `id`"
    for tpl in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([sh, "-c", agent.render_command(prompt2)],
                               capture_output=True, text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, sh, r.stderr)
            assert r.stdout == prompt2, (tpl, sh)


def test_render_command_command_substitution_quotes(tmp_path):
    """$(...) 内部的引号自成一体，不能影响外层引号状态。

    回归：解析器用单一引号状态机，把 "$(printf %s "$prompt")" 里的内层 "
    误判为闭合外层双引号，$prompt 按裸上下文插入 shlex.quote 引号——而
    模板自己的双引号还在，单引号变成字面值，提示词里的 $(cmd)/`cmd`
    反而被 shell 执行（注入）；$prompt_file 路径含空格时也会被拆碎。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"a'b $(touch {marker}) `touch {marker}.bt` \"d\" $HOME \\x"
    for tpl in ('printf %s "$(printf %s "$prompt")"',
                'printf %s "$( (printf %s "$prompt") )"'):
        assert command_receives_prompt(tpl) is True
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        r = subprocess.run(agent.render_command(prompt), shell=True,
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == prompt
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 外层未加引号时命令替换结果按空白拆词是 shell 语义，但绝不能执行内容
    tpl = 'printf %s $(printf %s "$prompt")'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(agent.render_command(prompt), shell=True,
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.replace(" ", "") == prompt.replace(" ", "")
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()

    # $prompt_file：内层引号里的路径必须原样送达（工作区路径含空格时
    # 不会被拆碎），双引号/单引号语境都要安全
    workspace = tmp_path / "some dir"
    workspace.mkdir()
    for tpl in ('printf %s "$(cat "$prompt_file")"',
                "printf %s \"$(cat '$prompt_file')\""):
        assert command_receives_prompt(tpl) is True
        agent = ShellAgent(tpl, workspace, timeout=5)
        r = subprocess.run(agent.render_command(prompt), shell=True,
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == prompt


def test_render_command_subshell_inside_command_substitution(tmp_path):
    """$(...) 内部的子 shell 括号不能提前结束命令替换的解析语境。

    回归：解析器遇到任意裸 ) 就弹出外层引号状态，子 shell 的 ) 会被误当成
    命令替换的结束——之后的 $prompt 按错误语境插入：提示词被拆词（多词
    粘连 / 参数碎裂），其中的分号等 shell 元字符还会被直接执行（注入）。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"a b; touch {marker}; printf %s y"
    tpl = 'echo "$( (true); printf %s $prompt )"'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(agent.render_command(prompt), shell=True,
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt + "\n"
    assert not marker.exists()

    # 多层子 shell 之后的双引号语境也要正确：$prompt_file 路径含空格
    # 时必须是「双引号内转义」，而不是被误判成裸语境套上 shlex.quote 引号
    workspace = tmp_path / "some dir"
    workspace.mkdir()
    tpl2 = 'printf %s "$( ( (true) ); cat "$prompt_file" )"'
    assert command_receives_prompt(tpl2) is True
    agent2 = ShellAgent(tpl2, workspace, timeout=5)
    r2 = subprocess.run(agent2.render_command(prompt), shell=True,
                        capture_output=True, text=True, cwd=tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout == prompt


def test_render_command_does_not_substitute_in_backquotes(tmp_path):
    """反引号命令替换内的占位符不能替换（插入的转义在内层 shell 失效）。

    回归：解析器把反引号当普通字符，$prompt 按外层引号语境插入的转义
    在 shell 对反引号的「第一遍」处理后会失效（\\$ 被还原成 $、引号里的
    裸反引号还会结束替换），提示词里的 $(...)/`...` 被真正执行（注入）。
    与 heredoc 正文同理：整体跳过、不做替换，并由配置校验拒绝这类模板。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"x $(touch {marker}) `touch {marker}.bt` y"
    for tpl in ('printf %s "`printf %s $prompt`"',
                "printf %s `printf %s $prompt`"):
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 与 heredoc 正文一致：占位符原样保留，提示词绝不进入反引号内容
        assert "$prompt" in rendered
        assert str(marker) not in rendered
        r = subprocess.run(rendered, shell=True, capture_output=True, text=True,
                           cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
        # 反引号内的 $prompt 不会送达 agent：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False
    # 反引号区域之外的占位符照常替换，提示词正常送达且不被执行
    tpl = 'printf %s "`echo ok`" "$prompt"'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(agent.render_command(prompt), shell=True,
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout and str(marker) in r.stdout
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_does_not_substitute_in_arithmetic_contexts(tmp_path):
    """算术语境里的占位符不能替换（插入的引号在表达式里不构成保护）。

    回归（bash 下可复现）：$[ $prompt ]、(( $prompt )) 与数组下标
    ${x[$prompt]} 都会对表达式里的 $(...)/`...` 求值执行——即使 $prompt
    被 shlex.quote/单引号包裹，引号字符只是表达式文本，不构成保护。
    与 heredoc 正文同理：整体跳过、不做替换，并由配置校验拒绝这类模板；
    ${x:-$prompt} 这类参数展开词语境同样整体跳过（无法安全转义，见
    test_render_command_does_not_substitute_in_parameter_expansion_words）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    bash = shutil.which("bash")
    marker = tmp_path / "pwned"
    prompt = f"x $(touch {marker}) `touch {marker}.bt` y"
    templates = (
        "echo $[ $prompt ] 2>/dev/null; echo done",
        "echo $[ ${a[0]} + $prompt ] 2>/dev/null; echo done",
        'echo "$[ $prompt ]" 2>/dev/null; echo done',
        "(( $prompt )) 2>/dev/null; echo done",
        "x=1; (( x + $prompt )) 2>/dev/null; echo done",
        "echo ${x[$prompt]:-y} 2>/dev/null; echo done",
        'echo "${x[$prompt]:-y}" 2>/dev/null; echo done',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 与 heredoc 正文一致：占位符原样保留，提示词绝不进入算术语境
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        # 显式用 bash 执行：这些语境在 bash 里会对 $(...)/`...` 求值执行
        r = subprocess.run([bash, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
        # 算术语境里的 $prompt 不会送达 agent：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
    # 正面对照：普通双引号语境照常替换、正常送达且不执行
    tpl = 'printf %s "$prompt"; echo'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert str(marker) in r.stdout
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_does_not_substitute_in_substring_expansion(tmp_path):
    """${name:offset[:length]} 子串展开的 offset/length 是算术语境。

    回归（bash 下可复现）：${x:'$(touch ...)'} 里的引号只是表达式文本，
    不构成保护——插入的提示词会真正执行其中的 $(...)/`...`（注入）。
    与 ${name[下标]} 同理整体跳过、不做替换，并由配置校验拒绝这类模板；
    词语境的 ${x:-$prompt} / ${x:+$prompt} 同样整体跳过（无法安全转义，
    见 test_render_command_does_not_substitute_in_parameter_expansion_words）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    bash = shutil.which("bash")
    marker = tmp_path / "pwned"
    prompt = f"0+$(touch {marker})"
    templates = (
        "x=abcdefgh; echo ${x:$prompt}",
        'x=abcdefgh; echo "${x:$prompt}"',
        "x=abcdefgh; echo ${x:1:$prompt}",
        'set a b; echo "${@:$prompt}"',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词绝不进入算术语境
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        r = subprocess.run([bash, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists(), tpl
        # 算术语境里的 $prompt 不会送达 agent：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
    # 正面对照：普通双引号语境照常替换、正常送达且不执行
    tpl = 'printf %s "$prompt"'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt
    assert not marker.exists()


def test_render_command_does_not_substitute_in_parameter_expansion_words(tmp_path):
    """${x:-word} 等参数展开词语境也必须整体跳过（无法安全转义）。

    回归：此前把 ${x:-$prompt} 当普通词语境、按双引号规则插入提示词，
    但一套转义无法同时适配 bash 与 dash（提示词内容运行时才确定）：
      - 提示词含 ' 时：按 dash 规则转义的 \\' 在 bash 展开体里不是转义
        （bash 把 ' 当引号），落单的 ' 让整条命令解析失败（unexpected
        EOF）；按 bash 规则转义又会在 dash 下出现别的偏差；
      - 提示词含 } 时：} 提前结束参数展开，两种 shell 下都静默丢字符
        （"${x:-foo}barbaz}" 输出 foobarbaz}，而不是 foo}barbaz）；
      - bash 还会把展开体里未配对的 >( / <( 当进程替换解析而报错。
    与算术/反引号/heredoc 正文一致：整段原样跳过、不做替换，并由配置
    校验拒绝这类模板。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"x $(touch {marker}) `touch {marker}.bt` y"
    templates = (
        'printf %s "${x:-$prompt}"; echo',
        'printf %s "${x:+$prompt}"; echo',
        "printf %s ${x:-$prompt}; echo",
        'printf %s "${x:-pre $prompt post}"; echo',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词绝不进入参数展开
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert str(marker) not in r.stdout, tpl
            assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
        # 参数展开里的 $prompt 不会送达 agent：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
    # 对照：展开区之外的占位符照常送达，展开区内的那处原样跳过
    tpl = 'printf %s "$prompt" "${x:-$prompt}"; echo'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    rendered = agent.render_command(prompt)
    assert '"${x:-$prompt}"' in rendered
    r = subprocess.run(["bash", "-c", rendered], capture_output=True,
                       text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt + "\n"
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 不含占位符的参数展开照常原样保留、正常执行
    tpl = 'x=ok; printf %s "${x:-no}" "$prompt"; echo'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(["bash", "-c", agent.render_command("hi")],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "okhi\n"


def test_render_command_quoted_closers_in_expansions_cannot_inject(tmp_path):
    """${...}/$[...]/$((...)) 内被引号「保护」的结束符不得被误当段尾。

    回归（bash 与 dash 下均可复现）：扫描器只用「第一个收尾符」给这类
    整体跳过的语境找结束位置，不识别引号——引号里的 } / ] / ) 并不终结
    展开（如 ${x:-"}"}、$[ "]" ]），扫描却提前停在假结束符上：余下模板
    被按外层引号语境解析，$prompt 的转义与 shell 的真实语境错位
    （如 ${x:-"}$prompt"}：$prompt 按裸语境插入 shlex.quote 的单引号，
    但 shell 仍在双引号内，单引号只是字面量），提示词里的 $(...)/`...`
    被真正执行（注入）。$((...)) 还有 $(("... 这类写法：shell 改按
    命令替换解析，紧挨结束符的引号若被跳过区吞掉同样会错位。
    修复：引号/反引号/反斜杠/嵌套替换可能隐藏结束符，遇到即整体吞到
    模板结尾（拒绝替换）；$((...)) 必须确认真的跟着第二个 )。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"P $(touch {marker}) `touch {marker}.bt` Q"
    templates = (
        # ${...}：引号里的 } 不终结展开
        'printf %s ${x:-"}$prompt"}',
        'printf "%s ${x:-"}$prompt"}"',
        "printf %s ${x:-'}'}$prompt",
        "printf %s ${x:-'}$prompt}'",
        "printf %s ${x:-'}'} $prompt ",
        'echo ${x:-"}"} "$prompt"',
        # $[...]：bash 识别引号（$[ "]" ] 的 ] 不终结展开）
        "printf %s $[']']$prompt",
        # $((...))：$(("... 时 shell 改按命令替换 + 子 shell 解析
        'printf "%s $(()""))$prompt"',
        'printf "%s $(()\\"))$prompt"',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词绝不进入这类语境
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            try:
                subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path, timeout=10)
            except subprocess.TimeoutExpired:
                pass
            assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), (tpl, shell)
        # 这类语境里的 $prompt 不会送达 agent：配置校验必须拒绝
        assert command_receives_prompt(tpl) is False, tpl
    # 正面对照：嵌套 ${（无引号等构造）与正常语境照常按深度配对/替换
    tpl = 'printf %s ${x:-${y:-plain}} "$prompt"; echo'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(["bash", "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "plain" + prompt + "\n"
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 正面对照：普通 $((...))/$[...] 不再被误判（配对仍然正确）
    for tpl, expected in (
        ('printf %s $((1 << 2)) "$prompt"; echo', "4"),
        ('printf %s $[ 1 + 2 ] "$prompt"; echo', "3"),
    ):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        r = subprocess.run(["bash", "-c", agent.render_command(prompt)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (tpl, r.stderr)
        assert r.stdout == expected + prompt + "\n", tpl
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_case_pattern_paren_in_expansion_cannot_inject(tmp_path):
    """命令替换里 case 的 pattern ) 不配对 (，不能被当成替换的结束。

    回归（bash 与 dash 下均可复现）：$(case x in x) echo "$prompt";; esac)
    里 pattern 结束的裸 ) 让括号深度配对提前闭合命令替换、恢复外层引号
    状态（双引号 → 裸），之后的 $prompt 按裸语境插入 shlex.quote 的单引号——
    但 shell 仍在双引号内，单引号只是字面量，提示词里的 $(...)/`...`
    被真正执行（注入）；参数文本也被拆坏。修复：命令替换内的裸 case
    之后无法安全配对括号，整体吞到模板结尾、不做替换，并由配置校验
    拒绝这类模板。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"P $(touch {marker}) `touch {marker}.bt` Q"
    templates = (
        'printf %s "$(case x in x) echo "$prompt";; esac)"',
        'printf %s "$(case x in x) echo $prompt;; esac)"',
        'printf %s "$(echo "$(case x in x) echo "$prompt";; esac)")"',
        # shell 分词前会删掉续行：ca\<换行>se 仍是 case 保留字，不能漏认
        'printf %s "$(ca\\\nse x in x) echo "$prompt";; esac)"',
        'printf %s "$(c\\\na\\\ns\\\ne x in x) echo "$prompt";; esac)"',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 与 heredoc 正文一致：占位符原样保留，提示词绝不进入该区域
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert str(marker) not in r.stdout, tpl
            assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
        # 命令替换里 case 之后的 $prompt 不会送达 agent：配置校验必须拒绝
        assert command_receives_prompt(tpl) is False, tpl
    # 对照：case 在命令替换之外不参与括号配对，$prompt 照常替换、正常送达
    tpl = "printf %s $prompt; case x in x) true;; esac"
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(["bash", "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 对照：只是以 case 为子串的普通单词（showcase）不触发关键字处理
    tpl3 = 'printf %s "$(showcase)" "$prompt"'
    assert command_receives_prompt(tpl3) is True
    agent3 = ShellAgent(tpl3, tmp_path, timeout=5)
    r3 = subprocess.run(["bash", "-c", agent3.render_command(prompt)],
                        capture_output=True, text=True, cwd=tmp_path)
    assert r3.returncode == 0, r3.stderr
    assert r3.stdout == prompt
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 对照：双引号里的 case 是普通字面量、不触发 case 关键字处理，
    # 命令替换内的 $prompt 仍安全送达
    tpl2 = 'printf %s "$(echo "case" "$prompt")"'
    assert command_receives_prompt(tpl2) is True
    agent2 = ShellAgent(tpl2, tmp_path, timeout=5)
    r2 = subprocess.run(["bash", "-c", agent2.render_command(prompt)],
                        capture_output=True, text=True, cwd=tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout == "case " + prompt
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_does_not_substitute_in_redirect_word(tmp_path):
    """裸 `>&word`（无 fd 号）重定向词里的占位符不能替换。

    回归（bash 下可复现，bash --posix / 以 sh 调用同样复现）：bash 把
    `>&word` 当 `&>word` 的别名，但对 word 的展开不遵守引号规则——单引号
    里的 $(...)/`...`/参数展开仍会被执行（`>&'$(cmd)'` 真的会跑 cmd），
    双引号里的 \\$ 也拦不住。按普通引号语境插入提示词会让提示词里的
    $(...)/`...` 被真正执行（注入）。修复：整词原样跳过、不做替换，
    并由配置校验拒绝这类模板；`&>`/`<>`/`>|` 等写法遵守引号规则，
    不在跳过之列（下方的正面对照）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    bash = shutil.which("bash")
    marker = tmp_path / "pwned"
    prompt = f"P $(touch {marker}) `touch {marker}.bt` Q"
    templates = (
        "printf %s >&$prompt",
        "printf %s >&'$prompt'",
        'printf %s >&"$prompt"',
        "printf %s >&pre$prompt",
        "printf %s >&case'$prompt'",
        "printf %s >&2'$prompt'",
        "cat >&$prompt_file",
        # `>` 紧跟 `(` 时是进程替换、仍属于该重定向词（`>&x>(...)` 同理），
        # 无法安全找词尾：整段跳过而不是把 $prompt 插进词的后半段
        'printf %s >&>(( 1 ))"$prompt">$(true)',
        'printf %s >&pre>(echo x)"$prompt"',
    )
    for tpl in templates:
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 与 heredoc 正文一致：占位符原样保留，提示词绝不进入该词
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        r = subprocess.run([bash, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
        # 该词里的 $prompt 不会送达 agent：配置校验必须拒绝这类模板
        assert command_receives_prompt(tpl) is False, tpl
    # 对照：`>&` 词之外的占位符照常替换，常见 fd 重定向写法不受影响
    for tpl, stream in (('printf %s "$prompt" >&2', "stderr"),
                        ('printf %s "$prompt" 2>&1', "stdout"),
                        ('printf %s 2>&1 "$prompt"', "stdout")):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (tpl, r.stderr)
        assert getattr(r, stream).strip() == prompt, tpl
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl
    # 对照：跳过词后同一行的后续参数照常替换（词边界识别正确）
    tpl = "printf %s >&'out' \"$prompt\""
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out").read_text(encoding="utf-8") == prompt
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()
    # 对照：`&>` 遵守引号规则，占位符照常送达且不执行
    tpl = 'printf %s &>' + "'out2' \"$prompt\""
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out2").read_text(encoding="utf-8") == prompt
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_does_not_substitute_after_unescaped_dollar(tmp_path):
    """紧跟在未转义 $ 后面的占位符不能替换（shell 把它当 $$ 的后半）。

    回归（bash 与 dash 行为一致）：`$$prompt` 里 shell 把 $$ 当 PID、
    `prompt` 只是字面量，`$prompt` 并不是真正的参数展开；但渲染器只检查
    前一个字符不是单词字符，仍会替换：双引号语境拼成 `"$"+提示词`——
    提示词以 ( 开头就直接构成 `$(...)` 命令替换并执行（注入，下方用
    `(touch ...)` 复现），以字母开头则被当成变量名（提示词被吞）；
    裸语境拼成 `$'...'` ANSI-C 引用，bash 解释反斜杠转义、dash 原样
    保留（提示词被篡改且两 shell 行为不一致）；`$$prompt_file` 把路径
    前缀上一个 $、agent 拿到坏路径。修复：连续未转义 $ 两两配成 $$、
    落单的那个才算展开开始（$$prompt 不替换；\\$$prompt、$$$prompt
    照常替换），单引号语境里 $ 只是字面量、不受影响。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    # 不依赖 shell 的判负用例：这些模板的占位符不会送达 agent
    for tpl in ('printf %s "$$prompt"', "printf %s $$prompt",
                'printf %s "x$$prompt"', "printf %s x$$prompt",
                'printf %s "$$prompt_file"',
                'printf %s "\\\\$$prompt"',    # 两个反斜杠：$$ 仍是 PID
                'printf %s "$$$$prompt"',      # 两对 $$，仍是字面量
                "printf %s \\$$$prompt"):      # $ 被转义后剩 $$ 配对
        assert command_receives_prompt(tpl) is False, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command("(touch PWNED)")
        # 占位符原样保留，提示词绝不进入渲染结果
        assert "$prompt" in rendered, tpl
        assert "PWNED" not in rendered, tpl

    if not _posix_shell_available():
        return
    # 注入回归：修复前 `printf %s "$$prompt"` 渲染成
    # `printf %s "$(touch ...)"`，命令替换被真正执行
    marker = tmp_path / "pwned"
    for tpl in ('printf %s "$$prompt"', 'printf %s "x$$prompt"'):
        prompt = f"(touch {marker})"
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert str(marker) not in rendered, tpl
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([shell, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists(), tpl

    # 对照：转义 $ 后的 \\$$prompt 里 $prompt 是新展开（shell 会先做
    # 转义再解析），照常替换；两个 shell 下都送达 $+提示词
    prompt = "P $(echo no) `echo no` Q"
    for tpl in ("printf %s \\$$prompt", 'printf %s "\\$$prompt"'):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert r.stdout == "$" + prompt, (tpl, shell, r.stdout)
    # 对照：连续的三个 $ 里落单的 $ 才开启新展开，$$$prompt 照常替换
    for tpl in ("printf %s $$$prompt", 'printf %s "$$$prompt"'):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            prefix = r.stdout[:-len(prompt)] if r.stdout.endswith(prompt) else ""
            assert prefix and prefix.isdigit(), (tpl, shell, r.stdout)
    # 对照：单引号语境没有 $ 展开，'$$prompt' 仍是占位符、原样送达
    tpl = "printf %s '$$prompt'"
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([shell, "-c", agent.render_command(prompt)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (shell, r.stderr)
        assert r.stdout == "$" + prompt, (shell, r.stdout)


def test_render_command_pid_dollar_does_not_open_substitution(tmp_path):
    """`$$(` 里第二个 $ 是 PID（$$）的后半，不能当命令替换处理。

    回归（bash 与 dash 一致）：`"x$$($prompt)x"` 里 $$ 是 PID、双引号内
    的 ( 只是字面量，$prompt 就是双引号语境里的普通参数展开；但渲染器
    对第二个 $ 匹配 `$(` 后切到独立（裸）上下文，按裸语境用 shlex.quote
    插入提示词（单引号），而实际 shell 仍在双引号里——单引号只是字面量，
    提示词里的 $(...)/`...` 逃出引用被真正执行（注入，下方两个 shell
    都能复现）。同理 `$${` / `$$[` / `$$'` 也不是参数展开/旧式算术/
    ANSI-C 引用。修复：这些展开头都要求 $ 真的开启展开
    （_dollar_starts_expansion），$$(、$${、$$[、$$' 按普通字符解析；
    渲染结果在双引号内转义 $，提示词原样送达且不执行。
    """
    import re
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    prompt = "$(touch PWNED) `touch PWNED2` $((1+1))"
    # 修复前会把提示词按裸语境插入；修复后这些模板仍然可用（送达提示词）
    for tpl in ('printf %s "x$$($prompt)x"',
                'printf %s "$$($prompt"',
                'printf %s "a$$($prompt"'):
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        assert "PWNED" in rendered and "touch PWNED2" in rendered, tpl
        # 提示词按双引号语境转义：$ ` 都被反斜杠保护成字面量
        assert "\\$(touch PWNED)" in rendered, tpl
        assert "\\`touch PWNED2\\`" in rendered, tpl

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    shells = filter(None, (shutil.which("bash"), shutil.which("dash")))
    for tpl in ('printf %s "x$$($prompt)x"', 'printf %s "$$($prompt"'):
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 提示词按双引号语境转义：$ 与 ` 都被反斜杠保护成字面量
        assert "\\$(touch" in rendered, tpl
        for shell in shells:
            subprocess.run([shell, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl

    # 对照：提示词确实送达（落在双引号词内、被转义成字面量）且原样保留。
    # 对照提示词特意不含 $ ` ( )：bash 对 `$$(` 还会先按命令列表扫描括号
    # 内容来找配对（展开时仍是 PID + 字面量），提示词里出现未配对的 (
    # 时会报解析错误（模板极端写法，安全性不受影响），对照用普通文本即可
    prompt = "P one; two Q"
    esc = re.escape(prompt)
    controls = (
        ('printf %s "x$$($prompt)x"', rf"x\d+\({esc}\)x"),
        ('printf %s "$$((1+1))$prompt"', rf"\d+\(\(1\+1\)\){esc}"),
        ('printf %s "$${y}$prompt"', rf"\d+\{{y\}}{esc}"),
        ("printf %s \"$$'$prompt'\"", rf"\d+'{esc}'"),
    )
    for tpl, pattern in controls:
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert re.fullmatch(pattern, r.stdout), (tpl, shell, r.stdout)


def test_render_command_comment_hash_after_expansion_close(tmp_path):
    """紧跟命令替换/算术展开/进程替换结束 ) 的 # 不是注释。

    回归（bash 与 dash 行为一致，进程替换在 bash 下）：`echo $(echo hi)#there`
    输出 hi#there——$() 的结束 ) 仍是同一个词的一部分，其后的 # 是词中
    字符；但渲染器只按前一个字符是 ) 判断，把 # 误当注释、把该行剩余
    部分（含不成对引号）整体跳过，与真实 shell 的引号状态正好相反：
    `true $(echo x)#'\\n' " $prompt"` 里 shell 的 ' 从行尾一直引用到下一行
    行首，提示词落在双引号词内，而渲染器按单引号语境插入（不转义 $），
    提示词里的 $(...)/`...` 被真正执行（注入，下方复现）。修复：记录
    词内 ) 的位置，其后的 # 不再算注释；子 shell/case pattern 的 ) 是
    词边界，其后的 # 仍是注释（下方正面对照）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    templates = (
        "true $(echo x)#'\n' \" $prompt\"",
        "true $((1+1))#'\n' \" $prompt\"",
        "true >(echo x)#'\n' \" $prompt\"",
    )
    for tpl in templates:
        # 提示词确实送达 agent（落在引号状态正确的词内），不是拒绝模板
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 提示词按双引号语境转义插入：$(...) 被转义成 \$(...) 字面量
        assert "\\$(touch" in rendered, tpl
        if not _posix_shell_available():
            continue
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([shell, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl

    if not _posix_shell_available():
        return
    # 对照：子 shell 的 ) 是词边界，其后的 # 仍是注释——注释里的 ' 不能
    # 污染后续占位符：`(true)#'` 整行被两个 shell 当注释忽略，第二行照常
    # 按双引号语境插入提示词、原样送达且不执行
    tpl = "(true)#'\nprintf %s \"$prompt\""
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([shell, "-c", agent.render_command(prompt)],
                           capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, (shell, r.stderr)
        assert r.stdout == prompt, (shell, r.stdout)
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_escaped_delimiter_hash_is_not_comment(tmp_path):
    """被反斜杠转义的词边界字符之后的 # 不是注释。

    回归（bash 与 dash 行为一致）：`echo \\ #x` 输出 ` #x`——`\\ ` 是转义
    空格、属于词的一部分，其后的 # 是词中字符而不是注释；渲染器只按前
    一个字符是否属于 " \\t\\n;&|()<>" 判断，把 # 误当注释、把该行剩余部分
    （含不成对引号）整体跳过，与真实 shell 的引号状态正好相反：
    `echo \\ #"` + 换行 + `printf %s $prompt` + 换行 + `"` 里 shell 的
    双引号从第一行一直引用到最后，提示词落在双引号词内，而渲染器按裸
    语境插入单引号（单引号在双引号内只是字面量），提示词里的
    $(...)/`...` 被真正执行（注入，下方复现同类模板）。修复：前一个字符
    被转义（_escaped_at）时不算词边界，# 不再是注释；`;`/`(`/`&` 等
    被转义的边界字符同理（每种都曾是同样的注入面）。未转义的边界字符
    后 # 仍是注释（下方正面对照）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    templates = (
        'echo \\ #"\nprintf %s $prompt\n"',
        'echo \\;#"\nprintf %s $prompt\n"',
        'echo \\(#"\nprintf %s $prompt\n"',
        'echo \\&#"\nprintf %s $prompt\n"',
        'echo \\|#"\nprintf %s $prompt\n"',
        'echo \\>#"\nprintf %s $prompt\n"',
        'echo \\<#"\nprintf %s $prompt\n"',
    )
    for tpl in templates:
        # 提示词确实送达（落在引号状态正确的词内），不是拒绝模板
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 提示词按双引号语境转义插入：$(...)/`...` 被反斜杠转义成字面量
        assert "\\$(touch" in rendered, tpl
        assert "\\`touch" in rendered, tpl
        if not _posix_shell_available():
            continue
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl

    if not _posix_shell_available():
        return
    # 对照：未转义的边界字符后 # 仍是注释——注释里不成对的引号不能
    # 污染后续占位符：第一行被两个 shell 当注释忽略，第二行照常按
    # 双引号语境插入提示词、原样送达且不执行
    for tpl in ('echo ;#"\nprintf %s "$prompt"',
                'echo \\\\ #"\nprintf %s "$prompt"'):
        # `\\\\ `（两个反斜杠）是字面反斜杠 + 未转义空格：空格仍是词边界
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 第一行的 " 必须整行留在注释里：line 2 的提示词按双引号语境转义
        assert "\\$(touch" in rendered, tpl
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            # echo 行先输出（空行 / 字面反斜杠），随后 printf 原样输出提示词
            assert r.stdout.endswith(prompt), (tpl, shell, r.stdout)
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_line_continuation_word_boundaries(tmp_path):
    """分词前删除的续行（反斜杠-换行）必须参与词边界与 $ 配对判断。

    回归（bash 与 dash 行为一致）：
    1) `a\\<换行># "$prompt"` 拼成 `a# "$prompt"`，`#` 是词中字符、不是
       注释；渲染器按「前一个字符是换行」误判成注释后整行跳过：$prompt
       原样保留、agent 收到字面量 `$prompt`（提示词被静默丢弃），而且
       这个模板本可送达提示词，command_receives_prompt 却误判为 False；
       $() 结束 ) 后的 # 同理（`$(cmd)\\<换行>#` 仍是同一个词）。
    2) `$\\<换行>$prompt` 拼成 `$$prompt`：第二个 $ 只是 $$（PID）的
       后半、不是展开的开始；误替换会在裸语境拼出 `$'提示词'`——bash
       按 ANSI-C 引用解释反斜杠转义、dash 把 $ 当字面量，提示词被篡改
       且行为随 /bin/sh 方言而变（$'...' 正是渲染器明确拒绝的写法）。
    修复：词边界、`#` 词首判定与连续 $ 配对都按「删除续行后的相邻关系」
    进行（_prev_effective_pos）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    prompt = "P $HOME `id` 'q' \\ d"
    # 能送达的模板：占位符替换后两个 shell 输出一致且提示词完整
    deliver = (
        # 词中 #（a# 是一个词），行尾的 "$prompt" 照常送达
        ('printf "<%s>\\n" a\\\n# "$prompt"', "<a#>\n<" + prompt + ">\n"),
        # $() 结束 ) 后的 # 仍是词中字符：词内 ) 的位置比较要跨过续行
        ('printf "%s\\n" $(echo hi)\\\n# "$prompt"', "hi#\n" + prompt + "\n"),
        # 续行删除后 $prompt 位于词首，照常送达
        ('printf "<%s>\\n" \\\n$prompt', "<" + prompt + ">\n"),
        # \$ 转义 + 续行删除后，落单的 $prompt 仍是真正的展开
        ('printf "<%s>\\n" \\$\\\n$prompt', "<$" + prompt + ">\n"),
    )
    for tpl, expected in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        if not _posix_shell_available():
            continue
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert r.stdout == expected, (tpl, shell, r.stdout)

    # 不能送达的模板：占位符必须原样保留（不替换、不拼出 $'...'）
    for frag in (
        '$\\\n$prompt',     # 拼成 $$prompt：$$ 是 PID，prompt 只是字面量
        'x\\\n$prompt',     # 拼成 x$prompt：紧贴单词字符，不是完整占位符
        '\\\n# "$prompt"',  # 拼成行首 #：是注释，$prompt 不会送达
    ):
        tpl = 'printf "%s" ' + frag
        assert command_receives_prompt(tpl) is False, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        assert "$prompt" in rendered and prompt not in rendered, tpl

    if not _posix_shell_available():
        return
    # 对照：$$ 加续行再接 $prompt（拼成 $$$prompt）里落单的 $ 是真展开，
    # 照常替换：两个 shell 都输出 PID + 提示词
    tpl2 = 'printf "%s" $$\\\n$prompt'
    assert command_receives_prompt(tpl2) is True
    rendered2 = ShellAgent(tpl2, tmp_path, timeout=5).render_command(prompt)
    for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([shell, "-c", rendered2], capture_output=True,
                           text=True, cwd=tmp_path)
        assert r.returncode == 0, (shell, r.stderr)
        assert r.stdout.endswith(prompt), (shell, r.stdout)
        assert r.stdout[:-len(prompt)].isdigit(), (shell, r.stdout)


def test_render_command_rejects_continuation_split_operators(tmp_path):
    """用续行（反斜杠-换行）拆开操作符/展开头的模板必须整体拒绝。

    回归：shell 在分词前删除续行，两侧字符会拼成一个新的操作符/展开头，
    而渲染器按续行两侧字符独立解析，引号状态与实际 shell 脱节：实测
    bash 下 `printf %s >\\<换行>&"$prompt"` 把提示词当裸 `>&` 重定向词
    执行（提示词里的 $(...) 真的会跑）；`cat <\\<换行><EOF` 拼成 heredoc
    （正文不认引号，bash 与 dash 都可注入）；双引号内的 `"$\\<换行>(`
    拼成 `"$(`（命令替换在引号内照常生效，bash 与 dash 都可注入）；
    `$[`（旧式算术）、`${`（参数展开）同理。修复：按「删除续行后的相邻
    关系」检测拼出的头部（_continuation_split_head），命中即整体拒绝，
    由配置校验拦下（与 $'...' 同口径）；`&&`/`>>` 等普通操作符与普通
    续行不受影响，`\\>`/`$$` 等转义或配对情形也不会误伤。另有
    `>&\\<换行>word`：重定向词被续行隔到下一行，词边界同样按删除续行后
    的相邻关系识别（_redirect_word_end），词里的占位符照旧整词跳过，
    否则 `>&"$prompt"` 这种不遵守引号规则的展开会把提示词当重定向词执行。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    prompt = "P $HOME `id` 'q' \\ d"

    # 拼出特殊头（>& / << / $( / $[ / ${ / (( / <( 等）：整体拒绝
    for tpl in (
        'printf %s >\\\n&"$prompt"',    # >\<换行>& 拼成裸 >&（bash 注入）
        'printf %s >\\\n&$prompt',      # 同上，裸提示词
        'cat <\\\n<EOF\n$prompt\nEOF',  # <\<换行>< 拼成 heredoc（两 shell）
        'printf %s $\\\n[$prompt]',     # $[ 旧式算术（bash）
        'printf %s $\\\n{$prompt}',     # ${ 参数展开
        'printf %s "$\\\n{$prompt}"',   # 双引号内 ${ 参数展开
        'printf %s "$\\\n(printf %s "$prompt")"',  # 双引号内 $(
        'printf %s (\\\n(printf %s "$prompt")',    # (( 算术命令
        'printf %s <\\\n(printf %s "$prompt")',    # <( 进程替换
    ):
        assert command_receives_prompt(tpl) is False, tpl
        try:
            ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        except ValueError:
            pass
        else:
            raise AssertionError(f"续行拆开操作符的模板应被拒绝: {tpl}")

    # 不构成特殊头（转义/配对排除）：不拒绝、照常渲染
    allow = (
        'printf %s \\>\\\n& "$prompt"',        # > 被转义：没有拼出 >&
        'printf %s "$$\\\n( "$prompt" )"',     # $$ 是 PID：不是 $( 展开
    )
    for tpl in allow:
        assert command_receives_prompt(tpl) is True, tpl
        ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)

    # 能送达的模板：占位符替换后两个 shell 输出一致且提示词完整
    deliver = (
        # 普通续行（两侧不是操作符字符）照常送达
        ('printf "<%s>\\n" \\\n"$prompt"', "<" + prompt + ">\n"),
        ('printf "<%s>\\n" \\\n$prompt', "<" + prompt + ">\n"),
        # && 被续行拆开：普通操作符，照常送达
        ('true &\\\n& printf "<%s>\\n" "$prompt"', "<" + prompt + ">\n"),
        # 模板末尾的续行删除后占位符仍是完整词，照常送达
        ('printf "%s" $prompt\\\n', prompt),
    )
    for tpl, expected in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        if not _posix_shell_available():
            continue
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert r.stdout == expected, (tpl, shell, r.stdout)

    # >> 被续行拆开：重定向到文件，提示词完整性用文件内容验证
    tpl = 'printf "%s" >\\\n>out "$prompt"'
    assert command_receives_prompt(tpl) is True
    rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
    if _posix_shell_available():
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            out = tmp_path / "out"
            if out.exists():
                out.unlink()
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (shell, r.stderr)
            assert out.read_text(encoding="utf-8") == prompt, shell

    # >& 的重定向词被续行隔到下一行：词按删除续行后的相邻关系识别。
    # `>&\<换行>"$prompt"` 的 $prompt 仍是重定向词（bash 对 >&word 的
    # 展开不遵守引号规则、可执行提示词里的 $(...)），照旧整词跳过；
    # `>&\<换行>out "$prompt"` 的词是 out，后续参数照常送达
    tpl = 'printf %s >&\\\n"$prompt"'
    assert command_receives_prompt(tpl) is False
    rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
    assert "$prompt" in rendered and prompt not in rendered
    tpl = 'printf %s >&\\\nout "$prompt"'
    assert command_receives_prompt(tpl) is True
    rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
    bash = shutil.which("bash")
    if _posix_shell_available() and bash:
        # dash 不支持无 fd 号的 >&word（Bad fd number），只用 bash 验证
        out = tmp_path / "out"
        if out.exists():
            out.unlink()
        r = subprocess.run([bash, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert out.read_text(encoding="utf-8") == prompt

    # 续行拼成的尾缀：占位符后还接着单词字符，不是完整占位符
    for frag in (
        '$prompt\\\nx',      # 拼成 $promptx：变量名还在延续
        '$prompt\\\n_file',  # 拼成 $prompt_file：整体是文件名占位符
    ):
        tpl = 'printf "%s" ' + frag
        assert command_receives_prompt(tpl) is False, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        assert "$prompt" in rendered and prompt not in rendered, tpl


def test_render_command_rejects_ansi_c_quotes(tmp_path):
    """裸上下文中的 ANSI-C 引用（$'...'）模板必须整体拒绝。

    回归：xuen 用 shell=True 执行命令，实际解释器是 /bin/sh ——
    Ubuntu/Debian 下是 dash，它不支持 ANSI-C 引用（$ 是字面量、后面是
    普通单引号串）；macOS/RHEL 下却是 bash（按反斜杠转义解释）。
    此前按 bash 语义转义插入提示词，在 dash 下引号边界会被打乱：
    提示词里的 `; touch ...` 逃出引用被当作命令执行（注入），而
    command_receives_prompt 仍按 bash 语义误判为「能送达」。方言无法预知，
    因此与 heredoc/反引号/算术语境一致：整体拒绝，绝不替换。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    for tpl in ("printf %s $'pre $prompt post'",
                "cat $'$prompt_file'",
                "printf %s $'$prompt'",
                # 曾在 dash 下可注入的模板：提示词里的引号能逃出引用
                "printf %s $'$prompt' '"):
        assert command_receives_prompt(tpl) is False, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        try:
            agent.render_command("x")
        except ValueError:
            pass
        else:
            raise AssertionError(f"含 $'...' 的模板应被拒绝: {tpl}")
    # 拒绝发生后工作区不能残留无消费者的提示词文件：$prompt_file 先落盘、
    # 随后的 $'...' 才触发拒绝时，渲染失败路径也必须清理
    mixed = '''printf %s "$prompt_file" >/dev/null; printf %s $'$prompt' '''
    with_cleanup = ShellAgent(mixed, tmp_path, timeout=5)
    try:
        with_cleanup.render_command("x")
    except ValueError:
        pass
    else:
        raise AssertionError("含 $'...' 的模板应被拒绝")
    assert [p.name for p in tmp_path.iterdir()] == []

    if not _posix_shell_available():
        return
    # 对照：$' 出现在 shell 注释里不参与解析，不触发拒绝
    prompt = "a'b \"c\" $HOME `id`"
    tpl = "printf %s $prompt # $'x'"
    assert command_receives_prompt(tpl) is True
    rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
    for argv in (["/bin/sh", "-c", rendered], ["bash", "-c", rendered]):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == prompt
    # 对照：双引号内的 $' 是普通字面量，不是 ANSI-C 语境
    tpl2 = "printf %s \"$'x' $prompt\""
    assert command_receives_prompt(tpl2) is True
    rendered2 = ShellAgent(tpl2, tmp_path, timeout=5).render_command(prompt)
    for argv in (["/bin/sh", "-c", rendered2], ["bash", "-c", rendered2]):
        r = subprocess.run(argv, capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout == "$'x' " + prompt


def test_arithmetic_expansion_not_treated_as_heredoc(tmp_path):
    """$((...)) 算术展开里的 << 不能按 heredoc 重定向登记。

    回归：$((1 << 2)) 的 << 被当成 heredoc 起始，模板后续换行处的
    $prompt 会连同「正文」一起被跳过，command_receives_prompt 误判为
    「提示词送不到」而拒绝合法模板。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    tpl = 'echo $((1 << 2))\nprintf %s "$prompt"'
    assert command_receives_prompt(tpl) is True

    if not _posix_shell_available():
        return
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(agent.render_command("hi `id`"), shell=True,
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "4\nhi `id`"


class _RecordingSink(Sink):
    """记录 runner 上报消息的测试用 sink。"""

    def __init__(self):
        self.messages = []

    def info(self, text): self.messages.append(("info", text))
    def ok(self, text): self.messages.append(("ok", text))
    def warn(self, text): self.messages.append(("warn", text))
    def err(self, text): self.messages.append(("err", text))
    def round_header(self, index, label): self.messages.append(("round", label))
    def agent_output(self, line): pass
    def agent_stderr(self, line): pass
    def section(self, name, content): pass


def _run_fake_words_scenario(tmp_path, agent_stdout, *, regen_words, reuse=True):
    """用假 agent（把收到的提示词记到日志、stdout 固定输出指定词表）跑一轮
    runner.run，返回 (sink, prompts, workspace, SystemExit 或 None)。"""
    import sys
    from xuen.config import AgentConfig, Config, LoopConfig, WordsConfig
    from xuen.runner import run

    workspace = tmp_path / "ws"
    workspace.mkdir()
    logs = tmp_path / "agent_log.txt"
    script = tmp_path / "fake_agent.py"
    out_text = agent_stdout + "\n"
    script.write_text(
        "import pathlib, sys\n"
        f"log = pathlib.Path({str(logs)!r})\n"
        "prev = log.read_text(encoding='utf-8') if log.exists() else ''\n"
        "log.write_text(prev + '\\n===PROMPT===\\n' + sys.argv[1], encoding='utf-8')\n"
        f"sys.stdout.write({out_text!r})\n",
        encoding="utf-8",
    )
    (workspace / "words.txt").write_text(
        "\n".join(f"DISKWORD{i}" for i in range(1, 6)) + "\n", encoding="utf-8")

    cfg = Config(
        workspace=str(workspace),
        agent=AgentConfig(command=f'"{sys.executable}" "{script}" "$prompt"'),
        words=WordsConfig(count=10, batch=10, pick=1, reuse=reuse),
        loop=LoopConfig(iterations=1),
    )
    sink = _RecordingSink()
    try:
        run(cfg, "测试任务", regen_words=regen_words, sink=sink)
        exc = None
    except SystemExit as e:
        exc = e
    prompts = logs.read_text(encoding="utf-8").split("===PROMPT===")[1:]
    return sink, prompts, workspace, exc


def _round_prompts(prompts):
    return [p for p in prompts if "本轮随机灵感词" in p]


def test_regen_words_partial_generation_uses_fresh_words(tmp_path):
    """--regen-words 明确要求重建词库：生成未完成时不能悄悄绕回旧词库。

    回归：生成结果比磁盘旧词库少时走了「保留并复用旧词库」分支，与
    --regen-words（忽略已有词库并重新生成）的语义相悖——用户显式要求
    重建，却拿到正是自己想替换掉的旧词，且新生成的词被整批丢弃。
    """
    sink, prompts, workspace, exc = _run_fake_words_scenario(
        tmp_path, "FRESHWORD1\nFRESHWORD2", regen_words=True)
    assert exc is None
    rounds = _round_prompts(prompts)
    assert rounds, "未观察到研究循环轮次的提示词"
    assert "FRESHWORD" in rounds[-1]
    assert "DISKWORD" not in rounds[-1]
    assert any("本次临时使用" in m for _, m in sink.messages)
    # 不能再拿残缺新词表覆盖磁盘上更完整的旧词库
    assert (workspace / "words.txt").read_text(encoding="utf-8") \
        .startswith("DISKWORD")


def test_regen_words_failed_generation_does_not_reuse_old_words(tmp_path):
    """--regen-words 下生成失败也不能回退复用旧词库，应明确失败。"""
    sink, prompts, workspace, exc = _run_fake_words_scenario(
        tmp_path, "", regen_words=True)
    assert exc is not None and "词库为空" in str(exc)
    assert not _round_prompts(prompts), "生成失败后不应进入研究循环"
    assert any("忽略磁盘上的旧词库" in m for _, m in sink.messages)
    assert (workspace / "words.txt").read_text(encoding="utf-8") \
        .startswith("DISKWORD")


def test_reuse_true_still_skips_generation(tmp_path):
    """未指定 --regen-words 时复用旧词库的常规路径不受影响。"""
    sink, prompts, workspace, exc = _run_fake_words_scenario(
        tmp_path, "FRESHWORD1\nFRESHWORD2", regen_words=False)
    assert exc is None
    rounds = _round_prompts(prompts)
    assert "DISKWORD" in rounds[-1]
    assert "FRESHWORD" not in rounds[-1]
    assert any("复用已有词库" in m for _, m in sink.messages)


def test_prompt_too_long_converted_to_actionable_error(tmp_path, monkeypatch):
    """E2BIG（命令行参数过长）不能以裸 [Errno 7] 抛出。

    回归：$prompt 模板把整段提示词塞进 sh -c 的单个参数，超过系统上限
    （Linux 约 128KB）时 Popen 抛 OSError(E2BIG)，运行期只看到
    「[Errno 7] Argument list too long」，看不出是提示词太长、更不知道
    该改用 $prompt_file。必须换成带解法建议的 PromptTooLongError；渲染时
    已落盘的提示词文件（混合 $prompt_file 模板）也要在失败路径清理。
    """
    import errno
    from xuen import agents
    from xuen.agents import PromptTooLongError, ShellAgent

    def boom(*args, **kwargs):
        raise OSError(errno.E2BIG, "Argument list too long: '/bin/sh'")

    monkeypatch.setattr(agents.subprocess, "Popen", boom)
    agent = ShellAgent('cat "$prompt_file" >/dev/null; printf %s "$prompt"',
                       tmp_path, timeout=5)
    try:
        agent.run("x")
    except PromptTooLongError as e:
        assert "$prompt_file" in str(e), str(e)
    else:
        raise AssertionError("E2BIG 应转换为 PromptTooLongError")
    assert [p.name for p in tmp_path.iterdir()] == []


def test_prompt_too_long_detected_on_real_ebig(tmp_path):
    """真实超过 Linux 单参数上限（MAX_ARG_STRLEN）时必须被识别。"""
    import sys
    from xuen.agents import PromptTooLongError, ShellAgent

    if not sys.platform.startswith("linux") or not _posix_shell_available():
        return
    agent = ShellAgent('printf %s "$prompt"', tmp_path, timeout=5)
    try:
        agent.run("x" * 300_000)
    except PromptTooLongError as e:
        assert "$prompt_file" in str(e), str(e)
    else:
        raise AssertionError("超过 Linux 单参数上限应触发 PromptTooLongError")


def test_runner_aborts_immediately_when_prompt_too_long(tmp_path, monkeypatch):
    """提示词过长是「模板/内容」问题，重试必然失败：必须立即中止。

    回归：E2BIG 被当作普通轮次失败，连续空转 3 轮后才以退出码 1 中止，
    错误信息也看不出根因；提示词不会自行缩短，重试毫无意义。
    """
    import errno
    from xuen import agents
    from xuen.config import AgentConfig, Config, LoopConfig, WordsConfig
    from xuen.runner import run

    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise OSError(errno.E2BIG, "Argument list too long: '/bin/sh'")

    monkeypatch.setattr(agents.subprocess, "Popen", boom)
    cfg = Config(
        workspace=str(tmp_path / "ws"),
        agent=AgentConfig(command='printf %s "$prompt"'),
        words=WordsConfig(pick=0),
        loop=LoopConfig(iterations=5),
    )
    sink = _RecordingSink()
    try:
        run(cfg, "测试任务", sink=sink)
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("提示词过长应中止循环")
    assert len(calls) == 1, "重试必然失败，不应空转多轮"
    assert any("$prompt_file" in m for _, m in sink.messages), sink.messages
