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


def test_kill_during_completed_run_cleanup_does_not_poison_next_run(
        tmp_path, monkeypatch):
    """进程已回收后、run() 还在收尾输出线程时到达的 kill 也要忽略。

    回归：run() 只在 finally 最末尾把 _idle_after_run 置位；进程已经
    wait() 成功但 timer/输出线程尚未 join 完的收尾窗口里，kill() 仍会
    把请求记成「待处理」，导致下一次 run() 刚拉起的进程被立即补杀。
    """
    import os
    import threading
    from xuen.agents import ShellAgent

    if os.name != "posix":
        return
    agent = ShellAgent("printf ok", tmp_path, timeout=5)
    real_join = threading.Thread.join
    fired = {"done": False}

    def join(self, timeout=None):
        if not fired["done"]:
            fired["done"] = True
            agent.kill()
        return real_join(self, timeout)

    monkeypatch.setattr(threading.Thread, "join", join)
    assert agent.run("") == "ok"
    assert agent.returncode == 0
    monkeypatch.setattr(threading.Thread, "join", real_join)

    assert agent.run("") == "ok"
    assert agent.returncode == 0
    assert agent.user_killed is False

def test_kill_after_process_exit_before_wait_does_not_poison_next_run(
        tmp_path, monkeypatch):
    """进程已退出但 run() 尚未从 wait() 返回时到达的 kill 也要忽略。

    回归：kill() 只看 _idle_after_run，未看 proc.poll()；这个窗口里
    进程已回收/已退出，kill 杀不到任何东西，却把请求记成「待处理」，
    下一次 run() 刚拉起的进程会被立即补杀。
    """
    import os
    import subprocess
    from xuen.agents import ShellAgent

    if os.name != "posix":
        return
    agent = ShellAgent("printf ok", tmp_path, timeout=5)
    real_wait = subprocess.Popen.wait
    fired = {"done": False}

    def wait(self, timeout=None):
        if timeout is None:
            rc = real_wait(self)
        else:
            rc = real_wait(self, timeout=timeout)
        if not fired["done"]:
            fired["done"] = True
            agent.kill()
        return rc

    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    assert agent.run("") == "ok"
    assert agent.returncode == 0
    monkeypatch.setattr(subprocess.Popen, "wait", real_wait)

    assert agent.run("") == "ok"
    assert agent.returncode == 0
    assert agent.user_killed is False


def test_kill_during_failed_popen_not_delivered_to_next_run(
        tmp_path, monkeypatch):
    """Popen 失败期间到达的 kill 没有进程可杀，不能留给下一轮补杀。"""
    import os
    import subprocess
    import pytest
    from xuen.agents import ShellAgent

    if os.name != "posix":
        return
    agent = ShellAgent("printf ok", tmp_path, timeout=5)
    real_popen = subprocess.Popen
    fired = {"done": False}

    def popen(*args, **kwargs):
        if not fired["done"]:
            fired["done"] = True
            agent.kill()
            raise OSError("boom")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(OSError, match="boom"):
        agent.run("")
    monkeypatch.setattr(subprocess, "Popen", real_popen)

    assert agent.run("") == "ok"
    assert agent.returncode == 0
    assert agent.user_killed is False
