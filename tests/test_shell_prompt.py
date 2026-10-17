"""提示词内 shell 片段与「提示词过长」错误的回归测试。"""
from __future__ import annotations

from xuen.sink import Sink


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
