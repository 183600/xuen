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
