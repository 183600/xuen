#!/usr/bin/env python3
"""文件体量门禁：拒绝超过 3,000 行的 Python 源文件。

背景：xuen/rounds.py 曾膨胀到 7,704 行，全面重写后压到 1,473 行。
为防止单文件重新失控，CI 对所有手写 .py 设 3,000 行红线；生成物
（如 pkg.generated*）不是人工维护的源码，不计入检查。

用法：
    python scripts/check_file_size.py [根目录]

任何文件超过上限时打印「相对路径: 行数」，并以非零码退出。
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple

MAX_LINES = 3000

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "node_modules",
    "site-packages",
}

EXCLUDED_DIR_PATTERNS = ("pkg.generated*",)
EXCLUDED_FILE_PATTERNS = ("pkg.generated*",)


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _is_excluded_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS or _matches(name, EXCLUDED_DIR_PATTERNS)


def iter_python_files(root: Path) -> Iterator[Path]:
    """遍历 root 下所有待检查的 .py 文件（跳过缓存/虚拟环境/生成物）。"""
    root = Path(root)
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(_is_excluded_dir(part) for part in rel.parts[:-1]):
            continue
        if _matches(path.name, EXCLUDED_FILE_PATTERNS):
            continue
        yield path


def count_lines(path: Path) -> int:
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def find_oversized(root: Path, max_lines: int = MAX_LINES) -> List[Tuple[Path, int]]:
    """返回超过 max_lines 的文件 (相对路径, 行数) 列表。"""
    root = Path(root)
    offenders: List[Tuple[Path, int]] = []
    for path in iter_python_files(root):
        lines = count_lines(path)
        if lines > max_lines:
            offenders.append((path.relative_to(root), lines))
    return offenders


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="拒绝超过 3,000 行的 Python 源文件")
    parser.add_argument(
        "root",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1]),
        help="扫描根目录（默认：仓库根）",
    )
    parser.add_argument("--max-lines", type=int, default=MAX_LINES,
                        help="行数上限（默认 3000）")
    args = parser.parse_args(argv)

    offenders = find_oversized(Path(args.root), args.max_lines)
    if not offenders:
        print("OK: 所有 Python 文件均不超过 {} 行".format(args.max_lines))
        return 0

    for rel, lines in offenders:
        print("{}: {} 行（上限 {}）".format(rel, lines, args.max_lines))
    print("FAIL: {} 个 Python 文件超过 {} 行，请优先删减或拆分".format(
        len(offenders), args.max_lines), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
