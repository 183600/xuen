"""配置加载与校验。

xuen 只通过外部 agent（如 opencode）工作，不再内置直连 LLM 的模式，
因此配置项也大幅简化：核心就是 agent.command（外部 agent 命令模板）。
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATHS = ("config.yaml", "config.yml", "xuen.yaml")


@dataclass
class WordsConfig:
    count: int = 1000   # 领域词目标数量
    batch: int = 100    # 每次请求外部 agent 生成的数量
    pick: int = 2       # 每轮随机灵感词数量 n（>=0；0 = 不抽词）
    reuse: bool = True  # words.txt 已存在则复用


@dataclass
class LoopConfig:
    iterations: Optional[int] = 5   # None 表示无限循环


@dataclass
class AgentConfig:
    command: str = ""        # 外部 agent 命令模板，如: opencode run "$prompt"
    timeout: float = 1800.0


@dataclass
class Config:
    extra_notes: str = ""
    words: WordsConfig = field(default_factory=WordsConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    workspace: str = "./workspace"
    tui: bool = True        # 默认启用 TUI（--no-tui 可关闭）
    color: bool = True


def find_config_path(explicit: Optional[str] = None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(explicit)
        return explicit
    for p in DEFAULT_CONFIG_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("当前目录下未找到 config.yaml（可用 -c 指定路径）")


def _parse_iterations(value: Any) -> Optional[int]:
    if value is None:
        return 5
    if isinstance(value, str):
        if value.strip().lower() in ("inf", ".inf", "+.inf", "infinite", "-1", "∞"):
            return None
        value = value.strip()
    # YAML 会把 .inf 解析成 float('inf')，int() 会抛 OverflowError
    if isinstance(value, float) and math.isinf(value):
        return None
    n = int(value)
    return None if n == -1 else n


def load_config(path: Optional[str] = None) -> Config:
    real_path = find_config_path(path)
    with open(real_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config()
    cfg.extra_notes = str(raw.get("extra_notes") or "")

    words = raw.get("words") or {}
    cfg.words = WordsConfig(
        count=int(words.get("count", cfg.words.count)),
        batch=int(words.get("batch", cfg.words.batch)),
        pick=int(words.get("pick", cfg.words.pick)),
        reuse=bool(words.get("reuse", cfg.words.reuse)),
    )

    loop = raw.get("loop") or {}
    cfg.loop = LoopConfig(iterations=_parse_iterations(loop.get("iterations", 5)))

    agent = raw.get("agent") or {}
    cfg.agent = AgentConfig(
        command=str(agent.get("command", "") or ""),
        timeout=float(agent.get("timeout", cfg.agent.timeout)),
    )

    # workspace 显式写成 null/空 时不能变成字面目录 "None"
    workspace = raw.get("workspace")
    if workspace is not None and str(workspace).strip():
        cfg.workspace = str(workspace)
    cfg.tui = bool(raw.get("tui", cfg.tui))
    cfg.color = bool(raw.get("color", cfg.color))

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.words.pick < 0:
        raise ValueError("words.pick（n）必须 >= 0")
    if cfg.words.count < 1 or cfg.words.batch < 1:
        raise ValueError("words.count / words.batch 必须为正整数")
    if cfg.loop.iterations is not None and cfg.loop.iterations < 1:
        raise ValueError("loop.iterations 必须为正整数或 inf(-1)")
    if cfg.agent.timeout <= 0:
        raise ValueError("agent.timeout 必须为正数（秒）")
    cmd = cfg.agent.command
    # 模板缺少占位符时提示词会被静默丢弃：agent 收不到任何输入，循环空转
    if cmd.strip() and not re.search(r"\$prompt(?:_file)?(?![A-Za-z0-9_])", cmd):
        raise ValueError(
            "agent.command 必须包含 $prompt 或 $prompt_file 占位符，"
            "否则提示词无法传给外部 agent"
        )
