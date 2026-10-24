# 玄 · 设计一个新的算法

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 一、上一轮留下的不是「不够强」，而是「不知道离最优多远」

v8.0 BRC-ALC 已经把固定 $h$ 的双向归约做得很完整：NO 侧有 QSP 探针、Farkas 证书、row-core 恢复和 fail-stop 分裂；YES 侧有根 LP 分布采样、串行 SGS、有界 DFS 和独立重放，141/141 个 YES 全部闭合。它真正的缺口不在某一个方向，而在**两个方向之间没有共同的度量**：

- NO 证明回答「$h$ 不可行」；
- YES 构造回答「$h$ 可行」；
- 但没有人回答「当前这个上界离 $\mathrm{OPT}$ 还有多远」。

v8.0 的已知风险也正好落在这里：YES 构造器是随机化、有界节点的，60k 节点之外不保证找到调度；NO 侧仍依赖 SD 割，根 LP 的 lazy 分离若耗尽预算就只能返回 UNKNOWN。换句话说，算法知道自己「证明了什么」，但不知道「还差多少」。

本轮灵感词是 **竞争比 / 凸包 / preprocessing**。我第一反应不是再加强某一条割，而是把这三个词接到同一个对象上：

> 可行 makespan 的集合是 $[\mathrm{OPT},\infty)$。它的凸包下端点就是 $\mathrm{OPT}$。  
> 我们用一个证书区间 $[\mathrm{LB},\mathrm{UB}]$ 包住这个端点；  
> **竞争比** $\rho=\mathrm{UB}/\mathrm{LB}$ 就是这个区间有多宽；  
> **preprocessing** 就是把这个区间压窄；  
> **凸包** 则是「用什么几何对象去压」的问题。

于是本轮算法叫 **CRISP-ALC（Competitive-Ratio Interval Shrinking Preprocessing）**：它不替代 v8.0 的固定 $h$ oracle，而是在 oracle 外面加一层「证书区间 + 预处理收缩 + 二分调用」的外壳。

## 二、第一次试错：高维 LP 投影盒太松

我最初把「凸包」理解成 LP 可行域的坐标投影：

\[
P(h)=\{z\ge 0: Az\le b,\ Ez=\mathbf 1\},\qquad
\pi_i(P(h))=[\mathrm{lo}_i(h),\mathrm{hi}_i(h)].
\]

因为每个整数可行调度都是 LP 可行的，所以它的开始时间向量必在盒

\[
H(h)=\prod_i[\mathrm{lo}_i(h),\mathrm{hi}_i(h)]
\]

里。这个盒子是**严格可靠**的：用它做域收缩不会删掉任何可行调度；如果 $\mathrm{lo}_i=\mathrm{hi}_i$，还可以把 $s_i$ 固定。理论上它应该能减少 SGS 的分支。

我在 `exp/v8c/chip.py` 里实现了 `hull_projection`，对 7 个 hard YES 做了投影盒 + 有界 LDS 的试验。结果是负的：

| 实例 | 盒宽 $\sum_i(\mathrm{hi}_i-\mathrm{lo}_i)$ | 盒 LDS 节点 | 结果 |
|---|---:|---:|---|
| holdout 35 | 100.0 | 65,411 | 找到 |
| large_a 5 | 135.3 | 70,659 | 4 层差异内失败 |
| large_het 0 | 179.5 | 718 | 找到 |
| large_het 3 | 261.0 | 12,634 | 找到 |
| large_het 7 | 250.3 | 98,491 | 4 层差异内失败 |
| hard3 4 | 185.6 | 33 | 找到 |
| large_b 1 | 251.8 | 681 | 找到 |

盒宽在 100–261 个时间单位之间，远大于实例的 $h$（30–41）。原因很朴素：LP 允许大量「分数拼接」的开始时间，坐标投影把这些分数可能性全都包进来，盒子自然很宽。盒 LDS 在 2/7 个 hard 实例上失败，而 CHD 在同一批实例上全部闭合（10–28 次 LP）。

这是一个有用的负结果：**LP 投影盒是可靠的，但不是紧的；把凸包当硬域约束，收益不足以抵消投影的 $2n$ 次 LP。**

## 三、第二次试错：投影尾界也太弱

退一步，不把投影盒当域，而是把它当**下界**。对任意 LP 可行解，$s_i\ge \mathrm{lo}_i$；再沿优先序的尾长 $q_i$，得到

\[
\mathrm{LB}_{\mathrm{hull}}(h)=\max_i\bigl(\mathrm{lo}_i(h)+p_i+q_i\bigr).
\]

这是严格下界：任取最优调度 $s^\ast$，它在 $h=\mathrm{UB}$ 处 LP 可行，所以 $s_i^\ast\ge \mathrm{lo}_i$，于是 $\mathrm{OPT}\ge s_i^\ast+p_i+q_i\ge \mathrm{lo}_i+p_i+q_i$。

我在 141 个 base 实例上、$h=\mathrm{UB}$ 处算了这个界：只有 4/141 个实例把 LB 抬高 1，0 个超过已知 OPT；12 个实例上它等于 OPT，但在其余实例上普遍弱于既有的 critical-path + eligibility-load 下界。也就是说，**投影尾界没有提供新的容量信息**；它只是把 critical path 的 $s_i\ge \mathrm{est}_i$ 换成了 $s_i\ge \mathrm{lo}_i$，而 $\mathrm{lo}_i$ 往往只比 $\mathrm{est}_i$ 大一点点。

两次负结果指向同一个结论：**高维凸包在这个问题上的信息密度太低。真正值得维护的凸包是一维的。**

## 四、把凸包降到一维：证书区间

可行 makespan 集合的凸包是 $[\mathrm{OPT},\infty)$。我们不需要知道高维开始时间向量的形状，只需要维护一个证书区间

\[
\mathrm{LB}\le \mathrm{OPT}\le \mathrm{UB}.
\]

- $\mathrm{LB}$ 由两类东西支撑：critical path / eligibility load，或在 $h=\mathrm{LB}$ 处的一张可重放的 NO 证书（window 或 energy）。
- $\mathrm{UB}$ 由一张通过 `check_schedule` 的调度支撑。
- 竞争比定义为 $\rho=\mathrm{UB}/\mathrm{LB}$。它不是在线算法的竞争比，而是**当前 incumbent 相对证书下界的近似比**；$\rho=1$ 时 incumbent 被证明最优。

这个一维凸包有一个很好的性质：**它是可操作的**。每次在 $h$ 处得到一个 NO，就把 $\mathrm{LB}$ 推到 $h+1$；每次得到一个 YES，就把 $\mathrm{UB}$ 压到该调度的实际 makespan。二分搜索每次把区间宽度减半，于是

\[
W_t\le \left\lceil \frac{W_0}{2^t}\right\rceil,\qquad
\rho_t\le 1+\frac{W_0}{2^t\,\mathrm{LB}_0}.
\]

这就是本轮的「竞争比」：不是事后评价，而是**预算分配和终止条件的坐标**。

## 五、preprocessing：两个算子，一个耦合

一维区间要靠 preprocessing 压窄。我用了两个算子，都很便宜：

### 5.1 UB drop：多订单 greedy

CAB 原来只用 est 顺序做一次 greedy。我改成 4 个确定性订单：

- `est`：最早开始；
- `latest`：最晚开始；
- `tail`：按尾长 $-q_i$；
- `mixed`：$\mathrm{est}_i-0.5q_i$。

每个订单跑一次串行 SGS，得到调度后立刻用 `check_schedule` 重放；只有重放通过且 makespan 更小才更新 UB。252 个实例中，201 个实例的 UB 被至少一个订单压低。

### 5.2 LB lift：energy / window NO

在 $h=\mathrm{LB}$ 处跑 SCALE 的 window 和 energy 过滤：

- window：$\mathrm{est}_i>\mathrm{latest}_i$；
- energy：对机器子集 $M$ 和时间区间 $[a,b)$，所有只能落在 $M$ 上的任务的强制重叠之和超过 $|M|(b-a)$。

一旦命中，就用 `verify_prep` 重放证书；验证通过才 $\mathrm{LB}\leftarrow h+1$。252 个实例上共触发 174 次 LB lift，全部证书验证通过。

### 5.3 顺序很重要

我先 UB drop，再 LB lift。原因是 LB lift 的循环上界是 UB：

- 先降 UB，LB 可以多爬几步；
- 先升 LB，UB 没变，energy 循环会更早停下。

消融实验（252 例，预测二分深度）很清楚地显示了这种耦合：

| 变体 | 区间宽度和 | $\rho=1$ 实例 | 预测二分深度 |
|---|---:|---:|---:|
| 无预处理 | 1069 | 11 | 558 |
| 只 LB lift | 895 | 11 | 538 |
| 只 UB drop | 478 | 50 | 303 |
| **两者** | **304** | **58** | **254** |

UB drop 是主驱动；LB lift 单独几乎不减少查询（558→538），但和 UB drop 合起来额外减少 49 次（303→254）。这就是「竞争比」的耦合：**下界提升只有在 上界已经被压低时才会兑现**。

## 六、实验：252 例上把区间压到 1/3

数据与 v8.0 相同：141 个 base YES/NO + 60 个扰动 + 51 个压力集，共 252 例；NO 取 $h=\mathrm{OPT}-1$，YES 取 $h=\mathrm{OPT}$。外层用 CAB 的 certified anytime bracket，内层分别用 CAB oracle 和 CHD oracle。

| 方法 | 认证 | 查询 | LP | YES 节点 | Markov | 墙钟 |
|---|---:|---:|---:|---:|---:|---:|
| CAB v9.0 | 252 | 560 | 3119 | 65,558 | 12,300 | 21.27 s |
| CRISP bounds + CAB | 252 | 336 | 1324 | 64,504 | 5,900 | 6.32 s |
| **CRISP + CHD** | **252** | **337** | **1403** | **64,039** | **0** | **7.27 s** |

查询减少 40%，LP 减少 55%，墙钟减少 66%。`64k` 的 YES 节点主要由压力集的一个 60k 上限实例贡献；只看 base+pert，YES 节点从 5,188 降到 4,038（−22%）。

区间本身：

| 语料 | $\mathrm{LB}_0$ | $\mathrm{UB}_0$ | $W_0$ | $\rho_0$ 均值 | $\mathrm{LB}$ | $\mathrm{UB}$ | $W$ | $\rho$ 均值 | $\rho=1$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base 141 | 3902 | 4388 | 486 | 1.129 | 4003 | 4144 | 141 | 1.032 | 55 |
| pert 60 | 1924 | 2249 | 325 | 1.168 | 1955 | 2045 | 90 | 1.046 | 3 |
| stress 51 | 1625 | 1883 | 258 | 1.158 | 1667 | 1740 | 73 | 1.044 | 0 |
| **总** | **7451** | **8520** | **1069** | **1.144** | **7625** | **7929** | **304** | **1.038** | **58** |

最大竞争比从 1.333 降到 1.122。58 个实例在调用任何 oracle 之前就已经 $\mathrm{LB}=\mathrm{UB}=\mathrm{OPT}$。

正确性方面：174 张 energy 证书全部通过 `verify_prep`；252/252 个区间满足 $\mathrm{LB}\le\mathrm{OPT}\le\mathrm{UB}$；252/252 个最终结果通过 `audit` 和 `proof_complete`，且 $h_{\mathrm{cert}}=\mathrm{OPT}-1$。没有出现「无证书的 NO」或「未重放的 YES」。

## 七、凸包到底留下了什么

我没有把高维凸包完全扔掉，而是把它降级为**顺序 oracle**：

- `hull_projection` 仍然保留，默认关闭；
- CHD 的 `hull:lo` 仍然是 phase B1 的一个候选顺序；
- 在 141 个 YES 上，CHD 的 full 配置只有 16 次 hull LP、1 次 hull 闭包；`no_hull` 也能 141/141，只是多 1 次 random fallback。`hull_only` 则要 719 次 hull LP、449,813 个 LDS 节点、13.72 s。

所以本轮的判断是：**高维凸包是一个可靠的 fallback，不是主引擎；一维证书区间才是主引擎。** 这比强行说「凸包带来了提升」更诚实，也更符合实验。

## 八、这一轮学到的东西

1. **竞争比可以不是评价指标，而是坐标系**：一旦把 $\mathrm{UB}/\mathrm{LB}$ 当成状态，预处理的目标就从「找更强的割」变成「把区间压窄」，预算分配也有了明确的对象。
2. **凸包要选对维度**：高维 LP 投影盒可靠但太松；一维 makespan 区间才是信息密度最高的凸包。
3. **预处理算子之间有耦合**：UB drop 和 LB lift 不是两个独立开关；先降 UB 再升 LB，才能把 energy 过滤的潜力兑现。
4. **负结果可以保留为组件**：投影盒和投影尾界都没有带来主收益，但它们的代码和消融保留了，后续如果换更大的实例或更强的割，可以重新评估。
5. **认证边界不变**：区间只是搜索的导航；最终 YES 仍由 `check_schedule` 确认，NO 仍由 Farkas/clause/energy 证书确认。CRISP 不把「区间里的点」当成证据。

## 九、一句话最大风险

**CRISP 的收益完全取决于预处理能否在预算内把 $[\mathrm{LB},\mathrm{UB}]$ 压窄；如果 energy/window 规则打不中，且 4 个 greedy 订单都找不到更优上界，区间仍然会很宽，后续 oracle 调用数会退化到 CAB 水平甚至更多。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## 0. 版本关系与本轮增量

本轮产物是 **v8.1 CRISP-ALC（Competitive-Ratio Interval Shrinking Preprocessing）**，它建立在 v8.0 BRC-ALC 之上，但不修改 v8.0 的固定 $h$ 判定器：

- **v8.0 BRC-ALC**：给定 $h$，用 QSP 探针、Farkas 证书、row-core 恢复、fail-stop 分裂和随机化 YES 构造器回答「$h$ 是否可行」。它的证书语义和 `check_schedule` 语义是本轮的地基。
- **v9.0 CAB-MC**：在 v8.0 外面加 certified anytime bracket，用 archive/Markov 构造器闭合 YES 侧；这是本轮的直接对照基线。
- **v9.1 CHD**：确定性 LDS 判定器，用 phase A（根 LP 的整数解）、cheap 顺序和 hull 顺序替代随机构造器；这是 CRISP 的默认内层 oracle。
- **v8.1 CRISP-ALC**：在 CAB 的外层 bracket 之前再加一层预处理，用可重放的 window/energy NO 证书抬升 LB、用 4 个 greedy 订单压低 UB，把 $[\mathrm{LB},\mathrm{UB}]$ 压窄后再调用内层 oracle。

因此本轮不是「替换 v8.0」，而是「给 v8.0/v9.0 换一个更窄的搜索区间」。`CRISP` 只继承并覆盖 `CABOpt` 的两个钩子：

```python
class CRISP(CABOpt):
    def initial_bounds(self): ...   # 返回预处理后的 LB, UB, schedule, machine
    def _decide(self, h): ...       # 返回 CHD 的 YES/NO/UNKNOWN
```

`optimize()`、`_result()`、`audit`、`proof_complete`、`check_schedule` 全部继承，因此外层 bracket 的正确性论证与 v9.0 相同，新增的只有预处理部分的可靠性。

复用模块：

- `exp/v8a/rdf.py`：`RDF`、`check_schedule`；
- `exp/v76/qsp.py`：`QSP`；
- `exp/v9b/chd.py`：`CHD`；
- `exp/v9c/scale.py`：`energy_cert`、`windows`、`verify_prep`；
- `exp/v9d/cab.py`：`CABOpt`、`CAB`、`_greedy_rank`；
- `exp/v8a/lazy.py`：`LazySD`（仅用于可选的 hull projection）。

新增文件：

- `exp/v8c/chip.py`：本轮的 CRISP-ALC 实现；
- `exp/v8c/bench_chip.py`：三组语料的主实验；
- `exp/v8c/bench_bounds.py`：bracket 统计、消融、证书验证；
- `exp/v8c/bench_chip.json`、`exp/v8c/bench_bounds.json`：原始结果。

## 1. 符号

| 符号 | 含义 |
|---|---|
| $I=(J,M,E,p,q,\mathrm{elig})$ | 调度实例 |
| $n,m$ | 任务数、机器数 |
| $p_i$ | 任务 $i$ 的加工时间 |
| $q_i$ | 任务 $i$ 的尾长（交付时间） |
| $\mathrm{est}_i$ | 任务 $i$ 的最早开始时间（heads） |
| $\mathrm{latest}_i(h)=h-q_i-p_i$ | 在 makespan $\le h$ 的调度中 $i$ 的最晚开始时间 |
| $s_i,C_i=s_i+p_i$ | 开始时间、完成时间 |
| $C_{\max}(s)=\max_i(s_i+p_i+q_i)$ | 调度 $s$ 的 makespan |
| $\mathrm{OPT}$ | 最优 makespan |
| $h$ | 候选 makespan |
| $P(h)$ | 固定 $h$ 的 LP 松弛 |
| $\mathrm{lo}_i(h),\mathrm{hi}_i(h)$ | $P(h)$ 在坐标 $s_i$ 上的投影端点 |
| $H(h)=\prod_i[\mathrm{lo}_i(h),\mathrm{hi}_i(h)]$ | LP 投影盒 |
| $\mathrm{LB}_0,\mathrm{UB}_0$ | 预处理前的初始下界、上界 |
| $\mathrm{LB},\mathrm{UB}$ | 预处理后的证书区间 |
| $W=\mathrm{UB}-\mathrm{LB}$ | 区间宽度 |
| $\rho=\mathrm{UB}/\mathrm{LB}$ | 证书区间的竞争比（近似比上界） |
| $Q$ | 外层 oracle 调用次数（查询数） |
| $\mathrm{predq}$ | 精确 oracle 下二分搜索的理想深度，不含最终 $\mathrm{OPT}-1$ 证明 |
| $\mathrm{cert}$ | 可重放的 NO 证书（window / energy / Farkas） |
| $\mathrm{sched},\mathrm{mach}$ | 通过 `check_schedule` 的调度与机器分配 |

注意：代码里的 `q` 有时指查询数，有时指尾长 `q[i]`。本文用 $Q$ 表示查询数，用 $q_i$ 表示尾长，避免混淆。

## 2. 形式化对象

### 2.1 实例与可行调度

实例是一个带优先约束的无关并行机调度：

- 每个任务 $i$ 必须在其所有前驱完成后开始；
- 任务 $i$ 只能放在 $\mathrm{elig}_i\subseteq M$ 中的一台机器上；
- 机器上的任务区间不重叠；
- 目标是最小化 $C_{\max}(s)=\max_i(s_i+p_i+q_i)$，其中 $q_i$ 是交付尾长。

一个调度是二元组 $(s,\mathrm{mach})$，$s_i\in\mathbb Z_{\ge 0}$，$\mathrm{mach}_i\in\mathrm{elig}_i$，满足优先约束和机器容量约束。`check_schedule(inst,h,start,mach)` 做独立重放：检查每个任务在 $[0,h]$ 内、机器合法、优先约束、机器不重叠。只有通过重放的调度才被接受。

记

\[
\mathcal M(I)=\{C_{\max}(s): (s,\mathrm{mach})\text{ 可行}\},
\qquad
\mathrm{OPT}=\min \mathcal M(I).
\]

### 2.2 LP 松弛与投影

固定 $h$，记 $P(h)$ 为 v7.6/QSP 的 LP 松弛（实际实现用 `LazySD` 的 start-time-indexed 形式）。概念上：

\[
P(h)=\left\{s\in\mathbb R_{\ge 0}^n:
\begin{array}{l}
s_i\ge \mathrm{est}_i,\\
s_j\ge s_i+p_i \quad ((i,j)\in E),\\
s_i+p_i+q_i\le h,\\
\text{机器容量约束的 LP 松弛成立}
\end{array}
\right\}.
\]

它不是整数规划；它允许分数开始时间和分数机器分配。但每个整数可行调度都满足这些约束，所以

\[
(s,\mathrm{mach})\text{ 可行},\ C_{\max}(s)\le h
\;\Longrightarrow\;
s\in P(h).
\]

坐标投影定义为

\[
\mathrm{lo}_i(h)=\min_{s\in P(h)} s_i,\qquad
\mathrm{hi}_i(h)=\max_{s\in P(h)} s_i.
\]

由可行性，任意整数可行调度的 $s_i$ 都落在 $[\mathrm{lo}_i(h),\mathrm{hi}_i(h)]$，因此投影盒

\[
H(h)=\prod_i[\mathrm{lo}_i(h),\mathrm{hi}_i(h)]
\]

是整数可行集的外包盒。它是**可靠的**，但不一定是**紧的**；第 6.6 节的负结果会量化这一点。

### 2.3 证书区间

一个证书区间是一对整数 $(\mathrm{LB},\mathrm{UB})$，满足

\[
\mathrm{LB}\le \mathrm{OPT}\le \mathrm{UB}.
\]

- $\mathrm{LB}$ 由下界论证或「在 $h=\mathrm{LB}$ 处存在可重放的 NO 证书」支撑；
- $\mathrm{UB}$ 由一张通过 `check_schedule` 的调度支撑；
- 若 $\mathrm{LB}=\mathrm{UB}$，则 incumbent 被证明最优。

定义宽度 $W=\mathrm{UB}-\mathrm{LB}$ 和竞争比

\[
\rho=\frac{\mathrm{UB}}{\mathrm{LB}}.
\]

这里的 $\rho$ 不是在线算法的竞争比，而是**当前 incumbent 相对证书下界的近似比**：

\[
\frac{C_{\max}(\text{incumbent})}{\mathrm{OPT}}
\le \frac{\mathrm{UB}}{\mathrm{LB}}=\rho.
\]

因为 incumbent 的 makespan 不超过 $\mathrm{UB}$，而 $\mathrm{OPT}\ge\mathrm{LB}$。$\rho=1$ 等价于 $\mathrm{LB}=\mathrm{UB}$，即已证明最优。

### 2.4 NO 证书

本轮使用两类 NO 证书，均由 `exp/v9c/scale.py` 提供并可重放：

**Window 证书。** 对任务 $i$，若

\[
\mathrm{est}_i+p_i+q_i>h,
\]

则任何 makespan $\le h$ 的调度都不存在。等价地 $\mathrm{est}_i>\mathrm{latest}_i(h)$。

**Energy 证书。** 对机器子集 $M'\subseteq M$ 和时间区间 $[a,b)$，令

\[
J(M')=\{i:\mathrm{elig}_i\subseteq M'\},
\]

\[
\mathrm{ov}_i(a,b)=\max\bigl(0,\ p_i-\max(0,a-\mathrm{est}_i)
-\max(0,\mathrm{latest}_i(h)+p_i-b)\bigr).
\]

$\mathrm{ov}_i(a,b)$ 是任务 $i$ 在 $[a,b)$ 内**无论怎样调度都必须重叠**的最小加工量。若

\[
\sum_{i\in J(M')}\mathrm{ov}_i(a,b) > |M'|(b-a),
\]

则这组任务在 $[a,b)$ 内无法全部塞进 $M'$ 的机器容量，故 $h$ 不可行。证书记录 $(M',a,b,J,\text{demand})$，`verify_prep(inst,h,cert)` 用整数算术重放这个不等式。

**Farkas 证书。** v8.0 的 LP 不可行性证书；本轮不直接生成它，但 `CHD`/`CAB` 的 NO 路径仍会产生，并由 `audit_rdf` 检查。

本轮只把 window/energy 用于**预处理阶段的 LB 抬升**；最终 $\mathrm{OPT}-1$ 的 NO 仍由内层 oracle 的完整证书负责。

### 2.5 UB 证书

任何通过 `check_schedule(inst,Cmax,start,mach)` 的调度都是 UB 证书：

\[
\mathrm{OPT}\le C_{\max}(s).
\]

`check_schedule` 检查所有任务在 $[0,C_{\max}]$ 内、机器合法、优先约束、机器不重叠。`chip_bounds` 在每次 UB 更新前都调用它，因此 UB 不依赖启发式的自述。

### 2.6 凸包：从高维到一维

可行 makespan 集合 $\mathcal M(I)$ 的凸包是区间 $[\mathrm{OPT},\max\mathcal M(I)]$。我们不需要知道高维开始时间向量的凸包；真正要维护的是这个一维凸包的下端点，即 $\mathrm{OPT}$。

证书区间 $[\mathrm{LB},\mathrm{UB}]$ 是 $[\mathrm{OPT},\infty)$ 的一个外区间：

\[
[\mathrm{OPT},\infty)\subseteq[\mathrm{LB},\mathrm{UB}].
\]

预处理的目标就是把这个外区间压到接近 $[\mathrm{OPT},\infty)$ 的下端。高维投影盒 $H(h)$ 是另一个外近似，但它通常远宽于整数可行集；第 6.6 节会看到，把 $H(h)$ 当硬域并不划算。**本轮最终选择的是低维凸包（一维区间），高维凸包只保留为可选的顺序 oracle。**

## 3. 算法

### 3.1 总览

CRISP 分三个阶段：

1. **初始界**：critical path + eligibility load 给 $\mathrm{LB}_0$，est 顺序 greedy 给 $\mathrm{UB}_0$；
2. **预处理**：先 UB drop（4 个 greedy 订单），再 LB lift（energy/window NO 证书），得到 $[\mathrm{LB},\mathrm{UB}]\subseteq[\mathrm{LB}_0,\mathrm{UB}_0]$；
3. **区间搜索**：在 $[\mathrm{LB},\mathrm{UB}]$ 上二分调用内层 oracle；NO 抬 LB，YES 压 UB；最后在 $\mathrm{OPT}-1$ 补一张 NO 证明，在 $\mathrm{OPT}$ 保留可重放调度。

### 3.2 初始界：`base_bounds`

Critical path 下界：

\[
\mathrm{LB}_{\mathrm{cp}}
=\max_i\bigl(\mathrm{est}_i+p_i+q_i\bigr).
\]

Eligibility load 下界：对每个非空机器子集 $M'\subseteq M$，只能放在 $M'$ 上的任务必须在 $|M'|$ 台机器上完成：

\[
\mathrm{LB}_{\mathrm{load}}
=\max_{\emptyset\ne M'\subseteq M}
\left\lceil
\frac{\sum_{i:\mathrm{elig}_i\subseteq M'}p_i}{|M'|}
\right\rceil.
\]

于是

\[
\mathrm{LB}_0=\max(\mathrm{LB}_{\mathrm{cp}},\mathrm{LB}_{\mathrm{load}}).
\]

$\mathrm{UB}_0$ 由 est 顺序的串行 SGS 给出，并用 `check_schedule` 重放。若 greedy 失败（DAG 异常），返回 `ok=False`，不做任何虚假声明。

复杂度：$O(2^m n+n\log n+\text{SGS})$。本语料 $m\le 4$，$2^m\le 16$，可忽略。

### 3.3 UB drop：4 个确定性订单

`order_portfolio(inst,est,q,ub)` 返回 4 个优先序：

| 名称 | 排序键 | 直觉 |
|---|---|---|
| `est` | $\mathrm{est}_i+i\cdot10^{-9}$ | 最早开始优先 |
| `latest` | $\mathrm{latest}_i+i\cdot10^{-9}$ | 最晚开始优先，给紧任务让路 |
| `tail` | $-q_i+i\cdot10^{-9}$ | 长尾优先 |
| `mixed` | $\mathrm{est}_i-0.5q_i+i\cdot10^{-9}$ | 头尾折中 |

每个订单跑一次 `_greedy_rank`（串行 SGS），得到 $(s,\mathrm{mach},C_{\max})$。只有当

\[
C_{\max}<\mathrm{UB}
\quad\text{且}\quad
\texttt{check\_schedule}(I,C_{\max},s,\mathrm{mach})
\]

时才更新 $\mathrm{UB}$。因此 UB drop 只会让上界更紧，不会引入未验证的调度。

252 个实例中，201 个实例的 UB 被至少一个订单压低（base 95/141、pert 60/60、stress 46/51）。成功的订单更新次数（含同一实例多次更新）为 base 101、pert 60、stress 46。

### 3.4 LB lift：energy / window 循环

在 $h=\mathrm{LB}$ 处：

1. 调 `energy_cert(inst,LB,64,20000)`；若返回证书，验证后 $\mathrm{LB}\leftarrow\mathrm{LB}+1$；
2. 若没有 energy 证书，调 `windows(inst,LB)`；若存在 $\mathrm{est}_i>\mathrm{latest}_i$，构造 window 证书，验证后 $\mathrm{LB}\leftarrow\mathrm{LB}+1$；
3. 若两者都没有，停止；
4. 若验证失败，记录 `cert_bad` 并停止，不抬 LB。

循环条件是 $\mathrm{LB}<\mathrm{UB}$，因为 $\mathrm{LB}=\mathrm{UB}$ 时区间已经精确，不需要再抬。

252 个实例共触发 174 次 LB lift（base 101、pert 31、stress 42），全部证书通过 `verify_prep`，`cert_bad=0`。

### 3.5 顺序：先 UB 后 LB

这个顺序不是随意的。LB lift 的循环上界是当前 $\mathrm{UB}$；先降 UB 可以让 LB 多爬几步，先升 LB 则 energy 循环会更早停下。第 6.5 节的消融显示：

- UB drop 单独把预测二分深度从 558 降到 303；
- LB lift 单独只从 558 降到 538；
- 两者合起来降到 254。

也就是说，**LB lift 的收益需要 UB drop 先创造空间**。这是本轮对「竞争比」最重要的结构性观察：上下界不是两个独立算子，而是一个耦合系统。

### 3.6 外层搜索：`CRISPBounds` 与 `CRISP`

`CRISPBounds` 和 `CRISP` 都继承 `CABOpt`，只在 `initial_bounds` 中调用 `chip_bounds`：

```python
def initial_bounds(self):
    b = chip_bounds(self.inst)
    self.chip = b
    return b['lb'], b['ub'], b['schedule'], b['machine']
```

区别在内层 oracle：

- `CRISPBounds._decide` 继承 `CABOpt`，用 `CAB`（archive + Markov）；
- `CRISP._decide` 覆盖为

```python
def _decide(self, h):
    rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
              hull_disc=4, hull_on=True)
    v, st = rdf.decide(budget=self.per_query_lp,
                       nodecap=self.per_query_nodes)
    return v, st, rdf
```

`CABOpt.optimize` 的循环不变式是

\[
\mathrm{LB}\le \mathrm{OPT}\le \mathrm{UB}.
\]

每次 `_decide(h)`：

- `v=True`：用返回调度的实际 $C_{\max}$ 更新 $\mathrm{UB}$（不会变大）；
- `v=False`：$\mathrm{LB}\leftarrow\max(\mathrm{LB},h+1)$，保存 NO 证明；
- `v=None`：UNKNOWN，`_recover_unknown` 在 $h$ 或 $h-1$ 重试，不把 UNKNOWN 当 NO。

当 $\mathrm{LB}=\mathrm{UB}$ 时，`optimize` 检查 $\mathrm{OPT}-1$ 是否已有 NO 证明；若没有，补一次 `_decide(OPT-1)`。只有这次返回 NO，`certified=True`。

### 3.7 伪代码

```
function CRISP(inst):
    (LB0, UB0, sched, mach, est, q) = base_bounds(inst)
    if UB0 is None or not check_schedule(inst, UB0, sched, mach):
        return UNKNOWN

    LB, UB = LB0, UB0
    for order in [est, latest, tail, mixed]:
        g = greedy_SGS(order)
        if g and g.Cmax < UB and check_schedule(inst, g.Cmax, g.starts, g.machs):
            UB, sched, mach = g.Cmax, g.starts, g.machs

    while LB < UB:
        cert = energy_cert(inst, LB)
        if cert is None:
            if no window violation at LB:
                break
            cert = window_cert(inst, LB)
        if not verify_prep(inst, LB, cert):
            break
        LB += 1

    Q = 0
    while LB < UB and Q < Qmax:
        h = floor((LB + UB) / 2)
        v, st = oracle(inst, h)
        Q += 1
        if v == YES:
            UB = min(UB, Cmax(st.schedule))
            sched, mach = st.schedule, st.machine
        elif v == NO:
            LB = h + 1
            no_states[h] = st
        else:
            retry(h), retry(max(LB, h - 1))

    if LB == UB:
        if (UB - 1) not in no_states:
            v = oracle(inst, UB - 1)
            Q += 1
            if v != NO:
                return UNKNOWN
        certified = True
    else:
        certified = False

    return (UB, sched, mach, LB, Q, certified)
```

### 3.8 查询记账

`Q` 包含：

- 二分搜索的每次 `_decide`；
- UNKNOWN 的每次重试；
- 最终的 $\mathrm{OPT}-1$ 证明（若搜索中没查过）。

`bench_bounds.py` 的 `predq` 只计算理想二分深度，不含最终证明。因此：

- 252 例的 `predq` 总和是 254；
- 58 个在预处理后已经 $\mathrm{LB}=\mathrm{UB}$ 的实例，每个需要一次 $\mathrm{OPT}-1$ 证明，贡献 58；
- 其余 194 个非精确实例中，有 25 个的 $\mathrm{OPT}-1$ 不在搜索轨迹里，需要补证明；
- 所以实际 $Q=254+58+25=337$。

这个记账解释很重要：**CRISP 的查询下降不是在「少证明」；恰恰相反，它在 58 个实例上完全跳过了搜索，只补一张最终 NO 证明。**

## 4. 正确性

### 4.1 引理 1（初始界可靠）

`base_bounds` 返回的 $\mathrm{LB}_0,\mathrm{UB}_0$ 满足

\[
\mathrm{LB}_0\le\mathrm{OPT}\le\mathrm{UB}_0.
\]

证明：critical path 下界和 eligibility load 下界都是标准松弛；$\mathrm{UB}_0$ 由 `check_schedule` 重放的可行调度给出。若 greedy 失败，函数返回 `ok=False`，不产生区间。$\square$

### 4.2 引理 2（UB drop 可靠）

每次 UB 更新都要求新调度通过 `check_schedule`；因此新值仍是可行调度的 makespan，满足 $\mathrm{OPT}\le C_{\max}$。取多个订单的最小值只会更紧，不会低于 $\mathrm{OPT}$。$\square$

### 4.3 引理 3（NO 证书可靠）

- Window：若 $\mathrm{est}_i+p_i+q_i>h$，任务 $i$ 即使最早开始也无法在 $h$ 内完成并交付，故 $h$ 不可行。
- Energy：$\mathrm{ov}_i(a,b)$ 是任务 $i$ 在 $[a,b)$ 内的强制重叠下界；若这些强制重叠之和超过 $|M'|(b-a)$，则 $M'$ 的容量不足以容纳它们，故 $h$ 不可行。
- `verify_prep` 用整数算术重放上述不等式；验证失败则不抬 LB。

因此，若 `chip_bounds` 在 $h$ 处接受了一张证书并令 $\mathrm{LB}=h+1$，则

\[
\mathrm{OPT}\ge h+1=\mathrm{LB}.
\]

$\square$

### 4.4 引理 4（LB lift 保持下界）

归纳：初始 $\mathrm{LB}_0\le\mathrm{OPT}$。每次抬升前，在 $h=\mathrm{LB}$ 处有已验证的 NO 证书，故 $\mathrm{OPT}\ge h+1$；抬升后仍成立。若循环因无证书或验证失败而停止，$\mathrm{LB}$ 不变，仍满足 $\mathrm{LB}\le\mathrm{OPT}$。$\square$

### 4.5 引理 5（区间不变式）

在 `chip_bounds` 返回时，

\[
\mathrm{LB}_0\le\mathrm{LB}\le\mathrm{OPT}\le\mathrm{UB}\le\mathrm{UB}_0.
\]

证明：引理 1 给初始；引理 2 给 $\mathrm{UB}$ 不降到 $\mathrm{OPT}$ 以下；引理 3–4 给 $\mathrm{LB}$ 不升到 $\mathrm{OPT}$ 以上。传递性给出链。$\square$

### 4.6 定理 1（最终答案可靠）

若 `optimize` 返回 `certified=True`，则 `opt` $=\mathrm{OPT}$，且：

- `schedule` 在 `opt` 处通过 `check_schedule`；
- `no_states[opt-1]` 是一张通过 `audit_rdf`/`proof_complete` 的 NO 证明；
- `cert_h=opt-1`。

证明：`certified=True` 要求 $\mathrm{LB}=\mathrm{UB}=\mathrm{opt}$，且 $\mathrm{opt}-1$ 有 NO 证明。由引理 5，$\mathrm{LB}\le\mathrm{OPT}\le\mathrm{UB}$，故 $\mathrm{OPT}=\mathrm{opt}$。调度和 NO 证明分别由 `check_schedule` 与 `audit_rdf`/`proof_complete` 独立检查。$\square$

若 `certified=False`，`opt` 仍是可行调度的 makespan，因此 $\mathrm{opt}\ge\mathrm{OPT}$；$\mathrm{LB}\le\mathrm{OPT}$ 仍成立。此时返回的是**有效的 anytime 区间**，不是「已证明最优」。

### 4.7 定理 2（竞争比与二分收缩）

设内层 oracle 精确（不返回 UNKNOWN），预处理后区间为 $[\mathrm{LB}_0,\mathrm{UB}_0]$，宽度 $W_0$。第 $t$ 次二分后，

\[
W_t\le\left\lceil\frac{W_0}{2^t}\right\rceil,
\qquad
\rho_t\le 1+\frac{W_0}{2^t\,\mathrm{LB}_0}.
\]

证明：每次二分把当前宽度 $W$ 分成 $\lfloor W/2\rfloor$ 和 $\lceil W/2\rceil$；最坏取 $\lceil W/2\rceil$。竞争比由 $\rho_t=\mathrm{UB}_t/\mathrm{LB}_t=1+W_t/\mathrm{LB}_t\le1+W_t/\mathrm{LB}_0$ 得到。$\square$

因此精确 oracle 下的查询上界是

\[
Q=O\bigl(\log(W_0+1)\bigr).
\]

预处理的作用是同时降低 $W_0$ 和 $\rho_0$；本轮把 252 例的总 $W_0$ 从 1069 压到 304，把平均 $\rho_0$ 从 1.144 压到 1.038。

### 4.8 UNKNOWN 的语义

`_decide` 返回 `None` 时，`optimize` 不改变 $\mathrm{LB}/\mathrm{UB}$ 的可靠性，只增加查询数并重试。若重试后仍 UNKNOWN，可能因 `max_queries` 提前结束，此时 `certified=False`。CRISP 从不把 UNKNOWN 解释为 NO 或 YES。$\square$

## 5. 复杂度

### 5.1 预处理

- `base_bounds`：$O(2^m n+n\log n+\text{SGS})$；本语料 $m\le4$。
- UB drop：4 次 SGS，$O(4(n\log n+nm))$。
- LB lift：最多 $W_0$ 次；每次 `energy_cert` 枚举 $\le64$ 个机器子集、$\le20{,}000$ 个区间，最坏 $O(W_0\cdot(64\cdot20{,}000+n))$。实际 252 例共 174 次 lift，预处理总墙钟约 0.36 s。
- 可选 hull projection：$2n$ 次 LP；本语料 $n\le21$，但默认关闭。

### 5.2 搜索

- 二分深度 $O(\log W_0)$；实际 252 例 `predq` 总和 254。
- 每次 `CHD` 调用受 `per_query_lp=80`、`per_query_nodes=5000` 约束；`max_queries=40`。
- 最终 $\mathrm{OPT}-1$ 证明最多一次额外调用。
- 实际总查询 337，总 LP 1403，总 YES 节点 64,039，总墙钟 7.27 s。

### 5.3 内存

- `chip_bounds` 保存 174 张证书（每张只含子集/区间/需求，整数），可忽略。
- `no_states` 最多保存 `max_queries` 个 NO oracle 状态；每个状态是 `RDF`/`CHD` 实例，大小与 LP 规模同阶。
- `trace` 保存每次查询的摘要，$O(Q)$。

### 5.4 实际开销

预处理不是瓶颈；内层 LP 和 LDS 仍是主要成本。CRISP 的 7.27 s 中，`bench_bounds` 测得的纯预处理约 0.36 s，其余是 337 次 oracle 调用。也就是说，**本轮的主要收益来自「少调用 oracle」，而不是「每次调用更快」**。

## 6. 实验

### 6.1 设置

- **base 141**：7 个族，`holdout` 50、`synth` 45、`large_a` 8、`large_b` 10、`large_het` 8、`hard3` 12、`deep` 8。
- **pert 60**：`exp/v71/perturb60.pkl`，在 base 上做扰动后的 NO 集。
- **stress 51**：`exp/v81/h5h47_branch.pkl`，`h=opt-1` 的压力集。
- 共 252 例；NO 取 $h=\mathrm{OPT}-1$，YES 取 $h=\mathrm{OPT}$。
- 基线：`exp/v9d/bench_opt.json` 的 CAB v9.0。
- `CRISPBounds`：CRISP 预处理 + 原 CAB oracle。
- `CRISP`：CRISP 预处理 + CHD oracle。
- 环境：`.venv`，HiGHS LP，确定性 CHD；CAB 基线保留其原始随机种子。

### 6.2 主结果

| 方法 | 认证 | 查询 | LP | YES 节点 | Markov | 墙钟 |
|---|---:|---:|---:|---:|---:|---:|
| CAB v9.0 | 252/252 | 560 | 3119 | 65,558 | 12,300 | 21.27 s |
| CRISP bounds + CAB | 252/252 | 336 | 1324 | 64,504 | 5,900 | 6.32 s |
| **CRISP + CHD** | **252/252** | **337** | **1403** | **64,039** | **0** | **7.27 s** |

相对 CAB：

- 查询 −39.8%；
- LP −55.0%；
- YES 节点 −2.3%（总量被 stress 的 60k 上限实例主导；只看 base+pert，从 5,188 降到 4,038，−22.2%）；
- Markov 评估 12,300→0；
- 墙钟 −65.8%。

### 6.3 分语料

| 语料 | 方法 | 查询 | LP | YES 节点 | Markov | 墙钟 |
|---|---|---:|---:|---:|---:|---:|
| base 141 | CAB | 300 | 1358 | 4,900 | 6,300 | 11.56 s |
| base 141 | bounds+CAB | 190 | 548 | 4,358 | 3,100 | 3.39 s |
| base 141 | **CRISP+CHD** | **191** | **612** | **4,038** | **0** | **4.15 s** |
| pert 60 | CAB | 147 | 882 | 288 | 1,800 | 4.45 s |
| pert 60 | bounds+CAB | 90 | 388 | 96 | 600 | 1.27 s |
| pert 60 | **CRISP+CHD** | **90** | **388** | **0** | **0** | **1.23 s** |
| stress 51 | CAB | 113 | 879 | 60,370 | 4,200 | 5.26 s |
| stress 51 | bounds+CAB | 56 | 388 | 60,050 | 2,200 | 1.66 s |
| stress 51 | **CRISP+CHD** | **56** | **403** | **60,001** | **0** | **1.89 s** |

CHD 在 base 上比 CAB oracle 多 64 次 LP、慢 0.76 s，但少 320 个 YES 节点；在 pert 上把 96 个 YES 节点降到 0。整体上，**区间收缩是主收益，oracle 替换是次收益**。

### 6.4 Bracket 压缩

| 语料 | $\mathrm{LB}_0$ | $\mathrm{UB}_0$ | $W_0$ | $\rho_0$ 均值 | $\mathrm{LB}$ | $\mathrm{UB}$ | $W$ | $\rho$ 均值 | $\rho=1$ | LB lift | UB drop 实例 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base 141 | 3902 | 4388 | 486 | 1.1292 | 4003 | 4144 | 141 | 1.0318 | 55 | 101 | 95 |
| pert 60 | 1924 | 2249 | 325 | 1.1681 | 1955 | 2045 | 90 | 1.0460 | 3 | 31 | 60 |
| stress 51 | 1625 | 1883 | 258 | 1.1579 | 1667 | 1740 | 73 | 1.0437 | 0 | 42 | 46 |
| **总** | **7451** | **8520** | **1069** | **1.1443** | **7625** | **7929** | **304** | **1.0376** | **58** | **174** | **201** |

最大竞争比：

- base：1.3333→1.1220；
- pert：1.2500→1.0909；
- stress：1.2500→1.0909。

总宽度 −71.6%，平均竞争比 −9.3%，58 个实例在 oracle 调用前已经精确。

### 6.5 消融

| 变体 | 区间宽度和 | $\rho=1$ 实例 | 预测二分深度 |
|---|---:|---:|---:|
| 无预处理 | 1069 | 11 | 558 |
| 只 LB lift | 895 | 11 | 538 |
| 只 UB drop | 478 | 50 | 303 |
| **两者** | **304** | **58** | **254** |

解读：

- UB drop 是主驱动（558→303，−45.7%）；
- LB lift 单独几乎不减少查询（558→538，−3.6%）；
- 两者合起来（558→254，−54.5%）超过各自贡献之和，说明 **LB lift 的收益依赖 UB 已被压低**；
- 58 个 $\rho=1$ 实例全部来自两者合用；只 UB drop 是 50 个，只 LB lift 是 11 个。

### 6.6 负结果：高维凸包太松

对 7 个 hard YES，计算 $h=\mathrm{OPT}$ 处的 LP 投影盒宽度：

| 实例 | 盒宽 $\sum_i(\mathrm{hi}_i-\mathrm{lo}_i)$ | 盒 LDS 节点 | 盒 LDS 结果 | CHD 结果 |
|---|---:|---:|---|---|
| holdout 35 | 100.0 | 65,411 | 找到 | hull:lo，28 LP / 16,381 LDS |
| large_a 5 | 135.3 | 70,659 | 4 层差异内失败 | phase A，10 LP / 0 LDS |
| large_het 0 | 179.5 | 718 | 找到 | cheap:mean，12 LP / 340 LDS |
| large_het 3 | 261.0 | 12,634 | 找到 | cheap:mean，12 LP / 3,745 LDS |
| large_het 7 | 250.3 | 98,491 | 4 层差异内失败 | cheap:mean，13 LP / 1,535 LDS |
| hard3 4 | 185.6 | 33 | 找到 | cheap:mean，12 LP / 173 LDS |
| large_b 1 | 251.8 | 681 | 找到 | cheap:mean，13 LP / 1,387 LDS |

盒宽 100–261，远大于实例的 $h$（30–41）。盒 LDS 在 2/7 上失败，而 CHD 在同一批实例上全部闭合（10–28 LP）。因此：

- **投影盒是可靠的，但不是紧的；**
- **把高维凸包当硬域约束，收益不足以抵消 $2n$ 次 LP；**
- 高维凸包只保留为可选的顺序 oracle（`hull_projection` 默认关闭）。

第二个负结果：投影尾界

\[
\mathrm{LB}_{\mathrm{hull}}(h)=\max_i\bigl(\mathrm{lo}_i(h)+p_i+q_i\bigr).
\]

在 141 个 base 实例上、$h=\mathrm{UB}$ 处：

- 只有 4 个实例把 LB 抬高 1；
- 0 个实例超过已知 OPT；
- 12 个实例等于 OPT；
- 其余普遍弱于 critical path + eligibility load。

因此它没有进入最终算法。

第三个负结果：hull 顺序消融（141 个 YES，来自 v9.1 CHD）：

| 变体 | YES | hull LP | LDS 节点 | random fallback | 墙钟 |
|---|---:|---:|---:|---:|---:|
| full | 141/141 | 16 | 39,420 | 0 | 7.17 s |
| no_hull | 141/141 | 0 | 39,403 | 1 | 7.25 s |
| hull_only | 141/141 | 719 | 449,813 | 3 | 13.72 s |

`no_hull` 只多 1 次 random fallback；`hull_only` 则要 719 次 hull LP 和 449,813 个 LDS 节点。结论：**hull 顺序是一个安全网，不是主引擎。**

### 6.7 证书与最终审计

| 检查 | 结果 |
|---|---|
| energy NO 证书 | 174 张，`verify_prep=True` 174/174，`cert_bad=0` |
| 区间可靠性 | 252/252 满足 $\mathrm{LB}\le\mathrm{OPT}\le\mathrm{UB}$ |
| CRISP 最终审计 | 252/252 `certified=True`、`audit=True`、`proof=True` |
| `cert_h` | 252/252 等于 $\mathrm{OPT}-1$ |
| UNKNOWN | 0（bound 与 crisp 都是 0） |
| 基线 CAB | 252/252 认证 |

`ok` 的定义是

```python
certified and opt == known and audit and proof and cert_h == known - 1
```

252/252 为真。没有出现「无证书的 NO」或「未重放的 YES」。

### 6.8 oracle 选择

| 对比 | 结论 |
|---|---|
| CRISP+CAB vs CRISP+CHD | CHD 少 12,300 次 Markov 评估、少 465 个 YES 节点；多 79 次 LP、多 0.95 s |
| CRISP+CAB vs CAB | 查询 560→336，LP 3119→1324，墙钟 21.27→6.32 s |
| CRISP+CHD vs CAB | 查询 560→337，LP 3119→1403，墙钟 21.27→7.27 s |

因此：

- 预处理本身（CRISP+CAB）已经拿到大部分收益；
- CHD 把随机构造器彻底移除，代价是少量额外 LP；
- 若目标是「无随机、可复现」，CRISP+CHD 更合适；若目标是「最小 LP」，CRISP+CAB 更合适。

### 6.9 威胁与边界

- 语料只有 252 例，$n\le21$、$m\le4$；不能外推到大规模。
- 墙钟是单次运行、共享 runner、Python 环境；应看相对比例，不看绝对秒数。
- CAB 基线含随机种子；CHD 是确定性的。基线的 YES 节点/Markov 可能随种子波动。
- `predq` 是理想二分深度；实际 `Q` 含最终证明和重试，比较时必须用同一记账。
- energy 过滤的预算（64 子集 / 20k 区间）是人为上限；更大的预算可能抬更多 LB，但预处理会变慢。
- `chip_bounds` 的 UB drop 只用 4 个订单；这不是 2-近似算法，只是便宜的上界组合。
- 高维凸包的负结果只覆盖 7 个 hard YES 和 141 base 的尾界实验；换语料可能不同。
- 竞争的语义是「证书区间比」，不是在线竞争比；不要把它和在线算法的 competitive ratio 混用。

## 7. 复现

### 7.1 文件

| 文件 | 作用 |
|---|---|
| `exp/v8c/chip.py` | CRISP-ALC：`base_bounds`、`order_portfolio`、`hull_projection`、`chip_bounds`、`CRISPBounds`、`CRISP`、`simulate_queries` |
| `exp/v8c/bench_chip.py` | 主实验：CAB / bounds+CAB / CRISP+CHD，写 `bench_chip.json` |
| `exp/v8c/bench_bounds.py` | bracket 统计、消融、证书验证，写 `bench_bounds.json` |
| `exp/v9d/cab.py` | `CABOpt`、`CAB`、`_greedy_rank` |
| `exp/v9b/chd.py` | `CHD` |
| `exp/v9c/scale.py` | `energy_cert`、`windows`、`verify_prep` |
| `exp/v8a/rdf.py` | `RDF`、`check_schedule` |
| `exp/v9d/bench_opt.json` | CAB 基线结果 |
| `exp/v71/perturb60.pkl` | 60 个扰动实例 |
| `exp/v81/h5h47_branch.pkl` | 51 个压力实例 |

### 7.2 命令

```bash
cd /home/runner/work/xuen/xuen/workspace
.venv/bin/python exp/v8c/bench_bounds.py
.venv/bin/python exp/v8c/bench_chip.py
```

### 7.3 预期输出

`bench_bounds.py` 应打印：

```
base ... span0 486 span 141
pert ... span0 325 span 90
stress ... span0 258 span 73
none   span 1069 exact 11 predq 558
lb     span 895 exact 11 predq 538
ub     span 478 exact 50 predq 303
both   span 304 exact 58 predq 254
```

`bench_chip.py` 应打印总表：

```
cab   {'n': 252, 'cert': 252, 'q': 560, 'lp': 3119, 'yn': 65558, 'mc': 12300, 't': 21.27}
bound {'n': 252, 'cert': 252, 'q': 336, 'lp': 1324, 'yn': 64504, 'mc': 5900, 't': 6.32}
crisp {'n': 252, 'cert': 252, 'q': 337, 'lp': 1403, 'yn': 64039, 'mc': 0, 't': 7.27}
```

秒数会因机器负载略有波动；查询、LP、YES 节点、Markov 是确定性的（CAB 基线的随机部分除外）。

## 8. 已知风险

1. **预处理覆盖不足。** energy 过滤只枚举 64 个子集、20k 个区间；在更大的 $m$ 或更长的时间域上可能漏掉 overload，导致 LB lift 为 0、区间仍然很宽。证伪方式：构造一个 $m\ge6$ 的语料，其中 energy 证书命中率显著下降，CRISP 退化到 CAB。
2. **UB 组合太窄。** 只有 4 个 greedy 订单；如果它们都不优于初始 est 调度，UB 不会下降。证伪方式：找一批实例，4 个订单的 $C_{\max}$ 都等于初始 UB，但 OPT 更低。
3. **下界证书类型有限。** 只用 window/energy；优先约束和整数性造成的 gap（例如 hard3#2）不会被这两类证书捕捉。证伪方式：找一批 integrality gap 大、但 energy 证书打不中的实例，观察 LB lift 是否接近 0。
4. **高维凸包负结果不可外推。** 7 个 hard YES 的盒宽 100–261；换语料可能更紧。证伪方式：找一个族，$H(h)$ 的宽度接近 0，且 box-LDS 明显优于 CHD。
5. **竞争比语义。** $\rho=\mathrm{UB}/\mathrm{LB}$ 是证书区间比，不是在线竞争比；$O(\log W_0)$ 的查询界假设 oracle 精确且不返回 UNKNOWN。证伪方式：在在线/对抗设置中使用，或让 oracle 频繁 UNKNOWN。
6. **oracle 完整性。** CHD/CAB 仍是 NP-hard 判定器，最坏情况会 UNKNOWN；本语料 0 UNKNOWN，不代表一般情况。CRISP 遇到 UNKNOWN 会重试，不会给假答案。
7. **规模。** $2^m$ 的 eligibility load 枚举和 energy 子集枚举不适合大 $m$；本语料 $m\le4$。证伪方式：$m\ge10$ 的实例。
8. **最终证明依赖 $\mathrm{OPT}-1$。** 若 oracle 无法在 $\mathrm{OPT}-1$ 给出 NO，`certified=False`；incumbent 可能仍最优，但未被证明。
9. **计时与基线。** 单次运行、共享 runner、Python 开销；CAB 基线含随机种子。应看相对比例。
10. **接口风险。** `CRISP` 依赖 `CABOpt.initial_bounds` 的返回约定和 `_result` 的 `lb0/ub0` 语义；若基类改变，bracket 统计可能被误读。复现时以 `bench_bounds.json` 的原始字段为准。

## 9. 一句话最大风险

**CRISP 的收益完全取决于预处理能否在预算内把 $[\mathrm{LB},\mathrm{UB}]$ 压窄；如果 energy/window 规则打不中，且 4 个 greedy 订单都找不到更优上界，区间仍然会很宽，后续 oracle 调用数会退化到 CAB 水平甚至更多。**
<!-- ARTIFACT:END -->
