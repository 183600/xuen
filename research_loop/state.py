"""research.md（想法区 + 产物区）的维护，以及供外部 agent 使用的写入助手脚本。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

SECTION_IDEA = "IDEA"
SECTION_ARTIFACT = "ARTIFACT"

HELPER_NAME = "write_section.py"


def start_marker(name: str) -> str:
    return f"<!-- {name}:START -->"


def end_marker(name: str) -> str:
    return f"<!-- {name}:END -->"


def scaffold(task: str) -> str:
    return (
        f"# 研究循环 · {task}\n\n"
        "> 本文件由 research-loop 维护：『想法区』『产物区』跨轮保留，"
        "每次写入会整体覆盖对应区块。编辑时请保留标记行。\n\n"
        f"{start_marker(SECTION_IDEA)}\n（暂无）\n{end_marker(SECTION_IDEA)}\n\n"
        f"{start_marker(SECTION_ARTIFACT)}\n（暂无）\n{end_marker(SECTION_ARTIFACT)}\n"
    )


def ensure_state_file(path: Path, task: str) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scaffold(task), encoding="utf-8")
    return path.read_text(encoding="utf-8")


def get_section(text: str, name: str) -> str:
    s, e = start_marker(name), end_marker(name)
    if s not in text or e not in text:
        return ""
    i = text.index(s) + len(s)
    j = text.index(e, i)
    return text[i:j].strip("\n")


def update_section_file(path: Path, name: str, content: str) -> Tuple[str, str]:
    """整体覆盖某个区块，返回 (旧内容, 新内容)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else scaffold("")
    old = get_section(text, name)
    new = content.strip().strip("\n")

    s, e = start_marker(name), end_marker(name)
    body = "\n" + new + "\n"
    if s in text and e in text and text.index(s) < text.index(e):
        text = text[: text.index(s) + len(s)] + body + text[text.index(e):]
    else:
        text = text.rstrip("\n") + f"\n\n{s}{body}{e}\n"

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return old, new


# ----------------------------------------------------------------_Settings
# 生成到工作区的独立小脚本：shell 模式下外部 agent 用它直接写文件，
# 从而实现「生成想法 / 生成产物」这两个工具（覆盖对应区块）。
# ----------------------------------------------------------------_Settings
HELPER_TEMPLATE = '''#!/usr/bin/env python3
"""research-loop 区块写入助手（供外部 agent 通过 shell 调用）。

用法:
  cat new.md | python write_section.py idea       # 用 stdin 内容覆盖『想法区』
  cat new.md | python write_section.py artifact   # 用 stdin 内容覆盖『产物区』
  python write_section.py show                    # 打印整个状态文件
"""
import os
import sys

STATE_FILE = r"""__STATE_FILE__"""
NAMES = {"idea": "IDEA", "artifact": "ARTIFACT"}


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not argv or argv[0].lower() in ("help", "h"):
        print(__doc__.strip())
        return 0
    cmd = argv[0].lower()
    if cmd == "show":
        with open(STATE_FILE, encoding="utf-8") as f:
            sys.stdout.write(f.read())
        return 0
    if cmd not in NAMES:
        print(f"未知区块 {cmd!r}，可用: idea / artifact / show", file=sys.stderr)
        return 2
    content = sys.stdin.read()
    name = NAMES[cmd]
    s, e = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    text = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            text = f.read()
    body = "\\n" + content.strip().strip("\\n") + "\\n"
    if s in text and e in text and text.index(s) < text.index(e):
        text = text[: text.index(s) + len(s)] + body + text[text.index(e):]
    else:
        text = text.rstrip("\\n") + f"\\n\\n{s}{body}{e}\\n"
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, STATE_FILE)
    print(f"[write_section] 已覆盖 {cmd} 区（{len(content)} 字符）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def write_helper_script(workspace: Path, state_path: Path) -> Path:
    helper = workspace / HELPER_NAME
    helper.write_text(
        HELPER_TEMPLATE.replace("__STATE_FILE__", str(state_path.resolve())),
        encoding="utf-8",
    )
    return helper
