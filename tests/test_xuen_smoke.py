"""xuen 包的冒烟测试（只依赖标准库 + PyYAML，不依赖 textual）。

这些测试让 Continuous Loop 的每轮候选都有一道最基本的自动验证：
import 断了、CLI 参数解析坏了，都会被 round_guard 拦下（不晋升为最佳）。
"""
from __future__ import annotations

import importlib


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
    没有下标的 ${x:-$prompt} 仍是词语境，照常安全替换。
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
    # 没有下标的参数展开仍是安全的词语境：照常替换、正常送达且不执行
    tpl = 'printf %s "${x:-$prompt}"; echo'
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
    词语境的 ${x:-$prompt} / ${x:+$prompt} 仍照常安全替换。
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
    # 正面对照：默认值/替代值等词语境照常替换、正常送达且不执行
    tpl = 'printf %s "${x:-$prompt}"'
    assert command_receives_prompt(tpl) is True
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run([bash, "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == prompt
    assert not marker.exists()


def test_render_command_ansi_c_quotes_escape_prompt(tmp_path):
    """ANSI-C 引用（$'...'）里的占位符必须按反斜杠转义规则插入。

    回归（bash 下可复现）：沿用普通单引号的 '\\'' 闭合重开写法时，
    值里的 \\' 在 $'...' 里是被转义的单引号、不会闭合引用——引号奇偶
    被打乱，值里随后的裸命令替换逃出引用被真正执行（注入）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    bash = shutil.which("bash")
    marker = tmp_path / "pwned"
    tpl = "printf %s $'pre $prompt post'"
    assert command_receives_prompt(tpl) is True
    prompt = f"\\' ; touch {marker} ; echo \\'"
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    rendered = agent.render_command(prompt)
    assert "$prompt" not in rendered
    r = subprocess.run([bash, "-c", rendered], capture_output=True,
                       text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    # 提示词原样送达（不执行、不被 ANSI-C 转义解释）
    assert r.stdout == f"pre {prompt} post"
    assert not marker.exists()
    # $prompt_file：路径经 ANSI-C 转义后仍能通向提示词文件（含空格工作区）
    workspace = tmp_path / "some dir"
    workspace.mkdir()
    tpl_file = "cat $'$prompt_file'"
    assert command_receives_prompt(tpl_file) is True
    agent_file = ShellAgent(tpl_file, workspace, timeout=5)
    r_file = subprocess.run([bash, "-c", agent_file.render_command(prompt)],
                            capture_output=True, text=True, cwd=tmp_path)
    assert r_file.returncode == 0, r_file.stderr
    assert r_file.stdout == prompt
    # 值尾部的反斜杠不能吞掉模板的结束引号；\x 序列不被解释成转义
    tpl2 = "printf %s $'$prompt'"
    assert command_receives_prompt(tpl2) is True
    for value in ("abc\\", "a\\nb", "a'b"):
        agent2 = ShellAgent(tpl2, tmp_path, timeout=5)
        r2 = subprocess.run([bash, "-c", agent2.render_command(value)],
                            capture_output=True, text=True, cwd=tmp_path)
        assert r2.returncode == 0, r2.stderr
        assert r2.stdout == value


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


def _run_fake_words_scenario(tmp_path, agent_stdout, *, regen_words, reuse=True):
    """用假 agent（把收到的提示词记到日志、stdout 固定输出指定词表）跑一轮
    runner.run，返回 (sink, prompts, workspace, SystemExit 或 None)。"""
    import sys
    from xuen.config import AgentConfig, Config, LoopConfig, WordsConfig
    from xuen.runner import run
    from xuen.sink import Sink

    class _RecordingSink(Sink):
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
