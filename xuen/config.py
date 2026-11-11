from typing import Optional, Any
from dataclasses import dataclass, field
import yaml
import os
import re
import sys
import math

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
    count: int = 1000
    batch: int = 100
    pick: int = 2
    reuse: bool = True

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
        return value
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{key} 必须是整数")

def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError):
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
    raise ValueError(f"{key} 必须是布尔值")

def _config_value(raw, key, default=None):
    if raw is None:
        return default
    return raw.get(key, default)

def _mapping_section(raw, name):
    if raw is None:
        return {}
    section = raw.get(name)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"{name} 配置段必须是键值映射")
    return section

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

def _parse_iterations(value, key="loop.iterations"):
    """轮数解析：正整数或 inf（解析成 None 表示无限循环）。

    YAML 里 `iterations: inf` 会解析成字符串 "inf"、`.inf` 解析成 float
    无穷大，两者都必须归一成 None，不能静默当成默认轮数。
    """
    if value is None:
        return 5
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是正整数或 inf")
    if isinstance(value, float):
        if math.isinf(value):
            return None
        if not math.isnan(value) and value.is_integer():
            value = int(value)
        else:
            raise ValueError(f"{key} 必须是正整数或 inf")
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("inf", ".inf", "+.inf", "-.inf", "+inf", "infinite", "∞", "-1"):
            return None
        try:
            value = int(s)
        except ValueError:
            raise ValueError(f"{key} 必须是正整数或 inf")
    if not isinstance(value, int):
        raise ValueError(f"{key} 必须是正整数或 inf")
    if value < 1:
        raise ValueError(f"{key} 必须在 1 或更多")
    return value

def _parse_loop_config(raw, section):
    if raw is None:
        raw = {}
    iterations = _parse_iterations(_config_value(raw, "iterations"), "loop.iterations")
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
    
    # Special handling for verify field: convert boolean False to string "off"
    verify_value = _config_value(raw, "verify", "auto")
    if verify_value is False and "verify" in raw:
        # Handle case where unquoted "off" is parsed as boolean False
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

def _parse_scalar_str(value, key, default=""):
    """标量 → 字符串；list/dict/bytes/set 等结构化值必须拒绝，不能 str() 成 repr。"""
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    raise ValueError(f"{key} 必须是字符串")

def _parse_bool_text(val, key):
    """布尔解析：额外接受带引号的 on/off/true/false 写法。"""
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("on", "true", "yes", "1"):
            return True
        if s in ("off", "false", "no", "0"):
            return False
        raise ValueError(f"{key} 必须是布尔值")
    return _parse_bool(val, key)

def find_config_path(path: Optional[str] = None) -> str:
    if path is None:
        return "./config.yaml"
    else:
        return os.path.abspath(path)

PROMPT_FILE_LEN = 12
PROMPT_LEN = 7
_WORD_CHAR = re.compile(r'[A-Za-z0-9_]')

def _has_valid_expansion(command: str) -> bool:
    """Check if command has $prompt or $prompt_file that will actually expand.
    
    On Windows ($$ is escape, $$$ has expansion), on POSIX ($$ is literal).
    This matches the behavior of _windows_placeholder_starts from agents.py.
    """
    if not command:
        return False

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

def _check_number(value, key):
    """数值类型与有限性检查。

    拒绝 bool 与超出 float/平台范围的巨大整数：math.isfinite 对超大 int
    会抛 OverflowError（而非返回 False），必须先做量级判断转成带字段名的
    ValueError，不能让 OverflowError 外泄。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数值")
    if isinstance(value, int) and abs(value) > sys.maxsize:
        raise ValueError(f"{key} 值超出范围")
    if not math.isfinite(value):
        raise ValueError(f"{key} 值超出范围")

def _validate(cfg: Config) -> None:
    """对（可能经程序化构造或 CLI 覆盖的）Config 做最终校验。

    load_config 解析成功后调用一次；CLI 覆盖 workspace/iterations 等
    字段后也会再次调用，确保覆盖值无法绕过任何配置期约束。
    """
    # ---- 字符串字段：None/list/dict 必须带字段名报错 ----
    for key, value in (
        ("extra_notes", cfg.extra_notes),
        ("workspace", cfg.workspace),
        ("agent.command", cfg.agent.command),
        ("rounds.dir", cfg.rounds.dir),
        ("rounds.repo", cfg.rounds.repo),
        ("rounds.judge_command", cfg.rounds.judge_command),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{key} 必须是字符串")

    # ---- 布尔字段：字符串/数字不能静默取真值 ----
    for key, value in (
        ("words.reuse", cfg.words.reuse),
        ("rounds.enabled", cfg.rounds.enabled),
        ("tui", cfg.tui),
        ("color", cfg.color),
    ):
        if not isinstance(value, bool):
            raise ValueError(f"{key} 必须是布尔值")

    # ---- 整数字段：bool 是 int 的子类，必须显式排除 ----
    for key, value in (
        ("words.count", cfg.words.count),
        ("words.batch", cfg.words.batch),
        ("words.pick", cfg.words.pick),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} 必须是整数")
    if cfg.words.pick < 0:
        raise ValueError("words.pick 必须 >= 0")

    iterations = cfg.loop.iterations
    if iterations is not None:
        if isinstance(iterations, bool) or not isinstance(iterations, int):
            raise ValueError("loop.iterations 必须是正整数或 inf")
        if iterations < 1:
            raise ValueError("loop.iterations 必须在 1 或更多")
        if iterations > sys.maxsize:
            raise ValueError("loop.iterations 超出 range 可表示范围")

    # ---- 数值字段：有限正数 / 0-10 评分 ----
    _check_number(cfg.rounds.adopt_score, "rounds.adopt_score")
    if not (0.0 <= cfg.rounds.adopt_score <= 10.0):
        raise ValueError("rounds.adopt_score 必须在 0-10 之间")
    _check_number(cfg.agent.timeout, "agent.timeout")
    if cfg.agent.timeout <= 0:
        raise ValueError("agent.timeout 必须是有限正数")
    _check_number(cfg.rounds.verify_timeout, "rounds.verify_timeout")
    if cfg.rounds.verify_timeout <= 0:
        raise ValueError("rounds.verify_timeout 必须是有限正数")
    _check_number(cfg.rounds.judge_timeout, "rounds.judge_timeout")
    if cfg.rounds.judge_timeout <= 0:
        raise ValueError("rounds.judge_timeout 必须是有限正数")

    # ---- 枚举字段 ----
    valid_verify = ("auto", "tests", "user", "ai", "off")
    if cfg.rounds.verify not in valid_verify:
        raise ValueError(f"rounds.verify 必须是 {valid_verify} 之一")
    valid_fallback = ("user", "ai")
    if cfg.rounds.fallback not in valid_fallback:
        raise ValueError(f"rounds.fallback 必须是 {valid_fallback} 之一")

    # ---- 命令模板：占位符必须会被实际替换（$$ 转义的不算）----
    if cfg.agent.command and not _has_valid_expansion(cfg.agent.command):
        raise ValueError("agent.command 必须包含会被实际替换的 $prompt 或 $prompt_file")
    if cfg.rounds.judge_command and not _has_valid_expansion(cfg.rounds.judge_command):
        raise ValueError("rounds.judge_command 必须包含会被实际替换的 $prompt 或 $prompt_file")

    # ---- Windows：cmd.exe 无法安全执行内嵌多行提示词，路径不能含元字符 ----
    if os.name == "nt":
        _validate_windows_command("agent.command", cfg.agent.command, cfg.workspace)
        if cfg.rounds.judge_command:
            _validate_windows_command(
                "rounds.judge_command", cfg.rounds.judge_command, cfg.workspace)

def load_config(path: Optional[str] = None) -> Config:
    """读取 YAML 配置并完成校验。

    path 为 None 时回退到 ./config.yaml；显式传入的空字符串是无效路径，
    必须抛 FileNotFoundError，不能静默当成默认路径。
    """
    if path is None:
        path = find_config_path()
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("配置文件顶层必须是键值映射")

    cfg = Config()
    cfg.extra_notes = _parse_scalar_str(
        _config_value(raw, "extra_notes", ""), "extra_notes", "")
    cfg.words = _parse_words_config(_mapping_section(raw, "words"), raw)
    cfg.loop = _parse_loop_config(_mapping_section(raw, "loop"), raw)
    cfg.agent = _parse_agent_config(_mapping_section(raw, "agent"), raw)
    cfg.rounds = _parse_rounds_config(_mapping_section(raw, "rounds"), raw)
    cfg.prompt = _parse_prompt_config(_mapping_section(raw, "prompt"), raw)
    cfg.tui = _parse_bool_text(_config_value(raw, "tui", cfg.tui), "tui")
    cfg.color = _parse_bool_text(_config_value(raw, "color", cfg.color), "color")
    cfg.workspace = _parse_scalar_str(
        _config_value(raw, "workspace", cfg.workspace), "workspace", "")

    _validate(cfg)
    return cfg
