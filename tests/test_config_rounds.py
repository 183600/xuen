"""rounds 配置段的解析与校验。"""
import textwrap

import pytest

from xuen.config import load_config


def write_cfg(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(p)


BASE = """
agent:
  command: 'opencode run "$prompt"'
"""


def test_rounds_defaults(tmp_path):
    cfg = load_config(write_cfg(tmp_path, BASE))
    assert cfg.rounds.enabled is True
    assert cfg.rounds.verify == "auto"
    assert cfg.rounds.fallback == "ai"
    assert cfg.rounds.adopt_score == 7.0
    assert cfg.rounds.dir == "rounds"


def test_rounds_full_section(tmp_path):
    cfg = load_config(write_cfg(tmp_path, BASE + """
rounds:
  enabled: true
  dir: snapshots
  verify: tests
  fallback: user
  adopt_score: 8.5
  verify_timeout: 300
  repo: /tmp/some/repo
  judge_command: 'opencode run "$prompt"'
  judge_timeout: 120
"""))
    assert cfg.rounds.dir == "snapshots"
    assert cfg.rounds.verify == "tests"
    assert cfg.rounds.fallback == "user"
    assert cfg.rounds.adopt_score == 8.5
    assert cfg.rounds.verify_timeout == 300.0
    assert cfg.rounds.repo == "/tmp/some/repo"
    assert cfg.rounds.judge_timeout == 120.0


def test_rounds_disable(tmp_path):
    cfg = load_config(write_cfg(tmp_path, BASE + """
rounds:
  enabled: false
"""))
    assert cfg.rounds.enabled is False


def test_rounds_verify_yaml_bool_off(tmp_path):
    """YAML 1.1 把未加引号的 off 解析成布尔 False：语义上正对应 "off" 模式，
    绝不能经 `or 默认值` 静默变成 auto。"""
    cfg = load_config(write_cfg(tmp_path, BASE + """
rounds:
  verify: off
"""))
    assert cfg.rounds.verify == "off"


def test_rounds_verify_yaml_bool_yes_rejected(tmp_path):
    """verify: yes（→ True → "on"）没有对应模式：必须报错而不是静默回退。"""
    with pytest.raises(ValueError, match="rounds.verify"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  verify: yes
"""))


def test_rounds_bad_verify(tmp_path):
    with pytest.raises(ValueError, match="rounds.verify"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  verify: maybe
"""))


def test_rounds_bad_fallback(tmp_path):
    with pytest.raises(ValueError, match="rounds.fallback"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  fallback: llm
"""))


def test_rounds_bad_adopt_score(tmp_path):
    with pytest.raises(ValueError, match="adopt_score"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  adopt_score: 11
"""))


def test_rounds_bad_timeout(tmp_path):
    with pytest.raises(ValueError, match="verify_timeout"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  verify_timeout: -5
"""))


def test_rounds_bad_judge_command(tmp_path):
    with pytest.raises(ValueError, match="judge_command"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  judge_command: 'echo 不带占位符'
"""))


def test_rounds_scalar_section_rejected(tmp_path):
    with pytest.raises(ValueError, match="rounds"):
        load_config(write_cfg(tmp_path, BASE + """
rounds: on
"""))


def test_windows_agent_command_prompt_rejected(tmp_path, monkeypatch):
    """Windows 下 cmd.exe 无法安全接收内嵌多行的 $prompt。"""
    monkeypatch.setattr("os.name", "nt")
    with pytest.raises(ValueError, match="agent.command"):
        load_config(write_cfg(tmp_path, BASE))


def test_windows_judge_command_prompt_rejected(tmp_path, monkeypatch):
    """评审命令与 agent.command 同经 cmd.exe 执行：$prompt 同样要拦下，
    否则评审提示词（含模型生成的候选内容）里的换行/&/% 会被 cmd 执行。"""
    monkeypatch.setattr("os.name", "nt")
    with pytest.raises(ValueError, match="judge_command"):
        load_config(write_cfg(tmp_path, """
agent:
  command: 'opencode run "$prompt_file"'
rounds:
  judge_command: 'opencode run "$prompt"'
"""))


def test_bool_fields_reject_non_boolean_values(tmp_path):
    """布尔配置写错类型必须报错，不能静默取真值。

    回归：_parse_bool 末尾直接 bool(value)——`tui: []`（缩进写错）会静默
    变成 False，`rounds.enabled: []` 更会悄悄关掉轮次守卫；与
    _parse_int/_parse_float 拒绝非法类型的口径保持一致。
    """
    with pytest.raises(ValueError, match="tui"):
        load_config(write_cfg(tmp_path, BASE + "tui: []\n"))
    with pytest.raises(ValueError, match="rounds.enabled"):
        load_config(write_cfg(tmp_path, BASE + """
rounds:
  enabled: []
"""))
    with pytest.raises(ValueError, match="words.reuse"):
        load_config(write_cfg(tmp_path, BASE + """
words:
  reuse: 2
"""))
    # 常见的标量写法仍然接受：数字 0/1、带引号的字符串
    cfg = load_config(write_cfg(tmp_path, BASE + """
tui: 1
color: "off"
words:
  reuse: 0
"""))
    assert cfg.tui is True
    assert cfg.color is False
    assert cfg.words.reuse is False


def test_windows_judge_command_bad_workspace(monkeypatch):
    """工作区路径含 cmd 元字符时，评审命令的 $prompt_file 也必须拒绝：
    只校验 agent.command 会漏掉评审命令（两条命令的路径都无法安全传递）。"""
    from xuen import config
    monkeypatch.setattr("os.name", "nt")
    with pytest.raises(ValueError, match="judge_command"):
        config._validate_windows_command(
            "rounds.judge_command", 'opencode run "$prompt_file"', "./ws&dir")


def test_windows_workspace_resolved_path_metachars_rejected(
        tmp_path, monkeypatch):
    """工作区原始字符串不含元字符、解析后的真实路径含元字符时也要拒绝。

    回归：runner 拼进 $prompt_file 的是 expanduser/resolve 后的绝对路径，
    只校验配置里的原始字符串会被「相对路径 + 元字符父目录」或符号链接
    目标绕过：路径裸插进 cmd 命令后会拆命令/丢字符。
    """
    from xuen import config
    monkeypatch.setattr("os.name", "nt")
    real = tmp_path / "a&b"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="元字符"):
        config._validate_windows_command(
            "agent.command", 'opencode run "$prompt_file"', str(link))


def test_windows_double_dollar_prompt_file_rejected(tmp_path, monkeypatch):
    """$$prompt_file 里的占位符不会兑现，配置必须拒绝而不是静默接受。

    回归：Windows 侧渲染器把第二个 $prompt_file 也替换掉，命令里残留
    `$+路径`（cmd 不展开 $，外部 agent 拿到坏路径）；POSIX 侧则整段
    不替换、command_receives_prompt 返回 False 后由配置校验明确拒绝。
    """
    monkeypatch.setattr("os.name", "nt")
    with pytest.raises(ValueError, match="必须包含会被实际替换"):
        load_config(write_cfg(tmp_path, """
agent:
  command: 'opencode run $$prompt_file'
"""))
