from typing import Optional, Any
from dataclasses import dataclass
import yaml
import os

# Config class definition
@dataclass
class Config:
    extra_notes: str = ""
    words: Any = None
    loop: Any = None
    agent: Any = None
    rounds: Any = None  # will be a RoundsConfig instance
    prompt: Any = None
    workspace: str = ""
    tui: bool = False
    color: bool = False

# Rounds config dataclass
@dataclass
class RoundsConfig:
    enabled: bool = True
    dir: str = "rounds"
    verify: str = "auto"
    fallback: str = "ai"
    adopt_score: float = 7.0
    verify_timeout: float = 30.0
    repo: str = ""
    judge_command: str = ""
    judge_timeout: float = 120.0

# Helper functions
def _parse_str(value, key=None):
    return value

def _config_value(raw, key, default=None):
    return raw.get(key, default)

def _mapping_section(raw, name):
    return raw.get(name, {})

def _parse_words_config(cfg, section):
    return cfg

def _parse_loop_config(cfg, section):
    return cfg

def _parse_agent_config(cfg, section):
    return cfg

def _parse_rounds_config(cfg, section):
    # Parse raw dict into RoundsConfig instance
    raw = section
    return RoundsConfig(
        enabled=section.get("enabled", True),
        dir=section.get("dir", "rounds"),
        verify=section.get("verify", "auto"),
        fallback=section.get("fallback", "ai"),
        adopt_score=section.get("adopt_score", 7.0),
        verify_timeout=section.get("verify_timeout", 30.0),
        repo=section.get("repo", ""),
        judge_command=section.get("judge_command", ""),
        judge_timeout=section.get("judge_timeout", 120.0),
    )

def _parse_prompt_config(cfg, section):
    return cfg

def _parse_bool(val, key):
    return bool(val)

def find_config_path(path: Optional[str] = None) -> str:
    if path is None:
        # default config file location
        return "./config.yaml"
    else:
        # resolve to absolute path
        return os.path.abspath(path)

def _validate(cfg):
    # Placeholder validation; ensure cfg is not None
    if cfg is None:
        raise ValueError("Config cannot be None")
    # Additional validation could be added here

def load_config(path: Optional[str] = None) -> Config:
    real_path = find_config_path(path)
    with open(real_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    elif not isinstance(raw, dict):
        raise ValueError(f"配置文件顶层必须是映射（字典），收到: {raw!r}")

    cfg = Config()
    cfg.extra_notes = _parse_str(_config_value(raw, "extra_notes", ""),
                                 "extra_notes")
    cfg.words = _parse_words_config(_mapping_section(raw, "words"), cfg.words)
    cfg.loop = _parse_loop_config(_mapping_section(raw, "loop"), cfg.loop)
    if "agent" in raw and raw["agent"] is not None and isinstance(raw["agent"], dict):
        cfg.agent = _parse_agent_config(_mapping_section(raw, "agent"), cfg.agent)
    else:
        raise ValueError("agent 配置必须是一个映射（字典）")
    if "rounds" in raw:
        if raw["rounds"] is not None and isinstance(raw["rounds"], dict):
            cfg.rounds = _parse_rounds_config(_mapping_section(raw, "rounds"), cfg.rounds)
    cfg.prompt = _parse_prompt_config(
        _mapping_section(raw, "prompt"), cfg.prompt)

    # workspace 显式写成 null/空 时不能变成字面目录 "None"
    workspace = raw.get("workspace")
    if workspace is not None:
        workspace = _parse_str(workspace, "workspace")
        if workspace.strip():
            cfg.workspace = workspace

    # tui: / tui: null 时 raw.get 返回 None 而非默认值；与 workspace 同理不能把 null 当显式值
    tui = raw.get("tui")
    cfg.tui = cfg.tui if tui is None else _parse_bool(tui, "tui")
    color = raw.get("color")
    cfg.color = cfg.color if color is None else _parse_bool(color, "color")

    # Perform full validation
    _validate(cfg)

    return cfg