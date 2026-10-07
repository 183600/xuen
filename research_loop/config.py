"""配置加载与校验。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

DEFAULT_CONFIG_PATHS = ("config.yaml", "config.yml", "research-loop.yaml")


@dataclass
class ModelConfig:
    name: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""                       # 留空则读环境变量
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 1.0
    max_tokens: int = 4096
    stream: bool = True
    request_timeout: float = 600.0
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def resolve_api_key(self) -> str:
        return self.api_key or os.environ.get(self.api_key_env, "")


@dataclass
class WordsConfig:
    count: int = 1000   # 领域词目标数量
    batch: int = 100    # 每次请求生成的数量
    pick: int = 2       # 每轮随机灵感词数量 n（>=0；0 = 不抽词）
    reuse: bool = True  # words.txt 已存在则复用
    via: str = "auto"   # auto | direct | shell


@dataclass
class LoopConfig:
    iterations: Optional[int] = 5   # None 表示无限循环


@dataclass
class AgentConfig:
    mode: str = "direct"     # direct | shell
    command: str = ""        # shell 模式命令模板，如: opencode run "$prompt"
    timeout: float = 1800.0
    max_steps: int = 24      # direct 模式每轮最大工具轮次


@dataclass
class ToolsConfig:
    shell: bool = True
    shell_timeout: int = 600
    max_tool_output: int = 20000


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    call_timeout: float = 300.0


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    extra_notes: str = ""
    words: WordsConfig = field(default_factory=WordsConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    mcp_servers: List[MCPServerConfig] = field(default_factory=list)
    workspace: str = "./workspace"
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
        if value.strip().lower() in ("inf", "infinite", "-1", "∞"):
            return None
        return int(value.strip())
    return int(value)


def load_config(path: Optional[str] = None) -> Config:
    real_path = find_config_path(path)
    with open(real_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config()

    model = raw.get("model") or {}
    cfg.model = ModelConfig(
        name=str(model.get("name", cfg.model.name)),
        base_url=str(model.get("base_url", cfg.model.base_url)),
        api_key=str(model.get("api_key", "") or ""),
        api_key_env=str(model.get("api_key_env", cfg.model.api_key_env)),
        temperature=float(model.get("temperature", cfg.model.temperature)),
        max_tokens=int(model.get("max_tokens", cfg.model.max_tokens)),
        stream=bool(model.get("stream", cfg.model.stream)),
        request_timeout=float(model.get("request_timeout", cfg.model.request_timeout)),
        extra_headers={str(k): str(v) for k, v in (model.get("extra_headers") or {}).items()},
    )

    cfg.extra_notes = str(raw.get("extra_notes") or "")

    words = raw.get("words") or {}
    cfg.words = WordsConfig(
        count=int(words.get("count", cfg.words.count)),
        batch=int(words.get("batch", cfg.words.batch)),
        pick=int(words.get("pick", cfg.words.pick)),
        reuse=bool(words.get("reuse", cfg.words.reuse)),
        via=str(words.get("via", cfg.words.via)).lower(),
    )

    loop = raw.get("loop") or {}
    cfg.loop = LoopConfig(iterations=_parse_iterations(loop.get("iterations", 5)))

    agent = raw.get("agent") or {}
    cfg.agent = AgentConfig(
        mode=str(agent.get("mode", cfg.agent.mode)).lower(),
        command=str(agent.get("command", "") or ""),
        timeout=float(agent.get("timeout", cfg.agent.timeout)),
        max_steps=int(agent.get("max_steps", cfg.agent.max_steps)),
    )

    tools = raw.get("tools") or {}
    cfg.tools = ToolsConfig(
        shell=bool(tools.get("shell", cfg.tools.shell)),
        shell_timeout=int(tools.get("shell_timeout", cfg.tools.shell_timeout)),
        max_tool_output=int(tools.get("max_tool_output", cfg.tools.max_tool_output)),
    )

    for s in raw.get("mcp_servers") or []:
        cfg.mcp_servers.append(MCPServerConfig(
            name=str(s.get("name") or f"mcp{len(cfg.mcp_servers) + 1}"),
            command=str(s.get("command") or ""),
            args=[str(a) for a in (s.get("args") or [])],
            env={str(k): str(v) for k, v in (s.get("env") or {}).items()},
            cwd=s.get("cwd"),
            call_timeout=float(s.get("call_timeout", 300)),
        ))

    cfg.workspace = str(raw.get("workspace", cfg.workspace))
    cfg.color = bool(raw.get("color", cfg.color))

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.words.pick < 0:
        raise ValueError("words.pick（n）必须 >= 0")
    if cfg.words.count < 1 or cfg.words.batch < 1:
        raise ValueError("words.count / words.batch 必须为正整数")
    if cfg.agent.mode not in ("direct", "shell"):
        raise ValueError("agent.mode 只能是 direct 或 shell")
    if cfg.words.via not in ("auto", "direct", "shell"):
        raise ValueError("words.via 只能是 auto / direct / shell")
    for s in cfg.mcp_servers:
        if not s.command:
            raise ValueError(f"MCP 服务器 {s.name} 缺少 command")
