"""ShellAgent 运行/终止生命周期的回归测试。"""
from __future__ import annotations


def test_kill_after_completed_run_does_not_poison_next_run(tmp_path):
    """正常跑完一轮后到达的 kill 不能被兑现到下一轮。

    回归：run() 收尾后 _proc 已为空，kill() 却把请求记成「待处理」，
    下一次 run() Popen 后立即补杀，agent 实例从此返回空输出与 rc=-9。
    用户按下 q 与上一轮收尾同时发生时，本不该影响尚未开始的下一轮。
    """
    import os
    from xuen.agents import ShellAgent

    if os.name != "posix":
        return
    agent = ShellAgent("printf ok", tmp_path, timeout=5)
    assert agent.run("") == "ok"
    assert agent.returncode == 0

    agent.kill()
    assert agent.run("") == "ok"
    assert agent.returncode == 0
    assert agent.user_killed is False
