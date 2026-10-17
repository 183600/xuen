"""确保仓库根（xuen 包所在目录）在 sys.path 里，无论从哪里启动 pytest。"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
