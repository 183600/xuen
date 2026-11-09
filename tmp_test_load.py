from xuen.config import load_config
import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    config_path = tmp_dir + "/config.yaml"
    with open(config_path, 'w') as f:
        f.write('''agent:
  command: 'opencode run "$prompt"'

rounds:
  verify_timeout: -5
''')
    cfg = load_config(config_path)
    print("Config loaded successfully")
    print(f"cfg.rounds.verify_timeout = {cfg.rounds.verify_timeout}")
    print(f"cfg.rounds.enabled = {cfg.rounds.enabled}")