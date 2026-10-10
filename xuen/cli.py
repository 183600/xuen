"""命令行入口。"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .ui import configure, ui


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xuen",
        description="灵感词驱动的研究循环：生成领域词库 → 每轮随机抽词 → "
                    "外部 agent（如 opencode）模拟人类研究者思考并演进想法区/产物区",
        epilog='示例：python main.py "设计一个新的优化器"',
    )
    p.add_argument("task", nargs="*", help="任务描述，例如：设计一个新的优化器")
    p.add_argument("-c", "--config", help="配置文件路径（默认：./config.yaml）")
    p.add_argument("--task-file", help="从文件读取任务")
    p.add_argument("--workspace", help="覆盖工作区目录")
    p.add_argument("--iterations", help="覆盖轮数（整数或 inf）")
    p.add_argument("--pick", type=int, help="覆盖每轮随机灵感词数量 n（>=0）")
    p.add_argument("--regen-words", action="store_true", help="忽略已有词库并重新生成")
    p.add_argument("--no-tui", action="store_true", help="不用 TUI，直接输出到终端")
    p.add_argument("--no-color", action="store_true", help="关闭彩色输出（--no-tui 时有效）")
    return p


def _resolve_task(args) -> str:
    task = " ".join(args.task).strip()
    if args.task_file:
        if task:
            print("位置参数任务与 --task-file 不能同时使用", file=sys.stderr)
            raise SystemExit(2)
        try:
            with open(args.task_file, encoding="utf-8") as f:
                task = f.read().strip()
        except (OSError, UnicodeDecodeError) as e:
            # UnicodeDecodeError：任务文件不是合法 UTF-8（如二进制/GBK 文件）
            print(f"无法读取任务文件 {args.task_file!r}：{e}", file=sys.stderr)
            raise SystemExit(2)
    if not task:
        try:
            task = input("请输入任务（例如：设计一个新的优化器）：").strip()
        except (EOFError, KeyboardInterrupt):
            task = ""
    return task


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    try:
        cfg = load_config(args.config)
    except FileNotFoundError as e:
        print(f"找不到配置文件：{e}", file=sys.stderr)
        print("请把 config.example.yaml 复制为 config.yaml（或用 -c 指定）。", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"配置文件解析失败：{e}", file=sys.stderr)
        return 2

    configure(not (args.no_color or not cfg.color))

    if args.workspace:
        cfg.workspace = args.workspace
    if args.pick is not None:
        if args.pick < 0:
            print("--pick 必须 >= 0", file=sys.stderr)
            return 2
        cfg.words.pick = args.pick
    if args.iterations is not None:
        v = args.iterations.strip().lower()
        if v in ("inf", ".inf", "+.inf", "infinite", "∞", "-1"):  # 与 config._parse_iterations 保持一致
            cfg.loop.iterations = None
        else:
            try:
                cfg.loop.iterations = int(v)
                if cfg.loop.iterations < 1:
                    raise ValueError
            except ValueError:
                print(f"--iterations 无效：{args.iterations!r}（应为整数或 inf）", file=sys.stderr)
                return 2

    task = _resolve_task(args)
    if not task:
        ui.err("未提供任务")
        return 2

    # TUI 模式（默认）：两个区块面板 + agent 输出日志 + 底部输入框
    if cfg.tui and not args.no_tui and sys.stdout.isatty():
        try:
            from .tui import run_tui
        except ImportError:
            ui.warn("未安装 textual，回退到纯终端输出（pip install textual 可启用 TUI）")
        else:
            return run_tui(cfg, task, regen_words=args.regen_words)

    from .runner import run  # 延迟导入，加快 --help

    try:
        run(cfg, task, regen_words=args.regen_words)
    except KeyboardInterrupt:
        print()
        ui.warn("已中断")
        return 130
    return 0
