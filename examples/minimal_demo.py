#!/usr/bin/env python3
"""xuen 最小可运行示例：一轮「灵感词 → 提示词 → 轮次守卫 → 终端报告」。

不需要安装 opencode 等外部 agent，也不需要网络或 pytest：
  * examples/mock_agent.py 扮演外部 agent（生成词库 / 写研究区块 / 当评审员）；
  * 临时仓库里的 Makefile 提供一个只依赖 Python 的 test 目标，用于演示
    「测试全部通过 → 候选晋升为最佳」的自动验证；
  * 若系统没有 make，则自动回落到 mock 评审员打分（verify=auto + fallback=ai）。

运行：
    python examples/minimal_demo.py
    python examples/minimal_demo.py --keep   # 保留临时工作区供查看
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xuen.config import Config  # noqa: E402
from xuen.runner import run  # noqa: E402
from xuen.sink import ConsoleSink  # noqa: E402
from xuen.ui import configure  # noqa: E402


def _quote_arg(value: object) -> str:
    text = str(value)
    if os.name == "nt":
        return subprocess.list2cmdline([text])
    return shlex.quote(text)


def _agent_command(agent: Path, workspace: Path) -> str:
    parts = [sys.executable, agent, workspace, ROOT]
    quoted = " ".join(_quote_arg(part) for part in parts)
    return quoted + ' "$prompt_file"'


def _write_mock_repo(base: Path) -> Path:
    """建一个只有 Python 依赖的测试仓库，供轮次守卫自动验证候选。"""
    repo = base / "mock_repo"
    repo.mkdir()
    check = f'{_quote_arg(sys.executable)} -c "print(\'mock test suite passed\')"'
    (repo / "Makefile").write_text(f"test:\n\t@{check}\n", encoding="utf-8")
    return repo


def _show_artifacts(workspace: Path) -> None:
    print("\n=== 演示产物（候选与最佳分离）===")
    for rel in ("research.md", "words.txt", "rounds/best.json",
                "rounds/best.md", "rounds/history.jsonl"):
        path = workspace / rel
        print(f"- {rel}: {'已生成' if path.exists() else '缺失'}")
    snaps = sorted((workspace / "rounds").glob("cand-*.md"))
    print(f"- 候选快照: {len(snaps)} 个"
          + (f"（{snaps[0].name}）" if snaps else ""))
    best_json = workspace / "rounds" / "best.json"
    if best_json.exists():
        print("- best.json 内容：")
        print(best_json.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="xuen 最小可运行示例")
    parser.add_argument("--keep", action="store_true",
                        help="保留临时工作区（默认运行结束后删除）")
    parser.add_argument("--no-color", action="store_true",
                        help="关闭终端颜色")
    args = parser.parse_args(argv)

    configure(not args.no_color)
    base = Path(tempfile.mkdtemp(prefix="xuen-demo-"))
    try:
        workspace = base / "workspace"
        workspace.mkdir()
        agent = Path(__file__).with_name("mock_agent.py")
        repo = _write_mock_repo(base)

        cfg = Config()
        cfg.workspace = str(workspace)
        cfg.agent.command = _agent_command(agent, workspace)
        cfg.agent.timeout = 60.0
        cfg.words.count = 6
        cfg.words.batch = 6
        cfg.words.pick = 2
        cfg.words.reuse = False
        cfg.loop.iterations = 1
        cfg.rounds.enabled = True
        cfg.rounds.verify = "auto"
        cfg.rounds.fallback = "ai"
        cfg.rounds.repo = str(repo)
        cfg.rounds.verify_timeout = 60.0
        cfg.rounds.judge_timeout = 60.0
        cfg.tui = False
        cfg.color = not args.no_color

        print(f"演示目录：{base}\n")
        run(cfg, "用随机灵感词设计一个更稳健的优化器", sink=ConsoleSink())
        _show_artifacts(workspace)
    finally:
        if args.keep:
            print(f"\n临时工作区已保留：{base}")
        else:
            shutil.rmtree(base, ignore_errors=True)
            print("\n临时工作区已清理（--keep 可保留查看）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
