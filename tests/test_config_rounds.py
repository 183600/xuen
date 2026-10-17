"""rounds 配置段的解析与校验。"""
import textwrap

import pytest
import yaml

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
