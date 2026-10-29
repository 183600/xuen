# xuen 最小示例

这个目录提供一个不依赖真实外部 agent、网络或 pytest 的最小演示：

```bash
python examples/minimal_demo.py
```

它会：

1. 用 `mock_agent.py` 生成一组领域词，并随机抽取 2 个灵感词；
2. 渲染研究轮提示词，由 mock agent 覆盖 `research.md` 的想法区/产物区；
3. 启动轮次守卫：保存候选快照、跑临时仓库的 `make test`（没有 `make`
   时改用 mock 评审员打分），通过后晋升为最佳；
4. 打印守卫汇总与最终状态，并列出候选快照、`best.md`、`best.json`、
   `history.jsonl` 等产物。

所有文件都写在系统临时目录里，运行结束后默认自动清理。想保留查看：

```bash
python examples/minimal_demo.py --keep
```

不需要安装 opencode、claude、aider 等任何外部可执行文件；只需要 Python
和本仓库依赖（`pip install -e .`）。示例的 mock 全部集中在
`examples/` 内，不修改 `xuen/` 的核心逻辑。
