    # 与 agent.command 同样的占位符校验：评审命令收不到提示词时，
    # AI 评分会静默拿不到候选内容而永远解析不出分数
    _require_prompt_placeholder("rounds.judge_command", jcmd,
                                _JUDGE_PLACEHOLDER_HINT)
    cmd = cfg.agent.command
    # 模板缺少占位符时提示词会被静默丢弃：agent 收不到任何输入，循环空转
    _require_prompt_placeholder("agent.command", cmd, _AGENT_PLACEHOLDER_HINT)
