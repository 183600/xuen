# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 想法区 · 新循环第 3 轮（承接 v9.0 ICF-PACT）：让对偶 LP 解直接生成原始调度

**灵感词**：control-flow analysis / denotational semantics / 算法分析  
**起点**：v9.0 ICF-PACT 已经把状态 $(L,U,s,m,\pi)$ 做成可审计的部分证书：$\pi$ 证明 $\mathrm{NO}(L-1)$，$(s,m)$ 是 $C_{\max}=U$ 的可行调度，$L\le U$；252 例上 356 次状态审计 0 失败、252/252 最终认证，`lower-first` 用 104 次 probe / 837 次 LP / 9.97 s 闭合。但 160 例弱语料（初始 gap 4–13）上，`lower-first` 需要 549 次 probe、1662 次搜索 LP + 341 次证书 LP，且在 `base/large_het/7` 上于 $h=39$ 返回 UNKNOWN，最终只有 159/160 完成；`binary` 也要 421 次 probe、1581 次搜索 LP + 248 次证书 LP。**v9.0 的主要遗留问题不是证书格式，而是：LP 只被当作“可行/不可行”的锚，没有被用来构造上界调度。**

## 一、先复盘：v9.0 的 LP 下界是“关着的”

v9.0 的每个 probe 都是一次固定 $h$ 的完整判定：LP 在根节点不可行时给 Farkas 证书；可行时进入分支。这个设计把 LP 用在了**下界**上，却把**上界**完全交给 PACT 的启发式调度。于是出现两个不对称：

- 下界侧：LP 很紧。252 例初始 gap 只有 148 个 0、103 个 1、1 个 5；弱语料经 LP pin 后仍有 0–11 的残差，大多数在 1–6。
- 上界侧：调度器在 $L$ 处经常“差一点”。如果 SGS 能在 $L$ 处直接命中，就完全不需要 probe；但 v9.0 没有把 LP 解当作 SGS 的优先级。

一个自然的追问是：**LP 解 $x^*$ 的分数开始时间，能不能直接解码成一个整数调度？** 如果行，那么 $L^*$（LP 阈值）就不只是下界，还可能直接成为上界；如果不行，差多少？这个“差多少”就是本轮的核心观测量。

## 二、三个灵感词分别落在哪里

### 1. denotational semantics：具体指称与抽象指称

把实例 $P$ 在 horizon $h$ 下的具体语义定义为可行调度的集合

\[
S_h=\{(s,m):\ s_i\ge est_i,\ s_j\ge s_i+p_i\ (i\to j),\ C_{\max}(s)\le h\},
\]

把 LP 松弛的抽象语义定义为

\[
P_h=\{x:\ \text{时间索引 LP 在 }h\text{ 下可行}\}.
\]

包含关系 $S_h\subseteq \gamma(P_h)$ 给出 $\mathrm{OPT}\ge L^*=\min\{h:P_h\ne\varnothing\}$。这正是 v9.0 的下界。**denotational semantics 的视角把“rounding”说清楚**：解码器 $\rho_h:P_h\to S_h\cup\{\bot\}$ 是一个部分收缩；如果 $\rho_h(x^*)\in S_h$，抽象解就被具体化，$L^*$ 直接闭合；如果 $\rho_h(x^*)=\bot$，抽象与具体之间的差距就是本轮要测的缺陷。

### 2. control-flow analysis：precedence DAG 的 dominator 树

把 precedence DAG 看成控制流图，加虚拟 source/sink，计算

\[
dom(v)=\{v\}\cup\bigcap_{u\in pred(v)}dom(u),\qquad
pdom(v)=\{v\}\cup\bigcap_{w\in succ(v)}pdom(w).
\]

如果 $i$ 支配 $j$，那么从 source 到 $j$ 的每条路径都经过 $i$，因此 $i$ 必须先于 $j$；dominator 深度可以作为 SGS 的安全优先级键。post-dominator 深度则给出“离 sink 多近”的对称键。这个想法很漂亮，但**本轮不把它当主卖点**：在 LP marginal 已经很强时，dominator 键的额外命中非常少（弱语料 +2，主语料 0–1），所以它只作为可解释的辅助顺序，并诚实报告负结果。

### 3. 算法分析：把精确 oracle 的调用次数写成缺陷的函数

如果 $L^*$ 是 LP 阈值，$\rho$ 在 $L^*$ 处返回长度 $L^*+\delta$ 的调度，那么

\[
L^*\le \mathrm{OPT}\le L^*+\delta.
\]

这就是**缺陷界**。它把算法分析从“gap 有多大”变成“解码器离目标有多远”：

- $\delta=0$：零次精确 probe；
- $\delta=1$：一次 probe 即可闭合（问 $L^*$，NO 则 $L^*+1$；YES 则直接闭合）；
- $\delta$ 大：退回二分/精确搜索。

因此复杂度应该写成

\[
O\big(\log(U-L)\cdot T_{\mathrm{LP}}+(K+R)\cdot T_{\mathrm{SGS}}+q\cdot T_{\mathrm{decide}}\big),
\]

其中 $q$ 是精确 probe 数，理想情况下 $q=O(\delta)$，而不是 $O(U-L)$。这就是本轮想要的“算法分析”落点：**不是再调一个 probe 顺序，而是让上界由 LP 解构造出来，让精确 oracle 只处理缺陷。**

## 三、第一次试错：先试图把下界再抬高，失败

最直接的想法是强化对偶侧：在 $h=\mathrm{OPT}-1$ 上加 energy/window 证书，或者把不可行的 start 值 shave 掉，再把 forbidden 集合传给 `pact_decide`。实测：

- `energy_cert` 在 $h=\mathrm{OPT}-1$ 能证 84/252 个 NO（74 个 energy + 10 个 window），168 个未知；
- shaving 每例删 5–20 个 start 值，但没有一例把域删空；
- 把 shave 后的 forbidden 传给 `pact_decide`，在 $h=\mathrm{OPT}-1$ 没有收益（根节点本来 1 次 LP），在 $h=\mathrm{OPT}$ 有时反而更差（holdout 1：2→5 个节点）。

**教训**：这批语料的 LP 下界已经很紧，继续抬下界的边际收益很小；真正的缺口在**上界构造**。这直接促成了“锚 → 解码 → probe”的顺序，而不是“probe → 修复”。

## 四、第二次试错：LPR + dominator，方向对但 CFA 不是主角

把 LP 解按任务开始时间的 marginal 排序，用 SGS 在 $L$ 处解码，再做随机重启；这就是 LPR 式 rounding。弱语料上：

- 确定性 quantile/mean/latest/tail 顺序：74/160 零 probe，91 次 probe；
- 加随机重启：91/160 零 probe，70 次 probe；
- 再加 dominator/post-dominator 顺序：只多 2 个命中，仍有 12 例 `noguide`。

这说明两件事：第一，**LP 解确实能直接生成大量最优调度**；第二，**CFA 的 dominator 顺序不是主要驱动力**，LP marginal 已经编码了大部分 precedence 信息。于是本轮保留 CFA 作为可解释的辅助顺序，但把主创新放在“对偶锚 + 原始解码 + 缺陷驱动”的整体控制上。

## 五、关键转折：`large_het 7` 说明锚和解码是互补的

弱语料里最难的 `base/large_het/7`：

- `init_weak` 给出 $L=39,U=52$，已知 $\mathrm{OPT}=41$；
- LP pin（`_pin_weak`）用 3 次 LP 把 $L$ 抬到 $41$，并在 $h=40$ 上给出 energy 证明；
- SGS 在 $L=41$ 处确定性/随机都失败（$C_{\max}$ 没有达到 41）；
- 但精确 probe 在 $h=41$ 上返回 YES，$C_{\max}=41$，用 17 次搜索 LP + 4 次证书 LP 闭合。

v9.0 的 `lower-first` 在这例上问的是 $h=39$，返回 UNKNOWN，最终 159/160。**同一个实例，差别不在 probe 顺序，而在“先让 LP 把 L 抬到 41，再问 41”**。这给出本轮的算法轮廓：

1. **ANCHOR**：用对偶 LP / pin 把 $L$ 抬到 $L^*$，并保留 $\mathrm{NO}(L^*-1)$ 的证书；
2. **ROUND**：把 LP 解解码到 $L^*$，能命中就零 probe 闭合；
3. **PROBE**：只在解码失败时问精确 oracle；问 $L^*$ 而不是原始 $L$。

## 六、本轮要做的 PD-ICF

**PD-ICF（Primal–Dual Invariant-Carrying Frontier）**：

- 状态仍是 v9.0 的 $(L,U,s,m,\pi)$，不改变证书格式；
- 增加一个**对偶锚**：复用 PACT pin 的参数化 LP 矩阵和最后一次可行解，不额外求解；
- 增加一个**原始解码器**：marginal quantile/mean/latest/tail + dominator 键 + 随机重启，在 $L$ 处跑 SGS；
- 增加一个**缺陷驱动策略**：若解码命中，$U\leftarrow C_{\max}$；若未命中，问 $L$；NO 后 $L\leftarrow L+1$ 并重试解码；残差大时二分；
- 每次状态转移都调用 `PartialCertificate.audit_rdf()`，最终用 `ICFCertificate` 审计。

本轮的**可证伪预测**是：如果 PD-ICF 的收益只是“多试了几个随机顺序”，那么零 probe 命中应该只比 LPR 多一点点；如果“锚 + 解码”真的把精确 oracle 限制在缺陷上，那么弱语料的 probe 数应该从几百降到几十，且 `large_het 7` 这类 gap 大的实例应该由锚而不是随机顺序救回来。实验结果（见产物区）支持后者：弱语料 60 次 probe、102/160 零 probe；`large_het 7` 由 LP pin 抬到 41 后 1 次 probe 闭合。

## 七、这一轮最想保留的“负结果”

- **CFA 的 dominator 顺序只是小配角**：主语料 +1 次 probe，弱语料 0；不要把它包装成主创新。
- **显式参数化重锚是冗余的**：PACT 的 pin 已经做了同样的事；独立 `anchor()` 在这批语料上不改变 probe，反而多花 LP。
- **局部 repair 不是万能药**：300 次 SGS 的 swap/insertion 局部搜索没有带来额外命中；缺陷 1 的近失手不一定是“一次交换”。
- **energy shaving / forbidden 剪枝在 OPT 附近可能反效果**：84/252 的 NO 证明很强，但把它变成搜索剪枝并不自动更快。

## 八、当前方案最大的风险

**最大风险是：PD-ICF 的收益可能主要来自“这批语料的 LP 锚恰好把 L 抬到 OPT 附近 + SGS 在 L 处命中”，而不是一个在弱 LP 下也成立的普遍机制；如果 LP 松弛变弱，缺陷界会变宽，算法会退化成 v9.0 的精确 probe。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 产物区 · v9.3 PD-ICF：对偶锚、原始解码与缺陷驱动的部分证书前沿

## 0. 本轮产物与一句话结论

**PD-ICF**（Primal–Dual Invariant-Carrying Frontier）在 v9.0 ICF-PACT 的部分证书

\[
\mathcal C=(L,U,s,m,\pi),\qquad \pi:\mathrm{NO}(L-1),\quad C_{\max}(s)=U,\quad L\le U
\]

外面加了两层：

1. **对偶锚（ANCHOR）**：复用 PACT pin / `_pin_weak` 的参数化 LP 矩阵，把 $L$ 抬到 LP 阈值 $L^*$，并把 $\mathrm{NO}(L^*-1)$ 的 Farkas/energy/bound 证书装进 $\pi$；这部分不改变 v9.0 的证书格式。
2. **原始解码（ROUND）**：把 LP 解 $x^*$ 的 marginal 解码成 SGS 优先级，在 $L$ 处直接构造调度；命中则 $U\leftarrow C_{\max}(s')$，零次精确 probe 闭合。
3. **缺陷驱动（PROBE）**：解码失败时才问精确 oracle。问的是 $L$ 而不是原始下界；NO 后 $L\leftarrow L+1$ 并重试解码；残差大时才二分。

在 252 例主语料上，PD-ICF 用 **66 次 probe / 261 次搜索 LP / 133 次证书 LP / 273 次 pin LP = 667 次 LP / 9.05 s** 完成 252/252 认证；v9.0 `lower-first` 是 104 / 429 / 135 / 273 = 837 次 LP / 9.97 s。在 160 例弱语料（初始 gap 4–13）上，PD-ICF 用 **60 次 probe / 247 次搜索 LP / 120 次证书 LP / 269 次 pin LP = 636 次 LP / 5.94 s** 完成 160/160 认证；v9.0 `lower-first` 是 549 次 probe / 1662 次搜索 LP / 341 次证书 LP = 2003 次 LP / 12.63 s，但只有 159/160 完成（`base/large_het/7` 在 $h=39$ 返回 UNKNOWN）。PD-ICF 的 412 个实例全部通过 `ICFCertificate.audit_rdf()`，部分证书审计 356 + 366 次，0 失败。

**一句话结论**：PD-ICF 把 v9.0 的“精确 probe 前缀”改造成“对偶锚 → 原始解码 → 精确 probe”的三段式；弱语料的 probe 数从 549/421 降到 60，且此前唯一失败的 gap-13 实例由 LP 锚抬到 41 后 1 次 probe 闭合。

---

## 1. 问题、记号与状态

实例 $P=(n,m,p_i,est_i,D,M_i)$：$n$ 个任务，$m$ 台机器，加工时间 $p_i$，释放时间 $est_i$，precedence DAG $D$（$i\to j$ 表示 $i$ 完成后 $j$ 才能开始），机器资格 $M_i$。调度 $(s,m)$ 满足：

\[
s_i\ge est_i,\qquad s_j\ge s_i+p_i\ \ (i\to j),\qquad
\text{同一机器上的区间不重叠}.
\]

$C_{\max}(s)=\max_i(s_i+p_i)$，$\mathrm{OPT}=\min C_{\max}(s)$。

固定 horizon $h$ 的具体指称（denotation）是

\[
S_h=\{(s,m):\ (s,m)\ \text{可行},\ C_{\max}(s)\le h\}.
\]

LP 松弛的抽象指称是

\[
P_h=\{x:\ \text{时间索引 SD-LP 在 }h\text{ 下可行}\}.
\]

包含 $S_h\subseteq \gamma(P_h)$ 给出

\[
L^*=\min\{h:P_h\ne\varnothing\}\le \mathrm{OPT}.
\]

v9.0 的部分证书 $\mathcal C=(L,U,s,m,\pi)$ 保持如下不变量：

\[
\mathrm{(I1)}\ \pi\ \text{审计通过且证明}\ \mathrm{NO}(L-1);\qquad
\mathrm{(I2)}\ C_{\max}(s)=U,\ (s,m)\ \text{可行};\qquad
\mathrm{(I3)}\ L\le U.
\]

由 (I1)(I2) 立刻得到 $L\le\mathrm{OPT}\le U$。本轮不改这个状态，只改**如何从 LP 解得到 $U$**，以及**先问哪个 $h$**。

---

## 2. 语义：具体指称、抽象指称与缺陷

### 2.1 具体语义与抽象语义

把 $S_h$ 看成程序 $P$ 在 horizon $h$ 下的具体指称，$P_h$ 看成它的抽象指称。抽象是可靠的（sound）：

\[
S_h\ne\varnothing\ \Longrightarrow\ P_h\ne\varnothing.
\]

因此 $L^*\le\mathrm{OPT}$。v9.0 的 `SDLP`/`farkas_bounds` 在 $P_h=\varnothing$ 时给出 Farkas 证书，正是 $\mathrm{NO}(h)$ 的证明；`verify` 审计它。

### 2.2 解码器是部分收缩

解码器 $\rho_h:P_h\to S_h\cup\{\bot\}$ 把 LP 解变成整数调度。理想情况下 $\rho_h(\alpha_h(s))=s$；实际只能保证：

- 若 $\rho_h(x)\ne\bot$，则 $\rho_h(x)\in S_h$（由 `check_schedule` 和 $C_{\max}\le h$ 审计）；
- 否则 $\rho_h(x)=\bot$，抽象解没有被具体化。

定义 $x\in P_h$ 的**缺陷**为

\[
\delta_h(x)=
\begin{cases}
C_{\max}(\rho_h(x))-h, & \rho_h(x)\ne\bot,\\
+\infty, & \rho_h(x)=\bot.
\end{cases}
\]

若 $\delta_h(x)<\infty$，则

\[
L^*\le \mathrm{OPT}\le C_{\max}(\rho_h(x))=h+\delta_h(x).
\]

特别地，当 $h=L^*$ 时，$\mathrm{OPT}\le L^*+\delta_{L^*}(x)$。若 $\delta_{L^*}(x)=0$，则 $S_{L^*}\ne\varnothing$，$L^*=\mathrm{OPT}$，零次精确 probe；若 $\delta_{L^*}(x)=1$，一次 probe 即可闭合。**注意**：实现里报告的 `defect` 是 rounding 之后的残差宽度 $G=U-L$，不是 $\delta_h(x)$；当解码成功时 $G=\delta_h(x)$，当解码失败时 $G$ 只是括号宽度，$\delta_h(x)=+\infty$。产物中的 `defect_hist` 因此应读作“残差宽度 $G$ 的分布”。

### 2.3 为什么“锚 + 解码”比“probe + 修复”好

v9.0 的顺序是：先问 $L$，NO 后再抬 $L$，YES 后再降 $U$。PD-ICF 的顺序是：先用 LP 把 $L$ 抬到 $L^*$，再在 $L^*$ 处尝试构造调度。两者的区别在 `base/large_het/7` 上非常清楚（见第 7.3 节）：v9.0 在原始 $L=39$ 处问，返回 UNKNOWN；PD-ICF 先用 3 次 LP 把 $L$ 抬到 41，再在 41 处问，YES，1 次 probe 闭合。**锚不是装饰，它决定了精确 oracle 问哪个 $h$。**

---

## 3. 控制流分析：precedence DAG 的 dominator 树

### 3.1 定义与数据流方程

给 precedence DAG 加虚拟 source $src$ 和 sink $sink$：$src\to$ 所有无前驱任务，所有无后继任务 $\to sink$。定义

\[
dom(v)=\{v\}\cup\bigcap_{u\in pred(v)}dom(u),\qquad
pdom(v)=\{v\}\cup\bigcap_{w\in succ(v)}pdom(w),
\]

用 chaotic iteration 求不动点。$n\le21$，用 Python 整数位集表示集合；复杂度 $O(n^3/w)$（$w$ 为字长），在本语料上远小于一次 LP。

### 3.2 支配者的 must-precede 引理

**引理 3.1**：若 $i\in dom(j)$ 且 $i\ne j$，则从 $i$ 到 $j$ 存在一条路径，因此在任何可行调度中 $s_j\ge s_i+p_i$。

**证明**：$i$ 支配 $j$ 意味着从 $src$ 到 $j$ 的每条路径都经过 $i$；取其中一条，截取 $i$ 到 $j$ 的后缀即可。沿这条路径反复使用 precedence 约束即得。$\square$

于是按 $|dom(i)|$ 升序排列，$i$ 会排在 $j$ 前面；这是一个安全的 must-precede 优先级。post-dominator 给出对称的“离 sink 多近”键，但它不是 must-precede（$i\in pdom(j)$ 说明 $j$ 在 $i$ 前面），所以实现里只把它当 SGS 的启发式键，实际合法性由 `topo_order` 保证。

### 3.3 在 PD-ICF 中的用法

`decode_orders` 在 LP marginal 的 quantile/mean/latest/tail 之外，加入 6 个 CFA 键：

```
(cfa:dom-mean,       (|dom(i)|, mean_i, eps_i))
(cfa:pdom-mean,      (|pdom(i)|, mean_i, eps_i))
(cfa:dom-pdom-mean,  (|dom(i)|, |pdom(i)|, mean_i, eps_i))
(cfa:slack-mean,     (H - tail_i - p_i - est_i, mean_i, eps_i))
(cfa:dom-tail,       (-|dom(i)|, -tail_i, mean_i, eps_i))
(cfa:pdom-tail,      (-|pdom(i)|, -tail_i, mean_i, eps_i))
```

所有键都只用于 `topo_order` 的候选排序；`topo_order` 只从“前驱已排”的任务里选，因此无论键是什么，返回的都是合法拓扑序。CFA 的作用是让“必须早做”的任务在边际相近时优先，而不是替代 precedence 约束。

**诚实结论**：CFA 的命中数很少（弱语料 2 个、主语料 1 个）；弱语料的 probe 总数没有下降（60 vs 60），主语料只省 1 次 probe。LP marginal 已经编码了大部分 precedence 信息；CFA 是可解释的辅助顺序，不是本轮的性能主引擎。

---

## 4. 算法 PD-ICF

### 4.1 伪代码

```
PD-ICF(P, initial=None):
    if initial is None:
        (L,U,s,m,pi) <- PACT-fixed-point(P)        # includes LP pin
    else:
        (L,U,s,m,pi) <- PIN-WEAK(P, initial)        # LP anchor on weak state
    audit(L,U,s,m,pi)
    if L == U: return CERT(L,U,s,m,pi)

    # ANCHOR + GUIDE: reuse the parametric matrix left by the pin
    (ps, z) <- GUIDE-AT(L)                          # z is a feasible LP solution
                                                    # (may be at a larger horizon)
    # ROUND at L
    if DECODE(ps,z,L) = s' with Cmax(s') <= L:
        U <- Cmax(s'); audit; return CERT
    # RANDOM ROUND
    if DECODE-RANDOM(ps,z,L) = s' with Cmax(s') <= L:
        U <- Cmax(s'); audit; return CERT

    first <- True
    while L < U and probes < max_probes:
        h <- L if first else (L+U)//2
        first <- False
        r <- PACT-DECIDE(P,h)                        # exact fixed-h oracle
        if r.verdict == NO:
            L <- h+1; pi <- r.proof; audit
            if L < U: retry DECODE at L (deterministic + random)
        elif r.verdict == YES:
            U <- min(U, Cmax(r.schedule)); s,m <- r.schedule; audit
        else:
            break                                    # UNKNOWN: keep partial cert
    return CERT if L==U else PARTIAL-CERT
```

### 4.2 对偶锚

- 主语料：`PACT(inst, pact_mode='complete', use_ga=False).initial_bounds()` 已经完成 LP pin，`co.pin` 里保留 `param`（参数化矩阵）和 `last_res`（最后一次可行 LP 解）。
- 弱语料：`_pin_weak` 用 PACT 的 LP pin 把 `init_weak` 的 $L$ 抬高；若 `co.pin['last_res']` 存在就直接复用，否则在 $L$ 处补一次 `ps.solve_h(L)`。弱语料 160 例中 52 例补了这一次 LP（`pin_lp` 269 vs anchor-only 217）。
- 独立的 `anchor()`（二分 + `farkas_bounds` + `FarkasPin`）也实现了，但在本语料上与 PACT pin 等价且更贵，因此主实验不调用它；它保留为可移植模块和消融对照。

### 4.3 原始解码器

`decode_orders` 的确定性顺序族：

- LP marginal 的分位数 $q\in\{0.02,0.1,0.25,0.5,0.75,0.9,0.98\}$；
- mean、latest、tail；
- 6 个 CFA 键（第 3.3 节）。

每个顺序用 `topo_order` 变成合法拓扑序，再用 `sgs` 在 horizon $L$ 上构造调度；`sgs` 返回 $(s,m,C_{\max})$，只有 $C_{\max}\le L$ 且 `check_schedule` 通过才接受。确定性失败后，`decode_random` 做最多 50 次随机重启（4 种分布，时间上限 0.08 s），每次仍是合法拓扑序 + SGS。局部 swap/insertion repair 也实现了（`local_search`），但主实验关闭；见第 7.5 节的负结果。

### 4.4 缺陷驱动的 probe 策略

- 解码命中：直接闭合，零 probe。
- 解码失败：问 $h=L$（不是原始下界）。NO 则 $L\leftarrow L+1$，在新 $L$ 上重试解码；YES 则用返回的调度降 $U$。
- 若仍然 $L<U$，下一次问 $(L+U)//2$。
- 每个状态都调用 `PartialCertificate.audit_rdf()`；最终用 `ICFCertificate.audit_rdf()`。

实现文件：`exp/v8u/pdicf.py`（算法）、`exp/v8u/bench_pdicf.py`（实验）。

---

## 5. 复杂度分析

设 $T_{\mathrm{LP}}$ 为一次 SD-LP 求解，$T_{\mathrm{SGS}}$ 为一次 SGS 解码，$T_{\mathrm{decide}}(h)$ 为一次固定 $h$ 精确判定，$K$ 为确定性顺序数（约 12 + 6 CFA），$R$ 为随机重启数（≤50），$q$ 为精确 probe 数。

- **锚**：PACT pin 的 LP 由初始化器承担；PD-ICF 额外最多一次 `ps.solve_h(L)`。独立 `anchor()` 是 $O(\log(U-L))$ 次参数化 LP。
- **解码**：$O((K+R)\cdot(T_{\mathrm{topo}}+T_{\mathrm{SGS}}))$，其中 $T_{\mathrm{topo}}=O(n\log n)$，$T_{\mathrm{SGS}}=O(nm+n\log n)$。
- **精确 probe**：$q\cdot T_{\mathrm{decide}}(h)$；在缺陷小的时候 $q=O(\delta)$，在残差大时退化为 $O(\log(U-L))$ 二分。
- **总**：

\[
O\!\left(\log(U-L)\cdot T_{\mathrm{LP}}+(K+R)\cdot T_{\mathrm{SGS}}+q\cdot T_{\mathrm{decide}}\right).
\]

- **空间**：LP 的 $O(nm)$ 变量、dominator 位集的 $O(n^2/w)$、调度/证书的 $O(n)$；本语料 $n\le21$，内存不是瓶颈。

**关键点**：PD-ICF 不试图降低单次 `pact_decide` 的复杂度；它降低的是**调用次数**。在弱语料上，`pact_decide` 的搜索 LP 从 1662 降到 247（−85%），证书 LP 从 341 降到 120（−65%）。

---

## 6. 正确性

**引理 6.1（初始不变量）**：`PACT`/`_pin_weak` 返回的 $(L,U,s,m,\pi)$ 满足 (I1)–(I3)。`_pin_weak` 只在 `p.audit_rdf()` 通过时才把 $L$ 抬到 `Lp`，因此 $\pi$ 仍然证明 $\mathrm{NO}(L-1)$。

**引理 6.2（锚的可靠性）**：若 `_pin_weak` 把 $L$ 从 $L_0$ 抬到 $L_1>L_0$，则存在审计通过的证明 $\pi_1$ 证明 $\mathrm{NO}(L_1-1)$，因此 $L_1\le\mathrm{OPT}$。

**引理 6.3（解码的可靠性）**：若 `DECODE` 返回 $(s',m')$ 且 $C_{\max}(s')\le h$，`check_schedule(P,C_{\max}(s'),s',m')` 通过，则 $(s',m')\in S_h$，故 $\mathrm{OPT}\le h$。

**引理 6.4（probe 的可靠性）**：若 `PACT-DECIDE(P,h)` 返回 NO 且 `proof` 审计通过，则 $S_h=\varnothing$，$\mathrm{OPT}>h$；若返回 YES 且调度通过 `check_schedule`，则 $\mathrm{OPT}\le C_{\max}\le h$。

**定理 6.5（不变量保持与终止）**：每次循环保持 (I1)–(I3)；NO 使 $L$ 严格增加，YES 使 $U$ 严格减小，UNKNOWN 不改变状态；$U-L$ 每次严格下降，故无预算版本终止。终止时 $L=U=\mathrm{OPT}$，最终的 `ICFCertificate` 通过 `audit_rdf()`，即得到最优性证书。若预算耗尽，返回的仍是满足 (I1)–(I3) 的部分证书。

**引理 6.6（CFA 合法性）**：`topo_order` 只从“所有前驱已排”的任务中选择；任何返回的序列都是 precedence DAG 的拓扑序，因此作为 SGS 优先级是合法的。支配者键只影响候选的优先级，不会绕过 precedence 约束。

**审计覆盖**：主语料 252 次初始状态 + 66 次 probe 后 + 38 次 rounding 后 = 356 次部分证书审计，0 失败；弱语料 160 次初始 + 60 次 probe 后 + 146 次 rounding 后 = 366 次，0 失败。最终 252/252 + 160/160 `ICFCertificate` 通过。

---

## 7. 实验

### 7.1 语料与口径

- **主语料 252**：`base=141, pert=60, stress=51`；初始 gap 分布 148 个 0、103 个 1、1 个 5（`base/large_het/7`）。stress 的 51 行是 26+25 个不同加工时间的扰动，不能按 `name/idx` 去重。
- **弱语料 160**：`hap.weak_rows(4)`，初始 gap 4–13，分布 `{4:47,5:37,6:31,7:32,8:8,9:2,10:1,11:1,13:1}`；`base=61, pert=54, stress=45`。LP pin 后残差分布 `{0:4,1:10,2:19,3:37,4:20,5:38,6:28,9:3,11:1}`。
- **LP 计数**：`pin LP` 是初始化器/PACT pin 的 LP；`search LP` 是精确 `pact_decide` 的搜索 LP；`cert LP` 是精确 probe 内的证书 LP；`总 LP = pin + search + cert`。v9.0 的弱语料基准 `pin_lp=0`，所以总 LP 是 `pact_lp + pact_cert_lp`。
- **时间**：同一台机器、同一套 Python 环境、单次运行；只用于量级比较，不作为严格计时基准。
- **审计**：`partial_ok/partial_fail` 是 `PartialCertificate.audit_rdf()` 的通过/失败次数；最终 `certified` 是 `ICFCertificate.audit_rdf()` 通过且 $L=U=\mathrm{known}$。

### 7.2 主语料 252

| 方法 | probes | 搜索 LP | 证书 LP | pin LP | 总 LP | 时间 | 部分审计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v9.0 `lower-first` | 104 | 429 | 135 | 273 | 837 | 9.97 s | 356 / 0 |
| v9.0 `binary` | 106 | 468 | 140 | 273 | 881 | 11.01 s | 358 / 0 |
| LPR `rand`（前序） | 69 | 271 | 133 | 273 | 677 | 9.20 s | 356 / 0 |
| PD-ICF anchor-only | 104 | 429 | 135 | 273 | 837 | 10.74 s | 356 / 0 |
| PD-ICF det | 79 | 323 | 134 | 273 | 730 | 9.78 s | 356 / 0 |
| PD-ICF rand, no CFA | 67 | 273 | 133 | 273 | 679 | 9.39 s | 356 / 0 |
| **PD-ICF rand + CFA** | **66** | **261** | **133** | **273** | **667** | **9.05 s** | **356 / 0** |
| PD-ICF seed 1000 | 64 | 254 | 133 | 273 | 660 | 9.34 s | 356 / 0 |
| PD-ICF seed 2000 | 64 | 254 | 133 | 273 | 660 | 9.11 s | 356 / 0 |

残差宽度 $G$：186 个 0、65 个 1、1 个 5；probe 分布：186 个 0、66 个 1。CFA 相比 no-CFA 只省 1 次 probe；随机重启相比 det 省 13 次 probe、62 次搜索 LP。

### 7.3 弱语料 160

| 方法 | probes | 搜索 LP | 证书 LP | pin LP | 总 LP | 时间 | 完成/审计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v9.0 `lower-first` | 549 | 1662 | 341 | 0 | 2003 | 12.63 s | 159/160, 708/0 |
| v9.0 `binary` | 421 | 1581 | 248 | 0 | 1829 | 14.95 s | 160/160, 581/0 |
| LPR `rand`（前序） | 70 | 284 | 119 | 257 | 660 | 5.95 s | 160/160, 365/0 |
| PD-ICF anchor-only | 266 | 1085 | 123 | 217 | 1425 | 10.19 s | 160/160, 426/0 |
| PD-ICF det | 87 | 409 | 122 | 269 | 800 | 7.24 s | 160/160, 370/0 |
| PD-ICF rand, no CFA | 60 | 247 | 120 | 269 | 636 | 5.96 s | 160/160, 366/0 |
| **PD-ICF rand + CFA** | **60** | **247** | **120** | **269** | **636** | **5.94 s** | **160/160, 366/0** |
| PD-ICF seed 1000 | 60 | 247 | 120 | 269 | 636 | 5.97 s | 160/160, 366/0 |
| PD-ICF seed 2000 | 59 | 230 | 116 | 269 | 615 | 5.52 s | 160/160, 366/0 |

残差宽度 $G$：102 个 0、4 个 1、4 个 2、16 个 3、7 个 4、8 个 5、18 个 6、1 个 11；probe 分布：102 个 0、57 个 1、1 个 3。三个种子的 probe 数为 60 / 60 / 59，总 LP 为 636 / 636 / 615，说明随机重启的方差很小。

**`base/large_het/7` 案例**（弱语料唯一 gap-13 实例）：

```
raw init:      L=39, U=52, OPT=41
LP pin:        3 LP  ->  L=41, proof at h=40 (energy)
rounding:      deterministic (16 orders) + 50 random restarts -> no schedule
probe at L=41: YES, Cmax=41, 17 search LP + 4 cert LP
total:         1 probe / 24 LP / 0.69 s
```

v9.0 `lower-first` 在这例上问 $h=39$，返回 UNKNOWN，因此 159/160。PD-ICF 的锚先把 $L$ 抬到 41，再问 41，问题变成“在 OPT 处构造一个调度”，而不是“在低于 OPT 处证明不可行”。这是本轮最有说服力的单例。

### 7.4 消融：锚、解码、CFA

- **锚-only → 锚 + 解码**：弱语料 266 → 60 probes（−77%），1425 → 636 总 LP（−55%）；主语料 104 → 66 probes（−37%），837 → 667 总 LP（−20%）。解码是主要收益来源。
- **det → rand**：弱语料 87 → 60 probes（−31%），800 → 636 总 LP（−20%）；主语料 79 → 66 probes（−16%），730 → 667 总 LP（−9%）。随机重启在确定性 quantile 之外补上了约 1/3 的零 probe 命中。
- **no CFA → CFA**：弱语料 60 → 60 probes（0），636 → 636 总 LP（0）；主语料 67 → 66 probes（−1），679 → 667 总 LP（−2%）。CFA 的贡献可忽略。
- **显式参数化重锚**：独立 `anchor()` 在主语料上与 PACT pin 给出相同的 $L$，但多花 LP；在弱语料上它甚至可能把 $L$ 抬到与 `_pin_weak` 不同的位置，未带来 probe 收益。因此主实验不调用它；它只作为可移植实现保留。

### 7.5 负结果

1. **energy/window 抬下界（早期原型）**：`energy_cert` 在 $h=\mathrm{OPT}-1$ 能证 84/252 个 NO（74 energy + 10 window），168 个未知；没有把任何一例的域删空。它是有用的 NO 证明，但不是本轮的上界引擎。
2. **forbidden 剪枝（早期原型）**：把 shave 后的 forbidden 传给 `pact_decide`，在 $h=\mathrm{OPT}-1$ 无收益（根节点本来 1 次 LP），在 $h=\mathrm{OPT}$ 有时更差（holdout 1：2→5 个节点）。**CFA/剪枝可以帮倒忙**。
3. **dominator 顺序（前序 LPR 原型）**：弱语料 base 命中 70，额外 dominator 命中 23，union 72（仅 +2）；主语料 80 例样本 base 7、extra 3、union 7（无额外命中）；12 例 `noguide`。LP marginal 已经很强，CFA 只是小配角。
4. **局部 repair**：300 次 SGS 的相邻 swap + insertion 局部搜索没有带来额外命中；缺陷 1 的近失手不一定是“一次交换”。`local_search` 保留为诊断工具，主实验关闭。
5. **显式重锚**：见 7.4；不是性能来源，反而多花 LP。

### 7.6 与前序算法的关系

| 算法 | 弱语料 queries | 记录 LP | 说明 |
|---|---:|---:|---|
| TA-ICF（前序） | 205 | 773 `pact_lp` + 123 `pact_cert_lp` + 586 prescan + 142 anchor cert = 1624 | 口径含 threshold prescan，不能与 PD 的 636 直接逐项比 |
| WICF（前序） | 157 | 375 `pact_lp` + 213 `pact_cert_lp` | primal repair 路线，LP 少但 queries 多 |
| HAP（前序） | 421 | 1581 `pact_lp` + 248 cert | hash-consed memo，时间 8.99 s |
| LPR（前序） | 70 | 660 total | 与 PD 同一 pin/search/cert 口径 |
| **PD-ICF** | **60** | **636 total** | 与 LPR 同口径 |

PD-ICF 相对 LPR 的增益不大（60 vs 70 probes，636 vs 660 LP），这是诚实的：**本轮真正的大头是把 v9.0 的 549/421 probes 降到 60，而不是把 LPR 的 70 降到 60。** LPR 已经证明了 LP rounding 的价值；PD-ICF 把“锚 + 解码 + 缺陷”组织成一个完整的、可审计的控制器，并在弱语料上补齐了 LPR 的 `noguide`/近失手情况。

---

## 8. 这一轮真正的新东西

1. **语义分解**：把 v9.0 的单一括号拆成“对偶锚 $L^*$ + 原始解码 $\rho$ + 缺陷 $\delta$”，并给出 $L^*\le\mathrm{OPT}\le L^*+\delta$ 的界。这个分解让“LP 解能不能构造上界”成为可测的问题，而不是哲学讨论。
2. **控制顺序**：`ANCHOR → ROUND → PROBE`，而不是 v9.0 的 `PROBE → 根据结果抬/降`。`large_het 7` 说明顺序本身就是算法的一部分。
3. **缺陷驱动**：解码成功时零 probe；失败时只问 $L$，NO 后重试解码；残差大时才二分。这把精确 oracle 的调用次数从“gap 的函数”变成“解码器缺陷的函数”。
4. **可审计性**：所有中间状态仍是 v9.0 的 `PartialCertificate`，所有最终状态是 `ICFCertificate`；412/412 通过，0 失败。新算法没有引入新的证书类型。
5. **诚实的 CFA**：dominator/post-dominator 顺序实现了、解释了、也测了；它只贡献 1 个主例 probe，不足以称为主创新。这个负结果本身是产物的一部分。

**范围说明**：本轮实现的是**单叶特化**（一个括号 $(L,U,s,m,\pi)$），不是多叶 frontier；名称里的 “Frontier” 指它沿用的 v9.0 证书格式与语义，不表示本轮新增了多叶搜索。多叶 frontier 与割循环仍未在本轮展开。

---

## 9. 风险与限制

1. **LP 锚的依赖性**：PD-ICF 的收益主要来自 LP pin 已经把 $L$ 抬到 $L^*$。如果 LP 松弛很弱（$L^*\ll\mathrm{OPT}$），锚的作用会变小，算法退化为“SGS + 精确 probe”。
2. **解码的分布依赖性**：弱语料 102/160 零 probe 很漂亮，但这是 `n≤21, m=3` 的语料；更大规模、更多机器、更复杂 eligibility 下，SGS 近失手可能更多，随机重启的收益会下降。
3. **`noguide` 与额外 LP**：`_guide_at` 在 `co.pin['last_res']` 缺失时会补一次 `ps.solve_h(L)`；弱语料有 52 例这样，增加了 pin LP。若 LP 很贵，这会抵消 probe 的节省。
4. **CFA 的弱贡献**：dominator 顺序在弱语料 0 个额外 probe，在主语料 1 个。不要把它当作主要卖点。
5. **局部 repair 未解决缺陷 1**：300 次 SGS 的 swap/insertion 没有带来额外命中；如果未来要追求“零 probe”，需要更强的 primal repair 或更强的 LP（cuts），而不是继续加随机顺序。
6. **时间不是稳定优势**：主语料 9.05 s vs v9.0 9.97 s，弱语料 5.94 s vs 12.63 s；时间受机器负载和单次运行影响，LP 计数更可靠。
7. **`known` 只用于离线验收**：生产环境应看 `certified`、`audit`、`partial_final`、`cert_h`；不要用 `known` 判断正确性。
8. **弱语料是构造出来的**：`weak_rows(4)` 是从 252 例里筛出初始 gap≥4 的子集，不是独立分布；它衡量“大 gap 上的行为”，不等于真实 workload 的泛化。
9. **审计信任基**：`verify`、`check_schedule`、`_domain`、`SDLP` 的数值容差仍是信任基；412 例通过不代表病态 LP 下也通过。
10. **实现的 `defect` 字段是 $G=U-L$**，不是 $\delta_h(x)$；读表时不要把 $G$ 当成 probe 数的上界。`large_het 7` 的 $G=11$ 但只用了 1 次 probe，因为 probe 在 $L$ 处直接 YES。

---

## 10. 最大风险（一句话）

**最大风险是：PD-ICF 的收益主要来自“这批语料的 LP 锚恰好把 $L$ 抬到 OPT 附近 + SGS 在 $L$ 处命中”；在 LP 松弛较弱、或 SGS 近失手需要多步修复的分布上，它会退化成 v9.0 的精确 probe，缺陷界也会变宽。**

---

## 11. 本轮结论（1–2 句）

**PD-ICF 把 v9.0 的精确 probe 前缀改造成“对偶锚 → 原始解码 → 精确 probe”的三段式：252 例用 66 probes / 667 LP / 9.05 s、160 弱例用 60 probes / 636 LP / 5.94 s 全部认证，412/412 审计通过；其中弱语料此前唯一失败的 gap-13 实例由 LP 锚抬到 41 后 1 次 probe 闭合。CFA 只贡献 1 个主例 probe，真正的主力是 LP 锚与 SGS 解码。**
<!-- ARTIFACT:END -->
