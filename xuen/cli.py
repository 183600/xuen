"""命令行入口。"""
from __future__ import annotations

import argparse
import sys

from .config import _validate, load_config
from .ui import configure, ui


def _load_tui():
    """延迟导入 TUI；独立成函数便于测试「未安装 textual」的降级路径。"""
    from .tui import run_tui
    return run_tui


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
    # ---- 轮次守卫：每轮快照、候选/最佳分离、自动验证与评分 ----
    p.add_argument("--no-rounds", action="store_true",
                   help="关闭轮次守卫（退回旧行为：每轮直接覆盖，无快照无最佳）")
    p.add_argument("--rounds-verify", choices=("auto", "tests", "user", "ai", "off"),
                   help="候选验证方式（默认 auto：有测试跑测试，否则用兜底评分者）")
    p.add_argument("--rounds-fallback", choices=("user", "ai"),
                   help="auto 模式下无测试可用时的兜底评分者（默认 ai）")
    p.add_argument("--rounds-score", type=float, metavar="N",
                   help="采纳阈值：评分 >= N 才把候选晋升为最佳（0-10，默认 7）")
    return p


def _resolve_task(args) -> str:
    task = " ".join(args.task).strip()
    if args.task_file:
        if task:
            print("位置参数任务与 --task-file 不能同时使用", file=sys.stderr)
            raise SystemExit(2)
        try:
            # utf-8-sig：Windows 记事本保存的任务文件常带 BOM，
            # 按 utf-8 读取会把 \ufeff 带进任务文本（标题与每轮提示词）
            with open(args.task_file, encoding="utf-8-sig") as f:
                task = f.read().strip()
        except (OSError, UnicodeDecodeError) as e:
            # UnicodeDecodeError：任务文件不是合法 UTF-8（如二进制/GBK 文件）
            print(f"无法读取任务文件 {args.task_file!r}：{e}", file=sys.stderr)
            raise SystemExit(2)
    if task:
        # 终端传入非法字节时，Python 以 surrogateescape 解出孤立代理字符：
        # 它们无法按 UTF-8 写进 research.md / 提示词文件（UnicodeEncodeError），
        # 必须在进入循环前给出明确错误，而不是运行期 traceback 或首轮失败
        try:
            task.encode("utf-8")
        except UnicodeEncodeError:
            print("任务包含无法用 UTF-8 编码的字符（终端传入的非法字节），"
                  "请重新输入", file=sys.stderr)
            raise SystemExit(2)
    if not task:
        try:
            task = input("请输入任务（例如：设计一个新的优化器）：").strip()
        except UnicodeError as e:
            # stdin 按严格 UTF-8 解码（sys.stdin.errors == "strict"）时，
            # 管道/终端里的非法字节会在 input() 内抛 UnicodeDecodeError；
            # 不能让它外泄成 traceback
            print(f"读取任务失败（输入不是合法 UTF-8）：{e}", file=sys.stderr)
            raise SystemExit(2)
        except EOFError:
            # stdin 被关闭/重定向（如 `xuen < /dev/null`、管道已读到 EOF）：
            # 没有任务可问，按「未提供任务」处理（退出码 2）。
            # KeyboardInterrupt 绝不能在这里一并吞掉：交互提示处按 Ctrl+C
            # 是「被中断」，必须按 README 的退出码约定返回 130，而不是被
            # 当成 EOF 一路走到「未提供任务」的退出码 2（由 main 统一处理）
            task = ""
        except RuntimeError:
            # 无控制台解释器（pythonw / 嵌入环境）里 sys.stdin 可能为 None，
            # input() 抛的是 RuntimeError('lost sys.stdin') 而不是 EOFError；
            # 与 EOF 同口径按「未提供任务」处理，不能让 traceback 外泄。
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

    if args.workspace is not None:
        workspace = args.workspace.strip()
        if not workspace:
            print("--workspace 不能为空", file=sys.stderr)
            return 2
        cfg.workspace = workspace
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

    # CLI 覆盖发生在 load_config 的校验之后，须对覆盖结果重新校验：
    # --workspace 可绕过 Windows cmd 元字符检查，--iterations 的巨大整数
    # 会让 runner 的 range() 抛 OverflowError（轮次守卫的 CLI 覆盖同理）
    need_revalidate = args.workspace is not None or args.iterations is not None

    # ---- 轮次守卫 CLI 覆盖 ----
    if args.no_rounds:
        cfg.rounds.enabled = False
    if args.rounds_verify is not None:
        cfg.rounds.verify = args.rounds_verify
        need_revalidate = True
    if args.rounds_fallback is not None:
        cfg.rounds.fallback = args.rounds_fallback
        need_revalidate = True
    if args.rounds_score is not None:
        if not (0.0 <= args.rounds_score <= 10.0):
            print("--rounds-score 必须在 0-10 之间", file=sys.stderr)
            return 2
        cfg.rounds.adopt_score = args.rounds_score
        need_revalidate = True

    if need_revalidate:
        try:
            _validate(cfg)
        except ValueError as e:
            print(f"参数覆盖无效：{e}", file=sys.stderr)
            return 2

    try:
        task = _resolve_task(args)
    except KeyboardInterrupt:
        # 交互式询问任务时按 Ctrl+C：与运行期中断同一约定（130），
        # 不能被 _resolve_task 吞成「未提供任务」（退出码 2 + 误导性报错）
        print()
        ui.warn("已中断")
        return 130
    except SystemExit as e:
        # _resolve_task 已把具体原因打印到 stderr，这里只把退出码转成
        # main() 的返回值：main() 的契约是返回 int（入口 sys.exit(main())），
        # 让 SystemExit 直接外泄会绕过调用方对返回码的处理
        return e.code if isinstance(e.code, int) else 2
    if not task:
        ui.err("未提供任务")
        return 2

    # TUI 模式（默认）：两个区块面板 + agent 输出日志 + 底部输入框。
    # textual 从 stdin 读取键盘输入：stdin 被重定向/关闭时（如
    # `xuen 任务 < /dev/null` 或先前的管道读到 EOF），TUI 收不到 q 与
    # 输入框内容，循环结束后会一直挂到进程被杀；此时按 README 的约定
    # 降级为纯终端输出。stdin/stdout 可能为 None（无控制台解释器），
    # getattr 兜底避免启动即 AttributeError。
    tty = all(getattr(stream, "isatty", lambda: False)()
              for stream in (sys.stdin, sys.stdout))
    if cfg.tui and not args.no_tui and tty:
        try:
            run_tui = _load_tui()
        except ImportError:
            ui.warn("未安装 textual，回退到纯终端输出（pip install textual 可启用 TUI）")
        else:
            try:
                return run_tui(cfg, task, regen_words=args.regen_words)
            except KeyboardInterrupt:
                print()
                ui.warn("已中断")
                return 130
            except Exception as e:
                # textual 在应用启动阶段失败时（如终端能力不足）后台线程的
                # 异常兜底尚未接管；在这里统一降级为友好错误与退出码 1
                ui.err(f"TUI 启动失败：{e}")
                return 1

    from .runner import run  # 延迟导入，加快 --help

    try:
        run(cfg, task, regen_words=args.regen_words)
    except SystemExit as e:
        # SystemExit(None)（如某个库直接 sys.exit()）是正常退出，必须判在
        # isinstance 之前：None 不是 int，否则会被误当日志消息打印出
        # "None" 并返回 2；TUI 路径（tui._run_loop）采用同一约定
        if e.code is None:
            return 0
        # run() 预检失败（如缺少 agent 命令）会以字符串消息抛 SystemExit；
        # 保持与 main() 其他配置错误一致退出码 2，避免与「全部轮次失败」
        # 的退出码 1 混淆
        if not isinstance(e.code, int):
            print(e.code, file=sys.stderr)
            return 2
        return e.code
    except KeyboardInterrupt:
        print()
        ui.warn("已中断")
        return 130
    return 0
