if not score_valid:
    cmd = cfg.agent.command
    _require_prompt_placeholder("agent.command", cmd, _AGENT_PLACEHOLDER_HINT)
