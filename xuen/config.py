from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

_WORD_CHAR = re.compile(r'[A-Za-z0-9_]')


@dataclass
class AgentConfig:
    command: str = ""
    timeout: float = 1800.0


@dataclass
class WordsConfig:
    count: int = 1000
    batch: int = 100
    pick: int = 2
    reuse: bool = True


@dataclass
class LoopConfig:
    iterations: Optional[int] = 5


@dataclass
class PromptConfig:
    max_state_chars: int = 60000


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


@dataclass
class Config:
    extra_notes: str = ""
    words: WordsConfig = field(default_factory=WordsConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    rounds: RoundsConfig = field(default_factory=RoundsConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    workspace: str = ""
    tui: bool = False
    color: bool = False


def _parse_str(value, key=None):
    if not isinstance(value, str):
        raise ValueError(f"{key or '字段'} 必须是字符串")
    return value


def _parse_int(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数")
    if isinstance(value, int):
        try:
            if not math.isfinite(value):
                raise ValueError(f"{key} 值超出范围")
        except (OverflowError, ValueError):
            raise ValueError(f"{key} 值超出范围")
        return value
    try:
        v = int(value)
    except (OverflowError, ValueError, TypeError):
        raise ValueError(f"{key} 必须是整数")
    try:
        if not math.isfinite(v):
            raise ValueError(f"{key} 值超出范围")
    except (OverflowError, ValueError):
        raise ValueError(f"{key} 值超出范围")
    return v


def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
    except (OverflowError, ValueError, TypeError):
        raise ValueError(f"{key} 必须是数值")
    if not math.isfinite(v):
        raise ValueError(f"{key} 值超出范围")
    return v


def _parse_bool(val, key):
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if val == 0:
            return False
        if val == 1:
            return True
    if isinstance(val, str):
        if val.lower() in ("off", "false", "no"):
            return False
        if val.lower() in ("on", "true", "yes"):
            return True
    raise ValueError(f"{key} 必须是布尔值")


def _config_value(raw, key, default=None):
    if raw is None:
        return default
    if not isinstance(raw, dict):
        return default
    return raw.get(key, default)


def _mapping_section(raw, name):
    if raw is None:
        return {}
    return raw.get(name, {})


def _parse_words_config(raw, section):
    if raw is None:
        raw = {}
    count = _parse_int(_config_value(raw, "count", 1000), "words.count")
    batch = _parse_int(_config_value(raw, "batch", 100), "words.batch")
    pick = _parse_int(_config_value(raw, "pick", 2), "words.pick")
    if pick < 0:
        raise ValueError("words.pick 必须 >= 0")
    reuse_val = _config_value(raw, "reuse", True)
    if isinstance(reuse_val, bool):
        reuse = reuse_val
    elif isinstance(reuse_val, (int, float)):
        if reuse_val in (0,):
            reuse = False
        elif reuse_val in (1,):
            reuse = True
        else:
            raise ValueError("words.reuse")
    else:
        raise ValueError("words.reuse")
    return WordsConfig(count=count, batch=batch, pick=pick, reuse=reuse)


def _parse_loop_config(raw, section):
    if raw is None:
        raw = {}
    iterations_raw = _config_value(raw, "iterations")
    if iterations_raw is None:
        iterations = 5
    else:
        iterations = _parse_int(iterations_raw, "loop.iterations")
        if iterations < 0:
            raise ValueError("loop.iterations 必须是正整数")
        if iterations == 0:
            raise ValueError("loop.iterations 必须在 1 或更多")
    return LoopConfig(iterations=iterations)


def _parse_agent_config(raw, section):
    if raw is None:
        raw = {}
    command = _parse_str(_config_value(raw, "command", ""), "agent.command")
    timeout = _parse_float(_config_value(raw, "timeout", 1800.0), "agent.timeout")
    return AgentConfig(command=command, timeout=timeout)


def _parse_rounds_config(raw, section):
    if raw is None:
        raw = {}
    enabled = _parse_bool(_config_value(raw, "enabled", True), "rounds.enabled")
    dir_val = _parse_str(_config_value(raw, "dir", "rounds"), "rounds.dir")

    verify_value = _config_value(raw, "verify", "auto")
    if verify_value is False and "verify" in raw:
        verify = "off"
    else:
        verify = _parse_str(verify_value, "rounds.verify")

    valid_verify = ("auto", "tests", "user", "ai", "off")
    if verify not in valid_verify:
        raise ValueError(f"rounds.verify 必须是 {valid_verify} 之一")
    fallback = _parse_str(_config_value(raw, "fallback", "ai"), "rounds.fallback")
    valid_fallback = ("user", "ai")
    if fallback not in valid_fallback:
        raise ValueError(f"rounds.fallback 必须是 {valid_fallback} 之一")
    adopt_score = _parse_float(_config_value(raw, "adopt_score", 7.0), "rounds.adopt_score")
    if not (0.0 <= adopt_score <= 10.0):
        raise ValueError("rounds.adopt_score 必须在 0-10 之间")
    verify_timeout = _parse_float(_config_value(raw, "verify_timeout", 30.0), "rounds.verify_timeout")
    repo = _parse_str(_config_value(raw, "repo", ""), "rounds.repo")
    judge_command = _parse_str(_config_value(raw, "judge_command", ""), "rounds.judge_command")
    judge_timeout = _parse_float(_config_value(raw, "judge_timeout", 120.0), "rounds.judge_timeout")
    return RoundsConfig(
        enabled=enabled, dir=dir_val, verify=verify, fallback=fallback,
        adopt_score=adopt_score, verify_timeout=verify_timeout,
        repo=repo, judge_command=judge_command, judge_timeout=judge_timeout
    )


def _parse_prompt_config(raw, section):
    if raw is None:
        raw = {}
    max_state_chars = _parse_int(_config_value(raw, "max_state_chars", 60000), "prompt.max_state_chars")
    return PromptConfig(max_state_chars=max_state_chars)


def load_config(path: str) -> Config:
    """从 YAML 配置文件加载 Config 实例。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise FileNotFoundError(path)
    cfg = _config_dict_to_obj(raw)
    _validate(cfg)
    return cfg


def _config_dict_to_obj(raw: Any) -> Config:
    if raw is None:
        raw = {}

    for section in ("words", "loop", "agent", "rounds", "prompt"):
        val = raw.get(section)
        if val is not None and not isinstance(val, dict):
            raise ValueError(f"{section}")

    words = _parse_words_config(_mapping_section(raw, "words"), "words")
    loop = _parse_loop_config(_mapping_section(raw, "loop"), "loop")
    agent = _parse_agent_config(_mapping_section(raw, "agent"), "agent")
    rounds = _parse_rounds_config(_mapping_section(raw, "rounds"), "rounds")
    prompt = _parse_prompt_config(_mapping_section(raw, "prompt"), "prompt")

    return Config(
        extra_notes=_config_value(raw, "extra_notes", ""),
        words=words,
        loop=loop,
        agent=agent,
        rounds=rounds,
        prompt=prompt,
        workspace=_config_value(raw, "workspace", ""),
        tui=_parse_bool(_config_value(raw, "tui", False), "tui"),
        color=_parse_bool(_config_value(raw, "color", False), "color"),
    )


def _validate(cfg: Config) -> None:
    """Validate all Config fields: types and value ranges.

    Any type or range error raises ValueError with field name for locating config issues.
    """

    for name in ("count", "batch", "pick"):
        val = getattr(cfg.words, name)
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValueError(f"words.{name}")

    if not isinstance(cfg.words.reuse, bool):
        raise ValueError("words.reuse")

    val = cfg.loop.iterations
    if val is None or isinstance(val, bool):
        pass
    elif not isinstance(val, int):
        raise ValueError(f"loop.iterations")

    if not isinstance(cfg.rounds.enabled, bool):
        raise ValueError("rounds.enabled")

    if not isinstance(cfg.tui, bool):
        raise ValueError("tui")
    if not isinstance(cfg.color, bool):
        raise ValueError("color")

    if not isinstance(cfg.rounds.verify, str):
        raise ValueError("rounds.verify")
    if not isinstance(cfg.rounds.fallback, str):
        raise ValueError("rounds.fallback")

    if not isinstance(cfg.rounds.adopt_score, (int, float)) or isinstance(cfg.rounds.adopt_score, bool):
        raise ValueError("rounds.adopt_score")
    if not (0.0 <= cfg.rounds.adopt_score <= 10.0):
        raise ValueError("rounds.adopt_score")

    for name in ("verify_timeout", "judge_timeout"):
        val = getattr(cfg.rounds, name)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ValueError(f"rounds.{name}")
        if not math.isfinite(val) or val <= 0:
            raise ValueError(f"rounds.{name}")

    if cfg.rounds.judge_command and ("$prompt" not in cfg.rounds.judge_command and "$prompt_file" not in cfg.rounds.judge_command):
        raise ValueError("judge_command")

    if not isinstance(cfg.agent.command, str):
        raise ValueError("agent.command")

    if not isinstance(cfg.agent.timeout, (int, float)) or isinstance(cfg.agent.timeout, bool):
        raise ValueError("agent.timeout")
    if not math.isfinite(cfg.agent.timeout):
        raise ValueError("agent.timeout")

    if not isinstance(cfg.prompt.max_state_chars, int) or isinstance(cfg.prompt.max_state_chars, bool):
        raise ValueError("prompt.max_state_chars")

    if cfg.extra_notes is None:
        raise ValueError("extra_notes")
    if cfg.workspace is None:
        raise ValueError("workspace")
    if isinstance(cfg.workspace, (list, dict)):
        raise ValueError("workspace")
    if isinstance(cfg.workspace, (int, float)):
        cfg.workspace = str(cfg.workspace)
    if not isinstance(cfg.workspace, str):
        raise ValueError("workspace")

    if os.name == "nt":
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    _validate_windows_command(
                        "agent.command", cfg.agent.command, cfg.workspace
                    )
                except ValueError:
                    raise ValueError("agent.command")
                try:
                    _validate_windows_command(
                        "rounds.judge_command", cfg.rounds.judge_command, cfg.workspace
                    )
                except ValueError:
                    raise ValueError("judge_command")
                try:
                    _validate_windows_command(
                        "agent.command", cfg.agent.command, cfg.workspace
                    )
                except ValueError as e:
                    if "必须包含会被实际替换" in str(e):
                        raise ValueError("必须包含会被实际替换")
        except (NotImplementedError, AttributeError, ImportError):
            pass
    if cfg.rounds.dir is None:
        raise ValueError("rounds.dir")
    if cfg.rounds.repo is None:
        raise ValueError("rounds.repo")
    if cfg.rounds.judge_command is None:
        raise ValueError("rounds.judge_command")


def find_config_path(path: Optional[str] = None) -> str:
    if path is None:
        return "./config.yaml"
    else:
        return os.path.abspath(path)


def _has_valid_expansion(command: str) -> bool:
    """Check if command has $prompt or $prompt_file that will actually expand.

    On Windows ($$ is escape, $$$ has expansion), on POSIX ($$ is literal).
    This matches the behavior of _windows_placeholder_starts from agents.py.
    """
    if not command:
        return False

    PROMPT_FILE_LEN = 12
    PROMPT_LEN = 7

    has_expansion = False
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if c == '^':
            i += 2
            continue
        if c == '"':
            i += 1
            continue

        if i + PROMPT_FILE_LEN <= n and command[i:i+PROMPT_FILE_LEN] == '$prompt_file':
            end = i + PROMPT_FILE_LEN
            if end < n and _WORD_CHAR.match(command[end]):
                i += 1
                continue
            k = i - 1
            dollars = 0
            while k >= 0 and command[k] == '$':
                dollars += 1
                k -= 1
            if dollars % 2 == 0:
                has_expansion = True
            i = end
            continue

        if i + PROMPT_LEN <= n and command[i:i+PROMPT_LEN] == '$prompt':
            if i + PROMPT_LEN < n and command[i+PROMPT_LEN] == '_':
                i += 1
                continue
            end = i + PROMPT_LEN
            if end < n and command[end].isalnum():
                i += 1
                continue
            k = i - 1
            dollars = 0
            while k >= 0 and command[k] == '$':
                dollars += 1
                k -= 1
            if dollars % 2 == 0:
                has_expansion = True
            i = end
            continue

        i += 1

    return has_expansion


def _validate_windows_command(field: str, command: str, workspace: str) -> None:
    if not command:
        raise ValueError(f"{field} 不能为空")

    has_expanding_prompt = False
    has_expanding_prompt_file = False

    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if c == '^':
            i += 2
            continue
        if c == '"':
            i += 1
            continue

        if i + PROMPT_FILE_LEN <= n and command[i:i+PROMPT_FILE_LEN] == '$prompt_file':
            end = i + PROMPT_FILE_LEN
            if end < n and _WORD_CHAR.match(command[end]):
                i += 1
                continue
            k = i - 1
            dollars = 0
            while k >= 0 and command[k] == '$':
                dollars += 1
                k -= 1
            if dollars % 2 == 0:
                has_expanding_prompt_file = True
            i = end
            continue

        if i + PROMPT_LEN <= n and command[i:i+PROMPT_LEN] == '$prompt':
            if i + PROMPT_LEN < n and command[i+PROMPT_LEN] == '_':
                i += 1
                continue
            end = i + PROMPT_LEN
            if end < n and command[end].isalnum():
                i += 1
                continue
            k = i - 1
            dollars = 0
            while k >= 0 and command[k] == '$':
                dollars += 1
                k -= 1
            if dollars % 2 == 0:
                has_expanding_prompt = True
            i = end
            continue

        i += 1

    if has_expanding_prompt:
        raise ValueError(f"{field} 包含 $prompt，Windows 不安全")

    if has_expanding_prompt_file:
        resolved = workspace
        try:
            resolved = os.path.realpath(workspace)
        except (OSError, RuntimeError):
            pass
        if re.search(r'[&%^|]', resolved):
            raise ValueError(f"{field} 包含 $prompt_file，工作区路径必须不含 cmd 元字符")