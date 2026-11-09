from xuen.config import load_config
from xuen.utils import write_cfg  # maybe not needed; we can just open file directly

import tempfile

# create a temporary file with the config
with tempfile.TemporaryDirectory() as tmp_dir:
    config_path = tmp_dir + "/config.yaml"
    with open(config_path, 'w') as f:
        f.write('''agent:
  command: 'opencode run "$prompt"'

rounds:
  verify_timeout: -5
''')
    # Now load the config
    cfg = load_config(config_path)
    print("Config loaded successfully")
    print(f"cfg.rounds.verify_timeout = {cfg.rounds.verify_timeout}")
    print(f"cfg.rounds.enabled = {cfg.rounds.enabled}")