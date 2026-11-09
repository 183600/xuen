import sys
sys.path.insert(0, '.')
from xuen.config import load_config

cfg = load_config('config/test.yaml')
print('verify_timeout:', cfg.rounds.verify_timeout)