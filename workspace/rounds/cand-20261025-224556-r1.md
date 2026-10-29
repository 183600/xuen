# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 想法区 · 新循环第 1 轮（承接 v8.9 PACT-ALC）：把「部分正确」变成可携带的部分证书

**灵感词**：partial correctness / integer programming / 循环不变式  
**起点**：v8.9 PACT-ALC 在 252 例上做到 252/252 认证、$Q=0$、总审计 252/252、10.59 s。它把 SAGE 的 capped 分支升级成按证书高度 $k$ 参数化的完整搜索，但最后一句风险仍然成立：$k\le4$ 只是这 252 例的经验事实，完整搜索最坏仍是 $2^k$；而退回 caps 又会把 $Q=0$ 和总证书一起丢掉。本轮不想再找一个更快的 oracle，而是想换一个角度：**能不能让「部分正确」本身变成算法状态的一部分，使得任何时候停下来，手里都有一个可审计的证书？**

## 一、先复盘：v8.9 的证书仍然是「事后」的

PACT-ALC 的 `TotalTrace` 很漂亮：它重放初始上下界、每次 probe 的 NO 证明或 YES 调度、最终 $\mathrm{NO}(v-1)$ 和 $C_{\max}=v$ 的调度。但它有一个结构上的限制：**它只在算法跑完之后才存在**。如果搜索被中断、预算耗尽、或者某个 probe 返回 UNKNOWN，我们手里没有一张「当前进度」的证书；只有一张最后才拼起来的轨迹。

更具体地说，PACT 的外层状态是

\[
(\mathrm{lb},\ \mathrm{ub},\ \mathrm{lb\_proof},\ s,\ m),
\]

其中 `lb_proof` 只对最后一次 NO 负责，前面的 YES 步和中间 NO 步只是 `steps` 列表里的记录。`TotalTrace` 把这些记录重新审计一遍，所以它是**轨迹证书**，不是**循环不变量**。

这正好撞上本轮的三个灵感词：

- **partial correctness**：一个循环的部分正确性，说的是「只要循环还没退出，已经建立的不变量一直成立」。它不要求终止；终止是另一个定理。
- **循环不变式**：不变量应该是一个**状态谓词**，每次迭代前后都保持，而不是最后才拼出来的证明。
- **integer programming**：固定 $h$ 的判定问题是一个 0-1 ILP；它的 LP 松弛、Farkas 证书、分支树和割平面，都可以作为不变量的构件。

三个词指向同一个设计：**把「下界证明 + 上界调度 + 括号关系」直接做成状态，并证明每次 probe 都保持它。** 这样，状态本身就是部分证书；如果它走到 $L=U$，就自动变成最优性证书。

## 二、第一次试错：给 ILP 加一个目标 $C$，下界太弱

最直接的整数规划想法是：不要固定 $h$ 反复判定，而是直接最小化 makespan。于是我在时间索引模型上加变量 $C$ 和约束

\[
C \ge t+p_i \quad\text{当 }x_{i,t}=1,
\]

也就是 $C\ge\sum_{i,t}(t+p_i)x_{i,t}$，然后最小化 $C$。如果这个 LP 的下界够紧，就可以直接做 B&B，甚至不需要 PACT 的固定 $h$ 搜索。

实测很失望：

| 实例 | 已知 OPT | LP 目标 $C^*$ |
|---|---:|---:|
| base holdout 0 | 32 | 30 |
| base holdout 1 | 29 | 27.667 |
| stress 47 | 35 | 33 |

LP 求解只要 0.006–0.01 s，但下界和目标差 2–3；加 big-M 也没有改善。原因不神秘：时间索引 LP 的分数解可以把不同任务的「尾段」拼在一起，目标 $C$ 只约束最后一个被选中的时间，放松了机器容量和优先级的联合结构。**这个方向不能作为新 B&B 的核心。**

这次失败给了一个有用的教训：真正强的下界不是「目标 LP」，而是**固定 $h$ 的可行性 LP + Farkas 证书**。PACT 的 `SDLP` 在 $h=\mathrm{OPT}-1$ 上经常根节点就不可行，正是因为它问的是「有没有一个长度为 $h$ 的调度」，而不是「最小长度是多少」。所以本轮保留固定 $h$ 的判定器，把创新放在**判定器外面的循环状态**上。

## 三、第二次试错：全 frontier B&B 和割循环，形式很漂亮，但这一轮跑不起来

第二个自然想法是完整的 branch-and-bound / branch-and-cut：

- 每个节点是一个 forbidden 集合 $F$（一个 box）；
- 维护一棵分区树 $T$，叶子是 open 或 closed；
- 每个叶子有局部下界 $L_f$ 和 NO 证明 $\pi_f$；
- 对分数 LP 做 split，或者加 split cut / cover cut；
- 全局下界 $L=\min_f L_f$，全局上界 $U=C_{\max}(s)$；
- 如果 $L=U$，树 + 调度就是最优性证书。

这就是标准的整数规划 B&B，也确实能把 PACT 的固定 $h$ 搜索嵌进去。问题是：**这一轮的语料没有足够的 gap 来撑起它。** 252 例的初始 gap 分布是 148 个 0、103 个 1、1 个 5；也就是说，对绝大多数实例，PACT 的初始括号已经紧到只差一层。一个多叶 frontier 在这些实例上根本不会长出来；即使实现，也测不到它的 split/lift 行为。

所以我做了一个折中：

1. **先把单叶特化跑起来**：所有 box 都是根，状态就是一个括号 $(L,U,s,m,\pi)$；这已经足以覆盖 252 例。
2. **保留一般的树/证明格式**：定义 `FrontierProof`，允许叶子的 horizon 不同；用 PACT 的 252 张 `BranchProof` 做 replay，验证分区树和叶子证明的审计。
3. **把多叶搜索和割循环写成形式化设计**，明确标为下一轮的实验，而不是把未跑的东西写成已跑的结果。

## 四、关键转折：括号本身就是最小不变式

真正让设计立住的，是一个很简单的观察：

> **`NO(L-1)` + 一个可行调度 $s$（$C_{\max}(s)=U$）+ $L\le U$，本身就已经是一个有效的括号 $L\le \mathrm{OPT}\le U$。**

证明只用两句话：$s$ 给出 $\mathrm{OPT}\le U$；`NO(L-1)` 给出 $\mathrm{OPT}\ge L$。不需要 `TotalTrace`，不需要把每次 probe 都重放一遍。

于是定义单叶状态

\[
\mathcal C=(L,U,s,m,\pi),
\]

不变量 $\mathcal I$ 是：

1. $\pi$ 证明 $\mathrm{NO}(L-1)$；
2. $(s,m)$ 是一个可行调度，且 $C_{\max}(s)=U$；
3. $L\le U$。

每次 probe 都保持它：

- 在 $h=L$ 上问：如果 NO，则 $L\leftarrow h+1$，$\pi\leftarrow$ 新证明；如果 YES，则 $U\leftarrow C_{\max}(s)\le h=L$，括号闭合。
- 在 $L<h<U$ 上问：如果 NO，则 $L\leftarrow h+1$；如果 YES，则 $U\leftarrow\min(U,C_{\max}(s))$。两种情况下 $L\le U$ 都保持。
- 如果 probe 返回 UNKNOWN，状态不变；仍然是一个有效的部分证书，只是没有前进。

这就是 partial correctness 的味道：**循环还没有退出时，状态已经是一个可以交给检查器的对象。** 它不需要等算法结束；它也不需要相信生成器的 `certified` 标志。

## 五、从单叶到 frontier：把「子问题」也放进不变量

单叶状态可以自然推广到多叶。设分区树 $T$ 的叶子分成 open 集 $O$ 和 closed 集 $C$。每个 open 叶子 $f$ 携带局部下界 $L_f$ 和证明 $\pi_f$；每个 closed 叶子 $c$ 携带 horizon $h_c$ 和证明 $\pi_c$。不变量变成：

1. $T$ 以根 box 为根，叶子恰好是 $O\cup C$，且每个 split 的子 box 恰好分区父 box；
2. 每个 open 叶子：$\pi_f$ 证明 $\mathrm{NO}(L_f-1\mid f)$；
3. 每个 closed 叶子：$\pi_c$ 证明 $\mathrm{NO}(h_c\mid c)$，且 $h_c\ge U-1$；
4. $(s,m)$ 可行，$C_{\max}(s)=U$；
5. $L=\min\bigl(\{L_f:f\in O\}\cup\{h_c+1:c\in C\}\bigr)$，且 $L\le U$。

转移有四类：

- **PROBE**：对某个 open 叶子做固定 $h$ 判定；YES 降 $U$，NO 升 $L_f$。
- **SPLIT**：把 open 叶子 $f$ 按任务 $i$ 的开始时刻从中位数切开，得到 $f_0,f_1$；两者继承 $L_f,\pi_f$。因为 $f_0,f_1$ 比 $f$ 更受限，父的 NO 证明对子仍然有效。
- **LIFT**：如果子问题在 $h$ 上 NO，就把它的局部下界抬到 $h+1$，并换上新的 NO 证明。
- **CUT**：在节点 LP 上加一条对整数调度有效的割；如果加割后 LP 在 $h$ 上不可行，就用「Farkas 证书 + 割的有效性见证」关闭该叶子。割循环可以是部分正确的：只要割本身有效，任何不可行结论都是可靠的；终止性则用有限割族或割预算来保证。

单叶版本就是 $O=\{\text{root}\}, C=\varnothing$ 的退化情形。它的部分正确性定理和多叶版本是同一个：**每个转移保持 $\mathcal I$；因此任意时刻的状态都是一个有效括号；如果 $L=U$，它就是一个最优性证书。** 终止性则是另一个定理：单叶时 $U-L$ 严格下降；多叶时用叶子测度的字典序下降。

## 六、探针策略：为什么先问下界 $L$？

不变量只规定「怎么保持」，不规定「先问哪一边」。PACT-C 的策略是：gap $\le4$ 时从 $L$ 开始扫，否则二分。这个策略在 252 例上留下了一个小尾巴：唯一的 gap $=5$ 实例 `large_het 7` 先从 43 开始二分，找到 43 的调度，再问 41，最后才闭合；如果第一问就问 41，一次就够了。

于是本轮试了四种策略：

- `pact`：gap $\le4$ 扫 $L$，否则二分（PACT-C 原策略）；
- `lower-first`：第一问固定问 $L$，之后在剩余区间二分；
- `upper-first`：第一问固定问 $U-1$；
- `binary`：不做扫描，直接二分。

`lower-first` 的直觉是：**如果 LP 下界 $L$ 已经等于 OPT，那么问 $L$ 会直接拿到调度并闭合；如果 $L=\mathrm{OPT}-1$，那么问 $L$ 会拿到 NO 证明并把 $L$ 抬到 OPT，也闭合。** 换句话说，$L$ 是「最可能一击命中」的那一侧，因为 LP pin 已经替我们做了大量工作。

这个策略的最坏情况也不差：第一问若 NO，$L$ 只加 1，然后在剩下的 gap 上二分，总 probe 数不超过

\[
1+\lceil\log_2 \mathrm{gap}\rceil.
\]

而 `upper-first` 在最坏情况下会沿着 $U-1,U-2,\dots$ 一路下降，gap 大时是线性的；252 例的 gap5 上它确实用了 5 次 probe。

## 七、小规模验证：252 例上的初步结果

我把单叶 ICF 实现成 `exp/v8u/icf.py`，用 `pact_decide` 的完整模式作为节点 oracle，在 252 例上跑了四种策略。结果如下（搜索 LP 不含 pin LP 和证书 LP）：

| 策略 | probes | 搜索 LP | 证书 LP | pin LP | 总 LP | 时间 |
|---|---:|---:|---:|---:|---:|---:|
| `pact` | 105 | 450 | 138 | 273 | 861 | 10.56 s |
| `lower-first` | 104 | 429 | 135 | 273 | 837 | 9.97 s |
| `upper-first` | 108 | 507 | 143 | 273 | 923 | 12.03 s |
| `binary` | 106 | 468 | 140 | 273 | 881 | 11.01 s |

`pact` 策略精确复现了 v8.9 PACT-C 的 105 次 probe、450 次搜索 LP、138 次证书 LP、273 次 pin LP 和 861 次总 LP，说明外围循环没有改变原算法的语义。`lower-first` 把唯一 gap5 实例从 2 次 probe / 38 次搜索 LP / 7 次证书 LP 降到 1 次 / 17 / 4，总共省下 24 次 LP。`upper-first` 明显更差（923 次 LP），说明「先问哪一边」不是无关紧要的旋钮。

更重要的是：在 252 例上，`lower-first` 让每个实例至多一次 probe 就闭合：

- 148 个 gap0 实例初始就有 $U=L$，不需要 probe；
- 103 个 gap1 实例问一次 $L$ 就闭合（NO 则 $L$ 抬到 $U$，YES 则 $U$ 降到 $L$）；
- 1 个 gap5 实例问一次 $L=41$ 就拿到 $C_{\max}=41$ 的调度，初始下界证明在 40，直接闭合。

也就是说，**这 252 例的 LP 下界要么精确、要么只差 1**；`lower-first` 的一次 probe 正好覆盖这两种情况。这个结果不是「算法普遍只需一次 probe」，而是「这批语料的 pin 下界非常紧」——这一点必须写进风险里。

另外，我对每个状态都做了 `PartialCertificate.audit_rdf()`：`lower-first` 共 356 次状态审计（252 个初始状态 + 104 个 probe 后状态），0 次失败，252/252 最终 `ICFCertificate` 通过。`pact` 是 357 次、`upper-first` 360 次、`binary` 358 次，全部 0 失败。

最后，我用 `replay_frontier.py` 把 PACT 的 252 张 `BranchProof` 转成 `FrontierProof`：252/252 通过分区树和叶子审计，共 320 个叶子；其中 194 张单叶、50 张两叶、7 张三叶、1 张五叶，58 张是非平凡分支树，合计 126 个非平凡叶子。这个 replay 不是新的搜索，但它验证了多叶证书格式的审计器。

## 八、这一轮真正的新东西是什么

不是「又调了一个 probe 顺序」，而是：

1. **状态即证书**：`(L,U,s,m,\pi)` 在每次迭代后都是可审计的部分证书；不需要等 `TotalTrace` 拼完。
2. **部分正确性先于终止性**：`L=U` 时自动最优；否则拿到的是有效括号，可以安全地停、恢复、或交给下一层。
3. **整数规划语义**：固定 $h$ 的 ILP、LP 松弛、Farkas 叶子、分区树、局部下界、可选的割循环，都被放进同一个不变量里。
4. **策略与正确性解耦**：`lower-first` 只是策略；换策略不改变证书和定理。

## 九、当前方案最大的风险

**最大风险是：本轮真正跑起来的是单叶特化，多叶 frontier 搜索与割循环还停留在形式化；252 例的初始 gap 只有 0/1/5，`lower-first` 的「一次 probe 闭合」很可能来自这批语料的 LP 下界过紧，而不是算法在大 gap 上的普遍优势。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 产物区 · v9.0 ICF-PACT：不变量携带的部分证书与 lower-first 前缀策略

## 0. 本轮产物与一句话结论

**ICF-PACT**（Invariant-Carrying Frontier PACT）把 v8.9 PACT-ALC 的「事后总轨迹」改造成「逐步可审计的部分证书」：

1. **部分证书**：状态 $\mathcal C=(L,U,s,m,\pi)$ 本身就是一张证书——$\pi$ 证明 $\mathrm{NO}(L-1)$，$(s,m)$ 是 $C_{\max}=U$ 的可行调度，$L\le U$。任意时刻停下来，手里都有一个有效的上下界括号。
2. **循环不变量**：每次 probe 都保持这个谓词；如果 probe 返回 UNKNOWN 或预算耗尽，状态不变，仍然是有效证书。正确性不依赖终止性，这就是 partial correctness。
3. **整数规划语义**：固定 $h$ 的 0-1 ILP、LP 松弛、Farkas 叶子、分区树、局部下界和可选的割循环，都被组织进同一个不变量；一般版本是一棵带局部界的 frontier，单叶版本是它的退化特化。
4. **lower-first 策略**：第一问固定问下界 $L$，之后在剩余 gap 上二分。252 例上每个实例至多一次 probe 闭合；唯一 gap $=5$ 的 `large_het 7` 从 PACT-C 的 2 次 probe / 38 次搜索 LP / 7 次证书 LP 降到 1 次 / 17 / 4。
5. **证书格式的 replay 验证**：把 PACT 的 252 张 `BranchProof` 全部转成 `FrontierProof`，252/252 通过分区树与叶子审计；共 320 个叶子，58 张非平凡分支树、126 个非平凡叶子。

在 252 例上：

| 策略 | probes | 搜索 LP | 证书 LP | pin LP | 总 LP | 时间 | 部分证书审计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `pact`（PACT-C 原策略） | 105 | 450 | 138 | 273 | 861 | 10.56 s | 357 / 0 |
| `lower-first` | **104** | **429** | **135** | 273 | **837** | **9.97 s** | 356 / 0 |
| `upper-first` | 108 | 507 | 143 | 273 | 923 | 12.03 s | 360 / 0 |
| `binary` | 106 | 468 | 140 | 273 | 881 | 11.01 s | 358 / 0 |

四组策略都是 252/252 最终认证；`pact` 策略精确复现了 v8.9 PACT-C 的 105 / 450 / 138 / 273 / 861，说明外围循环没有改变原算法的语义。`lower-first` 的收益全部来自唯一 gap $=5$ 的实例；其余 251 例两种策略完全相同。

结论：ICF-PACT 的主要收益不是墙钟，而是**证书语义**——状态本身可审计，$L=U$ 时自动成为最优性证书；`lower-first` 是这套语义下自然的 primal-first 策略。多叶 frontier 搜索和割循环本轮只做了形式化与证书 replay，尚未在语料上独立运行。

---

## 1. 产物清单

| 路径 | 内容 |
|---|---|
| `exp/v8u/icf.py` | ICF-PACT 实现：`PartialCertificate`、`FrontierProof`、`ICFCertificate`、`CertLeafProof`、`branch_to_frontier`、`run_icf` |
| `exp/v8u/bench_icf.py` | 252 例 × 四种 probe 策略的主实验 |
| `exp/v8u/bench_icf_pact.json` | `pact` 策略原始结果，252 行 |
| `exp/v8u/bench_icf_lower-first.json` | `lower-first` 策略原始结果 |
| `exp/v8u/bench_icf_upper-first.json` | `upper-first` 策略原始结果 |
| `exp/v8u/bench_icf_binary.json` | `binary` 策略原始结果 |
| `exp/v8u/replay_frontier.py` | 把 PACT 的 NO 树转成 frontier 证书并审计 |
| `exp/v8u/frontier_replay.json` | 252 张 frontier 证书的 replay 统计 |

运行方式（工作目录必须是 `/home/runner/work/xuen/xuen/workspace`）：

```bash
.venv/bin/python exp/v8u/bench_icf.py
.venv/bin/python exp/v8u/replay_frontier.py
```

---

## 2. 问题、ILP 与固定 $h$ 的 LP

### 2.1 时间索引 0-1 ILP

对实例 $I=(n,m,p,\mathrm{pred},elig)$、horizon $h$，变量 $x_{i,t,k}\in\{0,1\}$ 表示任务 $i$ 在机器 $k$ 上于时刻 $t$ 开始。整数可行集 $I(F,h)$ 由以下约束定义：

\[
\begin{aligned}
&\sum_{t,k} x_{i,t,k}=1 && \forall i,\\
&\sum_{i}\sum_{t'=t}^{t+p_i-1} x_{i,t',k}\le 1 && \forall k,t,\\
&s_i+p_i\le s_j && \forall (i,j)\in\mathrm{pred},\\
&x_{i,t,k}=0 && \text{若 }t<\mathrm{est}_i,\ t+p_i>h,\ (i,t)\in F,\ k\notin elig_i,\\
&x_{i,t,k}\in\{0,1\}.
\end{aligned}
\]

其中 $s_i=\sum_{t,k} t\,x_{i,t,k}$，$F\subseteq\{(i,t)\}$ 是一个 box 的 forbidden 集合。$I(F,h)\ne\varnothing$ 等价于「存在一个长度不超过 $h$、避开 $F$ 的可行调度」。

### 2.2 LP 松弛 $P(F,h)$

把 $x\in\{0,1\}$ 放松为 $0\le x\le1$，得到 $P(F,h)$。定义 LP 值函数

\[
L(F)=\min\{h\in\mathbb Z:\ P(F,h)\ne\varnothing\}.
\]

因为 $P(F,h)$ 对 $h$ 单调（$h$ 增大时变量集扩大、约束放松），$L(F)$ 是 box $F$ 的整数最优值的一个有效下界：

\[
L(F)\le \mathrm{OPT}(F).
\]

实现中 $P(F,h)$ 由 `exp/v60/sdecc.py` 的 `SDLP` 构造；`F` 通过 `forbid` 参数传入。`SDLP` 的时间索引变量数和约束数分别为

\[
V=O(nTm),\qquad R=O(mT+|E|T+n),
\]

`use_dom` 和 `elig_aware` 会进一步削减变量与约束。

### 2.3 判定器 $\mathrm{Decide}(F,h)$

固定 $h$ 的判定器返回三值之一：

\[
\mathrm{Decide}(F,h)\in\{\mathrm{NO}(\pi),\ \mathrm{YES}(s,m),\ \mathrm{UNKNOWN}\}.
\]

- **NO($\pi$)**：$\pi$ 是一张可重放的不可行性证明。实现中通常是 `BranchProof`：每个节点是一个 box 分区，叶子是 Farkas 证书或空域。
- **YES($s,m$)**：$(s,m)$ 是长度不超过 $h$ 的可行调度，外层用 `check_schedule` 逐项检查。
- **UNKNOWN**：预算、深度或数值原因未判定；它不产生错误结论，只表示「这一轮没有前进」。

v8.9 的 `pact_decide` 在完整模式下 `depthcap=None, nodecap=None`，对 252 例都返回 NO 或 YES；本轮把完整模式作为实验的节点 oracle。一般情形下，`Decide` 可以是深度参数化版本、割增强版本，或保留 UNKNOWN 的预算版本。

### 2.4 单调性

若 $h'\le h$，则 $I(F,h')\subseteq I(F,h)$，$P(F,h')\subseteq P(F,h)$。因此：

- $\mathrm{NO}(h)$ 推出 $\mathrm{NO}(h')$ 对所有 $h'\le h$；
- $\mathrm{YES}(h)$ 只说明 $\mathrm{OPT}\le h$，不说明 $\mathrm{OPT}=h$。

这条单调性是后面「closed 叶子在不同 horizon 上仍然有效」的依据。

---

## 3. 部分证书与不变量

### 3.1 单叶定义

单叶部分证书是一个五元组

\[
\mathcal C=(L,U,s,m,\pi),
\]

其中 $L,U\in\mathbb Z$，$s$ 是开始时刻向量，$m$ 是机器分配，$\pi$ 是一个证明对象。

### 3.2 不变量 $\mathcal I$

\[
\mathcal I(\mathcal C)\equiv
\begin{cases}
\pi.h=L-1,\\
\pi.\mathrm{audit\_rdf}()=\mathrm{True},\\
s\ \text{是可行调度，且}\ C_{\max}(s)=U,\\
L\le U.
\end{cases}
\]

注意这里没有任何「算法已结束」或「最终证明」的假设。只要 $\mathcal I$ 成立，$\mathcal C$ 就是一张有效的部分证书。

### 3.3 括号引理

**引理 3.1（bracket soundness）** 若 $\mathcal I(\mathcal C)$ 成立，则

\[
L\le \mathrm{OPT}\le U.
\]

**证明**：

- 上界：$s$ 可行且 $C_{\max}(s)=U$，所以 $\mathrm{OPT}\le U$。
- 下界：$\pi$ 证明 $\mathrm{NO}(L-1)$，即不存在长度不超过 $L-1$ 的可行调度；所以 $\mathrm{OPT}\ge L$。$\square$

这个引理不依赖 $\pi$ 是怎么生成的，只依赖 $\pi.\mathrm{audit\_rdf}()$。这就是「证书携带」的意义：检查器不需要重跑搜索。

### 3.4 终局引理

**引理 3.2（finalization）** 若 $\mathcal I(\mathcal C)$ 且 $L=U$，则 $\mathcal C$ 是最优性证书：

\[
\mathrm{OPT}=L=U,
\]

并且 $\pi$ 恰好是 $\mathrm{NO}(U-1)$ 的证明，$s$ 是 $C_{\max}=U$ 的调度。

**证明**：由引理 3.1，$U\le\mathrm{OPT}\le U$，故 $\mathrm{OPT}=U$。$\pi.h=L-1=U-1$，$\pi$ 证明 $\mathrm{NO}(U-1)$；$s$ 证明 $U$ 可行。$\square$

终局不需要额外的 `TotalTrace` 拼接；状态本身已经包含上下界的两张证明。

### 3.5 多叶推广

一般状态把根 box 分成一棵二叉树 $T$。叶子分为 open 集 $O$ 与 closed 集 $C$。每个 open 叶子 $f$ 携带局部下界 $L_f$ 和证明 $\pi_f$；每个 closed 叶子 $c$ 携带 horizon $h_c$ 和证明 $\pi_c$。令

\[
L=\min\Bigl(\{L_f:f\in O\}\cup\{h_c+1:c\in C\}\Bigr).
\]

不变量 $\mathcal I_{\rm tree}$ 为：

1. $T$ 以根 box 为根；每个 split 的两个子 box 恰好分区父 box；叶子恰好是 $O\cup C$。
2. 每个 open 叶子：$\pi_f$ 证明 $\mathrm{NO}(L_f-1\mid f)$，即 $\pi_f.h=L_f-1$，$\pi_f.\mathrm{audit\_rdf}()$，且 $\pi_f$ 的根 forbidden 集包含于 $f$ 的 forbidden 集。
3. 每个 closed 叶子：$\pi_c$ 证明 $\mathrm{NO}(h_c\mid c)$，且 $h_c\ge U-1$。
4. $(s,m)$ 可行，$C_{\max}(s)=U$。
5. $L\le U$。

单叶版本就是 $O=\{\text{root}\}$、$C=\varnothing$、$L=L_{\rm root}$、$\pi=\pi_{\rm root}$。

**引理 3.3（frontier soundness）** 若 $\mathcal I_{\rm tree}$ 成立，则 $L\le\mathrm{OPT}\le U$。

**证明**：上界同引理 3.1。下界：任取可行调度 $S$；由于 $T$ 的叶子分区根 box，$S$ 属于某个叶子。若叶子是 open $f$，$\mathrm{NO}(L_f-1\mid f)$ 推出 $C_{\max}(S)\ge L_f$；若叶子是 closed $c$，$\mathrm{NO}(h_c\mid c)$ 推出 $C_{\max}(S)\ge h_c+1$。两种情况下 $C_{\max}(S)\ge L$，所以 $\mathrm{OPT}\ge L$。$\square$

**引理 3.4（frontier finalization）** 若 $\mathcal I_{\rm tree}$ 且 $L=U$，则把每个 open 叶子的 $\pi_f$ 通过 horizon 单调性重定向到 $U-1$（因为 $L_f\ge L=U$，故 $\pi_f.h=L_f-1\ge U-1$），得到一棵全部叶子都在 $U-1$ 上 NO 的 `FrontierProof`；加上调度 $s$，即为最优性证书。

---

## 4. 转移与正确性

### 4.1 PROBE：一次判定同时推进两侧

对某个 open 叶子 $f$，取 $h$ 满足 $L_f\le h<U$，调用 $\mathrm{Decide}(f,h)$。

- **NO($\pi$)**：令 $L_f\leftarrow h+1$，$\pi_f\leftarrow\pi$，重新计算全局 $L$。新证明恰好是 $\mathrm{NO}(L_f-1\mid f)$，不变量 2 保持；因为 $h<U$，有 $h+1\le U$，不变量 5 保持。
- **YES($s',m'$)**：令 $U'\leftarrow\min(U,C_{\max}(s'))$，$(s,m)\leftarrow(s',m')$，$L$ 不变。由上一状态的括号引理，$L\le\mathrm{OPT}\le C_{\max}(s')$，所以 $L\le U'$；不变量 4、5 保持。
- **UNKNOWN**：状态不变；不变量保持。算法可以选择停止并返回部分证书。

**引理 4.1（PROBE preservation）** 若 $\mathcal I_{\rm tree}$ 在 PROBE 前成立，则 PROBE 后仍成立。

**证明**：逐条检查上面的定义即可；关键是 NO 分支的 $\pi.h=h=L_f^{\rm new}-1$，以及 YES 分支的 $L\le U'$ 由括号引理给出。$\square$

### 4.2 SPLIT：把 box 分区

对 open 叶子 $f$，记它的 forbidden 集为 $F_f$。选任务 $i$ 和一个分割点 $\mathrm{mid}$，令

\[
F_0=F_f\cup\{(i,t):t>\mathrm{mid}\},\qquad
F_1=F_f\cup\{(i,t):t\le\mathrm{mid}\}.
\]

用两个 open 叶子 $f_0,f_1$ 替换 $f$，两者继承 $L_f,\pi_f$。

- 不变量 1：$F_0,F_1$ 恰好分区 $F_f$ 的允许开始时刻（在目标 horizon 下）。
- 不变量 2：$\pi_f$ 证明的是 $\mathrm{NO}(L_f-1\mid f)$；$f_0,f_1$ 比 $f$ 更受限（forbidden 集更大），所以同一个证明对子 box 仍然有效。$\pi_f$ 的根 forbidden 集包含于 $F_f$，因而也包含于 $F_0,F_1$。
- 不变量 5：$L$ 可能保持不变（两个子叶子的局部下界都还是 $L_f$），仍然 $\le U$。

**测度**：定义 $\mu(f)=\sum_i |D_i(f)|$，其中 $D_i(f)$ 是任务 $i$ 在目标 horizon 下避开 $f$ 的允许开始时刻。SPLIT 满足

\[
\mu(f)=\mu(f_0)+\mu(f_1),\qquad \mu(f_0),\mu(f_1)<\mu(f)
\]

（只要两侧都非空）。因此叶子的测度多重集在字典序下严格下降。

### 4.3 LIFT：抬高局部下界

LIFT 是 PROBE 的 NO 分支，不改 $U$：若在 $h$ 上得到 $\mathrm{NO}$，令 $L_f\leftarrow h+1$，$\pi_f\leftarrow\pi$。它把局部下界从 $L_f$ 抬到 $h+1$，并保持不变量 2。

### 4.4 CLOSE：按目标 horizon 关闭

若叶子 $f$ 在 $h=U-1$ 上得到 NO，则把它从 $O$ 移到 $C$，令 $h_f=U-1$。不变量 3 成立。对于 $h<U-1$ 的 NO，不能直接关闭到目标 $U-1$；正确做法是用 LIFT 把 $L_f$ 抬到 $h+1$，保留为 open，等后续在更高的 $h$ 上再判定。单叶实现就是这样处理的：`L` 抬到 `h+1`，`π` 换成新证明，循环继续，直到 `L=U`。

### 4.5 CUT：整数规划的割循环（形式化）

在节点 LP $P(f,h)$ 上，可以加入一条对整数调度有效的割 $\alpha$。割必须携带有效性见证 $w$：所有满足 $f$ 的整数调度都满足 $\alpha$。CUT 循环维护：

- 每条已加入的割都有有效性见证；
- 当前 LP 是原 LP 加上这些割；
- 若扩展 LP 在 $h$ 上不可行，则「Farkas 证书 + 割见证」证明 $\mathrm{NO}(h\mid f)$；
- 若扩展 LP 仍可行，则继续加割或退回 SPLIT。

CUT 的部分正确性是直接的：只要割有效，任何由扩展 LP 推出的不可行性都对原整数问题有效。终止性需要额外的有限性假设：有限割族，或割预算 $q_{\max}$；否则割循环本身可能不终止。本轮没有实现割循环，只把它作为下一轮的整数规划增强。

### 4.6 部分正确性定理

**定理 4.2（partial correctness）** 若初始状态满足 $\mathcal I_{\rm tree}$，且每次转移是 PROBE / SPLIT / LIFT / CLOSE / CUT 之一，则每个可达状态都满足 $\mathcal I_{\rm tree}$。特别地：

- 若算法在 $L<U$ 时停止（预算、中断、UNKNOWN），返回的状态是一个有效的部分证书，括号 $[L,U]$ 可信；
- 若算法在 $L=U$ 时停止，返回的状态是一个最优性证书。

**证明**：初始条件 + 引理 4.1 + SPLIT/LIFT/CLOSE/CUT 的逐条保持 + 引理 3.4。这个证明不使用终止性。$\square$

这就是本轮对「partial correctness」的直接使用：**正确性是关于状态的，不是关于运行到结束的。**

### 4.7 终止性定理

**定理 4.3（termination）** 在以下假设下，循环终止：

1. 单叶：每次成功 PROBE 要么把 $L$ 增加至少 1，要么把 $U$ 减少至少 1，故 $U-L$ 是严格下降的非负整数；最多 $U_0-L_0+1$ 次成功 probe。
2. 多叶：用四元字典序测度
   \[
   \Bigl(U,\ \mathrm{sortdesc}\{\mu(f):f\in O\cup C\},\
   \sum_{f\in O}(U-L_f)+\sum_{c\in C}\bigl(U-(h_c+1)\bigr),\
   q_{\rm rem}\Bigr)
   \]
   其中 $\mu(f)=\sum_i|D_i(f)|$，$q_{\rm rem}$ 是剩余割预算（无割时恒为 0）。逐项检查：
   - PROBE 的 YES 分支降低 $U$，第一分量严格下降；
   - PROBE 的 NO 分支 / LIFT 抬高某个 $L_f$，前两分量不变，第三分量严格下降；
   - SPLIT 用 $\mu(f_0),\mu(f_1)$ 替换 $\mu(f)$，且 $\mu(f_0),\mu(f_1)<\mu(f)$，第二分量严格下降；第三分量可能增加，但第二分量优先；
   - CLOSE 把 open 叶子移到 closed，第三分量变为 $U-(h_c+1)\le U-L_f$，严格下降（若 $h_c=U-1$ 且 $L_f<U$）；
   - CUT 若不改变前三个分量，则消耗一次割预算，第四分量严格下降；若割导致 NO/LIFT/CLOSE，则按上面的分支下降。
   $\mu$ 的值域是 $[0,n(T+1)]$ 的有限整数，$U-L_f$ 与 $q_{\rm rem}$ 也是有限非负整数，故四元字典序良基。
3. 割循环：若使用 CUT，则要求有限割族或割预算 $q_{\max}$；否则终止性不成立。

**证明**：单叶是显然的；多叶用上述四元良基测度；CUT 由有限性假设。$\square$

### 4.8 总正确性定理

**定理 4.4（total correctness，无预算版本）** 若

- 初始状态满足 $\mathcal I_{\rm tree}$；
- `Decide` 是可靠的（NO 证明可审计，YES 调度可检查）；
- 循环不设 probe 预算，或预算足够大；
- 割循环满足有限性假设；

则算法终止，并且返回的状态满足 $L=U$，从而是最优性证书。

**证明**：定理 4.3 给出终止；终止时若 $L<U$，循环条件仍允许 PROBE（除非 `Decide` 返回 UNKNOWN；无预算版本假设不会），矛盾；故 $L=U$。定理 4.2 给出部分正确性，引理 3.4 给出最优性。$\square$

**实现说明**：`run_icf` 有 `max_probes=64` 的安全阀。若预算耗尽且 $L<U$，它返回 `PartialCertificate`，而不是声称最优。因此实现是**部分正确的**；在 252 例上所有实例都在 1 次 probe 内闭合，预算从未触发，所以总正确性定理在这些运行中适用。

### 4.9 审计定理

**定理 4.5（audit soundness）** 下列检查器返回 True 蕴含对应的不变量：

- `PartialCertificate.audit_rdf()`：检查 $\pi.h=L-1$、$\pi.\mathrm{audit\_rdf}()$、$L\le U$、$C_{\max}(s)=U$、`check_schedule(inst,U,s,m)`。
- `ICFCertificate.audit_rdf()`：检查 $\pi.h=U-1$、$\pi.\mathrm{audit\_rdf}()$、单叶 `FrontierProof` 在目标 $U-1$ 上审计、$C_{\max}(s)=U$、`check_schedule`。
- `FrontierProof.audit_rdf()`：递归检查分区树；叶子检查 $F$ 精确匹配、$h\ge$ target、$\pi.\mathrm{audit\_rdf}()$、$\pi$ 的根 forbidden 集包含于 $F$。
- `CertLeafProof.audit_rdf()`：对 Farkas 叶子调用 `verify(inst,h,cert,forbid=F)`；对空域叶子检查任务的所有允许时刻都在 $F$ 中。

这些检查器不信任生成器的 `certified` 标志，也不复用搜索状态；它们只依赖证明对象、`verify`、`check_schedule` 和 `_domain`。

---

## 5. 算法

### 5.1 单叶主循环

```text
ICF-PACT(I, B, policy):
    (L,U,s,m) = InitialBounds(I)          # chip + LP pin + LP schedule + LNS + STAB
    pi = LowerBoundProof(I, L)            # NO(L-1)
    probes = 0
    first = True
    while L < U and probes < B:
        h = Policy(L, U, first)
        r = Decide(I, h)                  # complete pact_decide in the experiment
        probes += 1
        if r is NO(pi2):
            L = h + 1
            pi = pi2
        elif r is YES(s2, m2):
            U = min(U, Cmax(s2))
            s, m = s2, m2
        else:
            break                         # keep the partial certificate
        first = False
        assert PartialCertificate(I,L,U,s,m,pi).audit_rdf()
    if L == U:
        return ICFCertificate(I,U,s,m,pi)
    return PartialCertificate(I,L,U,s,m,pi)
```

`InitialBounds` 继承 v8.9 的 APEX/PACT 初始化：`chip_bounds`、`lp_threshold`（LP pin）、`lp_schedule`、`lns_drop`、STAB。`LowerBoundProof` 调用 PACT 的 `_ensure_lb_proof`，优先复用已有的 Farkas / energy / bound 证明。实验中 `use_ga=False`，所以 YES 侧完全由完整 `pact_decide` 的 YES 叶子提供；这让四种策略在同一个内层 oracle 上可比。

### 5.2 探针策略

```text
Policy(L,U,first):
    pact:        if U-L <= 4: L else (L+U)//2
    lower-first: if first: L else (L+U)//2
    upper-first: U-1
    binary:      (L+U)//2
```

`pact` 复现 PACT-C 的 `scan_cap=4`。`lower-first` 是第一问固定问 $L$，之后二分；`upper-first` 是第一问固定问 $U-1$；`binary` 不做扫描。

### 5.3 与 PACT-ALC 的关系

- **相同的内层**：`SDLP`、`BranchProof`、Farkas/empty 叶子、`check_schedule`、完整搜索、LP pin、LNS、STAB。
- **相同的外层括号**：`lb`/`ub` 的更新规则与 PACT 一致。
- **不同的状态语义**：PACT 把中间步骤放在 `steps`，最后用 `TotalTrace` 重放；ICF 把当前括号直接作为 `PartialCertificate`，每个转移后审计。
- **不同的外层策略**：PACT-C 是 `scan<=4` 的二元策略；ICF 把策略抽象成 `Policy`，并新增 `lower-first`。
- **不同的证明格式**：`TotalTrace` 是线性轨迹；`FrontierProof` 是分区树，叶子可以有不同的 horizon，`BranchProof` 是它所有叶子同 horizon 的特例。`branch_to_frontier` 给出嵌入。

因此 ICF-PACT 不是 PACT 的替代，而是 PACT 的**状态/证明层升级**：内层搜索和初始化可以原封不动，外层从「事后重放」变成「逐步携带」。

---

## 6. 复杂度

### 6.1 单次判定

一次 `Decide` 在最坏情况下探索高度为 $k$ 的证书树，节点数至多 $2^{k+1}-1$。每个节点解一次 SDLP，并可能在叶子生成 Farkas 证书。设

- $T_{\rm LP}$：一次 SDLP 求解时间；
- $T_{\rm cert}$：一次叶子证书生成/验证时间；
- $k$：NO 证书高度（最坏 $k\le n(T+1)$）。

则

\[
T_{\rm Decide}=O\bigl(2^k(T_{\rm LP}+T_{\rm cert})\bigr).
\]

在 252 例上，NO 侧的 $k$ 分布是 194 个 0、50 个 1、7 个 2、1 个 4；YES 侧最坏 $k=29$（v8.9 数据）。本轮的单叶循环在 252 例上从未触发深 YES 搜索，因为 YES 都来自 $L$ 上的第一次 probe。

### 6.2 单叶循环

设 probe 次数为 $P$，每次 probe 的判定成本为 $T_{\rm Decide}$，状态审计与调度检查为 $T_{\rm audit}$。则

\[
T_{\rm ICF}=O\bigl(P\,(T_{\rm Decide}+T_{\rm audit})\bigr).
\]

不同策略的 probe 上界：

- `upper-first`：最坏 $P\le \mathrm{gap}$（每次 $U$ 降 1）。
- `binary`：$P\le \lceil\log_2(\mathrm{gap}+1)\rceil$。
- `pact`：先扫至多 4 次，再二分，$P\le 4+\lceil\log_2\mathrm{gap}\rceil$。
- `lower-first`：第一问 $L$；若 NO，$L$ 只加 1，剩下 $\mathrm{gap}-1$ 上二分，故
  \[
  P\le 1+\lceil\log_2\mathrm{gap}\rceil.
  \]

### 6.3 多叶 frontier

设 $B$ 是分支节点数，$Q$ 是割轮数，$T_{\rm LP}$、$T_{\rm cert}$ 同上。用优先队列按 $L_f$ 取最小叶子，主循环

\[
O\bigl((B+Q)(T_{\rm LP}+T_{\rm cert})+B\log B\bigr).
\]

最坏 $B$ 仍是指数（$B\le 2^{n(T+1)}$）；割的 rank 可能很大。ICF 不声称多项式时间，只声称：

- 单叶时 $P$ 由 gap 控制；
- 多叶时 $B$ 由实际搜索/割决定；
- 任意时刻的状态都可审计，因此可以在预算处安全停止。

### 6.4 证书审计

- 单叶：$O(1)$ 个结构检查 + 一次 $\pi.\mathrm{audit\_rdf}()$ + 一次 `check_schedule`。
- 多叶：$O(|T|+\text{leaves}\cdot T_{\rm cert})$；252 例 replay 共 320 个叶子，58 张非平凡树，审计总成本远小于一次主搜索。
- 内存：单叶 $O(V)$（当前 LP）+ $O(1)$ 状态；多叶 $O(|T|n)$ 的 forbidden 对 + 活跃 LP。

---

## 7. 实验

### 7.1 设置

- **语料**：252 例，`base=141`、`pert=60`、`stress=51`；$n\le21$、$m\le4$、$T\le68$。`stress` 的 51 行是 `stress 47`（26 个）和 `stress 5`（25 个）的加工时间扰动，行之间 `name/idx` 相同但 `p` 不同，是不同实例；不要按 `name/idx` 去重。
- **初始化**：`PACT(inst, pact_mode='complete', use_ga=False)` 的 `initial_bounds()`；包含 chip、LP pin、LP schedule、LNS、STAB。
- **内层 oracle**：`pact_decide(inst, h, depthcap=None, nodecap=None)`，完整搜索；不使用 GA/CHD。
- **验收**：`ok = (L==U==known) and final_audit and partial_fail==0 and partial_final`。`known` 只用于离线验收；生产字段是 `certified`、`audit`、`partial_final`。
- **时间**：同一 runner 的单次墙钟，没有置信区间；LP 计数比时间更稳定。

### 7.2 主结果

| 策略 | probes | 搜索 LP | 证书 LP | pin LP | 总 LP | 时间 | 部分审计（成功/失败） | 最终认证 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `pact` | 105 | 450 | 138 | 273 | 861 | 10.56 s | 357 / 0 | 252/252 |
| `lower-first` | **104** | **429** | **135** | 273 | **837** | **9.97 s** | 356 / 0 | 252/252 |
| `upper-first` | 108 | 507 | 143 | 273 | 923 | 12.03 s | 360 / 0 | 252/252 |
| `binary` | 106 | 468 | 140 | 273 | 881 | 11.01 s | 358 / 0 | 252/252 |

`pact` 行与 v8.9 PACT-C 的 105 次 probe、450 次搜索 LP、138 次证书 LP、273 次 pin LP、861 次总 LP 完全一致。这既是回归测试，也说明 ICF 的外层状态没有偷偷改变 PACT 的搜索。

分语料看，差异只来自 `base`：

| 语料 | 策略 | probes | 搜索 LP | pin LP | 时间 |
|---|---|---:|---:|---:|---:|
| base (141) | `pact` | 25 | 199 | 120 | 6.06 s |
| base (141) | `lower-first` | 24 | 178 | 120 | 5.47 s |
| pert (60) | `pact` | 29 | 78 | 81 | 1.12 s |
| pert (60) | `lower-first` | 29 | 78 | 81 | 1.15 s |
| stress (51) | `pact` | 51 | 173 | 72 | 3.37 s |
| stress (51) | `lower-first` | 51 | 173 | 72 | 3.35 s |

`lower-first` 的 24 次 LP 节省全部来自 `base/large_het/7`（唯一 gap $=5$ 的实例）。

### 7.3 策略消融

`upper-first` 在 gap5 上走了 5 次 probe（45,44,43,42,41），每次返回一个 $C_{\max}=h$ 的调度；它没有利用「下界 41 已经是 OPT」这个事实，所以最差。`binary` 走了 3 次（43,42,41）。`pact` 走了 2 次（43,41）。`lower-first` 走了 1 次（41）。

| 策略 | gap5 probes | gap5 搜索 LP | gap5 证书 LP | gap5 时间 |
|---|---:|---:|---:|---:|
| `pact` | 2 | 38 | 7 | 1.28 s |
| `lower-first` | **1** | **17** | **4** | **0.76 s** |
| `upper-first` | 5 | 95 | 12 | 2.75 s |
| `binary` | 3 | 56 | 9 | 1.68 s |

这组消融说明：**在 LP 下界紧的语料上，先问 $L$ 是正确方向；先问 $U-1$ 会把一个本来一次就能闭合的实例拖成线性扫描。**

### 7.4 为什么 `lower-first` 在 252 例上至多一次 probe

`lower-first` 的总 probe 是 104，而 252 例的 gap 分布是 148 个 0、103 个 1、1 个 5。104 = 103 + 1；148 个 gap0 不需要 probe。因此：

- 148 例初始 $U=L$，零 probe；
- 103 个 gap1 例问一次 $L$：NO 则 $L$ 抬到 $U$，YES 则 $U$ 降到 $L$；
- 1 个 gap5 例问一次 $L=41$，拿到 $C_{\max}=41$ 的调度，初始下界证明在 40，直接 $L=U=41$。

这不是算法在任意语料上的定理，而是**这批语料的 LP pin 下界非常紧**：194 例的下界等于 OPT，58 例只差 1。`lower-first` 正好把「等于」和「差 1」两种情况都一次闭合。

### 7.5 部分证书审计

每个状态（初始 + 每次 probe 后）都构造 `PartialCertificate` 并调用 `audit_rdf()`。四种策略的失败数都是 0：

| 策略 | 状态审计数 | 失败 | 最终 `ICFCertificate` |
|---|---:|---:|---:|
| `pact` | 357 | 0 | 252/252 |
| `lower-first` | 356 | 0 | 252/252 |
| `upper-first` | 360 | 0 | 252/252 |
| `binary` | 358 | 0 | 252/252 |

这验证了 partial correctness 的实现侧：**每一个中途状态都是可审计的括号**，不只是最后一个状态。对 `lower-first`，356 = 252 个初始状态 + 104 个 probe 后状态。

最终 `proof_kind` 分布在四种策略下完全相同：

```text
farkas 110, branch 58, bound 60, energy 24
```

这与 v8.9 的最终证明分布一致，说明外层策略只改变了 probe 的高度，没有改变内层证书的类型。

### 7.6 Frontier 证书 replay

`replay_frontier.py` 对每个实例运行 `pact_decide(inst, known-1)`，取 `BranchProof`，用 `branch_to_frontier` 把它的树转成 `FrontierProof`，再调用 `audit_rdf()`。结果：

| 指标 | 数值 |
|---|---:|
| 实例数 | 252 |
| frontier 审计通过 | 252 |
| 叶子总数 | 320 |
| 单叶树 | 194 |
| 两叶树 | 50 |
| 三叶树 | 7 |
| 五叶树 | 1 |
| 非平凡树（叶子数 >1） | 58 |
| 非平凡叶子数 | 126 |

叶子直方图与 v8.9 的证明高度分布一一对应：$k=0\to1$ 叶，$k=1\to2$ 叶，$k=2\to3$ 叶，$k=4\to5$ 叶。`FrontierProof` 检查了：

- 每个 split 的两个子 forbidden 集恰好分区父 box；
- 每个叶子的 $F$ 精确匹配；
- 每个叶子的证明 horizon $\ge$ target；
- 每个叶子的 Farkas/empty 证书在它的 forbid 集上通过 `verify` 或空域检查；
- 证明的根 forbidden 集包含于叶子的 $F$。

这个 replay **不是**新的 ICF 搜索，而是证书格式的兼容性验证：`BranchProof` 是 `FrontierProof` 的特例，新的 tree 审计器能重放旧的 NO 树。

### 7.7 解释与边界

- **主收益是语义，不是速度。** `lower-first` 只省了 24 次总 LP 和约 0.6 s；这不是数量级提升。真正的变化是：每个状态都有 `PartialCertificate`，可以在预算处安全停止，并且最终证书不依赖 `TotalTrace` 的重放。
- **语料偏置。** 252 例的 gap 只有 0/1/5；`lower-first` 的一次 probe 闭合是「LP 下界紧」的直接结果。若新语料的 $L$ 远离 OPT，第一次问 $L$ 会得到一个 NO 并只把 $L$ 抬 1，随后二分接管；不会像 `upper-first` 那样线性扫描。
- **多叶搜索未实测。** `FrontierProof` 的 split/lift/close 审计通过 replay 验证，但 live 的多叶 frontier 循环没有在 252 例上长出来（因为不需要），也没有在大 gap 合成语料上跑过。这是下一轮的主要实验缺口。
- **割循环未实现。** 4.5 节是形式化设计；没有 split cut / cover cut 的实现，也没有割有效性的数值实验。这是「integer programming」灵感中尚未落地的部分。

---

## 8. 与 v8.9 的差异

| 维度 | v8.9 PACT-ALC | v9.0 ICF-PACT |
|---|---|---|
| 外层状态 | `(lb,ub,lb_proof,s)` + `steps` | `PartialCertificate(L,U,s,m,π)` |
| 最终证书 | `TotalTrace` 线性重放 | `ICFCertificate`：单叶 frontier + 调度 |
| 中间状态 | 不可独立审计 | 每个 probe 后审计 |
| 证明格式 | `BranchProof` 所有叶子同 horizon | `FrontierProof` 允许叶子不同 horizon；`BranchProof` 是特例 |
| 外层策略 | `scan<=4` 否则二分 | 可插拔 `Policy`；新增 `lower-first` |
| 早停 | 只能返回 UNKNOWN / 未完成 | 返回有效部分证书 `[L,U]` |
| 正确性 | 终止后总审计 | partial correctness + termination + finalization |
| 多叶 B&B | 无 | 形式化 SPLIT/LIFT/CLOSE/CUT；本轮只 replay 证书格式 |

ICF 没有改动 PACT 的内层搜索、LP pin、LNS、STAB 或 Farkas 证书；它改变的是外层如何**持有**和**审计**这些证据。

---

## 9. 已知风险与限制

1. **单叶特化是实际跑的部分。** 多叶 frontier 的 live 搜索（SPLIT/LIFT/CLOSE 在循环中真正生长）没有在 252 例上发生；`branch_to_frontier` 只是把 PACT 的树换一种格式审计。不能把 replay 的成功当作多叶搜索的性能证据。
2. **语料偏置。** 252 例初始 gap 只有 0/1/5；`lower-first` 的一次 probe 闭合依赖 LP pin 下界等于 OPT 或 OPT−1（194 + 58）。若新语料的 LP 下界更松，第一次问 $L$ 可能只是浪费一次 NO probe；二分接管后仍正确，但「一次闭合」的结论不成立。
3. **$k$ 仍是经验参数。** ICF 没有消除 `Decide` 的 $2^k$ 最坏情况；NO 侧 $k\le4$ 只是这 252 例的观察。YES 侧最坏 $k=29$ 仍然存在。
4. **割循环未实现。** 4.5 节只有形式化；没有 split cut、cover cut、割有效性见证的实现和实验。CUT 的终止性依赖有限割族/预算，当前没有验证。
5. **时间不是显著差异。** `lower-first` 比 `pact` 快约 0.6 s（10.56 → 9.97），是单次运行；不应把 0.6 s 解读为稳定优势。LP 计数（861 → 837）更可靠，但差距也只有 24。
6. **多叶证书的混合 horizon 需要小心。** `FrontierProof` 允许叶子的 $h\ge$ target；当前 replay 的所有叶子都在同一个 $h$。混合 horizon 的覆盖证明依赖 `_domain(target)` 与叶子 $F$ 的精确匹配；本轮没有构造混合 horizon 的实例来测试。
7. **审计依赖外部检查器。** `verify`、`check_schedule`、`_domain`、`SDLP` 的数值容差是信任基；252 例通过不代表病态 LP 下也通过。
8. **实现预算。** `run_icf(max_probes=64)` 在预算耗尽时返回部分证书；总正确性定理只对无预算版本成立。252 例都在 1 次 probe 内闭合，预算未触发。
9. **`known` 只用于离线验收。** 生产环境应只看 `certified`、`audit`、`partial_final`、`cert_h`；不要用 `known` 判断正确性。
10. **stress 行不能按 `name/idx` 去重。** 51 行 stress 是 26 + 25 个不同加工时间的扰动；按名字去重会误以为只有两个实例，破坏 252 的计数。
11. **最终证明类型与 v8.9 相同。** `farkas 110, branch 58, bound 60, energy 24` 说明 ICF 没有引入新的内层证明类型；它的新意在外层状态和 frontier 格式，而不是新的 Farkas 生成器。
12. **`lower-first` 的策略分析是描述性的。** 它没有用学习或理论证明「$L$ 一定更可能命中」；只是在这批 LP 紧的语料上经验更好。`upper-first` 的反例说明策略确实会显著影响 probe 数。

---

## 10. 最大风险（一句话）

**最大风险是：本轮真正跑起来的是单叶特化，多叶 frontier 搜索与割循环还停留在形式化；252 例的初始 gap 只有 0/1/5，`lower-first` 的「一次 probe 闭合」很可能来自这批语料的 LP 下界过紧，而不是算法在大 gap 上的普遍优势。**

---

## 11. 本轮结论（1–2 句）

**ICF-PACT 把 PACT 的事后 `TotalTrace` 改造成逐步可审计的部分证书：任意时刻停下的状态都是 `[L,U]` 的有效证书，`L=U` 时自动成为最优性证书；252 例上 356 次状态审计 0 失败、252/252 最终认证。`lower-first` 在全部 252 例上至多一次 probe 闭合，并把唯一 gap=5 实例从 PACT-C 的 2 次 probe / 38 次搜索 LP 降到 1 次 / 17 次；但多叶 frontier 与割循环仍需下一轮的真实实验。**
<!-- ARTIFACT:END -->
