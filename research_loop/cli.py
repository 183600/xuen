"""命令行入口。"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .ui import configure, ui


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research-loop",
        description="灵感词驱动的研究循环：生成领域词库 → 每轮随机抽词 → "
                    "LLM 模拟人类研究者思考并演进想法区/产物区",
        epilog='示例：python main.py "设计一个新的优化器"',
    )
    p.add_argument("task", nargs="*", help="任务描述，例如：设计一个新的优化器")
    p.add_argument("-c", "--config", help="配置文件路径（默认：./config.yaml）")
    p.add_argument("--task-file", help="从文件读取任务")
    p.add_argument("--workspace", help="覆盖工作区目录")
    p.add_argument("--iterations", help="覆盖轮数（整数或 inf）")
    p.add_argument("--pick", type=int, help="覆盖每轮随机灵感词数量 n（>=0）")
    p.add_argument("--mode", choices=("direct", "shell"), help="覆盖 agent 模式")
    p.add_argument("--regen-words", action="store_true", help="忽略已有词库并重新生成")
    p.add_argument("--no-mcp", action="store_true", help="本次运行不启动 MCP 服务器")
    p.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    return p


def _resolve_task(args) -> str:
    task = " ".join(args.task).strip()
    if args.task_file:
        with open(args.task_file, encoding="utf-8") as f:
            task = f.read().strip()
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
    if args.mode:
        cfg.agent.mode = args.mode
    if args.pick is not None:
        if args.pick < 0:
            print("--pick 必须 >= 0", file=sys.stderr)
            return 2
        cfg.words.pick = args.pick
    if args.iterations is not None:
        v = args.iterations.strip().lower()
        cfg.loop.iterations = None if v in ("inf", "infinite", "-1") else int(v)

    task = _resolve_task(args)
    if not task:
        ui.err("未提供任务")
        return 2

    from .runner import run  # 延迟导入，加快 --help

    try:
        run(cfg, task, regen_words=args.regen_words, use_mcp=not args.no_mcp)
    except KeyboardInterrupt:
        print()
        ui.warn("已中断")
        return 130
    return 0
