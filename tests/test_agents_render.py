"""ShellAgent 命令渲染的回归测试（注入防护与占位符边界）。

这些测试来自轮次守卫验证过的候选快照，让 agents.py 的渲染加固有
一道可自动执行的防线：命令替换/反引号/算术语境/heredoc/注释里的
占位符不能替换、提示词里的 $(...)/`...` 不能注入执行。
"""
from __future__ import annotations


def _posix_shell_available():
    import os
    import shutil
    return os.name == "posix" and shutil.which("bash") and shutil.which("sh")


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
    for tpl in ("cat <<EOF\n$prompt\nEOF",
                "cat <<'EOF'\n$prompt\nEOF",
                "cat <<-EOF\n\t$prompt\n\tEOF"):
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


def test_render_command_heredoc_delimiter_split_expansion_cannot_inject(tmp_path):
    """终止符词里用续行拆开的展开头/引用头不能按截断后的短终止符收正文。

    回归：shell 在分词前删除续行，`cat <<$\\<换行>(echo X) > /dev/null`
    的终止符词是字面量 `$(echo X)`（词不展开、只做引号移除）；渲染器在
    `(` 处把词截成 `$`，正文行 `$` 被当成终止符、正文提前结束，$prompt
    被替换进 shell 仍当作正文的区域——不加引号的正文会执行提示词里的
    $(...)/`...`（注入，实测 bash 下创建文件）。`$[`/`${` 含空白的展开
    内部同理（`$[X Y]` 的终止符是字面量 `$[X Y]`，简单扫描按空白截断）。
    修复：终止符词里续行拼出的展开/引用头与紧邻写法同口径整体拒绝
    （$(`、$[、${、$'、$"，双引号内的 $(/${/$[）：边界与 quoted 语义
    都无法安全确定，由配置校验拦下；普通续行拼接（E+续行+OF、
    $+续行+X、A$+续行+B、被转义的 \\$+续行+( ）不受影响。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # $ + 续行 + ( 拼成命令替换：终止符是字面量 $(echo X)（注入）
        "cat <<$\\\n(echo X) > /dev/null\n$\nprintf %s $prompt\n",
        # $[ / ${ 的展开内部含空白：按空白截断词边界会提前收正文
        "cat <<$\\\n[X Y] > /dev/null\n$[X\nprintf %s $prompt\n",
        "cat <<$\\\n{X:-a b} > /dev/null\n${X:-a\nprintf %s $prompt\n",
        # $' / $" 是方言相关的引用语法（bash 解释、dash 当字面量）
        "cat <<$\\\n'EOF' > /dev/null\nbody\nprintf %s $prompt\n",
        'cat <<$\\\n"EOF" > /dev/null\nbody\nprintf %s $prompt\n',
        # 双引号内的 $ + 续行 + ( 同理：嵌套展开内部的引号让字面找 "
        # 截错词边界，正文范围失控
        'cat <<"$\\\n(echo "x y")" > /dev/null\nbody\nprintf %s $prompt\n',
    )
    prompt = "a'b $HOME `id` $(touch pwned) \\ d"
    for tpl in templates:
        assert command_receives_prompt(tpl) is False, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        # 占位符原样保留，提示词绝不进入任何会被 shell 执行的区域
        assert "$prompt" in rendered, tpl
        assert "touch" not in rendered and "pwned" not in rendered, tpl
        if not _posix_shell_available():
            continue
        marker = tmp_path / "pwned"
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            if marker.exists():
                marker.unlink()
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
            assert not marker.exists(), (tpl, sh)
    if not _posix_shell_available():
        return
    # 对照：普通续行拼接不构成展开头，照常送达；被转义的 \$ 只是字面量
    deliver = (
        "cat <<E\\\nOF > /dev/null\nbody\nEOF\nprintf %s $prompt",
        "cat <<A$\\\nB > /dev/null\nbody\nA$B\nprintf %s $prompt",
        "cat <<$\\\nX > /dev/null\nbody\n$X\nprintf %s $prompt",
        'cat <<"a\\$\\\n(x)" > /dev/null\nbody\na$(x)\nprintf %s $prompt',
    )
    for tpl in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            if (tmp_path / "pwned").exists():
                (tmp_path / "pwned").unlink()
            r = subprocess.run([sh, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, sh, r.stderr)
            assert r.stdout == prompt, (tpl, sh, r.stdout)
            assert not (tmp_path / "pwned").exists(), (tpl, sh)


def test_render_command_heredoc_delimiter_process_substitution_cannot_inject(tmp_path):
    """终止符词里的进程替换 <(...)/>(...) 不能按 < 截断后的短终止符收正文。

    回归：进程替换与相邻字符同属一个词（`echo a<(cmd)` 输出
    a/dev/fd/63）；bash 对 `cat <<EOF<(echo X)` 的终止符是字面量
    `EOF<(echo X)`（进程替换本身不执行、只留字面文本），正文一直延伸到
    模板结尾。渲染器在 < 处把词截成 EOF、正文提前结束，$prompt 被替换进
    shell 仍当作正文的区域——不加引号的正文会执行提示词里的 $(...)/``
    （注入，实测 bash 创建文件；dash 对 <( 直接报语法错误）；带引号部分
    不改变 <( 同属一词（`<<'EOF'<(cmd)` 的终止符仍是 EOF<(cmd)），虽不
    展开、提示词也会被静默吞掉。修复：终止符词里的裸 <( / >( 与
    ${/反引号 等同类，返回 (None, n) 整体拒绝，剩余模板吞掉、不替换。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # 裸 <(：bash 的终止符是字面量 EOF<(echo X)
        "cat <<EOF<(echo X) > /dev/null\nbody\nEOF\n$prompt\n",
        # 裸 >(：同理
        "cat <<a>(echo X) > /dev/null\nbody\na\n$prompt\n",
        # 带引号的部分不改变 <( 属于同一个词
        "cat <<'EOF'<(echo X) > /dev/null\nbody\nEOF\n$prompt\n",
        # 续行隔开 $ 与 <(：拼接后仍同属一个词
        "cat<<$\\\n<(echo X) > /dev/null\n$\nprintf %s $prompt\n",
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


def test_render_command_closed_substitution_heredoc_without_outer_cannot_inject(tmp_path):
    """已闭合替换里的 heredoc 没有外层正文覆盖时必须整体吞掉、不替换。

    回归：`cat <> /dev/null $(cat <<B)\\n<<x\\nA\\nB\\n$prompt` 里 B 的替换
    在同一行闭合、外层没有任何 heredoc。bash 在下一个换行处补收 B 的正文
    （`<<x`、`A`，终止符 `B`），dash 却把 B 静默丢弃、把后续行当命令解析：
    其中 `<<x` 会再开一个吞到模板结尾的正文，渲染器在这之后恢复替换的
    `$prompt` 行正落进该正文——不加引号的正文会执行提示词里的
    $(touch ...)/反引号（注入，实测 dash 创建文件；bash 无此问题，跨 shell
    必须按更危险的一侧处理）。修复：存在登记深度比当前深度更深的 heredoc
    时，只有 dash 口径（只收深度 == 当前深度的正文）与 bash 口径（深度
    降序收全部）的正文终点完全一致才恢复替换，否则剩余模板整体吞掉、
    不做替换（见 consume_heredoc_bodies）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    templates = (
        # 无外层 heredoc：dash 丢弃 B，`<<x` 开启吞到模板结尾的正文
        ("cat <> /dev/null $(cat <<B)\n"
         "<<x\n"
         "A\n"
         "B\n"
         "$prompt\n"),
        # 深度 2：B、C 都注册在已闭合的替换里，同理
        ("cat <> /dev/null $(cat <<B $(cat <<C))\n"
         "<<x\n"
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
        # 占位符原样保留，提示词绝不进入 shell 当作正文的区域
        assert "$prompt" in rendered, tpl
        assert str(marker) not in rendered, tpl
        for sh in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            subprocess.run([sh, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert not marker.exists() and not (tmp_path / "pwned.bt").exists(), tpl


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


def test_render_command_legacy_arithmetic_hash_comment_cannot_inject(tmp_path):
    """$[...] 区域内的词首 # 在 dash 下是注释，会吞掉提示词的引号语境。

    回归（dash 下实测创建文件）：dash 不支持 $[...]——`$[` 只是普通词、
    区域内容按普通词语境解析，词首 # 开启注释、把结束符 ] 与同行后续
    （含后面单引号串的起始引号）一起吞到行尾，提示词的第二行成为裸命令、
    其中的 $(...)/`...` 被真正执行（fuzz 模板 `$[ #c elif local ] for[
    declare[ (echo $prompt)` 下 $(touch PWN_A)/$(( $(touch PWN_B) )) 均被
    执行；bash 在算术区解析 # 报错、不执行）。修复：$[...] 区域内遇到
    词首 # 即整体吞到模板结尾，占位符原样保留、不替换
    （command_receives_prompt 据此拒绝这类模板）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"l1\n$(touch {marker})\n$(( $(touch {marker}.bt) ))\nend\n"
    templates = (
        # fuzz 实测命中的模板（dash 下 PWN_A/PWN_B 均被创建）
        "$[ #c elif local ] for[declare[ (echo $prompt)",
        # 最小化：区域内词首 # 的注释吞掉结束符后的引号
        "$[ # ] (echo $prompt)",
        # 双引号语境同样按「整体跳过、不替换」处理
        'printf %s "$[ #x ]$prompt"',
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
    # 正面对照：# 前是数字的 bash 基数写法不触发（词中 # 不是注释），
    # 普通 $[...] 照常按深度配对、其后占位符正常替换
    tpl = 'printf %s $[16#ff] "$prompt"; echo'
    assert command_receives_prompt(tpl) is True, tpl
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    r = subprocess.run(["bash", "-c", agent.render_command(prompt)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "255" + prompt + "\n", r.stdout
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


def test_render_command_case_after_comment_line_continuation_cannot_inject(tmp_path):
    """注释行尾的反斜杠不续行：`#x\\<换行>case` 的 case 仍是关键字。

    回归（bash 与 dash 下均可复现）：反斜杠是注释内最后一个字符时，
    换行结束注释、并不构成续行；命令替换里的裸 case 依旧是真关键字。
    而 _is_case_keyword 的向左边界检查无条件跨过 `\\<换行>`，把上一行
    注释里的字符当成词内字符、漏认 case，pattern ) 破坏括号配对恢复
    错误引号状态，之后的 $prompt 按裸语境插入双引号转义——shell 仍在
    裸语境，提示词里的 `; touch ...` 被真正执行（注入）。修复：向左
    跨续行前确认反斜杠所在物理行不含 #（可能在注释里时按硬换行处理，
    宁可误认关键字整体跳过/拒绝，不可漏认）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt, _is_case_keyword

    # 真续行合并出的词（xcase）不是关键字；注释里的反斜杠不合并
    assert _is_case_keyword("x\\\ncase", 3) is False
    assert _is_case_keyword("#x\\\ncase", 4) is True
    assert _is_case_keyword("#a\\\n\\\ncase", 6) is True
    assert _is_case_keyword("#a\\\nb\\\ncase", 7) is False

    if not _posix_shell_available():
        return
    marker = tmp_path / "pwned"
    prompt = f"x; touch {marker}; echo y"
    tpl = 'printf %s "$(echo hi #x\\\ncase x in x) printf %s $prompt;; esac)"'
    # 命令替换里 case 之后的 $prompt 不会送达 agent：配置校验必须拒绝
    assert command_receives_prompt(tpl) is False
    agent = ShellAgent(tpl, tmp_path, timeout=5)
    rendered = agent.render_command(prompt)
    assert "$prompt" in rendered, tpl
    assert str(marker) not in rendered, tpl
    for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        r = subprocess.run([shell, "-c", rendered], capture_output=True,
                           text=True, cwd=tmp_path)
        assert r.returncode == 0, (shell, r.stderr)
        assert not marker.exists(), (shell, rendered)


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
    渲染结果在双引号内转义 $，提示词原样送达且不执行。区域里出现引号
    （渲染器会切换语境、bash 不会）的写法另见
    test_render_command_rejects_pid_paren_quote_region。
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


def test_render_command_rejects_pid_paren_quote_region(tmp_path):
    """`$$(` / `$${` 区域里出现引号切换的模板必须整体拒绝（bash 注入回归）。

    回归：shell 把 `$$(` / `$${` 的 $$ 当 PID、后面的括号当字面量，但
    bash 会对 `(` 到配对 `)`（以及 `{` 到配对 `}`）的区域做命令替换式
    配对扫描——区域里的引号只是字面量、不切换外层双引号状态（实测
    `v="$$(a"b"c)d"` 在 bash 下 v 是 `PID(a"b"c)d`、dash 是
    `PID(abc)d`；`$${x:-"b"}` 同理 bash 保留引号、dash 去掉引号）。
    渲染器（与 dash 一致）在 `"` 处切换语境：
    `printf %s "$$<续行>( "$prompt" )"` 与
    `printf "%s $${x:-"}$prompt"}"` 渲染后提示词按裸语境插成
    shlex.quote 单引号，而 bash（实际执行 /bin/sh 的方言无法预知）仍把
    它当双引号内文本——单引号只是字面量，提示词里的 $(...)/`...` 逃出
    引用被真正执行（注入，实测 bash 创建文件、dash 安全；前者此前还是
    「续行拆操作符」测试里的允许对照）。修复：区域里出现会切换引号的
    `"` 且能配到结束符时整体拒绝（与 $'...' / 续行拆操作符同口径），
    由配置校验拦下（command_receives_prompt 返回 False）。
    区域没有结束符时 bash 报解析错误、不会执行（允许对照）；
    配对结束符之后的引号两个 shell 行为一致，不受影响（允许对照）。
    """
    import re
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    reject = (
        'printf %s "$$\\\n( "$prompt" )"',    # 旧允许对照：实测 bash 注入
        'printf %s "$$\\\n( "*$prompt" )"',   # 区域内还有 * 前缀的变体
        'printf %s "$$("$prompt")"',           # 无续行：区域里直接切换引号
        'printf %s "x$$(a"b"$prompt"c)d"',     # 引号在前、提示词仍在区域内
        'printf %s "$$(x\\\\"$prompt)"',       # 双反斜杠后引号仍会切换
        'printf %s "$$(x"y)$prompt"',          # 提示词在配对的 ) 之前
        'printf "%s $${x:-"}$prompt"}"',       # $${ 区域：实测 bash 注入
        'printf "%s $${x:-"a b"}$prompt"',     # $${ 区域：bash 报坏替换
    )
    for tpl in reject:
        assert command_receives_prompt(tpl) is False, tpl
        try:
            ShellAgent(tpl, tmp_path, timeout=5).render_command("x")
        except ValueError:
            pass
        else:
            raise AssertionError(f"`$$(` 区域含引号的模板应被拒绝: {tpl}")

    # 允许对照：区域内没有引号切换，两个 shell 行为一致、照常送达
    prompt = "P one; two Q"
    esc = re.escape(prompt)
    deliver = (
        # 区域紧跟提示词（不含引号）：bash 在该区域内按双引号展开，一致
        ('printf %s "$$\\\n($prompt)done"', rf"\d+\({esc}\)done"),
        # 配对 ) 之后的引号照常切换，两个 shell 一致
        ('printf %s "$$(x)"$prompt""', rf"\d+\(x\){esc}"),
    )
    for tpl, pattern in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert re.fullmatch(pattern, r.stdout), (tpl, shell, r.stdout)

    # 没有结束 ) 的区域：bash 报解析错误、dash 正常送达，都不可注入
    marker = tmp_path / "pwned"
    prompt = f"$(touch {marker}) `touch {marker}.bt`"
    tpl = 'printf %s "$$($prompt"'
    assert command_receives_prompt(tpl) is True
    rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
    assert "\\$(touch" in rendered
    for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
        subprocess.run([shell, "-c", rendered], capture_output=True,
                       text=True, cwd=tmp_path)
    assert not marker.exists() and not (tmp_path / "pwned.bt").exists()


def test_render_command_adjacent_placeholders(tmp_path):
    """紧贴上一个占位符兑现结果的占位符（含只隔续行的情形）也要替换。

    回归：`$prompt$prompt` 里第二个占位符前面紧贴的是第一个占位符的
    替换结果（单词字符 t/e），渲染器的「完整词」左边界检查把替换结果
    误当模板字面量、只兑现第一个：命令里留下字面 `$prompt`，shell 把它
    当空变量展开——提示词被静默丢掉一半；`$prompt_file$prompt`
    （或 `$prompt_file$prompt_file`）同理漏替换。隔续行的
    `$prompt\\<换行>$prompt` 在分词前被删除、与紧邻写法等价，同样会漏。
    修复：记录最近兑现占位符的结束位置，紧贴它的单词字符不再拦截；
    模板里字面紧贴的 `x$prompt` / `$prompt_out` / `$$prompt` 仍然不
    替换（下方负面对照）。
    """
    import shutil
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    prompt = "P $(touch PWNED) `touch PWNED2` 'q' \\ d"

    # 相邻占位符全部兑现：两个 shell 下都输出提示词拼接/翻倍
    deliver = (
        ("printf %s $prompt$prompt", prompt + prompt),
        ('printf %s "$prompt$prompt"', prompt + prompt),
        ("printf %s '$prompt$prompt'", prompt + prompt),
        # 续行在分词前被删除：第二个占位符同样紧贴第一个的兑现结果
        ("printf %s $prompt\\\n$prompt", prompt + prompt),
        # 三个相邻占位符都要兑现（漏一个就会少一段）
        ("printf %s $prompt$prompt$prompt", prompt * 3),
    )
    for tpl, expected in deliver:
        assert command_receives_prompt(tpl) is True, tpl
        # 不依赖 shell 的判据（用无特殊字符的提示词，转义后原样可数）：
        # 修复前只有第一个占位符被兑现，计数必然偏少
        count = expected.count(prompt)
        probe = ShellAgent(tpl, tmp_path, timeout=5).render_command("PPXQ")
        assert probe.count("PPXQ") == count, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        if not _posix_shell_available():
            continue
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert r.stdout == expected, (tpl, shell, r.stdout)
            assert not (tmp_path / "PWNED").exists(), (tpl, shell)
            assert not (tmp_path / "PWNED2").exists(), (tpl, shell)

    # $prompt_file 与 $prompt 相邻混排：路径与提示词兑现为同一个词
    mixed = (
        ("printf %s $prompt_file$prompt", False),
        ("printf %s $prompt$prompt_file", True),
    )
    for tpl, prompt_first in mixed:
        assert command_receives_prompt(tpl) is True, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        rendered = agent.render_command(prompt)
        pfile = agent._prompt_file
        assert pfile is not None
        if not _posix_shell_available():
            continue
        path = str(pfile.resolve())
        expected = prompt + path if prompt_first else path + prompt
        for shell in filter(None, (shutil.which("bash"), shutil.which("dash"))):
            r = subprocess.run([shell, "-c", rendered], capture_output=True,
                               text=True, cwd=tmp_path)
            assert r.returncode == 0, (tpl, shell, r.stderr)
            assert r.stdout == expected, (tpl, shell, r.stdout)

    # 负面对照：模板里字面紧贴的单词字符/$$ 仍不算占位符（不替换）
    for tpl in ("printf %s x$prompt", "printf %s $prompt_out",
                "printf %s $$prompt", 'printf %s "x$prompt"',
                "printf %s x$prompt$prompt", "printf %s $promptx$prompt"):
        assert command_receives_prompt(tpl) is False, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        assert "$prompt" in rendered and prompt not in rendered, tpl


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
        # $$ 是 PID：( 不是 $( 展开的起点；区域内没有引号，照常渲染
        # （区域里出现引号切换的 `$$(` 写法见
        # test_render_command_rejects_pid_paren_quote_region）
        'printf %s "$$\\\n($prompt)done"',
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


def test_render_command_rejects_locale_quotes(tmp_path):
    """裸上下文中的本地化引用（$"..."）模板必须整体拒绝。

    回归：$"..." 与 $'...' 同为方言相关的引用语法——bash 把 $"..."
    当 gettext 本地化字符串，dash（Ubuntu/Debian 的 /bin/sh）则把 $ 当
    字面量、后面只是普通双引号串。此前这类模板能通过配置校验：在 dash
    下送达的提示词被静默多拼出一个 $ 前缀（`$"$prompt"` 渲染成
    `$"提示词"`，dash 输出 `$提示词`），两 shell 送达内容不一致；
    `$`+续行+`"` 拼成的本地化引用同样漏网。方言无法预知，与 $'...'
    同口径整体拒绝，绝不替换。
    """
    import subprocess
    from xuen.agents import ShellAgent, command_receives_prompt

    for tpl in ('printf %s $"$prompt"',
                'printf %s x$"$prompt"',
                'printf %s x=$"$prompt"',
                'printf %s $"$prompt_file"',
                'printf %s $\\\n"$prompt"',     # 续行拼成本地化引用
                'printf %s x$\\\n"$prompt"'):
        assert command_receives_prompt(tpl) is False, tpl
        agent = ShellAgent(tpl, tmp_path, timeout=5)
        try:
            agent.render_command("x")
        except ValueError:
            pass
        else:
            raise AssertionError(f'含 $"..." 的模板应被拒绝: {tpl}')
    # 拒绝发生后工作区不能残留无消费者的提示词文件：$prompt_file 先落盘、
    # 随后的 $"..." 才触发拒绝时，渲染失败路径也必须清理
    mixed = 'printf %s "$prompt_file" >/dev/null; printf %s $"$prompt"'
    with_cleanup = ShellAgent(mixed, tmp_path, timeout=5)
    try:
        with_cleanup.render_command("x")
    except ValueError:
        pass
    else:
        raise AssertionError('含 $"..." 的模板应被拒绝')
    assert [p.name for p in tmp_path.iterdir()] == []

    if not _posix_shell_available():
        return
    # 对照：$$" 是 PID + 普通双引号、\$" 的 $ 被转义、双引号内的 $ 紧邻
    # 结束引号——都不是本地化引用，照常送达且两 shell 一致
    prompt = "a'b \"c\" $HOME `id`"
    for tpl, prefix in (('printf %s $$"$prompt"', None),
                        ('printf %s \\$"$prompt"', "$"),
                        ('printf %s "x$"y"$prompt"', "x$y")):
        assert command_receives_prompt(tpl) is True, tpl
        rendered = ShellAgent(tpl, tmp_path, timeout=5).render_command(prompt)
        for argv in (["/bin/sh", "-c", rendered], ["bash", "-c", rendered]):
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=tmp_path)
            assert r.returncode == 0, (tpl, argv, r.stderr)
            if prefix is None:
                assert r.stdout.endswith(prompt), (tpl, r.stdout)
                assert r.stdout[:-len(prompt)].isdigit(), (tpl, r.stdout)
            else:
                assert r.stdout == prefix + prompt, (tpl, r.stdout)


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
