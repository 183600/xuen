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
