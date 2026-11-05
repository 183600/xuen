if not score_valid:
    # dummy
    cmd = cfg.agent.command
    # comment
    _require_prompt_placeholder("agent.command", cmd, _AGENT_PLACEHOLDER_HINT)
