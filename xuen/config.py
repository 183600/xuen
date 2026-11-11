"""配置加载与校验。

xuen 只通过外部 agent（如 opencode）工作，不再内置直连 LLM 的模式，
因此配置项也大幅简化：核心就是 agent.command（外部 agent 命令模板）。
"""
from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATHS = ("config.yaml", "config.yml", "xuen.yaml")


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
class AgentConfig:
    command: str = ""
    timeout: float = 1800.0


@dataclass
class RoundsConfig:
    """轮次守卫（xuen/rounds.py）：每轮快照、候选/最佳分离、自动验证与评分。

    verify 取值：
      auto  有可运行的测试套件就跑测试（pytest → make → npm → go 级联），
            没有则用 fallback 指定的评分者（user / ai）
      tests 只跑测试；没有套件/跑不起来时候选挂起等待用户评分
      user  只用用户评分（rounds/verdicts.txt，异步补分）
      ai    只用 AI 评分（复用外部 agent 当评审员打分）
      off   不验证：快照照存，最新即最佳（仅退化为"防丢失"模式）
    """
    enabled: bool = True
    dir: str = "rounds"
    verify: str = "auto"
    fallback: str = "ai"
    adopt_score: float = 7.0
    verify_timeout: float = 600.0
    repo: str = ""
    judge_command: str = ""
    judge_timeout: float = 600.0


@dataclass
class PromptConfig:
    max_state_chars: int = 60000


@dataclass
class Config:
    extra_notes: str = ""
    words: WordsConfig = field(default_factory=WordsConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    rounds: RoundsConfig = field(default_factory=RoundsConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    workspace: str = "./workspace"
    tui: bool = True
    color: bool = True


def find_config_path(explicit: Optional[str] = None) -> str:
    if explicit is not None:
        if not explicit:
            raise FileNotFoundError(explicit)
        if not os.path.exists(explicit):
            raise FileNotFoundError(explicit)
        return explicit
    for p in DEFAULT_CONFIG_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("当前目录下未找到 config.yaml（可用 -c 指定路径）")


PROMPT_FILE_LEN = 12
PROMPT_LEN = 7
_WORD_CHAR = re.compile(r'[A-Za-z0-9_]')


def _parse_iterations(value: Any) -> Optional[int]:
    if value is None:
        return 5
    if isinstance(value, str):
        if value.strip().lower() in ("inf", ".inf", "+.inf", "infinite", "-1", "∞"):
            return None
        value = value.strip()
    if isinstance(value, float) and math.isinf(value) and value > 0:
        return None
    if isinstance(value, bool):
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到布尔值: {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到: {value!r}") from None
    if n < 0:
        raise ValueError(f"loop.iterations 必须是正整数或 inf(-1)")
    if n == 0:
        raise ValueError(f"loop.iterations 必须在 1 或更多")
    if n > sys.maxsize:
        raise ValueError(f"loop.iterations 值超出平台 range 上限")
    return None if n == -1 else n


def _parse_int(value: Any, key: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数，收到布尔值: {value!r}")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{key} 必须是整数，收到: {value!r}")
        if not math.isfinite(value):
            raise ValueError(f"{key} 值超出范围")
        return int(value)
    if isinstance(value, int):
        try:
            if not math.isfinite(value):
                raise ValueError(f"{key} 值超出范围")
        except OverflowError:
            raise ValueError(f"{key} 值超出范围")
        return value
    if isinstance(value, str):
        try:
            v = int(value)
            try:
                if not math.isfinite(v):
                    raise ValueError(f"{key} 值超出范围")
            except OverflowError:
                raise ValueError(f"{key} 值超出范围")
            return v
        except ValueError:
            raise ValueError(f"{key} 必须是整数")
    raise ValueError(f"{key} 必须是整数")


def _parse_float(value: Any, key: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数值，收到布尔值: {value!r}")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{key} 值超出范围")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            if not math.isfinite(value):
                raise ValueError(f"{key} 值超出范围")
            return float(value)
        except OverflowError:
            raise ValueError(f"{key} 值超出范围")
    if isinstance(value, str):
        try:
            v = float(value)
            if not math.isfinite(v):
                raise ValueError(f"{key} 值超出范围")
            return v
        except ValueError:
            raise ValueError(f"{key} 必须是数值")
    raise ValueError(f"{key} 必须是数值")


def _parse_bool(val: Any, key: str) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "yes", "on", "1"):
            return True
        if v in ("false", "no", "off", "0"):
            return False
        raise ValueError(f"{key} 必须是布尔值")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if val == 0:
            return False
        if val == 1:
            return True
    raise ValueError(f"{key} 必须是布尔值")


def _config_value(raw: Optional[dict], key: str, default: Any = None) -> Any:
    if raw is None:
        return default
    v = raw.get(key, default)
    if v is None:
        return default
    return v


def _parse_str(value: Any, key: str, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return str(value)
    raise ValueError(f"{key} 必须是字符串")


def _parse_verify_value(value: Any, key: str) -> str:
    if value is None:
        return "auto"
    if isinstance(value, bool):
        if not value:
            return "off"
        raise ValueError(f"{key} 必须是字符串（auto/tests/user/ai/off），收到布尔值")
    return str(value).strip().lower()


def _mapping_section(raw: Optional[dict], name: str) -> dict:
    if raw is None:
        return {}
    v = raw.get(name, {})
    if isinstance(v, dict):
        return v
    if v is None:
        return {}
    raise ValueError(f"{name} 必须是映射（字典），收到: {v!r}")


def load_config(path: Optional[str] = None) -> Config:
    real_path = find_config_path(path)
    with open(real_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    elif not isinstance(raw, dict):
        raise ValueError(f"配置文件顶层必须是映射（字典），收到: {raw!r}")

    cfg = Config()
    cfg.extra_notes = str(raw.get("extra_notes") or "")

    words_raw = _mapping_section(raw, "words")
    cfg.words = WordsConfig(
        count=_parse_int(_config_value(words_raw, "count", 1000), "words.count"),
        batch=_parse_int(_config_value(words_raw, "batch", 100), "words.batch"),
        pick=_parse_int(_config_value(words_raw, "pick", 2), "words.pick"),
        reuse=_parse_bool(_config_value(words_raw, "reuse", True), "words.reuse"),
    )
    if cfg.words.pick < 0:
        raise ValueError("words.pick 必须 >= 0")

    loop_raw = _mapping_section(raw, "loop")
    cfg.loop = LoopConfig(iterations=_parse_iterations(loop_raw.get("iterations")))

    agent_raw = _mapping_section(raw, "agent")
    cfg.agent = AgentConfig(
        command=_parse_str(agent_raw.get("command"), "agent.command"),
        timeout=_parse_float(
            _config_value(agent_raw, "timeout", 1800.0),
            "agent.timeout",
        ),
    )

    rounds_raw = _mapping_section(raw, "rounds")
    cfg.rounds = RoundsConfig(
        enabled=_parse_bool(_config_value(rounds_raw, "enabled", True), "rounds.enabled"),
        dir=_parse_str(_config_value(rounds_raw, "dir"), "rounds.dir", "rounds"),
        verify=_parse_verify_value(_config_value(rounds_raw, "verify", "auto"), "rounds.verify"),
        fallback=_parse_verify_value(_config_value(rounds_raw, "fallback", "ai"), "rounds.fallback"),
        adopt_score=_parse_float(_config_value(rounds_raw, "adopt_score", 7.0), "rounds.adopt_score"),
        verify_timeout=_parse_float(_config_value(rounds_raw, "verify_timeout", 600.0), "rounds.verify_timeout"),
        repo=_parse_str(_config_value(rounds_raw, "repo"), "rounds.repo"),
        judge_command=_parse_str(_config_value(rounds_raw, "judge_command"), "rounds.judge_command"),
        judge_timeout=_parse_float(_config_value(rounds_raw, "judge_timeout", 600.0), "rounds.judge_timeout"),
    )

    prompt_raw = _mapping_section(raw, "prompt")
    cfg.prompt = PromptConfig(
        max_state_chars=_parse_int(_config_value(prompt_raw, "max_state_chars", 60000), "prompt.max_state_chars"),
    )

    workspace_val = raw.get("workspace")
    if workspace_val is not None:
        ws = _parse_str(workspace_val, "workspace")
        ws = ws.strip()
        if ws:
            cfg.workspace = ws

    tui_val = raw.get("tui")
    if tui_val is not None:
        cfg.tui = _parse_bool(tui_val, "tui")

    color_val = raw.get("color")
    if color_val is not None:
        cfg.color = _parse_bool(color_val, "color")

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if not isinstance(cfg.extra_notes, str):
        raise ValueError("extra_notes 必须是字符串")
    if not isinstance(cfg.workspace, str):
        raise ValueError("workspace 必须是字符串")
    if not isinstance(cfg.agent.command, str):
        raise ValueError("agent.command 必须是字符串")
    if not isinstance(cfg.rounds.dir, str):
        raise ValueError("rounds.dir 必须是字符串")
    if not isinstance(cfg.rounds.repo, str):
        raise ValueError("rounds.repo 必须是字符串")
    if not isinstance(cfg.rounds.judge_command, str):
        raise ValueError("rounds.judge_command 必须是字符串")
    
    if not isinstance(cfg.words.reuse, bool):
        raise ValueError("words.reuse 必须是布尔值")
    if not isinstance(cfg.rounds.enabled, bool):
        raise ValueError("rounds.enabled 必须是布尔值")
    if not isinstance(cfg.tui, bool):
        raise ValueError("tui 必须是布尔值")
    if not isinstance(cfg.color, bool):
        raise ValueError("color 必须是布尔值")
    
    if not isinstance(cfg.words.count, int) or isinstance(cfg.words.count, bool):
        raise ValueError("words.count 必须是整数")
    if not isinstance(cfg.words.batch, int) or isinstance(cfg.words.batch, bool):
        raise ValueError("words.batch 必须是整数")
    if not isinstance(cfg.words.pick, int) or isinstance(cfg.words.pick, bool):
        raise ValueError("words.pick 必须是整数")
    if cfg.words.pick < 0:
        raise ValueError("words.pick（n）必须 >= 0")
    if cfg.words.count < 1 or cfg.words.batch < 1:
        raise ValueError("words.count / words.batch 必须为正整数")
    if cfg.loop.iterations is not None:
        if not isinstance(cfg.loop.iterations, int) or isinstance(cfg.loop.iterations, bool):
            raise ValueError("loop.iterations 必须是整数")
        if cfg.loop.iterations < 1:
            raise ValueError("loop.iterations 必须为正整数或 inf(-1)")
        if cfg.loop.iterations > sys.maxsize:
            raise ValueError("loop.iterations 值超出平台 range 上限")
    try:
        is_finite = math.isfinite(cfg.agent.timeout)
    except OverflowError:
        is_finite = False
    if not is_finite or cfg.agent.timeout <= 0:
        raise ValueError("agent.timeout 必须为有限的正数（秒）")

    from .rounds import FALLBACK_SCORERS, VERIFY_MODES
    if cfg.rounds.verify not in VERIFY_MODES:
        raise ValueError(f"rounds.verify 必须是 {'/'.join(VERIFY_MODES)}，"
                         f"收到: {cfg.rounds.verify!r}")
    if cfg.rounds.fallback not in FALLBACK_SCORERS:
        raise ValueError(f"rounds.fallback 必须是 {'/'.join(FALLBACK_SCORERS)}，"
                         f"收到: {cfg.rounds.fallback!r}")
    if not isinstance(cfg.rounds.adopt_score, (int, float)) or isinstance(cfg.rounds.adopt_score, bool):
        raise ValueError("rounds.adopt_score 必须是数值")
    if not (0.0 <= cfg.rounds.adopt_score <= 10.0):
        raise ValueError(f"rounds.adopt_score 必须在 0-10 之间，"
                         f"收到: {cfg.rounds.adopt_score!r}")
    if cfg.rounds.enabled and not cfg.rounds.dir.strip():
        raise ValueError("rounds.dir 不能为空")
    for name in ("verify_timeout", "judge_timeout"):
        v = getattr(cfg.rounds, name)
        try:
            is_finite = math.isfinite(v)
        except OverflowError:
            is_finite = False
        if not is_finite or v <= 0:
            raise ValueError(f"rounds.{name} 必须为有限的正数（秒）")

    jcmd = cfg.rounds.judge_command.strip()
    if jcmd:
        from .agents import command_receives_prompt
        if not command_receives_prompt(jcmd):
            raise ValueError(
                "rounds.judge_command 必须包含会被实际替换的 $prompt 或 "
                "$prompt_file 占位符（被转义的 \\$prompt 不会被替换）")
        if os.name == "nt" and re.search(r"(?<![A-Za-z0-9_$])\$prompt(?![A-Za-z0-9_])", jcmd):
            raise ValueError(
                "Windows 的 rounds.judge_command 不能使用 $prompt；请改用 "
                "$prompt_file（提示词会被写入文件，避免 cmd 转义/换行问题）"
            )

    cmd = cfg.agent.command.strip()
    if cmd:
        from .agents import command_receives_prompt
        if not command_receives_prompt(cmd):
            raise ValueError(
                "agent.command 必须包含会被实际替换的 $prompt 或 "
                "$prompt_file 占位符（被转义的 \\$prompt 不会被替换），"
                "否则提示词无法传给外部 agent"
            )

    if os.name == "nt" and re.search(r"(?<![A-Za-z0-9_$])\$prompt(?![A-Za-z0-9_])", cmd):
        raise ValueError(
            "Windows 的 agent.command 不能使用 $prompt；请改用 "
            "$prompt_file（提示词会被写入文件，避免 cmd 转义/换行问题）"
        )

    if (os.name == "nt"
            and re.search(r"(?<![A-Za-z0-9_])\$prompt_file(?![A-Za-z0-9_])", cmd)
            and re.search(r"[%!&^<>|]", cfg.workspace)):
        raise ValueError(
            "Windows 下工作区路径含 cmd 元字符（% ! & ^ < > |），"
            "$prompt_file 无法安全传递给外部 agent；请更换工作区路径"
        )


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