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
        # Python int 是任意精度：超出 float 范围的巨大整数在这里合法，
        # 超出平台 range 上限的轮数由 _validate 统一拒绝（不能让
        # math.isfinite 的 float 换算抛 OverflowError 外泄）
        return value
    try:
        v = int(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{key} 必须是整数")
    return v

def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError):
        # OverflowError：YAML 可解析出超出 float 范围的巨大整数，
        # 必须转成带字段名的 ValueError，不能外泄 OverflowError
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
def _parse_switch(value, key):
    """解析 tui/color 这类界面开关：布尔、0/1 数字与常见的字符串写法
    （YAML 1.1 会把未加引号的 on/off/yes/no 解析成布尔，但带引号的
    "off" 是字符串，语义上仍应当作开关值接受）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 0:
            return False
        if value == 1:
            return True
        raise ValueError(f"{key} 必须是布尔值")
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "on", "true", "yes"):
            return True
        if s in ("0", "off", "false", "no"):
            return False
    raise ValueError(f"{key} 必须是布尔值")

def _parse_workspace(value):
    """workspace 接受标量（字符串/数字，数字按 YAML 源文本转 str），
    拒绝 list/dict/set/bytes 等结构化值，不能 str() 成 Python repr。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        raise ValueError("workspace 必须是字符串")
    if isinstance(value, (int, float)):
        return str(value)
    raise ValueError("workspace 必须是字符串")

def _section_mapping(raw, name):
    """取出顶层配置段并确保它是映射：`rounds: on`（YAML 解析成布尔）
    这类标量段必须报错，不能让解析器对非映射调 .get 崩溃或静默取默认。"""
    section = _mapping_section(raw, name)
    if not isinstance(section, dict):
        raise ValueError(f"{name} 配置段必须是键值映射")
    return section

def _default_config_path() -> str:
    """未用 -c/--config 指定时，依次查找当前目录的
    config.yaml → config.yml → xuen.yaml；都不存在则 FileNotFoundError。"""
    for name in ("config.yaml", "config.yml", "xuen.yaml"):
        if os.path.isfile(name):
            return name
    raise FileNotFoundError(
        "找不到配置文件：当前目录没有 config.yaml / config.yml / xuen.yaml")

def load_config(path: Optional[str] = None) -> Config:
    """读取 YAML 配置并构造 Config，最后经 _validate 整体校验。

    path 为 None 时按 config.yaml → config.yml → xuen.yaml 顺序查找；
    显式传入的路径（包括空字符串）不做任何回退，文件不存在时抛
    FileNotFoundError。解析或校验失败一律抛 ValueError。
    """
    if path is None:
        path = _default_config_path()
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("配置文件根必须是键值映射")

    extra_notes = raw.get("extra_notes")
    if extra_notes is None:
        extra_notes = ""

    words_raw = _section_mapping(raw, "words")
    loop_raw = _section_mapping(raw, "loop")
    agent_raw = _section_mapping(raw, "agent")
    rounds_raw = _section_mapping(raw, "rounds")
    prompt_raw = _section_mapping(raw, "prompt")

    cfg = Config(
        extra_notes=_parse_str(extra_notes, "extra_notes"),
        words=_parse_words_config(words_raw, words_raw),
        loop=_parse_loop_config(loop_raw, loop_raw),
        agent=_parse_agent_config(agent_raw, agent_raw),
        rounds=_parse_rounds_config(rounds_raw, rounds_raw),
        prompt=_parse_prompt_config(prompt_raw, prompt_raw),
        workspace=_parse_workspace(_config_value(raw, "workspace", "")),
        tui=_parse_switch(_config_value(raw, "tui", False), "tui"),
        color=_parse_switch(_config_value(raw, "color", False), "color"),
    )
    _validate(cfg)
    return cfg

def _validate(cfg: Config) -> None:
    """对 Config 做整体校验（load_config 末尾与 CLI 覆盖之后共用）。

    程序化构造的 Config 可能带任意类型的字段值：必须先按字段名做类型
    与范围检查，再做占位符与平台相关的命令检查；agent.command 允许为
    空字符串（空命令由 runner 的预检负责报错）。
    """
    # ---- 字符串字段：None/list 等必须带字段名报 ValueError，不能让
    # .strip()/正则/Path() 先抛 AttributeError/TypeError ----
    for field_name, value in (
        ("extra_notes", cfg.extra_notes),
        ("workspace", cfg.workspace),
        ("agent.command", cfg.agent.command),
        ("rounds.dir", cfg.rounds.dir),
        ("rounds.repo", cfg.rounds.repo),
        ("rounds.judge_command", cfg.rounds.judge_command),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{field_name} 必须是字符串")

    # ---- 布尔字段：字符串 "false" / 数字 0 不能被 if 静默当真值 ----
    for field_name, value in (
        ("words.reuse", cfg.words.reuse),
        ("rounds.enabled", cfg.rounds.enabled),
        ("tui", cfg.tui),
        ("color", cfg.color),
    ):
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} 必须是布尔值")

    # ---- 整数字段：bool 是 int 子类，必须显式排除 ----
    for field_name, value in (
        ("words.count", cfg.words.count),
        ("words.batch", cfg.words.batch),
        ("words.pick", cfg.words.pick),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field_name} 必须是整数")
    if cfg.words.pick < 0:
        raise ValueError("words.pick 必须 >= 0")

    iterations = cfg.loop.iterations
    if iterations is not None:
        if isinstance(iterations, bool) or not isinstance(iterations, int):
            raise ValueError("loop.iterations 必须是整数")
        if iterations < 1:
            raise ValueError("loop.iterations 必须是正整数")
        # runner 用 range(1, iterations + 1) 表示轮数上限：超出平台
        # ssize_t 的整数语义上合法但 range 无法表示，必须在配置阶段拒绝
        if iterations > sys.maxsize - 1:
            raise ValueError("loop.iterations 超出平台 range 可表示范围")

    if isinstance(cfg.prompt.max_state_chars, bool) \
            or not isinstance(cfg.prompt.max_state_chars, int):
        raise ValueError("prompt.max_state_chars 必须是整数")
    if cfg.prompt.max_state_chars < 0:
        raise ValueError("prompt.max_state_chars 不能为负数")

    # ---- 数值字段：有限正数；超出 float 范围的巨大整数不能从
    # math.isfinite 泄漏 OverflowError，必须转成带字段名的 ValueError ----
    for field_name, value in (
        ("agent.timeout", cfg.agent.timeout),
        ("rounds.verify_timeout", cfg.rounds.verify_timeout),
        ("rounds.judge_timeout", cfg.rounds.judge_timeout),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} 必须是数值")
        try:
            finite = math.isfinite(value)
        except (OverflowError, ValueError, TypeError):
            finite = False
        if not finite:
            raise ValueError(f"{field_name} 值超出范围")
        if value <= 0:
            raise ValueError(f"{field_name} 必须是有限正数")

    adopt_score = cfg.rounds.adopt_score
    if isinstance(adopt_score, bool) \
            or not isinstance(adopt_score, (int, float)):
        raise ValueError("rounds.adopt_score 必须是数值")
    try:
        finite = math.isfinite(adopt_score)
    except (OverflowError, ValueError, TypeError):
        finite = False
    if not finite:
        raise ValueError("rounds.adopt_score 值超出范围")
    if not (0.0 <= adopt_score <= 10.0):
        raise ValueError("rounds.adopt_score 必须在 0-10 之间")

    # ---- 枚举字段 ----
    if cfg.rounds.verify not in ("auto", "tests", "user", "ai", "off"):
        raise ValueError("rounds.verify 必须是 auto/tests/user/ai/off 之一")
    if cfg.rounds.fallback not in ("user", "ai"):
        raise ValueError("rounds.fallback 必须是 user/ai 之一")

    # ---- 命令模板必须包含会被实际替换的占位符（与平台无关）：
    # $$prompt_file 这类不会兑现的写法必须拒绝，而不是静默接受 ----
    if cfg.agent.command and not _has_valid_expansion(cfg.agent.command):
        raise ValueError("agent.command 必须包含会被实际替换的 "
                         "$prompt / $prompt_file 占位符")
    if cfg.rounds.judge_command \
            and not _has_valid_expansion(cfg.rounds.judge_command):
        raise ValueError("rounds.judge_command 必须包含会被实际替换的 "
                         "$prompt / $prompt_file 占位符")

    # ---- Windows：cmd.exe 无法安全接收内嵌多行的 $prompt；只有工作区
    # 路径不含 cmd 元字符时才允许把 $prompt_file 的解析路径裸插进命令 ----
    if os.name == "nt":
        _validate_windows_command("agent.command", cfg.agent.command,
                                  cfg.workspace)
        if cfg.rounds.judge_command:
            _validate_windows_command("rounds.judge_command",
                                      cfg.rounds.judge_command,
                                      cfg.workspace)
