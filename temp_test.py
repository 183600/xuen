cmd = cfg.agent.command
    # 模板缺少占位符时提示词会被静默丢弃：agent 收不到任何输入，循环空转
    _require_prompt_placeholder("agent.command", cmd, _AGENT_PLACEHOLDER_HINT)
