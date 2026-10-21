"""仓库卫生回归：运行产物绝不能重新进入版本库。

本仓库由自动化循环维护（.github/workflows/continuous-loop.yml）：
每轮跑完测试后用 `git add -A` 提交全部改动——历史上 coverage 覆盖率数据
（.coverage，二进制）与自动化会话遗留的临时工作区 ws/（含内嵌生成机器
绝对路径的 write_section.py）被误提交后，会被后续每轮以内容变化持续
重复提交，污染每次迭代的 diff；同类工作区后来又以 ok-ws/ 的名字被误提交。

这些生成物必须保持「未被 git 跟踪」且「被 .gitignore 覆盖」：
只要 .gitignore 有规则，`git add -A` 就不会再把它们重新纳入索引；
本测试在非 git 环境（安装包 / 源码导出目录）自动跳过。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 运行产物及其应命中的 .gitignore 规则（同一批路径，逐一断言）
GENERATED = (
    ".coverage",
    "ws/research.md",
    "ws/write_section.py",
    "ok-ws/research.md",
    "ok-ws/write_section.py",
    # 仓库根直接跑循环时产生的运行期状态（.rounds 曾被误提交）
    ".rounds/state.json",
    ".rounds/review.md",
    "research.md",
    "words.txt",
    "write_section.py",
    "rounds/history.jsonl",
)


def _git(*args: str):
    """在仓库根跑 git；不可用（无 git / 非仓库 / 执行失败）时返回 None。"""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        return None
    try:
        return subprocess.run(("git",) + args, cwd=str(ROOT),
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


@pytest.mark.parametrize("rel", GENERATED)
def test_generated_artifact_not_tracked(rel):
    """产物不得被跟踪：ls-files --error-unmatch 命中即为被误提交。"""
    r = _git("ls-files", "--error-unmatch", "--", rel)
    if r is None:
        pytest.skip("不在 git 仓库中（安装包/导出目录）")
    assert r.returncode != 0, (
        f"{rel} 是 xuen/coverage 的运行产物，不应被 git 跟踪；"
        "请执行 git rm --cached 并确认 .gitignore 覆盖"
    )


@pytest.mark.parametrize("rel", GENERATED)
def test_generated_artifact_ignored(rel):
    """产物必须被 .gitignore 覆盖：check-ignore 无匹配即为漏网。"""
    r = _git("check-ignore", "--no-index", "-q", "--", rel)
    if r is None:
        pytest.skip("不在 git 仓库中（安装包/导出目录）")
    assert r.returncode == 0, (
        f"{rel} 未被任何 .gitignore 规则覆盖，自动化循环的 git add -A "
        "会把它重新提交进版本库"
    )
