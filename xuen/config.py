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
class RoundsConfig:
    """轮次守卫（xuen/rounds.py）：每轮快照、候选/最佳分离、自动验证与评分。

    verify 取值：
      auto  有可运行的测试套件就跑测试（pytest → make → npm → go 级联），
            没有则用 fallback 指定的评分者（user / ai）
      tests 只跑测试；没有套件/跑不起来时候选挂起等待用户评分
      user  只用用户评分（rounds/verdicts.txt，异步补分）
      ai    只用 AI 评分（复用外部 agent 当评审员打分）
      off   不验证：快照照存，最新即最佳（仅退化为“防丢失”模式）
    """
    enabled: bool = True
    dir: str = "rounds"          # 守卫目录（相对 workspace）
    verify: str = "auto"
    fallback: str = "ai"         # auto 模式下无测试可用时的兜底评分者：user / ai
    adopt_score: float = 7.0     # 评分达到该阈值才采纳候选为最佳（0-10）
    verify_timeout: float = 600.0   # 单次测试套件运行超时（秒）
    repo: str = ""               # 测试验证的目标目录；空 = 自动探测（工作区所在 git 根，否则工作区）
    judge_command: str = ""      # AI 评审命令模板；空 = 复用 agent.command
    judge_timeout: float = 600.0    # AI 评审单次调用超时（秒）


@dataclass
class Config:
    extra_notes: str = ""
    words: WordsConfig = field(default_factory=WordsConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    rounds: RoundsConfig = field(default_factory=RoundsConfig)
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
    # YAML 会把 .inf 解析成 float('inf')，int() 会抛 OverflowError；
    # 注意 -.inf 的 isinf 也为真，但负无穷不是合法的「无限循环」写法，放给后面按数值报错
    if isinstance(value, float) and math.isinf(value) and value > 0:
        return None
    # YAML 把 yes/no/true/false 解析成 bool（int 的子类），
    # int(True)==1 会把 iterations: yes 静默解释成 1 轮
    if isinstance(value, bool):
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到布尔值: {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"loop.iterations 必须是整数或 inf，收到: {value!r}") from None
    return None if n == -1 else n


def _parse_int(value: Any, name: str) -> int:
    """解析整数配置；与 _parse_iterations 同理拒绝 bool 与非整数 float：
    YAML 把 yes 解析成 True，int(True)==1 会把 words.pick: yes 静默解释成 1；
    count: 100.5 会被 int() 静默截断成 100。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是整数，收到布尔值: {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} 必须是整数，收到: {value!r}")
    return int(value)


def _parse_float(value: Any, name: str) -> float:
    """解析浮点配置；拒绝 bool（timeout: yes 会被静默当成 1.0 秒）。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是数值（秒），收到布尔值: {value!r}")
    return float(value)


def _config_value(source: dict, name: str, default: Any) -> Any:
    """读取字段；YAML 显式写成 `null` 时视为未设置并回落默认值。"""
    value = source.get(name)
    return default if value is None else value


def _parse_bool(value: Any, name: str) -> bool:
    """解析布尔配置；容忍带引号的字符串写法，如 tui: "false"。"""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "on", "1"):
            return True
        if v in ("false", "no", "off", "0"):
            return False
        raise ValueError(f"{name} 必须是布尔值（true/false），收到: {value!r}")
    return bool(value)


def _mapping_section(raw: Any, name: str) -> dict:
    """配置段落缺省（null/未写）时使用默认映射；标量则给出明确字段错误。"""
    value = raw.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是映射（字典），收到: {value!r}")
    return value


def _mode_str(value: Any) -> str:
    """枚举型配置取字符串。YAML 1.1 会把未加引号的 on/off/yes/no 解析成
    布尔：off/no=False 在语义上正对应 "off"（如 verify: off）；True 没有
    对应模式，保留 "on" 让后续校验给出明确报错，而不是经 `or 默认值`
    静默吞掉用户的显式选择（verify: off 曾因此悄悄变成 auto）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "off" if not value else "on"
    return str(value).strip().lower()


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

    words = _mapping_section(raw, "words")
    cfg.words = WordsConfig(
        count=_parse_int(_config_value(words, "count", cfg.words.count),
                         "words.count"),
        batch=_parse_int(_config_value(words, "batch", cfg.words.batch),
                         "words.batch"),
        pick=_parse_int(_config_value(words, "pick", cfg.words.pick),
                        "words.pick"),
        reuse=_parse_bool(_config_value(words, "reuse", cfg.words.reuse),
                          "words.reuse"),
    )

    loop = _mapping_section(raw, "loop")
    cfg.loop = LoopConfig(iterations=_parse_iterations(loop.get("iterations", 5)))

    agent = _mapping_section(raw, "agent")
    cfg.agent = AgentConfig(
        command=str(agent.get("command", "") or ""),
        timeout=_parse_float(
            _config_value(agent, "timeout", cfg.agent.timeout),
            "agent.timeout",
        ),
    )

    rounds = _mapping_section(raw, "rounds")
    verify = _mode_str(_config_value(rounds, "verify", cfg.rounds.verify)) \
        or cfg.rounds.verify
    fallback = _mode_str(_config_value(rounds, "fallback",
                                       cfg.rounds.fallback)) \
        or cfg.rounds.fallback
    cfg.rounds = RoundsConfig(
        enabled=_parse_bool(_config_value(rounds, "enabled", cfg.rounds.enabled),
                            "rounds.enabled"),
        dir=str(_config_value(rounds, "dir", cfg.rounds.dir) or "rounds"),
        verify=verify,
        fallback=fallback,
        adopt_score=_parse_float(
            _config_value(rounds, "adopt_score", cfg.rounds.adopt_score),
            "rounds.adopt_score"),
        verify_timeout=_parse_float(
            _config_value(rounds, "verify_timeout", cfg.rounds.verify_timeout),
            "rounds.verify_timeout"),
        repo=str(_config_value(rounds, "repo", cfg.rounds.repo) or ""),
        judge_command=str(_config_value(rounds, "judge_command",
                                        cfg.rounds.judge_command) or ""),
        judge_timeout=_parse_float(
            _config_value(rounds, "judge_timeout", cfg.rounds.judge_timeout),
            "rounds.judge_timeout"),
    )

    # workspace 显式写成 null/空 时不能变成字面目录 "None"
    workspace = raw.get("workspace")
    if workspace is not None and str(workspace).strip():
        cfg.workspace = str(workspace)
    # tui: / tui: null 时 raw.get 返回 None 而非默认值；与 workspace 同理不能把 null 当显式值
    tui = raw.get("tui")
    cfg.tui = cfg.tui if tui is None else _parse_bool(tui, "tui")
    color = raw.get("color")
    cfg.color = cfg.color if color is None else _parse_bool(color, "color")

    _validate(cfg)
    return cfg


def _validate_windows_command(name: str, template: str,
                              workspace: str) -> None:
    """校验命令模板在 Windows（cmd.exe）下能否安全接收提示词。

    agent.command 与 rounds.judge_command 都经 ShellAgent 交给 cmd.exe
    执行：$prompt 会把多行提示词直接嵌进命令行（换行把提示词后续内容
    拆成独立命令执行，% & ^ 等元字符还会被命令解释器展开），含元字符的
    工作区路径也会让 $prompt_file 的路径被 cmd 破坏。两条命令必须同口径
    校验——只查 agent.command 会把评审提示词里的候选内容送进 cmd 解析。
    """
    if os.name != "nt":
        return
    if re.search(r"(?<![A-Za-z0-9_])\$prompt(?![A-Za-z0-9_])", template):
        raise ValueError(
            f"Windows 的 {name} 不能使用 $prompt；请改用 $prompt_file"
            "（提示词会被写入文件，避免 cmd 转义/换行问题）"
        )
    if (re.search(r"(?<![A-Za-z0-9_])\$prompt_file(?![A-Za-z0-9_])", template)
            and re.search(r"[%!&^<>|]", workspace)):
        raise ValueError(
            f"Windows 下工作区路径含 cmd 元字符（% ! & ^ < > |），"
            f"{name} 的 $prompt_file 无法安全传递给外部 agent；"
            "请更换工作区路径"
        )


def _validate(cfg: Config) -> None:
    if cfg.words.pick < 0:
        raise ValueError("words.pick（n）必须 >= 0")
    if cfg.words.count < 1 or cfg.words.batch < 1:
        raise ValueError("words.count / words.batch 必须为正整数")
    if cfg.loop.iterations is not None and cfg.loop.iterations < 1:
        raise ValueError("loop.iterations 必须为正整数或 inf(-1)")
    if not math.isfinite(cfg.agent.timeout) or cfg.agent.timeout <= 0:
        raise ValueError("agent.timeout 必须为有限的正数（秒）")
    # ---- 轮次守卫 ----
    # 延迟导入：rounds.py 依赖 agents/sink，--help 等路径不该背上这些依赖
    from .rounds import FALLBACK_SCORERS, VERIFY_MODES
    if cfg.rounds.verify not in VERIFY_MODES:
        raise ValueError(f"rounds.verify 必须是 {'/'.join(VERIFY_MODES)}，"
                         f"收到: {cfg.rounds.verify!r}")
    if cfg.rounds.fallback not in FALLBACK_SCORERS:
        raise ValueError(f"rounds.fallback 必须是 {'/'.join(FALLBACK_SCORERS)}，"
                         f"收到: {cfg.rounds.fallback!r}")
    if not (0.0 <= cfg.rounds.adopt_score <= 10.0):
        raise ValueError(f"rounds.adopt_score 必须在 0-10 之间，"
                         f"收到: {cfg.rounds.adopt_score!r}")
    if cfg.rounds.enabled and not cfg.rounds.dir.strip():
        raise ValueError("rounds.dir 不能为空")
    for name in ("verify_timeout", "judge_timeout"):
        v = getattr(cfg.rounds, name)
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"rounds.{name} 必须为有限的正数（秒）")
    jcmd = cfg.rounds.judge_command
    # 与 agent.command 同样的占位符校验：评审命令收不到提示词时，
    # AI 评分会静默拿不到候选内容而永远解析不出分数
    if jcmd.strip():
        from .agents import command_receives_prompt
        if not command_receives_prompt(jcmd):
            raise ValueError(
                "rounds.judge_command 必须包含会被实际替换的 $prompt 或 "
                "$prompt_file 占位符（被转义的 \\$prompt 不会被替换）")
    cmd = cfg.agent.command
    # 模板缺少占位符时提示词会被静默丢弃：agent 收不到任何输入，循环空转。
    # 判断必须复用 ShellAgent 的实际渲染逻辑，不能用正则近似匹配
    # "$prompt" 子串：被 shell 转义的 \$prompt（或 "$prompt"）虽然包含
    # 子串，渲染时并不会替换，恰好会漏掉本条校验要拦的场景。
    # 延迟导入：避免 --help 等路径也背上 agents 的依赖
    if cmd.strip():
        from .agents import command_receives_prompt
        if not command_receives_prompt(cmd):
            raise ValueError(
                "agent.command 必须包含会被实际替换的 $prompt 或 "
                "$prompt_file 占位符（被转义的 \\$prompt、shell 注释、"
                "heredoc 正文、反引号命令替换、算术语境（$[...]、"
                "((...))）与 ${...} 参数展开（含数组下标/子串展开等算术"
                "语境和 ${x:-word} 等词语境）内的占位符都不会被替换；"
                "$[...] 区域内词首的 # 在 dash 下是注释、会吞掉同行后续"
                "（含结束符 ] 与提示词引号，bash 则在算术区报错），"
                "这类模板同样整体拒绝；"
                "命令替换（$(...)）内的 case 语句因 pattern 以裸 ) 结束、"
                "无法安全配对括号，其后的占位符同样不会被替换；"
                "裸 >&word 重定向词（bash 按 &>word 处理、展开不遵守"
                "引号规则，单引号里的 $(...)/`...` 仍会被执行）内的占位符"
                "不会被替换；紧跟在未转义 $ 后面的占位符（如 $$prompt，"
                "shell 把 $$ 当 PID、prompt 只是字面量）也不会被替换；"
                "用续行（反斜杠-换行）拆开操作符/展开头的模板（如 > 后"
                "换行再 & 拼成 >&、$ 后换行再 ( 拼成 $(，续行在 shell"
                "分词前会被删除、两侧字符实际拼成一个操作符）会整体拒绝；"
                "ANSI-C 引用（$'...'）的语义随系统 /bin/sh 方言（bash/"
                "dash）变化、无法安全替换，这类模板也会被拒绝；bash 数组"
                "赋值（NAME=(...)）不是 POSIX 语法（dash 下无法运行），"
                "且 bash 在数组内语法错误时会把后续行当命令执行（提示词"
                "注入），这类模板同样被拒绝），否则提示词无法传给外部 "
                "agent"
            )
    # cmd.exe 无法安全接收内嵌多行参数：$prompt_file 的路径也只经
    # list2cmdline 处理空格/引号、不转义 cmd 元字符。两条命令同口径校验
    # （评委命令原来漏检，评审提示词会被 cmd 当命令解析）
    _validate_windows_command("agent.command", cmd, cfg.workspace)
    _validate_windows_command("rounds.judge_command", jcmd, cfg.workspace)
