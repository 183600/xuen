from typing import Optional, Any
from dataclasses import dataclass, field
import yaml
import os
import re
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
        if not math.isfinite(value):
            raise ValueError(f"{key} 值超出范围")
        return value
    try:
        v = int(value)
        if not math.isfinite(v):
            raise ValueError(f"{key} 值超出范围")
        return v
    except (ValueError, TypeError):
        raise ValueError(f"{key} 必须是整数")


def _parse_float(value, key):
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值")
    try:
        v = float(value)
        if not math.isfinite(v):
            raise ValueError(f"{key} 值超出范围")
        return v
    except (ValueError, TypeError):
        raise ValueError(f"{key} 必须是数值")


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
    verify = _parse_str(_config_value(raw, "verify", "auto"), "rounds.verify")
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


def _validate(cfg: Config) -> None:
    if cfg is None:
        raise ValueError("Config 不能为 None")
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
    if os.name == "nt":
        if not _has_valid_expansion(command):
            raise ValueError("agent.command 必须包含会被实际替换的 $prompt 或 $prompt_file")
        _validate_windows_command("agent.command", command, cfg.workspace)
    rounds = cfg.rounds
    if rounds is not None:
        if not isinstance(rounds, RoundsConfig):
            raise ValueError("rounds 必须是 RoundsConfig 实例")
        if rounds.judge_command:
            if os.name == "nt":
                if not _has_valid_expansion(rounds.judge_command):
                    raise ValueError("rounds.judge_command 必须包含会被实际替换的 $prompt 或 $prompt_file")
                _validate_windows_command("rounds.judge_command", rounds.judge_command, cfg.workspace)
    words = cfg.words
    if words is None:
        raise ValueError("words 必须配置")
    if not isinstance(words, WordsConfig):
        raise ValueError("words 必须是 WordsConfig 实例")
    if words.count is None or not isinstance(words.count, int):
        raise ValueError("words.count 必须是整数")
    if words.batch is None or not isinstance(words.batch, int):
        raise ValueError("words.batch 必须是整数")
    if words.pick is None or not isinstance(words.pick, int):
        raise ValueError("words.pick 必须是整数")
    if words.reuse is None or not isinstance(words.reuse, bool):
        raise ValueError("words.reuse 必须是布尔值")
    loop = cfg.loop
    if loop is not None:
        if not isinstance(loop, LoopConfig):
            raise ValueError("loop 必须是 LoopConfig 实例")
        if loop.iterations is not None:
            if not isinstance(loop.iterations, int):
                raise ValueError("loop.iterations 必须是整数")
            if isinstance(loop.iterations, bool):
                raise ValueError("loop.iterations 必须是整数")
    prompt = cfg.prompt
    if prompt is not None:
        if not isinstance(prompt, PromptConfig):
            raise ValueError("prompt 必须是 PromptConfig 实例")
        if prompt.max_state_chars is None:
            raise ValueError("prompt.max_state_chars 不能为 None")


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
    cfg.words = _parse_words_config(_mapping_section(raw, "words"), cfg.words)
    cfg.loop = _parse_loop_config(_mapping_section(raw, "loop"), cfg.loop)
    agent_section = _mapping_section(raw, "agent")
    if not agent_section:
        raise ValueError("agent 配置必须是一个映射（字典）")
    cfg.agent = _parse_agent_config(agent_section, cfg.agent)
    if "rounds" in raw:
        rounds_section = raw.get("rounds")
        if rounds_section is not None and isinstance(rounds_section, dict):
            cfg.rounds = _parse_rounds_config(rounds_section, cfg.rounds)
    cfg.prompt = _parse_prompt_config(_mapping_section(raw, "prompt"), cfg.prompt)

    workspace = raw.get("workspace")
    if workspace is not None:
        workspace = _parse_str(workspace, "workspace")
        if workspace.strip():
            cfg.workspace = workspace

    tui = raw.get("tui")
    cfg.tui = cfg.tui if tui is None else _parse_bool(tui, "tui")
    color = raw.get("color")
    cfg.color = cfg.color if color is None else _parse_bool(color, "color")

    _validate(cfg)

    return cfg