"""ShellAgent 命令渲染的回归测试：heredoc / 命令替换 / 反引号注入防护。

这些测试来自轮次守卫验证过的候选快照，让 agents.py 的渲染加固有
一道可自动执行的防线：命令替换/反引号/算术语境/heredoc/注释里的
占位符不能替换、提示词里的 $(...)/`...` 不能注入执行。

本文件是按被测功能拆分后的第一组（物理重组，断言保持不变）。
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


def test_command_receives_prompt_ignores_probe_literal_in_template():
    """模板里恰好含探测令牌时不能误判成「占位符已送达」。

    回归：dry_run 用固定令牌 XUENPROMPTPROBE7C4F1D 渲染，模板本身含
    该字面量但没有 $prompt/$prompt_file 时，探测结果里当然能找到令牌，
    旧逻辑因此放行一个提示词被静默丢弃的模板。"""
    from xuen.agents import _PLACEHOLDER_PROBE, command_receives_prompt

    literal = f"opencode run {_PLACEHOLDER_PROBE}"
    assert command_receives_prompt(literal) is False
    assert command_receives_prompt(f"{literal} # \\$prompt") is False
    # 有真正的占位符时仍要判真（令牌字面量本身不能干扰探测）
    assert command_receives_prompt(f"{literal} $prompt") is True
    assert command_receives_prompt(
        f"{literal} \"$prompt\"") is True
    assert command_receives_prompt(f"{literal} $prompt_file") is True
    # 令牌字面量 + 注释里的占位符仍然没有送达
    assert command_receives_prompt(f"{literal} # $prompt") is False
    assert command_receives_prompt(f"{literal} # $prompt_file") is False


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

