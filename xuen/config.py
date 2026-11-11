from typing import Optional, Any
from dataclasses import dataclass, field
import yaml
import os
import re
import math
import sys

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
        if not _is_finite_int(value):
            raise ValueError(f"{key} 值超出范围")
        return value
    try:
        v = int(value)
        if not _is_finite_int(v):
            raise ValueError(f"{key} 值超出范围")
        return v
    except (ValueError, TypeError):
        raise ValueError(f"{key} 必须是整数")

def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
    except OverflowError:
        raise ValueError(f"{key} 值超出范围")
    except (ValueError, TypeError):
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

def _is_finite_int(value):
    """超大整数转 float 会抛 OverflowError：统一按「超出范围」处理。"""
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def _config_value(raw, key, default=None):
    if raw is None:
        return default
    return raw.get(key, default)

def _mapping_section(raw, name):
    if raw is None:
        return {}
    value = raw.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是映射（键值对）")
    return value

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
    """轮数：正整数；inf（及等价写法）表示无限循环。"""
    if value is None:
        return 5
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _INFINITE_ITERATIONS:
            return None
    elif isinstance(value, float) and math.isinf(value):
        return None
    iterations = _parse_int(value, key)
    if iterations < 0:
        raise ValueError(f"{key} 必须是正整数")
    if iterations == 0:
        raise ValueError(f"{key} 必须在 1 或更多")
    return iterations

def _parse_loop_config(raw, section):
    if raw is None:
        raw = {}
    iterations = _parse_iterations(_config_value(raw, "iterations"))
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

def _parse_optional_str(value, key, default=""):
    """可选字符串字段：缺省（或写成空）用默认值，其余必须是字符串。"""
    if value is None:
        return default
    return _parse_str(value, key)

def _parse_switch(value, key, default=False):
    """顶层开关：接受布尔、0/1 与 on/off 字符串。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 0:
            return False
        if value == 1:
            return True
        raise ValueError(f"{key} 必须是布尔值")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("on", "true", "yes"):
            return True
        if text in ("off", "false", "no"):
            return False
    raise ValueError(f"{key} 必须是布尔值")

def _parse_workspace(value, key="workspace"):
    """工作区路径：字符串；写成数字时按字面目录名处理。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是字符串")
    if isinstance(value, int):
        return str(value)
    raise ValueError(f"{key} 必须是字符串")

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

_INFINITE_ITERATIONS = ("inf", ".inf", "+.inf", "infinite", "∞")
_VALID_VERIFY = ("auto", "tests", "user", "ai", "off")
_VALID_FALLBACK = ("user", "ai")
DEFAULT_CONFIG_NAMES = ("config.yaml", "config.yml", "xuen.yaml")

def _find_default_config() -> str:
    """未指定 -c 时按 config.yaml → config.yml → xuen.yaml 顺序查找。"""
    for name in DEFAULT_CONFIG_NAMES:
        if os.path.isfile(name):
            return name
    raise FileNotFoundError(
        "当前目录没有 " + " / ".join(DEFAULT_CONFIG_NAMES))

def load_config(path: Optional[str] = None) -> Config:
    """读取配置文件并校验；path 为 None 时按默认顺序查找当前目录的配置。"""
    if path is None:
        path = _find_default_config()
    if not path:
        raise FileNotFoundError("配置文件路径为空")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("配置文件顶层必须是键值映射")
    cfg = Config(
        extra_notes=_parse_optional_str(raw.get("extra_notes"), "extra_notes"),
        words=_parse_words_config(_mapping_section(raw, "words"), "words"),
        loop=_parse_loop_config(_mapping_section(raw, "loop"), "loop"),
        agent=_parse_agent_config(_mapping_section(raw, "agent"), "agent"),
        rounds=_parse_rounds_config(_mapping_section(raw, "rounds"), "rounds"),
        prompt=_parse_prompt_config(_mapping_section(raw, "prompt"), "prompt"),
        workspace=_parse_workspace(raw.get("workspace")),
        tui=_parse_switch(raw.get("tui"), "tui", Config.tui),
        color=_parse_switch(raw.get("color"), "color", Config.color),
    )
    _validate(cfg)
    return cfg

def _check_str(value, key):
    if not isinstance(value, str):
        raise ValueError(f"{key} 必须是字符串")
    return value

def _check_bool(value, key):
    if not isinstance(value, bool):
        raise ValueError(f"{key} 必须是布尔值")
    return value

def _check_int(value, key, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} 必须是整数")
    if minimum is not None and value < minimum:
        raise ValueError(f"{key} 必须 >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{key} 必须 <= {maximum}")
    return value

def _check_number(value, key, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数值")
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError):
        raise ValueError(f"{key} 值超出范围")
    if not math.isfinite(number):
        raise ValueError(f"{key} 值超出范围")
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} 必须 >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{key} 必须 <= {maximum}")
    return number

def _check_positive_number(value, key):
    number = _check_number(value, key)
    if number <= 0:
        raise ValueError(f"{key} 必须是有限正数")
    return number

def _validate_command(field: str, command: str, workspace: str) -> None:
    """命令模板校验：必须真的把提示词送到外部 agent。"""
    if not command:
        return
    # 复用渲染器的实际行为判断占位符是否会被兑现：被转义、落在注释/
    # heredoc 里或被 $$ 吃掉的写法都不会替换提示词，此时必须拒绝配置，
    # 而不是运行期静默丢弃提示词。
    from .agents import command_receives_prompt

    if not command_receives_prompt(command):
        raise ValueError(f"{field} 必须包含会被实际替换的提示词占位符"
                         "（$prompt / $prompt_file）")
    if os.name == "nt":
        _validate_windows_command(field, command, workspace)

def _validate(cfg: Config) -> None:
    """校验配置；命令行覆盖之后同样要重新校验（覆盖值不能绕过约束）。"""
    _check_str(cfg.extra_notes, "extra_notes")
    _check_str(cfg.workspace, "workspace")
    _check_str(cfg.agent.command, "agent.command")
    _check_str(cfg.rounds.dir, "rounds.dir")
    _check_str(cfg.rounds.repo, "rounds.repo")
    _check_str(cfg.rounds.judge_command, "rounds.judge_command")

    _check_bool(cfg.words.reuse, "words.reuse")
    _check_bool(cfg.rounds.enabled, "rounds.enabled")
    _check_bool(cfg.tui, "tui")
    _check_bool(cfg.color, "color")

    _check_int(cfg.words.count, "words.count", minimum=1)
    _check_int(cfg.words.batch, "words.batch", minimum=1)
    _check_int(cfg.words.pick, "words.pick", minimum=0)
    _check_int(cfg.prompt.max_state_chars, "prompt.max_state_chars", minimum=0)
    if cfg.loop.iterations is not None:
        _check_int(cfg.loop.iterations, "loop.iterations", minimum=1)
        # 超出平台 range 上限的轮数必须提前拒绝：否则 runner 的 range()
        # 会抛 OverflowError。
        if cfg.loop.iterations > sys.maxsize:
            raise ValueError("loop.iterations 超出范围（无法用 range 表示）")

    _check_positive_number(cfg.agent.timeout, "agent.timeout")
    _check_positive_number(cfg.rounds.verify_timeout, "rounds.verify_timeout")
    _check_positive_number(cfg.rounds.judge_timeout, "rounds.judge_timeout")
    _check_number(cfg.rounds.adopt_score, "rounds.adopt_score",
                  minimum=0, maximum=10)

    if cfg.rounds.verify not in _VALID_VERIFY:
        raise ValueError(f"rounds.verify 必须是 {_VALID_VERIFY} 之一")
    if cfg.rounds.fallback not in _VALID_FALLBACK:
        raise ValueError(f"rounds.fallback 必须是 {_VALID_FALLBACK} 之一")

    _validate_command("agent.command", cfg.agent.command, cfg.workspace)
    _validate_command("rounds.judge_command", cfg.rounds.judge_command,
                      cfg.workspace)
