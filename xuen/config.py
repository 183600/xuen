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


def _parse_path_str(value, key):
    """路径类字符串字段：标量按字面量转成字符串，容器（list/dict/set/bytes）拒绝。

    `workspace: 2024` 这类纯数字写法按路径名处理（YAML 会把它解析成整数），
    但列表/字典等结构化写法必须报错——直接 str() 会把 Python repr 当成路径。
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是字符串")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{key} 值超出范围")
    return str(value)


def _parse_int(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数")
    if isinstance(value, int):
        v = value
    else:
        try:
            v = int(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"{key} 必须是整数")
    # 超出平台 int/range 上限的值（如 YAML 里的 400 位整数）会让 runner
    # 的 range() 抛 OverflowError，必须在配置阶段带字段名拒绝
    if abs(v) > sys.maxsize:
        raise ValueError(f"{key} 值超出范围")
    return v


def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
    except OverflowError:
        # 超大整数转 float 溢出：报字段名而不是泄漏 OverflowError
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
    if isinstance(val, str):
        # 带引号的常见写法：YAML 只有未加引号的 off/on/yes/no 才是布尔，
        # 加引号后是字符串，按常见语义解析
        text = val.strip().lower()
        if text in ("true", "yes", "on", "1"):
            return True
        if text in ("false", "no", "off", "0"):
            return False
    raise ValueError(f"{key} 必须是布尔值")


def _config_value(raw, key, default=None):
    if raw is None:
        return default
    return raw.get(key, default)


def _mapping_section(raw, name):
    if raw is None:
        return {}
    return raw.get(name, {})


def _section_mapping(raw, name):
    """取顶层某个配置段：必须是映射（字典），否则带段名报错。"""
    value = _mapping_section(raw, name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} 配置必须是一个映射（字典）")
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
        reuse = _parse_bool(reuse_val, "words.reuse")
    return WordsConfig(count=count, batch=batch, pick=pick, reuse=reuse)


# 无限轮数的写法：与 CLI 的 --iterations inf 保持一致
_INFINITE_ITERATIONS = ("inf", ".inf", "+.inf", "infinite", "∞")


def _parse_iterations(value):
    """轮数：正整数；inf（或其别名）表示无限循环（None）。"""
    if value is None:
        return 5
    if isinstance(value, str) and value.strip().lower() in _INFINITE_ITERATIONS:
        return None
    if isinstance(value, float) and math.isinf(value):
        return None
    iterations = _parse_int(value, "loop.iterations")
    if iterations < 0:
        raise ValueError("loop.iterations 必须是正整数")
    if iterations == 0:
        raise ValueError("loop.iterations 必须在 1 或更多")
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
    _check_timeout(timeout, "agent.timeout")
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
    _check_timeout(verify_timeout, "rounds.verify_timeout")
    repo = _parse_path_str(_config_value(raw, "repo", ""), "rounds.repo")
    judge_command = _parse_str(_config_value(raw, "judge_command", ""), "rounds.judge_command")
    judge_timeout = _parse_float(_config_value(raw, "judge_timeout", 120.0), "rounds.judge_timeout")
    _check_timeout(judge_timeout, "rounds.judge_timeout")
    return RoundsConfig(
        enabled=enabled, dir=dir_val, verify=verify, fallback=fallback,
        adopt_score=adopt_score, verify_timeout=verify_timeout,
        repo=repo, judge_command=judge_command, judge_timeout=judge_timeout
    )


def _parse_prompt_config(raw, section):
    if raw is None:
        raw = {}
    max_state_chars = _parse_int(_config_value(raw, "max_state_chars", 60000), "prompt.max_state_chars")
    if max_state_chars < 0:
        raise ValueError("prompt.max_state_chars 必须 >= 0")
    return PromptConfig(max_state_chars=max_state_chars)


def find_config_path(path: Optional[str] = None) -> str:
    if path is None:
        return "./config.yaml"
    if not path.strip():
        # 显式传入空路径：不能静默回退到当前目录的 config.yaml
        return path
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


def _is_finite_number(value) -> bool:
    """数值是否是有限的（超大整数转 float 会溢出，按不可表示处理）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int):
        return abs(value) <= sys.maxsize
    return math.isfinite(value)


def _check_timeout(value, key) -> None:
    """超时必须是有限正数（README：单次调用超时须为有限正数）。"""
    if not _is_finite_number(value) or value <= 0:
        raise ValueError(f"{key} 必须是有限正数")


def _command_receives_prompt(command: str) -> bool:
    """命令模板是否真的会把提示词交给外部 agent。

    复用 agents 的实际渲染逻辑（dry_run 不落盘）：写在注释、heredoc 正文
    或被转义的 $prompt 不会被替换，不能只看模板里有没有 "$prompt" 子串。
    """
    from .agents import command_receives_prompt

    return command_receives_prompt(command)


def _validate(cfg: Config) -> None:
    if cfg is None:
        raise ValueError("Config 不能为 None")

    if not isinstance(cfg.extra_notes, str):
        raise ValueError("extra_notes 必须是字符串")
    if not isinstance(cfg.workspace, str):
        raise ValueError("workspace 必须是字符串")

    words = cfg.words
    if words is None:
        raise ValueError("words 必须配置")
    if not isinstance(words, WordsConfig):
        raise ValueError("words 必须是 WordsConfig 实例")
    for name in ("count", "batch", "pick"):
        value = getattr(words, name)
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"words.{name} 必须是整数")
    if words.pick < 0:
        raise ValueError("words.pick 必须 >= 0")
    if not isinstance(words.reuse, bool):
        raise ValueError("words.reuse 必须是布尔值")

    loop = cfg.loop
    if loop is not None:
        if not isinstance(loop, LoopConfig):
            raise ValueError("loop 必须是 LoopConfig 实例")
        if loop.iterations is not None:
            if isinstance(loop.iterations, bool) or not isinstance(loop.iterations, int):
                raise ValueError("loop.iterations 必须是整数")
            if loop.iterations < 1:
                raise ValueError("loop.iterations 必须在 1 或更多")
            if abs(loop.iterations) > sys.maxsize:
                raise ValueError("loop.iterations 值超出范围")

    rounds = cfg.rounds
    if rounds is not None:
        if not isinstance(rounds, RoundsConfig):
            raise ValueError("rounds 必须是 RoundsConfig 实例")
        if not isinstance(rounds.enabled, bool):
            raise ValueError("rounds.enabled 必须是布尔值")
        if not isinstance(rounds.dir, str):
            raise ValueError("rounds.dir 必须是字符串")
        valid_verify = ("auto", "tests", "user", "ai", "off")
        if not isinstance(rounds.verify, str) or rounds.verify not in valid_verify:
            raise ValueError(f"rounds.verify 必须是 {valid_verify} 之一")
        valid_fallback = ("user", "ai")
        if not isinstance(rounds.fallback, str) or rounds.fallback not in valid_fallback:
            raise ValueError(f"rounds.fallback 必须是 {valid_fallback} 之一")
        if isinstance(rounds.adopt_score, bool) or not isinstance(rounds.adopt_score, (int, float)):
            raise ValueError("rounds.adopt_score 必须是数值")
        if not (0.0 <= rounds.adopt_score <= 10.0):
            raise ValueError("rounds.adopt_score 必须在 0-10 之间")
        _check_timeout(rounds.verify_timeout, "rounds.verify_timeout")
        if not isinstance(rounds.repo, str):
            raise ValueError("rounds.repo 必须是字符串")
        if not isinstance(rounds.judge_command, str):
            raise ValueError("rounds.judge_command 必须是字符串")
        _check_timeout(rounds.judge_timeout, "rounds.judge_timeout")

    prompt = cfg.prompt
    if prompt is not None:
        if not isinstance(prompt, PromptConfig):
            raise ValueError("prompt 必须是 PromptConfig 实例")
        value = prompt.max_state_chars
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("prompt.max_state_chars 必须是整数")
        if value < 0:
            raise ValueError("prompt.max_state_chars 必须 >= 0")

    if not isinstance(cfg.tui, bool):
        raise ValueError("tui 必须是布尔值")
    if not isinstance(cfg.color, bool):
        raise ValueError("color 必须是布尔值")

    agent = cfg.agent
    if agent is None:
        raise ValueError("agent 必须配置")
    if not isinstance(agent, AgentConfig):
        raise ValueError("agent 必须是 AgentConfig 实例")
    command = agent.command
    if command is None:
        raise ValueError("agent.command 不能为 None")
    if not isinstance(command, str):
        raise ValueError("agent.command 必须是字符串")
    if not command.strip():
        raise ValueError("agent.command 不能为空")
    try:
        command.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("agent.command 包含无法用 UTF-8 编码的字符")
    _check_timeout(agent.timeout, "agent.timeout")

    if os.name == "nt":
        if not _has_valid_expansion(command):
            raise ValueError("agent.command 必须包含会被实际替换的 $prompt 或 $prompt_file")
        _validate_windows_command("agent.command", command, cfg.workspace)
        if rounds is not None and rounds.judge_command:
            if not _has_valid_expansion(rounds.judge_command):
                raise ValueError("rounds.judge_command 必须包含会被实际替换的 $prompt 或 $prompt_file")
            _validate_windows_command("rounds.judge_command", rounds.judge_command, cfg.workspace)
    else:
        if not _command_receives_prompt(command):
            raise ValueError("agent.command 必须包含会被实际替换的 $prompt 或 $prompt_file")
        if rounds is not None and rounds.judge_command:
            if not _command_receives_prompt(rounds.judge_command):
                raise ValueError("rounds.judge_command 必须包含会被实际替换的 $prompt 或 $prompt_file")


def load_config(path: Optional[str] = None) -> Config:
    real_path = find_config_path(path)
    with open(real_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    elif not isinstance(raw, dict):
        raise ValueError(f"配置文件顶层必须是映射（字典），收到: {raw!r}")

    cfg = Config()
    cfg.extra_notes = _parse_str(_config_value(raw, "extra_notes", ""), "extra_notes")
    cfg.words = _parse_words_config(_section_mapping(raw, "words"), cfg.words)
    cfg.loop = _parse_loop_config(_section_mapping(raw, "loop"), cfg.loop)
    agent_section = _section_mapping(raw, "agent")
    if not agent_section:
        raise ValueError("agent 配置必须是一个映射（字典）")
    cfg.agent = _parse_agent_config(agent_section, cfg.agent)
    rounds_section = _section_mapping(raw, "rounds")
    if rounds_section:
        cfg.rounds = _parse_rounds_config(rounds_section, cfg.rounds)
    cfg.prompt = _parse_prompt_config(_section_mapping(raw, "prompt"), cfg.prompt)

    workspace = raw.get("workspace")
    if workspace is not None:
        workspace = _parse_path_str(workspace, "workspace")
        if workspace.strip():
            cfg.workspace = workspace

    tui = raw.get("tui")
    cfg.tui = cfg.tui if tui is None else _parse_bool(tui, "tui")
    color = raw.get("color")
    cfg.color = cfg.color if color is None else _parse_bool(color, "color")

    _validate(cfg)

    return cfg
