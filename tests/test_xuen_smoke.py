"""xuen 包冒烟测试：导入、CLI、示例配置。"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_import_package():
    from xuen import agents, cli, config, procs, rounds, runner, sink, state, words
    assert hasattr(rounds, "RoundGuard")
    assert hasattr(rounds, "VERIFY_MODES")
    assert hasattr(config, "RoundsConfig")


def test_version_matches_pyproject():
    """包内 __version__ 必须与 pyproject 元数据同步（bump 时曾漏改其一）。"""
    import xuen
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert m is not None, "pyproject.toml 缺少 version 字段"
    assert xuen.__version__ == m.group(1)


def test_cli_help():
    from xuen.cli import build_parser
    p = build_parser()
    args = p.parse_args(["--help"][:0])
    # --help 会 SystemExit(0)，这里只验证参数可解析
    args = p.parse_args(["任务", "--no-rounds", "--rounds-verify", "auto",
                         "--rounds-fallback", "ai", "--rounds-score", "7"])
    assert args.no_rounds and args.rounds_verify == "auto"
    assert args.rounds_fallback == "ai" and args.rounds_score == 7.0


def test_example_config_loads():
    from xuen.config import load_config
    cfg = load_config(str(ROOT / "config.example.yaml"))
    assert cfg.agent.command.strip()
    assert cfg.rounds.enabled is True


def test_main_module_help_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "xuen", "--help"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    assert "--rounds-verify" in (proc.stdout + proc.stderr)
