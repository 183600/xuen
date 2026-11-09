from typing import Optional


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