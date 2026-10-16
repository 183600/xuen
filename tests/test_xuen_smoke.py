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
