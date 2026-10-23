# 产物区 · v2.2：X-DUB/PACE-ΠA-CP*

> PACE-ΠA-CP = PACE-ΠA with **Chain-Preconditioned Search**（链前置搜索）。
> 在 v2.1 的 `MAP`（tier 0.10）、`DHD`（tier 0.20）、`DCD`（tier 0.30）、`ODOM`、`HPACK`、`PACK-front`、`MINT`、`PACK-SET`、`SOP` 之上，本轮只加一层：
> **tier 0.15 `CPS`**：取一条链 `P`，枚举 `P` 在 `[0,h]` 内的所有整数 placement；固定 placement 后，把跨块优先序翻译成剩余任务的 release/deadline 与随时间变化的容量 profile，再判定剩余非抢占 residual；若**所有** placement 的 residual 都不可行，则 `σ` 为 NO。
> 状态：设计稿 + 可运行实现 + 38 例 + deep 8 + held-out 50 + easy 60 + **5 个残例根闭** + **1,430 / 1,977 / 1,977 状态对拍** + **50 个 h=OPT 的 0 假 NO** + **PAR-CPS 4 核 1.98×** + **MC-CPS 4k 预算下（critical+longest）3/5→5/5**；未接 PSPLIB，未做 Coq/Lean 形式化验证。

---

## 0. 版本关系与本轮增量

v2.1 的资产全部保留：`MAP`、`DHD`、`DCD`、`ODOM`、`HPACK`、`PACK-front`、`LC-PACK` 的 0/0.5/1/2/3 层、`LC-DEC`、`CHECK-LC`、`PROFILE`、`(est,A)` Pareto 前沿 `G`、孪生机器商 `CANON`、`FRONT`/`FRONT-SUB`/`NO-INT` 证书、`MINT`、`PACK-SET`、`SOP`、carry 定理。

本轮增量只有一条核心规则和两组围绕它的扩展：

1. **`CPS`（tier 0.15）**：链 `P` 的每个 placement `s` 定义一个 case；`s` 固定后做 release/deadline 传播和容量 profile，residual 用精确回溯判不可行；全部 case 失败才是 NO。
2. **严格强于 MAP 的分离例**：held-out 的 5 个残例（idx 5/21/32/42/47）在 `h=OPT−1` 上 `MAP=1`、`CPS=0`；v2.1 的 26/23/47/42/46 个节点全部在根上闭合为 1。
3. **归约语义**：`SCHED(σ) ⇒ ∃ placement s : RES(σ,P,s)`。CPS 是**全称**证书：`∀s ¬RES(σ,P,s) ⇒ ¬SCHED(σ)`。全资格 + 精确 residual 时反向也成立（定理 2），所以 CPS 在该条件下是 **exact decomposition**，不是 relaxation。
4. **并行**：placement 之间无依赖；`PAR-CPS` 把 placement 集合分块给 worker，OR/AND 合并；早停只允许在 YES 上。4 vCPU 实测 1.98×（受最长单个 residual 限制，见 §5.4）。
5. **蒙特卡洛**：只采样**链**，不采样 placement；每条链仍穷尽枚举。链被驳倒 ⇒ NO 可靠；漏检概率 ≤ `(1−ρ)^K`。默认 cap 下 0 额外收益；4k 预算下关键链 3/5、链 portfolio（critical+longest）5/5。
6. **实验**：38 例 38→**38**；deep 8→**8**；held-out 229→**50**（4.58×，50/50 根闭）；easy 781→**781**；planted 21→**21**；5 个残例 184→**5**；held-out 时间 2.18 s→3.51 s（1.61×）。
7. **一个明确的边界**：CPS 的完备性依赖**精确 residual 回溯**。把 residual 换成多项式 flow，5 个残例全部只能给 unknown；node cap 命中、`S>4`、`n>16`、异资格时，CPS 也只给 unknown，不返回 NO。

退化关系：

```text
cps_on=False（保留 v2.1 全部层）       → 逐字回到 v2.1 的 38 / 8 / 229 / 781
cps_tau=0                              → CPS 不触发，逐字回到 v2.1
cps_ncap<13                            → 5 个残例不触发，回到 v2.1
residual='flow'（多项式抢占松弛）       → 5 个残例全部 unknown；不回退，只是不剪
cps_depth=0（默认，仅根）               → 5 个残例仍全部 1 节点
cps_nodecap 调小                        → 更多 unknown，不会多 NO
全资格 + 精确 residual + S≤τ            → 定理 2：CPS 是 exact decomposition
异资格                                  → CPS=NO 仍可靠；CPS=YES 只当 unknown
```

---

## 1. 符号

| 符号 | 含义 |
|---|---|
| `I=(n,m,p,E,≺,h)` | 实例：加工时间、机器数、资格、优先图、公共期限 |
| `σ=(R,A,est)` | DEC 状态：未调度集、机器可用时刻、最早开始 |
| `Ready(R)` | `{i∈R : pred(i)∩R=∅}` |
| `sink(S)` | `{i∈S : succ(i)∩S=∅}` |
| `q_i` | 残余图中 i 到汇点的最长路，不含 `p_i` |
| `cp(σ)` | `max_{i∈R}(est_i+p_i+q_i)`，最长路径下界 |
| `P=(i_1,…,i_L)` | 一条链；相邻两项有优先边（允许传递） |
| `S(P)` | 链松弛 `h−(est_{i_1}+Σp_{i_t}+q_{i_L})` |
| `S(σ)` | 关键松弛 `h−cp(σ)`；`S(P)≥S(σ)` |
| `s=(s_1,…,s_L)` | P 的一个整数 placement（起点向量） |
| `g=(g_0,…,g_L)` | placement 的 gap 向量；`Σg=S(P)` |
| `r_j,d_j` | 固定 placement 后剩余任务 j 的 release / latest finish |
| `c_s(t)` | 时刻 t 的剩余容量：可用机器数减 P 的占用 |
| `RES(σ,P,s)` | 剩余非抢占 residual（定义 5） |
| `CPS(σ)` | `NO` / `YES` / `UNKNOWN`（定义 6） |
| `τ` | `cps_tau`，默认 4 |
| `Ncap` | `cps_nodecap`，默认 300,000 |
| `W,D` | 并行的总工作量 / 最长单个 placement 的工作量 |
| `ρ` | 链分布 D 下「可驳倒链」的比例 |
| `d` | Ready 集大小（DHD/DCD 前） |
| `c` | 分支集大小（DHD/DCD 后） |
| `ω` | 机器字长，64 |

---

## 2. 形式定义

### 2.1 链与链松弛

**定义 1（链）**。`P=(i_1,…,i_L)` 是残余 DAG 中的一条有向路径：对每个 `1≤t<L`，`i_t≺i_{t+1}`（允许直接边或传递边）。`L=|P|`。

**定义 2（链松弛）**。

```text
S(P) = h − ( est_{i_1} + Σ_{t=1..L} p_{i_t} + q_{i_L} ) .
```

对关键路径，`S(P)=h−cp(σ)`；对任意链，`S(P)≥h−cp(σ)`，因为 `cp` 是所有链长度的最大值。`S(P)<0` 时，这条链本身就超期，状态必不可行。

### 2.2 placement 与 gap

**定义 3（placement）**。P 的一个整数起点向量 `s∈Z^L` 是 placement，若

```text
s_1 ≥ est_{i_1},
s_{t+1} ≥ s_t + p_{i_t}          (1≤t<L),
s_t + p_{i_t} ≤ h − q_{i_t}      (1≤t≤L).
```

**定义 4（gap 分解）**。对 placement s，定义

```text
g_0 = s_1 − est_{i_1},
g_t = s_{t+1} − (s_t + p_{i_t})            (1≤t<L),
g_L = (h − q_{i_L}) − (s_L + p_{i_L}).
```

则 `g_t≥0` 且

```text
Σ_{t=0..L} g_t = h − est_{i_1} − Σp_{i_t} − q_{i_L} = S(P).
```

反过来，任意非负整数 composition `g`（和为 `S(P)`）通过

```text
s_1 = est_{i_1} + g_0,
s_{t+1} = s_t + p_{i_t} + g_t          (1≤t<L)
```

给出一个候选 placement；它可能违反某个中间 deadline `s_t+p_t≤h−q_t`，需要逐项检查。`g_L` 是链后剩余松弛，不参与建 `s`，只负责把总和补齐。枚举所有 composition 就是枚举 P 的所有整数 placement；合法 placement 的数量为 `C(S(P)+L, L)` 减去被 deadline 过滤掉的那些，至多 `C(S(P)+L, L)`。

**例**：idx 5 的 `S=1, L=6`，`C(7,6)=7`；idx 21 的 `S=2, L=4`，`C(6,4)=15`；idx 42 的 `S=3, L=5`，`C(8,5)=56`。实测 placement 数正好是 7/15/56（§5.3）。

### 2.3 固定 placement 后的 release / deadline

**定义 5（窗口传播）**。固定 P 和 s 后，在残余 DAG 的拓扑序上做两遍最长路：

```text
r_j = max( est_j, max_{u≺j} ( r_u + p_u ) ) ,
d_j = min( h−q_j, min_{j≺v} ( d_v − p_v ) ) .
```

其中，若 `u∈P`，`r_u=s_u`；若 `v∈P`，`d_v=s_v+p_v`。传播后必须检查：

```text
r_j + p_j ≤ d_j                 对所有 j∈R,
r_u + p_u ≤ r_v                 对所有 u≺v,
d_u ≤ d_v − p_v                 对所有 u≺v.
```

任一条不成立，这个 placement 就不可能延拓成完整排程，直接丢弃。

**注**：链任务 `i_t` 的 `d_{i_t}` 被钉成 `s_t+p_{i_t}`，不是 `h−q_{i_t}`；这是**更强**的窗口（它要求链任务按 placement 的精确时刻完成），也是精确分解的关键。全局 deadline `s_t+p_t≤h−q_t` 在 placement 检查时单独做。

### 2.4 容量 profile 与 residual

**定义 6（容量 profile）**。对 placement s，

```text
c_s(t) = |{ k∈[m] : A_k ≤ t }| − |{ i_t∈P : s_t ≤ t < s_t+p_{i_t} }| ,
        t = 0,1,…,h−1.
```

第一项是 t 时刻已经可用的机器数；第二项是链在 t 时刻的占用。因为 P 是链，第二项在任意 t 至多为 1。若 `c_s(t)<0`，该 placement 不可行。

**定义 7（residual）**。给定 `σ,P,s`，`RES(σ,P,s)` 是如下判定问题：给每个 `j∈R\P` 选整数起点 `t_j`，使得

```text
r_j ≤ t_j,                                      (1)
t_j + p_j ≤ d_j,                                (2)
u≺v ⇒ t_u + p_u ≤ t_v,                         (3)
|{ j∈R\P : t_j ≤ t < t_j+p_j }| ≤ c_s(t)        (4)  对所有 t.
```

注意：`RES` **不**检查 `j` 的 eligibility，也**不**区分具体机器；它只检查聚合容量。全资格时这是精确的（区间图染色，见引理 2）；异资格时它是原问题的松弛，所以 `RES=0` 可靠，`RES=1` 只是 unknown。

### 2.5 CPS 的三值语义

**定义 8（CPS）**。

```text
CPS(σ) =
  NO       若 S(σ)<0，或对 P 的每一个 placement s，RES(σ,P,s)=0；
  YES      若存在一个 placement s 使 RES(σ,P,s)=1（仅在全资格 + 精确 residual 时作为可行性证明）；
  UNKNOWN  若 S(σ)>τ、或某个 placement 的 residual 撞上 Ncap、或异资格下 RES=1。
```

搜索里只允许在 `CPS=NO` 时剪枝；`YES`/`UNKNOWN` 都继续走 v2.1 的分支。主算法里 `P` 是关键链，`S(P)=S(σ)`；portfolio 里每条链用**自己的** `S(P)` 替换门里的 `S(σ)`。

### 2.6 触发门

**定义 9（CPS 门）**。

```text
cps_gate(σ) = ( |R| ≤ 16 ) ∧ ( S(σ) ≤ cps_tau ) ∧ ( depth ≤ cps_depth ) .
```

默认 `cps_tau=4`、`cps_depth=0`、`cps_ncap=16`、`cps_nodecap=300000`、`cps_gate_fan=0`。门是**覆盖率**参数，不是可靠性参数：门关掉只会少剪，不会多剪。`cps_gate_fan` 在实现里用分支集大小做省时间跳过；它同样只影响覆盖率。对非关键链，门里的 `S(σ)` 要换成 `S(P)`；否则一条 slack 更大的链会绕过 `cps_tau`。

### 2.7 链分布与链 portfolio

**定义 10（链分布 D）**。D 是残余 DAG 上所有链的一个概率分布。实现里有三种：

```text
critical:  取 argmax_i(est_i+p_i+q_i) 重构出的关键链；
longest:   按顶点数最长（DAG 上 unit-weight 最长路）的链；
random:    给每个任务随机权重 w_i，取 max-weight 路径；
           权重 w_i = U[0,1] + ε·p_i（ε=0.001），偏置到高加工时间的链。
```

**定义 11（可驳倒链）**。称 P 在状态 σ 下是**可驳倒的**，若 `CPS(σ;P)=NO`（在该预算/cap 下）。

链 portfolio 是：采样 `P_1,…,P_K ~ D`，对每条链跑一次 CPS；只要有一条返回 NO，就返回 NO；否则 UNKNOWN。它不改变单条链的语义，只改变「先试哪条链」。

---

## 3. 算法

### 3.1 CPS 主循环

```text
CPS(σ; P=None):
    if R=∅: return YES
    cp ← max_{i∈R}(est_i+p_i+q_i);  S ← h−cp
    if S<0: return NO
    if S>τ or |R|>ncap or depth>depth_cap: return UNKNOWN
    if P is None: P ← CRITICAL_PATH(σ)
    if S(P)>τ: return UNKNOWN        # 非关键链也要过 slack 门
    any_unknown ← False
    for g in COMPOSITIONS(S(P), |P|+1):
        s ← PLACE(P,g)                 # 用 g_0..g_{L-1}; g_L 是链后松弛
        if not VALID(s): continue
        (r,d) ← WINDOWS(σ,P,s)
        if (r,d)=⊥: continue
        c ← CAPACITY(σ,P,s)
        if min(c)<0: continue
        rr ← RESIDUAL(σ\P, r, d, c, Ncap)
        if rr=YES:
            return YES if full_elig else UNKNOWN
        if rr=UNKNOWN: any_unknown ← True
    return UNKNOWN if any_unknown else NO
```

`COMPOSITIONS(S,L+1)` 枚举 `g_0+…+g_L=S` 的所有非负整数解；`PLACE` 只使用 `g_0..g_{L-1}`，`g_L` 是链后松弛。`VALID(s)` 检查 placement 的 release/deadline；`WINDOWS` 检查传播后的所有边；`CAPACITY` 检查 `c_s(t)≥0`；`RESIDUAL` 是精确 DFS（§3.6）。

### 3.2 PAR-CPS

```text
PAR-CPS(σ,P,W):
    Π ← ENUM_PLACEMENTS(σ,P)
    split Π into W chunks (round-robin or contiguous)
    parallel for w in 1..W:
        for s in chunk[w]:
            if not VALID(s): continue
            (r,d) ← WINDOWS(σ,P,s); if ⊥: continue
            c ← CAPACITY(σ,P,s); if min(c)<0: continue
            rr ← RESIDUAL(σ\P,r,d,c,Ncap)
            if rr=YES: return FEASIBLE
            if rr=UNKNOWN: mark unknown
    if any FEASIBLE: return FEASIBLE
    if any unknown: return UNKNOWN
    return NO
```

正确性：`Π` 被划分，所有 placement 恰好被一个 worker 检查；`FEASIBLE` 是存在句，早停安全；`NO` 要求所有 chunk 都 NO，是合取。对全资格，`FEASIBLE` 是 YES；对异资格，它只是 UNKNOWN；两者都不产生 NO。实现用 `os.fork` + 管道，不依赖 `/dev/shm`；每个 worker 继承已加载的实例，不需要 pickle。静态 round-robin 分块在 5 个残例上已经够用；动态调度是后续工作。

### 3.3 MC-CPS

```text
MC-CPS(σ,K,Ncap):
    for k in 1..K:
        P_k ← SAMPLE_CHAIN(D)          # critical / longest / random
        if CPS(σ;P_k,Ncap)=NO: return NO
    return UNKNOWN
```

关键点：每条 `P_k` 仍然做**到 NO 为止的穷尽** placement 枚举；随机性只决定「试哪条链」，不决定「跳过哪些 placement」。所以 `MC-CPS=NO` 是可靠证书；`MC-CPS=UNKNOWN` 只表示 K 条链都没驳倒。实现里异资格若某个 placement 的 RES=YES 会提前返回 UNKNOWN（不再检查其余 placement）；这只少剪，不会多剪。

### 3.4 接进 PACE-ΠA

```text
PACE-ΠA-CP(σ,h):
  1  if R=∅: return YES([])
  2  if DEAD(σ): return NO
  3  σ←NORM(σ); A*←CANON(A); estt←est|R
  4  exact memo / F_sub / INT                            # v2.0，不变
  5  window 层: energy / clique / subset / HPACK          # v2.0，不变
  6  MINT / PACK-SET / SOP                                # v2.0，不变
  7  if ¬PACK(σ,h): F_pack.insert; return NO(PACK)        # v2.0，不变
  8  q ← tails(R)                                         # v2.0，不变
  9  if MAP-gate(σ):
         ok ← MAP(σ)                                      # v2.1，tier 0.10
         if ¬ok: return NO(MAP)
 10  ready ← READY(R)
 11  drop ← DHD(ready) ∪ DCD(ready)                       # v2.1，tier 0.20/0.30
 12  if CPS-gate(σ) and |ready\drop| > 0:
         v ← CPS(σ)                                       # v2.2，tier 0.15
         if v=NO: return NO(CPS)
 13  for i in K=ready\drop:
         for k in machines(i):
             t ← max(A_k,est_i)
             if t+p_i+q_i(R\{i}) > h: continue
             r ← PACE-ΠA-CP(child(i,k,t),h)
             if r=YES: return YES([(i,k,t)]+r)
 14  F_sub.insert(estt,A*); return NO(RESOLVE)
```

与 v2.1 的差异只有第 12 步；它在分支之前，只做有证书的剪枝。实现里 CPS 在 DHD/DCD 之后调用（用 `ready\drop` 做 fan-out 门），但仍在**分支之前**；这不改变语义，只让 `cps_gate_fan` 能看到有效分支集。

### 3.5 证书格式与检查

**CPS-NO 证书**：

```text
kind    = 'CPS'
payload = (R, A, est, q, h, P, [s_1,…,s_M], [res_1,…,res_M])
claim   = 每个 s_j 是 P 的合法 placement，且 RES(σ,P,s_j)=0
```

检查器独立重算：

```text
CHECK_CPS(inst, σ, P, [s_j]):
    recompute VALID(s_j), WINDOWS, CAPACITY for each j
    for each j: rerun RESIDUAL(σ\P,r,d,c,Ncap)
    accept iff all j return NO and the s_j list covers all compositions
```

这是**重放证书**，不是短证书：检查代价与生成代价同阶（placement 枚举 × residual DFS）。优点是检查器不需要信任搜索树、不需要浮点、不需要 LP；缺点是证书长度/检查时间不短。

**PAR-CPS 证书**：额外带每个 worker 的 chunk 划分，检查器验证 chunk 覆盖 `Π` 且无交叠；每个 chunk 的 NO 重放。早停的 FEASIBLE 不需要证书（它只阻止剪枝，不产生 NO）。

**MC-CPS 证书**：带被驳倒的那条链 `P_k`；随机种子和采样历史**不需要**进证书，因为可靠性只依赖 `CPS(σ;P_k)=NO` 这一事实。这正是「只采样链」的好处：随机性不进入证明。

### 3.6 residual 的精确回溯

```text
RESIDUAL(res, r, d, cap, Ncap):
    if res=∅: return YES
    pick i∈res with no predecessor in res and the fewest feasible starts
    for t in feasible starts of i (ascending):
        decrement cap[t..t+p_i)
        push release of successors to t+p_i
        if RESIDUAL(res\{i}, …) = YES: return YES
    if nodes > Ncap: return UNKNOWN
    memoize (res, cap, rel); return NO after exhaustive search
```

实现细节：

- 任务选择用 **minopts**（可行起点数最少），起点升序；这是本轮实测最好的顺序（§5.8）。
- memo key 是 `(mask, tuple(cap), tuple(rel))`；`rel` 只对剩余任务取值。
- 一个简单的 energy 剪枝：若剩余 `Σp > Σcap`，直接 NO。
- `Ncap` 命中返回 UNKNOWN，不是 NO；只有完整穷尽才返回 NO。

### 3.7 复杂度

设 `k=|P|`、`S=S(P)`、`r=|R\P|`。

```text
placement 枚举:        O(C(S+k,k)) 个候选，每个 O(n+h) 做窗口/容量
residual 精确回溯:     最坏 O(r!) 量级；memo 状态 (mask, cap, rel)，
                       实际由 Ncap 截断；每个 placement 独立
CPS 每状态:            O(C(S+k,k) · (n+h) + Σ_s T_res(s))
PAR-CPS:               work W=Σ_s T_res(s)，depth D=max_s T_res(s)
                       makespan ≤ W/P + (1−1/P)·D（list scheduling）
MC-CPS:                K 条链 × 单链 CPS 成本；可靠性不依赖 K
主搜索:                N(σ)=1+Σ_{i∈K} N(σ_i)，最坏仍指数
```

`CPS` 没有打破 NP-hard 下界：固定链后的 residual 仍含 `P||Cmax`（无优先、全资格时链长为 1，residual 就是 m 机装填）；它把指数从搜索树搬到了 `S` 和 residual 上。`S≤4` 且 `k≤16` 时，placement 数至多 `C(20,16)=4845`，实际 5 个残例是 7/15/21/56/7。

---

## 4. 定理与证明

### 4.1 链投影引理

**引理 1（投影）**。设从 `σ` 出发存在可行排程。对任意链 `P`，取 P 在排程中的实际起点 `s=(s_1,…,s_L)`。则：

1. `s` 是 P 的 placement；
2. 其余任务的起点构成 `RES(σ,P,s)` 的一个可行解（在 full eligibility 下；异资格下是容量松弛的可行解）。

**证明**。

1. 实际排程满足优先序和 `est`，所以 `s_1≥est_{i_1}`、`s_{t+1}≥s_t+p_{i_t}`；实际排程满足公共期限 `h` 和 `q`，所以 `s_t+p_{i_t}≤h−q_{i_t}`。这正是 placement 的三条。
2. 对每个 `j∉P`，实际起点 `t_j` 满足 `t_j≥est_j`；沿优先序归纳，`t_j≥r_j`（因为 `r` 是固定链和 `est` 下的最长路，实际排程是其中一条可行路径）。同理，反向归纳 `t_j+p_j≤d_j`。容量不等式由实际排程的直接事实给出：任意 t 时刻活跃的任务数不超过可用机器数，而链的活跃数至多 1，所以 residual 的活跃数 ≤ `c_s(t)`。∎

**推论 1（可靠性）**。若 `CPS(σ)=NO`，即对 P 的每个 placement 都有 `RES=0`，则从 `σ` 出发不存在可行排程。

**证明**。引理 1 的逆否：若存在可行排程，则至少有一个 placement 的 RES 可行，与「所有 placement 都 RES=0」矛盾。∎

### 4.2 精确性：全资格下的反向

**引理 2（区间染色）**。设有一组区间 `[t_i,t_i+p_i)`，每台机器 `k` 从 `A_k` 起可用。若对每个时刻 `t`，

```text
|{ i : t_i ≤ t < t_i+p_i }| ≤ a(t) = |{ k : A_k ≤ t }| ,
```

则存在一个把区间分配给机器的方案，使每个区间 `i` 分到一台 `A_k≤t_i` 的机器，且同一机器上的区间不重叠。

**证明**。按起点 `t_i` 升序贪心。处理区间 i 时，若所有 `a(t_i)` 台可用机器都忙，则这 `a(t_i)` 台机器上各有一个在 `t_i` 活跃的区间；加上 i 本身，`t_i` 时刻有 `a(t_i)+1` 个活跃区间，违反假设。所以至少有一台可用机器空闲；把 i 分给它。已分配的区间若在 `t_i` 之后仍活跃，就会占着机器，与「空闲」矛盾；所以不会重叠。机器可用性是单调的（`A_k` 固定，一旦可用永久可用），贪心不需要回退。∎

**定理 2（CPS 精确性）**。若所有任务全资格、`RESIDUAL` 精确且未撞 `Ncap`，则

```text
CPS(σ)=YES  ⇔  从 σ 出发存在可行排程。
```

**证明**。

- `⇒`：由 `CPS=YES`，存在 placement s 和 residual 的起点 `t_j`。把所有任务（链 + residual）的区间放在一起。窗口传播保证：链内优先序、residual 内优先序、以及跨链/residual 的优先序都在起点上成立（若 `u≺v` 且 `u` 在链上，则 `r_v≥s_u+p_u`；若 `v` 在链上，则 `d_u≤s_v`；两边都在链上由 placement；两边都在 residual 由 RES 的约束）。容量不等式保证任意 t 的活跃区间数 ≤ `a(t)`。由引理 2，存在机器分配。于是得到一个满足优先、release、deadline、机器不重叠、资格（全资格）的完整排程。
- `⇐`：引理 1。∎

**注**：链任务不要求在同一台机器上；优先序只约束时间，机器可以切换。引理 2 的染色会把链区间和 residual 区间一起分配，这正是「链只是一组时间区间」的意思。

**注（异资格为什么不行）**：引理 2 的贪心依赖「任意区间可以上任意机器」。异资格下这个前提不成立。反例：`m=2, A=(6,0), h=10`，链 `i≺j`，`p_i=p_j=4`，`i` 只 eligible 机器 0，`j` 只 eligible 机器 1。placement `s_i=0,s_j=4` 的容量 profile 在 `[0,8)` 上只减 1，residual 为空，所以 `RES=YES`；但 `i` 在机器 0 上最早 6 点开始、10 点结束，`j` 必须 10 点后开始、14 点结束，超期。CPS 只能返回 UNKNOWN，不能返回 NO。这个反例说明：**异资格下 CPS=YES 不是可行性证明**，只有 CPS=NO 可靠。

### 4.3 并行正确性

**定理 3（PAR-CPS）**。设 `Π` 是 P 的所有 placement，`Π_1,…,Π_W` 是 `Π` 的一个划分。若每个 worker 对它那一块做与顺序 CPS 相同的判定，则：

- 任一 worker 返回 `FEASIBLE` ⇒ 存在 placement 的 RES 可行（存在句，早停安全）；
- 所有 worker 返回 `NO` 且无 `UNKNOWN` ⇒ `CPS=NO`（合取）；
- 否则 `UNKNOWN`。

**证明**。`Π` 的划分保证每个 placement 恰好被检查一次；`FEASIBLE` 是 `∨`，`NO` 是 `∧`；早停只发生在 `∨` 为真时，不会丢掉 NO 所需的 case。∎

**系（加速上界）**。设 `W=Σ_s T(s)`、`D=max_s T(s)`。P 个 worker 的 list-scheduling 上界是 `C_max≤W/P+(1−1/P)D`，所以

```text
speedup ≤ P / (1 + P·D/W) .
```

当 `D/W→0` 时接近 P；当 `D/W→1` 时退化到 1。5 个残例的 `D/W` 约 0.12–0.22，4 核上界约 2.1–3.6×；实测 1.70–2.07×（§5.4）。

### 4.4 蒙特卡洛可靠性

**定理 4（MC-CPS）**。固定链分布 D 和预算 `Ncap`。采样 `P_1,…,P_K~D`，每条链穷尽到返回 NO（异资格下遇到 RES=YES 可提前 UNKNOWN，只影响覆盖率）；若某条链返回 NO，则 `σ` 不可行。因此：

```text
P(假 NO) = 0 ,
P(漏检) ≤ (1−ρ)^K ,   其中 ρ = D({P : CPS(σ;P)=NO}) .
```

**证明**。每条链的 NO 由推论 1 保证；假 NO 需要某条链在被驳倒时 σ 仍可行，这与推论 1 矛盾。漏检是 K 条链都不在可驳倒集合中，概率 `(1−ρ)^K`（iid）。∎

**注**：`ρ` 是未知的；`(1−ρ)^K` 是条件界，不是无条件的保证。实验里用命中率估计 `ρ`（case 21: 12/30，case 47: 10/30）。如果一条链都不中，不能声称「大概率没有可驳倒链」，只能声称「这次没找到」。

**注（为什么不能采样 placement）**。placement 是存在句：一个可行排程只需要一个 placement；抽到 M 个失败的 placement，不能推出第 M+1 个也失败。除非穷尽，否则 `¬∃` 不成立。链是全称句：每条链都在每个可行排程里；驳倒一条链就足够。这是本轮把「蒙特卡洛」用在链上、而不是 placement 上的根本原因。

### 4.5 集成保持完备性

**定理 5（集成）**。PACE-ΠA-CP 只可能比 v2.1 多剪「已证明 NO」的状态；未被剪的状态仍按 v2.1 的 DHD/DCD 分支。因此：

- 若 PACE-ΠA-CP 返回 YES，排程可行；
- 若存在可行排程，PACE-ΠA-CP 不会返回 NO（除非 CPS/MAP 不可靠，而定理 1/2 与 v2.1 的 MAP 定理排除了这一点）。

**证明**。第 12 步的剪枝由推论 1（或定理 2 的 NO 方向）给出 NO 证书；其余步骤逐字是 v2.1。对搜索树归纳：每个被剪子树确实无解；未被剪的分支覆盖 v2.1 的全部分支。∎

**注**：`Ncap` 命中只产生 UNKNOWN，不产生 NO；`cps_tau`/`cps_ncap`/`cps_depth` 门关掉只少剪；异资格下 `YES` 被降级为 UNKNOWN。所以这些参数都不破坏完备性。

### 4.6 与 MAP 的分离

**命题 1（5 个残例是严格分离）**。在 held-out 的 idx 5/21/32/42/47 上，`h=OPT−1`：

```text
MAP(σ)=1，CPS(σ)=0，v2.1 节点 26/23/47/42/46，v2.2 节点 1/1/1/1/1。
```

`CPS=0` 由推论 1 是 NO 证书；`MAP=1` 说明 MAP 的划分/匹配 relaxation 在这些状态上没有矛盾。所以 MAP 严格弱于 CPS（在 CPS 能跑的紧状态上），两者的差距不是常数因子，而是**时间变量**。

**证明**。`CPS=0` 的可重放证书见 §5.3；`MAP=1` 由 v2.1 的 MAP DP 返回。两者在同一状态上同时成立，故 MAP 不是 CPS 的细化。∎

**注**：CPS 在它的门内是精确的，所以它也会覆盖 MAP 的 NO；但 MAP 更便宜、覆盖更宽（不要求 S≤4），所以主配置仍把 MAP 放在 CPS 前面。

### 4.7 NP-hard 下界

**命题 2**。CPS 没有打破 NP-hard 下界：

- MAP 的判定在 `m=2`、无优先、全资格时是 PARTITION：把 `p` 分成两块，每块和 ≤h；NP-hard。
- CPS 固定链后的 residual 在无优先、全资格、链长为 1 时是 `P||Cmax` 的判定（m 机装填到 h）；NP-hard。

所以 CPS 的指数不是实现问题，而是问题本身；它把指数从「搜索树的 d!」搬到「S 的 composition 数 × residual 的回溯」。∎

---

## 5. 实验

### 5.1 设置

Python 3.12，4 vCPU，单线程跑主搜索；并行原型用 `os.fork`。主配置：

```text
mode='pot', nodecap=3,000,000, mint_on=True, mint_depth=0,
packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
dhd=True, dcd=True, hpack_on=True, odom=False,
omd=fe(inst)（全资格才开）, map_on=True, map_tau=4, map_ncap=16,
cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
cps_nodecap=300000, cps_gate_fan=0.
```

数据与 v2.0/v2.1 逐字相同：`exp/v13/hard3.pkl`（12）、`exp/v14/{large_a,large_b,large_het}.pkl`（8+10+8）、`exp/v18/deep.pkl`（8）、`exp/v20/holdout_cases50.pkl`（50）、easy 60、planted 21。代码：核心 `exp/v25/cps_lib.py` + `exp/v25/pace_v25.py`；本轮并行/蒙特卡洛原型 `exp/v26/`。

### 5.2 主结果

| 集合 | 数量 | v2.0 | v2.1 | **v2.2** | v2.2/v2.1 | 时间 v2.1→v2.2 |
|---|---:|---:|---:|---:|---:|---:|
| `hard3` + `large_*` | 38 | 88 | 38 | **38** | 1.000× | 0.1127→0.1125 s |
| `deep` | 8 | 223 | 8 | **8** | 1.000× | 0.303→0.303 s |
| `held-out` | 50 | 1,935 | 229 | **50** | **4.580×** | 2.177→3.505 s |
| `easy`（h=OPT+5） | 60 | 781 | 781 | **781** | 1.000× | 0.1663→0.1665 s |
| `planted` n=17–24 | 21 | 7,869 | 21 | **21** | 1.000× | — |

表数：38 例 23→2→2；deep 115→6→6；held-out 818→128→**44**。5 个残例是 held-out 的全部节点差（229−50=179=184−5）；其余 45 例 v2.1 已经是 1 节点，v2.2 不动。

**逐例**：38 例和 deep 的 v2.1→v2.2 变化为 0；held-out 只有 idx 5/21/32/42/47 变化；easy 的 CPS 调用 0 次（`slack` 大，门不触发）；planted 由 MAP 根闭，CPS 不调用。所以本轮是「用一个根证书换 5 个残例」，不是全局提速。

### 5.3 5 个残例：CPS 的正面结果

| idx | n | v2.1 节点 | **v2.2** | MAP | CPS | S | L | placements | residual 节点 | CPS 时间 |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 5 | 15 | 26 | **1** | 1 | **NO** | 1 | 6 | 7 | 16,810 | 0.380 s |
| 21 | 13 | 23 | **1** | 1 | **NO** | 2 | 4 | 15 | 36,979 | 0.751 s |
| 32 | 15 | 47 | **1** | 1 | **NO** | 2 | 5 | 21 | 900 | 0.027 s |
| 42 | 16 | 42 | **1** | 1 | **NO** | 3 | 5 | 56 | 19,208 | 0.265 s |
| 47 | 15 | 46 | **1** | 1 | **NO** | 1 | 6 | 7 | 37,074 | 0.606 s |
| **合计** | | **184** | **5** | | | | | 106 | 110,971 | 2.03 s |

5 个残例的关键链（`critical_path`）分别是：

```text
idx 5 : [0,1,4,8,12,14]      S=1
idx 21: [0,1,8,11]           S=2
idx 32: [0,2,10,11,13]       S=2
idx 42: [0,3,7,8,15]         S=3
idx 47: [0,1,2,5,12,13]      S=1
```

placement 数正好是 `C(S+L,L)` 再减去被 deadline 过滤的候选：5/47 是 7，21 是 15，32 是 21，42 是 56。全部 placement 的 residual 都是 NO，所以 CPS 在根上闭合。这里的 NO 由同一 CPS 内核（minopts 顺序）生成；换一个独立检查器的顺序，case 21 会有 placement 撞 2M cap（§6.6），说明证书可重放、但不短。

**为什么这 5 个例子的不可行性不是 MAP 能看见的**：它们是全资格，MAP 的块到机器匹配没有矛盾；不可行性来自「块与块之间的时间」——一个块里的任务必须早，另一个块里的任务必须晚，两个块的内部可行顺序在时间上无法同时成立。CPS 把这件事变成「链的所有 placement 都失败」，逐个时刻检查。以 idx 32 为例，关键链 `[0,2,10,11,13]` 有 21 个合法 placement；对每个 placement，窗口传播都成立、初始容量也非负，但 residual 的 21 次精确回溯都找不到一组同时满足优先、窗口和容量的起点。没有单个 O(1) 的矛盾，21 个 case 合起来才是证书——这正是 MAP 的「块级存在句」看不见、而 CPS 的「链级全称句」能看见的东西。

### 5.4 并行：4 核 1.98×

| idx | placements | W=1 | W=2 | W=4 | 4 核加速 |
|---|---:|---:|---:|---:|---:|
| 5 | 7 | 0.338 | 0.178 | 0.166 | 2.04× |
| 21 | 15 | 0.755 | 0.411 | 0.366 | 2.07× |
| 32 | 21 | 0.027 | 0.016 | 0.016 | 1.70× |
| 42 | 56 | 0.270 | 0.158 | 0.148 | 1.83× |
| 47 | 7 | 0.607 | 0.381 | 0.311 | 1.95× |
| **合计** | 106 | **1.997** | 1.143 | **1.006** | **1.98×** |

环境：4 vCPU，Python 3.12，`os.fork`，静态 round-robin 分块，`Ncap=300k`，3 次中位数；全部 verdict 为 NO。W=2 时合计 1.143 s（1.75×），W=4 时 1.006 s（1.98×）。

**解释**：`D/W` 在 case 5/21 约 0.22/0.22，4 核上界 `4/(1+4·0.22)=2.13×`，实测 2.04/2.07×，几乎贴着上界；case 32/42 的 `D/W` 小，但总工作量只有 0.027/0.270 s，fork/管道/静态分块的开销占比上升，所以只有 1.70/1.83×。这不是「并行没用」，而是「证书的关键路径就是最长的那个 residual」；要再快，需要并行化 residual DFS 本身，而不是 placement。

### 5.5 蒙特卡洛：预算受限时才有用

默认 `Ncap=300k` 时，关键链 5/5 根闭，链 portfolio 没有额外收益。把每个 placement 的预算收紧到 `Ncap=4,000`：

| 链 | 5 | 21 | 32 | 42 | 47 | 根闭 |
|---|---|---|---|---|---|---|
| critical | NO | **UNK** | NO | NO | **UNK** | 3/5 |
| longest / portfolio | NO | NO | NO | NO | NO | **5/5** |
| 随机链（30 条命中率） | — | 12/30 | — | — | 10/30 | — |

- case 21 的关键链单个 placement 需要 8,098 节点；4k 预算下有 placement 撞 cap，无法给 NO。
- case 47 的关键链单个 placement 超过 8,000 节点；4k 下同样 UNK。
- 换一条更长的链（residual 更小）后，单 placement 的尾部下降：case 21 的 `longest` 最大 3,913，case 47 的 `longest` 最大 1,854；两者都能在 4k 内被驳倒。`longest` 的代价是 placement 数变多（case 47 的 217 vs 7；总节点 181,634 vs 37,074），所以它是**预算/tail** 的备选，不是默认。
- 随机链：case 21 的 30 条里 12 条 NO（最好 `[0,2,3,11]`，501 placements，max 2,036）；case 47 的 30 条里 10 条 NO（最好 `[0,1,3,4,8,11]`，217 placements，max 1,854）。`ρ≈0.33–0.40`，K=8 的漏检估计约 `0.6^8–0.67^8≈1.7–3.9%`。

**结论**：蒙特卡洛的正确用法是「预算受限时换一条链」，不是「随机化 placement」。默认预算下它是纯开销；4k 预算下它把 3/5 提到 5/5（用 longest）或提供 40% 的随机命中率。这个边界要写清楚，不能把它说成普遍的节点收益。

### 5.6 正确性

| 测试 | 规模 | 结果 |
|---|---|---|
| CPS-vs-精确引擎，A=0，全资格 | 1,430 状态 | **0 不一致**（2.13 s） |
| CPS-vs-精确引擎，随机 A，全资格 | 1,977 状态 | **0 不一致**（1.86 s） |
| 异资格：CPS=NO ⇒ 精确引擎 NO | 1,977 状态 | **150 个 NO，0 假 NO**（2.59 s） |
| held-out `h=OPT` | 50 | 49 YES / 1 UNKNOWN / **0 NO**；50 个 YES 排程独立验证 |
| held-out `h=OPT−1` | 50 | 全部 NO；5 个残例由 CPS 根闭，其余由 MAP/搜索 |
| 5 个残例的 CPS 证书 | 5 | 同一内核重放每个 placement 的 residual=NO；独立检查器换顺序后 case 21 撞 2M cap（§6.6） |

「0 不一致」的定义：同一实例、同一 h、同一状态，CPS 与精确引擎（v2.1 的完整搜索，`map_on=False`）返回同一布尔值；YES 时两边都独立验证排程（任务一次、优先、机器不重叠、资格、h）。异资格只比较「CPS=NO ⇒ 引擎 NO」，因为 CPS=YES 在异资格下只是 unknown。

**注意**：这不是 Coq/Lean；是随机/半穷举对拍 + 可重放内核。

### 5.7 消融

**(a) `cps_tau`（5 个残例）**：

| tau | 节点 | CPS calls | prunes |
|---:|---:|---:|---:|
| 0 | 184 | 0 | 0 |
| 1 | 114 | 2 | 2 |
| 2 | 46 | 4 | 4 |
| 3 | **5** | 5 | 5 |
| 4 | **5** | 5 | 5 |

tau=3 已经饱和；默认 4 留一档余量。tau=0 逐字回到 v2.1 的 184。

**(b) `cps_depth`**：0/1/2/3/∞ 在 5 个残例上都是 5 节点（根已经闭合）；更深只增加调用机会，本轮没有观察到收益。默认 0 是成本门。

**(c) residual 用 flow**：把精确回溯换成多项式抢占 flow（`_residual_flow`），5 个残例的每个都至少有一个 placement 的 flow 松弛返回「可行」，CPS 提前 UNKNOWN，节点回到 184。**这是本轮最重要的负结果**：多项式松弛不够；精确 residual 是 CPS 的力量来源，也是它的成本来源。

**(d) 链选择**：

| idx | critical S / placements / 节点 / 时间 | longest S / placements / 节点 / 时间 |
|---|---|---|
| 5 | 1 / 7 / 16,810 / 0.380 | 5 / 55 / 15,575 / 0.330 |
| 21 | 2 / 15 / 36,979 / 0.751 | 3 / 31 / 42,012 / 0.978 |
| 32 | 2 / 21 / 900 / 0.027 | 3 / 45 / 915 / 0.028 |
| 42 | 3 / 56 / 19,208 / 0.265 | 7 / 464 / 156,586 / 2.265 |
| 47 | 1 / 7 / 37,074 / 0.606 | 1 / 7 / 37,074 / 0.606 |

critical 在 4/5 上更便宜；idx 42 的 longest 是 8.6× 慢。**不要默认用 longest**；它只是预算受限时的备选。这里的 longest 是 `chain_analysis.py` 的一种 tie-break；§5.5 的 portfolio 对 47 用了另一条同长度链 `[0,1,3,4,8,11]`（217 placements、max 1,854、总 181,634），它能在 4k 下闭合关键链闭不了的 case。这说明「同样的长度，不同的链」也有成本差异，tie-break 本身也是链选择的一部分，portfolio 有意义。

### 5.8 负结果：随机化 residual 顺序是坏的

case 42（56 placements）的 residual 节点数：

| 变量/值顺序 | 总节点 | 单 placement 最大 |
|---|---:|---:|
| **minopts + 升序（默认）** | **19,208** | **2,209** |
| maxp + 升序 | 2,427,057 | 90,928 |
| mindeadline + 升序 | 21,361 | 2,652 |
| random + random，seed 0 | 1,580,254 | 65,891 |
| random + random，seed 2 | 547,573 | 32,326 |

minopts 是一个强 MRV 启发式；随机化把它破坏，节点数上升 28–126×。所以本轮不做「residual 的随机重启」，只做「链的随机化」。这是一个明确的负结果，也是下一轮如果要并行化 residual DFS 时必须先解决的问题。

---

## 6. 负结果与陷阱

### 6.1 flow 松弛不够

把 residual 换成多项式抢占 flow（任务→时刻→容量），5 个残例全部 UNKNOWN；flow 能看见「总量/区间」超载，但看不见「非抢占 + 优先序 + 紧窗口」的组合。CPS 的力量来自精确回溯；这也是它的成本。

### 6.2 CPS 是根证书，不是可扩展算法

门是 `S≤4, n≤16, depth=0`。5 个残例的 S=1,2,2,3,1，n=13–16；换成 n=20、S=10，placement 数 `C(30,20)=30,045,015`，CPS 不可能跑。它不是「解决 P|prec|Cmax」，而是「在紧状态上把 5 个残例从搜索树里拿掉」。

### 6.3 异资格只保证 NO

`RESIDUAL` 不检查 eligibility；`CPS=YES` 在异资格下只是 unknown。实现里异资格遇到 RES=YES 会提前返回 UNKNOWN，不再检查剩余 placement；这是一个覆盖率折中（只少剪，不多剪），完整版应继续检查其余 placement。反例见 §4.2：`m=2, A=(6,0)`，`i` 只上机器 0、`j` 只上机器 1，CPS 的容量模型说可行，实际超期。所以异资格实例的 `omd=False` 硬门仍然要保留；CPS 不修这个问题。

### 6.4 并行是 Amdahl，不是线性

4 核 1.98×，不是 4×；`D/W≈0.22` 时理论上界只有 2.13×。并行化的正确目标是 residual DFS 的内部，而不是 placement 之间；但那需要共享 memo/剪枝，难度更高。

### 6.5 链选择不是免费的

critical 在 idx 42 是 56 placements / 0.265 s；longest 是 464 / 2.265 s（8.6×）。默认 critical 是对的；portfolio 只在预算/tail 受限时用。idx 47 的 tie-break 还说明「同长度不同链」的成本可以差很多（7 vs 217 placements），所以链的采样/选择是一个真问题，不是随便取一条。

### 6.6 没有短证书，且检查器的顺序也影响成本

CPS-NO 的检查器要重跑 placement 枚举 + residual DFS，代价与生成同阶；它不是 LP 对偶/团证书那样的 O(n) 短证书。优点是检查器不需要信任搜索树、不需要浮点/ LP；缺点是证书不短。更麻烦的是，residual 的变量/值顺序会改变检查成本：同一内核的 minopts 在 case 21 只要 36,979 节点；独立检查器用 latest-deadline/降序，9 个 placement 撞 2M cap。也就是说，证书可重放，但「重放」本身不是免费的，检查器必须用和生成器同阶的搜索。

### 6.7 `est/q/A` 必须精确

`est` 高估、`q` 高估、`A` 高估都会让 CPS 假 NO；低估只会让 CPS 更弱（更安全）。PACE 里 `est` 是精确最长头、`q` 是精确最长尾、`A` 是实际可用时刻；这个继承的规格不能动。

### 6.8 公共期限

CPS 用公共期限 `h` 和 `q_i`。若任务有各自期限 `d_i`，把 `h−q_i` 换成 `d_i`，引理 1/2 的窗口部分仍成立；但 residual 的容量/精确性要重证，引擎里没有这条路径。

### 6.9 实现陷阱

- gap 的最后一个分量 `g_L` 是**链后松弛**，不是 `h−(s_L+p_L)`；两者差 `q_{i_L}`。写成后者会把 composition 的和算错，导致漏 placement 或越界。
- 链任务的 `d_i` 要钉成 `s_i+p_i`，不是 `h−q_i`；否则窗口传播不够紧，residual 会假可行。
- 容量 `c_s(t)` 要按整数时刻 t 建，长度 h；链占用是半开区间 `[s,s+p)`。
- residual 的 memo key 要含 `cap` 和 `rel`；只含 `mask` 会把不同窗口的状态合并，假 NO。
- `Ncap` 命中必须是 UNKNOWN，不能当 NO；这是最容易写错的一行。

### 6.10 没有形式化验证

1,430/1,977/1,977 对拍 + 5 个残例的重放 + 50 个 h=OPT 的 0 假 NO + 50 个 YES 排程验证，是很强的证据，但不是 Coq/Lean。定理 1–5、引理 1–2 是纸面证明 + 可重放内核。

---

## 7. 与 v2.1 的差异清单

| 项 | v2.1 | v2.2 |
|---|---|---|
| 攻击对象 | 块到机器的匹配 | 链到时间的 placement |
| 新层 | `MAP`（tier 0.10） | `CPS`（tier 0.15） |
| 判据 | `∃` 划分 + 单射 `φ`，`f_{φ(j)}[S_j]<∞` | `∀` placement `s`，`RES(σ,P,s)=0` |
| 用到的结构 | 每机器单机 postcondition `f_k[S]` | 链 + 窗口 + 容量 profile + residual |
| 证书 | 重放 MAP DP | 重放 placement 枚举 + residual DFS |
| 与精确性的关系 | relaxation | 全资格 + 精确 residual 时 exact |
| 新定理 | MAP 可靠性、β 退化、严格分离、见证、CSE、单向性 | + 链投影、CPS 可靠性、精确性、并行、MC 可靠性、集成 |
| 新负结果 | 5 残例、β 漏机器、无短证书、见证启发式、DP bug | + flow 不够、随机 residual 坏、Amdahl、异资格反例、链选择 |
| held-out | 229 / 128 表 / 2.18 s | **50 / 44 表 / 3.51 s** |
| 5 残例 | 184 | **5** |
| 38 / deep / easy / planted | 38 / 8 / 781 / 21 | 38 / 8 / 781 / 21 |
| 代价 | MAP 的 3^k（k≤16） | CPS 的 `C(S+L,L)` × residual（S≤4, n≤16） |

---

## 8. 已知风险

1. **CPS 是根证书**：`S≤4、n≤16、depth=0`；n=20、S=10 时 placement 数爆炸，CPS 不可用。它不是可扩展算法。
2. **精确 residual 是指数**：最坏 O(r!)；`Ncap` 命中只给 UNKNOWN。flow 松弛不够（5/5 UNKNOWN），所以不能用一个多项式内核替代。
3. **异资格只保证 NO**：`RES` 忽略 eligibility；`CPS=YES` 不是可行性证明。反例见 §4.2；`omd=False` 硬门仍要保留。
4. **没有短证书**：CPS-NO 是重放，检查器要重跑 placement + residual；不是 O(n) 证明。
5. **并行上限**：4 核 1.98×，`D/W` 大时理论上界只有 2.1×；不是线性。
6. **MC 是覆盖率启发式**：默认 cap 下 0 额外收益；4k 下依赖 ρ，K 条漏检概率 `(1−ρ)^K`，ρ 未知；不能把「没抽到」当成「不存在」。
7. **链选择**：critical 通常最便宜，但 idx 42 的 longest 慢 8.6×；idx 47 的同长度 tie-break 成本差 7 vs 217 placements。默认 critical，portfolio 只在预算受限时用。
8. **`est/q/A` 精确性**：高估会假 NO；这是继承的规格，不能动。
9. **`omd` 硬门**：异资格必须 `omd=False`；CPS 不修 v1.6 的支配条件。
10. **公共期限**：各自期限 `d_i` 的路径未实现；把 `h−q_i` 换成 `d_i` 后 residual 的精确性要重证。
11. **门的覆盖率**：`S≤4` 是启发式；更松的紧实例可能不触发。门关掉只少剪，不多剪，但会改变实验数字。
12. **时间**：held-out 2.18→3.51 s（1.61×）；38/deep 几乎不变；easy +0.0002 s。对根下界已经接近 OPT 的实例，CPS 是纯开销。
13. **内存/栈**：residual DFS 递归深度 ≤ r；`cap` 数组长度 h；5 个残例的 r≤11，没问题；n=16 以上要小心。
14. **没有形式化验证**：纸面证明 + 随机/半穷举 + 重放，不是 Coq/Lean。

---

## 9. 一句话最大风险

**CPS 用「枚举一条链的所有 placement + 精确 residual 回溯」换来了 5 个残例的根闭，但它的完备性只覆盖 `S≤4`、`n≤16`、全资格且 residual 未撞 cap 的紧状态；一旦 residual 变大或资格异构，它只能退回 unknown，最坏情况仍是 d!。**
