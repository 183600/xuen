#!/usr/bin/env python3
"""示例用的假外部 agent：不依赖 opencode / 网络，纯本地完成三种工作。

同一个脚本按提示词内容分派：
  1. 词库生成提示词 → 输出一组领域词；
  2. 轮次评审提示词 → 输出一条评分（用于 verify=auto 的 AI 兜底）；
  3. 研究轮提示词 → 实际覆盖 research.md 的想法区/产物区。

用法（由 examples/minimal_demo.py 自动拼装）：
    python mock_agent.py <workspace> <repository-root> <prompt-file>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORDS = (
    "稀疏性",
    "收敛速度",
    "参数效率",
    "泛化能力",
    "梯度估计",
    "鲁棒性",
    "自适应步长",
    "二阶信息",
)


def _read_prompt(argv: list[str]) -> str:
    if len(argv) < 4:
        return ""
    try:
        return Path(argv[3]).read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: mock_agent.py <workspace> <repository-root> <prompt-file>",
              file=sys.stderr)
        return 2
    workspace = Path(sys.argv[1])
    repo_root = Path(sys.argv[2])
    # 让子进程能 import xuen.state（示例从源码树直接运行时也能工作）
    sys.path.insert(0, str(repo_root))
    from xuen import state

    prompt = _read_prompt(sys.argv)

    # 1) 词库生成：runner 的提示词里有「术语/关键词」
    if "术语/关键词" in prompt:
        print("\n".join(WORDS))
        return 0

    # 2) AI 评审兜底：让 verify=auto 在没有 make/pytest 的环境里仍能自动判定
    if "轮次评审员" in prompt:
        print("候选围绕灵感词补充了可执行的实验设计，相较最佳更完整。")
        print("评分: 9")
        return 0

    # 3) 研究轮：把本轮内容写入两个区块（与真实外部 agent 的写入方式一致）
    counter = workspace / "counter.txt"
    n = int(counter.read_text(encoding="utf-8")) + 1 if counter.exists() else 1
    counter.write_text(str(n), encoding="utf-8")
    match = re.search(r"本轮随机灵感词：(.*)", prompt)
    inspiration = match.group(1).strip() if match else "（未解析到灵感词）"
    idea = (
        f"第 {n} 轮想法（来自随机灵感词）：{inspiration}\n\n"
        f"- 观察：把 {inspiration} 联系起来，可能得到更稳健的方案。\n"
        "- 假设：先做小步自适应更新，再用二阶信息校正方向。\n"
        "- 下一步：用消融实验确认每个灵感的贡献。"
    )
    artifact = (
        f"第 {n} 轮产物：可执行的实验草案\n\n"
        "```python\n"
        "def step(x, grad, state):\n"
        "    state['m'] = 0.9 * state.get('m', 0) + 0.1 * grad\n"
        "    return x - 0.01 * state['m']\n"
        "```\n\n"
        "- 对照组：固定步长；实验组：自适应步长。\n"
        "- 指标：收敛轮数、最终损失、参数更新方差。"
    )
    state.update_section_file(workspace / "research.md",
                              state.SECTION_IDEA, idea)
    state.update_section_file(workspace / "research.md",
                              state.SECTION_ARTIFACT, artifact)
    print(f"[mock agent] 第 {n} 轮完成：灵感词 {inspiration}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
