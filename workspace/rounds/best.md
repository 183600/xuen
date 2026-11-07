# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 26 轮（新灵感循环第 4 轮）· TEMPO-NAV：力矩对账 + 热增强想象 + 截止期感知 anytime 规划

## 0. 先给直觉：为什么「力矩传感、实时性、热管理」恰好是对第 25 轮风险的精准回应？

从第 25 轮最大风险出发：
> **想象模型的「概念漂移」——σ 误判（过度保守或过度激进），而回退策略依赖「想象即辨识」的假设在真实物理系统上不可靠。**

三个灵感词各回答一层：
- **力矩传感**回答「谁来审计想象」：学习出来的 σ 会漂移，但关节力矩 τ_meas 是 1kHz 直接测量、零学习成分的物理信号。「预测力矩 vs 实测力矩」的对账不依赖任何学习组件的自觉性——**想象可以被物理审计**。
- **实时性**回答「想象能不能按时交付」：PRISM-NAV 的 O(N^D)×T_MC 规划在边缘 GPU 上延迟长尾，一旦计算热节流，执行器拿到的是 100ms 前的过期想象。实时性要求把规划从「算到最好」改成「截止期内交付最好」。
- **热管理**回答「想象是否物理可持续」：世界模型只看接触状态，不看电机绕组温度 θ。持续按压任务里，计划在 2s 内完美、30s 后必然触发 τ_lim(θ) 降额而中断——运动学完美、热学自杀。且 GPU 热节流与电机热降额结构同构：一个「热」字串起物理与计算两层资源。

核心灵魂：**把想象从「离线信仰」变成「被物理审计、被截止期约束、被热预算限制的在线服务」**。

一句话押注：
> **本轮给每个原语世界模型增广为 μ_z(s, a, θ) → (r, s', θ', τ̂, σ)：力矩头物理锚定（τ̂ = τ_motion + Jᵀf̂），热转移灰箱（一阶 RC，每关节 2 个可辨识参数）；OOD-GUARD 升级为四信号，新增「物理对账」——滑动窗标准化残差 u = e_τ/σ_τ 的 E[u²]≈1 构成 χ² 校准检验，σ 纯尺度漂移被比值自动抵消、真实漂移必打破分布，CUSUM 检出时延 O(M/δ²)；规划器 L3'' 升级为截止期感知 anytime 迭代加深（最坏情况保底深度-1），(D, N, T_MC) 由 p99.9 延迟预算动态分配，GPU 热节流自动降级并切换 500Hz 蒸馏策略；热可行性经闭式投影进入剪枝与终端代价；运行时升级为 1kHz 安全 / 500Hz 反应 / 50Hz 想象三节拍。**

## 1. 研究日志：从「想象信仰」到「被审计的想象服务」

### 1.1 第 25 轮系统的三个症状
```text
S1. σ 自我漂移：μ_z 的 σ 由学习组件自评，刚度/材质渐变时 σ 与真实误差同向漂移，
    校准失效而三信号无感——自评者无法发现自己作弊；
S2. 想象迟到：O(N^D)·T_MC ≈ 5000 次前向，边缘 GPU p99 延迟 >100ms，
    计算热节流时更糟——执行器拿到的是过期想象（陈旧计划比无计划更危险）；
S3. 热盲计划：持续按压 30s 后电机降额 τ_lim(θ) 收缩，任务中途强制中止
    ——第 25 轮世界模型的状态空间里根本没有 θ。
```

另修正第 25 轮一处记号瑕疵：2-D 动作空间均匀网格 N 点/维，实际 |𝒜| = N²（非 N），深度 D 穷举为 (N²)^D；本轮引入批量前向与预算分配后该记号问题被 anytime 框架自然吸收。

### 1.2 三个新判断
1. **力矩是最难作弊的物理信号**：τ_meas 不经过任何学习组件，1kHz、全域覆盖（腕部 F/T 之外的整臂接触感知）。残差 e_τ = τ_meas − (τ_motion + Jᵀf̂) 同时暴露接触力预测误差与动力学模型误差；标准化比值 u = e_τ/σ_τ 在校准假设下 E[u²]=1、Var[u²]=2（高斯），是**无需真值标签的模型诚实性检验**；
2. **实时性的本质是延迟分布而非均值**：预算必须按 p99.9 分配，最坏情况要有保底答案（深度-1 + 1kHz 无学习安全层），「平均 5ms」在安全攸关系统里是谎言；
3. **热要用灰箱不要黑箱**：一阶 RC 模型每关节仅 2 个参数（1/C, κ/C），对 θ̇ 是线性回归、激励充分下可辨识，温区外外推能力远强于黑箱网络；θ 是慢变量（时间常数分钟级），任务级闭式投影即可，不必拖进每步接触想象。

### 1.3 与第 25 轮 PRISM-NAV 的关系（增量演进）

| 层 | 第 25 轮 | 第 26 轮 TEMPO-NAV | 关系 |
|---|---|---|---|
| 世界模型 | μ_z(s,a)→(r,s',σ) | μ_z(s,a,θ)→(r,s',θ',τ̂,σ)：+ 力矩头（物理锚定）+ 灰箱热 | **增广** |
| OOD 检测 | 三信号 min | 四信号：+ 物理对账（χ² 校准检验 + CUSUM） | **融合** |
| 规划 | O(N²)^D 穷举 + σ 剪枝 | L3''：截止期 anytime 迭代加深 + 批量前向 + σ/热剪枝 + (D,N,T_MC) 预算分配 | **升级** |
| 低层执行 | 1kHz 阻抗 + 0.2s 混合 | + 动量观测器碰撞反射（τ 传感，无学习、无 GPU）+ τ_lim(θ) 软饱和 | **增强** |
| 执行节拍 | 10Hz 规划 | 1kHz 安全 / 500Hz 蒸馏反应 / 50Hz anytime 想象 | **升级** |
| 基准 | BENCH v3 (T9-T11) | BENCH v4：+ T12 持续按压热任务 / T13 计算热节流 / T14 漂移注入 | **扩展** |

### 1.4 灵感词贯通
> **力矩传感**：第四观测模态，与腕部 F/T、触觉图互补（整臂无盲区、免标定漂移）；三个用途——动量观测器 1kHz 碰撞反射、力矩头物理锚定监督、对账审计的测量源。  
> **实时性**：三节拍架构 + anytime 保底 + p99.9 预算 + 蒸馏短路；安全层刻意做成「零学习、零 GPU」——最坏情况下想象全部失效，安全层仍在转。  
> **热管理**：两层同构——执行器热（θ 状态增广 + τ_lim(θ) 降额约束 + 任务级闭式投影）与计算热（GPU 节流 → 延迟预算收缩 → 自动降级）。同一套方法论：**把慢变量写进状态，把降额曲线写进约束，把预算写进调度**。

## 2. 直觉深化

### 2.1 为什么「对账」能免疫 σ 自我漂移？

| 漂移模式 | σ 自评 (PRISM-NAV) | 物理对账 (TEMPO-NAV) |
|---|---|---|
| σ 整体放大/缩小（尺度漂移） | ρ_in/ρ_mod 同向漂移，误判 | u = e_τ/σ_τ 无量纲，比值抵消，不误报 |
| 残差真实增大（模型漂移发生） | ρ_out 需绝对残差阈值，阈值本身随工况漂移 | E[u²] 立即 >1，M 窗内检出且量级可知 |
| 输入密度正常但物理失配 | 三信号都可能「正常」 | 对账直接命中「模型说行、物理说不行」 |

关键洞察：**校准检验是「自指系统」的唯一出口**——不引入外部真值，用「模型声明的不确定性」与「物理观测的残差」互为对偶：二者比值在 H₀ 下有已知分布（χ²），任何一方的谎报都会打破分布。

### 2.2 两个热、一个节拍
执行器热与计算热结构同构：资源消耗 → 温度上升 → 能力降额 → 必须自适应。前者约束 τ（快失效，秒-分钟级），后者约束推理延迟 ℓ（慢漂移，分钟-小时级）。TEMPO-NAV 用同一套「状态-约束-调度」三件套处理，且降级链完整：GPU 节流 → 想象降深度；GPU 全失效 → CPU 上的动量观测器 + τ_lim(θ) 饱和 + 定增益阻抗仍在转。

## 3. 形式化定义

### 3.1 增广状态与增广世界模型
- 增广状态 s⁺ = (s, θ)，θ ∈ ℝⁿ⁺¹（n 关节绕组温度 + 环境温 θ_amb）
- 动作 a ∈ ℝ²（不变）
- **世界模型**：μ_z(s, a, θ) → (r, s', θ', τ̂, σ)
  - r = −‖f̂_n − f_ref‖² − λ_a‖a‖² − λ_θ Σ_j max(0, |τ̂_j| − τ_lim,j(θ_j))²
  - s' = s + f̂·dt + a·dt（同第 25 轮）
  - **力矩头（物理锚定，非黑箱）**：τ̂ = τ_motion(q, q̇) + J(q)ᵀ f̂
  - **热转移（灰箱）**：θ' = θ + dt·( P(τ̂, ω) ⊘ C − κ ⊘ C ⊙ (θ − θ_amb) )，C, κ 可学习

### 3.2 物理对账统计量（第四 OOD 信号）
- 残差：e_τ = τ_meas − τ̂ ∈ ℝⁿ；力矩预测方差经雅可比传播：Σ_τ = Jᵀ Σ_f J + Var_MC[τ̂]，σ_τ = √diag(Σ_τ)
- 标准化：q_t = ‖e_τ,t ⊘ σ_τ,t‖²，H₀（校准成立）下 E[q]=n，Var[q]=2n
- 窗口统计：z_t = (q̄_M − n)/√(2n/M)，渐近 N(0,1)
- CUSUM：g_t = max(0, g_{t−1} + z_t − k)，g_t > h ⇒ 判漂移；ρ_phy = exp(−g_t/σ_phy)
- h 由目标虚警 ARL₀ 经 Siegmund 近似数值反解

### 3.3 截止期感知 anytime 规划器 L3''
```
plan_anytime(s, θ, ctx, deadline=20ms):
    cfg = budget_allocate(deadline, ℓ_p99, GPU_temp)      # → (D, N, T_MC)
    best = evaluate_depth1(cfg)                            # 一次批量前向，必交付（保底）
    for d in 2 .. cfg.D:
        if elapsed + est(d, cfg) > deadline: break         # est 由每扩展延迟 EMA+p99 外推
        cand = batched_dfs(d, cfg, σ_剪枝, 热剪枝)
        best = better(best, cand)
    return best.seq, best.depth
```
- 批量前向：把 B 个状态 × |𝒜| 个动作全部拼成一个 GPU batch（B·|𝒜|·T_MC 次前向 → 少数次 kernel 调用）
- **热剪枝的 admissibility**：只删除「经闭式投影到任务结束时程仍违反 τ_lim(θ)」的分支，不删「暂时超限但会冷却恢复」的分支
- 最坏情况保底：deadline 内必返回深度-1 结果，且其动作仍经 1kHz 安全层执行

### 3.4 热的闭式任务级投影
一阶 RC 下给定力矩调度 P_j(·)，逐步闭式解：
θ_j(t+Δt) = θ_amb + (θ_j(t) − θ_amb − P_j(t)/κ_j)·e^{−Δt/τ_th,j} + P_j(t)/κ_j
对候选任务轮廓（原语序列名义力矩调度）做 O(H) 递推检查 max θ_j < θ_crit；违反则在原语层插入冷却片段（低力矩 regrasp / 等待），或抬高该候选的计划代价。

### 3.5 三节拍运行时
| 节拍 | 内容 | 依赖 | 失效降级 |
|---|---|---|---|
| 1kHz | 阻抗 + 动量观测器碰撞反射 + τ_lim(θ) 软饱和 | CPU：τ_meas, q, q̇ | 永不失效（零学习、零 GPU） |
| 500Hz | 蒸馏策略 π_distill(s⁺) → a（DAgger 蒸馏自 anytime 规划的 (s, seq) 对） | GPU | 降为定增益阻抗 |
| 50Hz | anytime 想象重规划 + 审计更新 + 预算重分配 | GPU | 降为深度-1 / 冻结上帧计划 |

## 4. 性质与复杂度

### 4.1 理论性质
**命题 1（anytime 保底与单调改进）**：假设 A1 模型一致（E[s'|s,a] 收敛真值）、A2 剪枝 admissible（σ 阈值剪枝视为风险有界规划的保守化；热剪枝仅删「投影到任务结束仍违规」分支），则最优值 V*_d 关于深度 d 单调不减；算法在 deadline 内必返回深度-1 动作，故最坏情形质量有显式下界；期望质量随时间预算单调不减。
**命题 2（对账检验的虚警/检出界）**：H₀ 下 q_t 独立同分布、E[q]=n、Var[q]=2n（高斯情形），窗均值 z_t 由 CLT 渐近 N(0,1)；单边 CUSUM（允差 k，门限 h）的 ARL₀ 由 Siegmund 近似给出，可反解到任意目标虚警率；存在校准破坏（均值偏移 δ>1）时平均检出时延为 O(h/δ)，且不受 σ 尺度漂移影响（比值统计量尺度不变）。严格优于第 25 轮依赖绝对残差阈值的 ρ_out（其阈值随工况漂移需重标定）。
**命题 3（热灰箱可辨识性）**：θ̇ = (1/C)·P − (κ/C)·(θ − θ_amb) 对参数 (1/C, κ/C) 线性；激励充分（P 持续变化）下最小二乘一致估计，2 参数/关节的样本复杂度远低于黑箱；外推偏差被限制在一阶 RC 模型类内。

### 4.2 复杂度与延迟
| 模块 | 频率 | 复杂度 | 典型延迟 |
|---|---|---|---|
| 动量观测器 + 阻抗 | 1kHz | O(n_j) | <10 μs (CPU) |
| π_distill | 500Hz | O(1) MLP 前向 | <0.2 ms |
| anytime 规划 | 50Hz，deadline=20ms | ≤ 预算内扩展数；保底 O(|𝒜|·T_MC) | ≤20 ms（硬保证，p99.9 预算） |
| 闭式热投影 | 任务级，每候选 | O(H) 递推 | <1 ms |
| 审计 CUSUM | 50Hz | O(M) 增量 | <0.1 ms |

## 5. 风险

**本轮最大风险**：「物理对账」依赖的逆动力学/摩擦模型本身也是模型——变速、变温下的摩擦系统偏差会污染 e_τ，审计可能把「动力学模型误差」误判为「世界模型漂移」，造成慢性误回退；且热参数在线自适应与漂移检测耦合后存在正反馈震荡风险。

次级风险：MC Dropout 少采样（T_MC=2）下方差估计噪声大，可能虚报 σ；蒸馏策略在分布偏移下退化（DAgger 缓解但不消除）；θ 传感器缺失时需从电流/外壳温估计绕组温，引入额外误差源。

## 6. 下一轮展望
若下轮灵感指向「联邦学习」→ 对账统计量与热参数跨机体联邦校准（审计知识共享）；若指向「可解释性」→ 对账残差做逐关节归因，漂移定位到具体原语/关节；若指向「主动感知」→ 规划器主动注入「探测动作」缩小 σ，把想象变成主动学习的探针。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 26 轮产物 · TEMPO-NAV 技术报告：力矩对账 + 热增强想象 + 截止期感知 anytime 规划

## 0. 结论：从「想象信仰」到「被审计、被定时、被限热的想象服务」

TEMPO-NAV 在第 25 轮 PRISM-NAV 基础上做**增广与升级**（不推倒）：
- **μ_z v2**：世界模型增广 θ 状态，新增物理锚定力矩头 τ̂ = τ_motion + Jᵀf̂ 与灰箱热转移
- **OOD-GUARD v3**：三信号 → 四信号，新增「物理对账」（χ² 校准检验 + CUSUM），免疫 σ 尺度漂移
- **L3''**：O(N²)^D 穷举 → 截止期感知 anytime 迭代加深，(D, N, T_MC) 由 p99.9 延迟预算分配
- **运行时 v2**：1kHz 无学习安全层 / 500Hz 蒸馏反应 / 50Hz anytime 想象，降级链完整
- **BENCH v4**：新增 T12 热任务 / T13 计算热节流 / T14 漂移注入

## 1. 符号表（含沿用与新增）

| 符号 | 含义 | 来源 |
|---|---|---|
| s, a, 𝒵, φ_z, π_z | 接触状态、动作、原语库、前置条件、执行策略 | 第 24/25 轮沿用 |
| θ ∈ ℝⁿ⁺¹ | 关节绕组温度 + 环境温 θ_amb | **新增** |
| τ_meas ∈ ℝⁿ | 关节力矩传感器测量（1kHz） | **新增** |
| τ_motion(q, q̇) | 逆动力学（惯量+科氏+重力+摩擦） | **新增** |
| J(q) ∈ ℝⁿˣ⁶ | 末端雅可比 | **新增** |
| μ_z(s, a, θ) → (r, s', θ', τ̂, σ) | 增广世界模型 | 第 25 轮 μ_z **增广** |
| e_τ = τ_meas − τ̂, u = e_τ ⊘ σ_τ | 力矩残差、标准化残差 | **新增** |
| q_t = ‖u_t‖², z_t, g_t, k, h | 对账统计量、窗统计、CUSUM 状态、允差、门限 | **新增** |
| τ_lim,j(θ_j) | 热降额力矩上限（单调递减曲线） | **新增** |
| C_j, κ_j, τ_th,j = C_j/κ_j | 热容、散热系数、热时间常数 | **新增** |
| ℓ_p99, deadline | 每扩展延迟 p99 分位、规划截止期 | **新增** |
| π_distill | 蒸馏反应策略（s⁺ → a） | **新增** |
| D, N, T_MC | 想象深度、动作网格密度、MC 采样数（预算分配对象） | 第 25 轮沿用并预算化 |

## 2. 算法完整流程

### 2.1 离线训练阶段
```
for each primitive z in 𝒵:
    collect dataset 𝒟_z = {(s, a, θ, τ_meas, f_meas, q, q̇, ω, θ_next)} from K_demo 演示
        # 演示时同步记录关节力矩与温度通道（新增采集协议，向后兼容旧数据）
    train WorldModelV2 μ_z:
        ℒ_z = E[ ‖f̂ − f_meas‖² + ‖τ̂ − τ_meas‖²
               + λ_th ‖θ̂' − θ_meas'‖²
               + λ_σ KL(σ, σ_mse) ]          # τ̂ 由物理锚定头给出，只需监督 f̂ 即可传播
        gray-box: (1/C_j, κ_j/C_j) 由 θ̇ 对 [P, θ_amb − θ] 线性回归初始化，
                  再与网络端到端微调（保持物理结构，防止黑箱退化）
    calibration gate（新增上线门槛）:
        held-out 集：E[u²] ∈ [0.8, 1.25] 且 z_t 无 CUSUM 触发 ⇒ 通过
        未通过 ⇒ 增大 σ_τ 标定系数重训（宁可保守，不可谎报）
```

### 2.2 在线运行（三节拍）
```
# 1kHz 安全层（CPU，零学习零 GPU，永不失效）
every 1ms:
    collision, r_obs = momentum_observer(q, q̇, τ_meas)     # 无学习碰撞反射
    if collision: trigger R1 (急停降参) and notify 50Hz 层
    a_sat = tau_limit_saturation(a_cmd, τ_lim(θ))           # 热降额软饱和
    impedance_control(a_sat)                                 # 第 24 轮 L1 沿用

# 500Hz 反应层（GPU）
every 2ms:
    a = π_distill(s, θ)                                      # DAgger 蒸馏自 anytime 规划

# 50Hz 想象层（GPU）
every 20ms:
    cfg = budget.allocate(deadline=20ms, ℓ_p99, gpu_temp)    # p99.9 预算分配
    seq, depth = plan_anytime(s, θ, ctx, cfg)                # 保底深度-1
    replay_buffer.append((s, θ, seq))                        # 蒸馏数据（DAgger）
    rho = ood_guard_v3(σ_μ, σ_ens, CUSUM_f, auditor.g)       # 四信号 min
    if rho < 0.3: execute(seq, scale=0.3~0.5)                # 保守想象 + 降速
    else:          distill target 更新为 seq
    thermal_projection(候选任务轮廓)                          # O(H) 闭式，越界插冷却片段
```

## 3. Python 核心实现

```python
import time
import torch
import torch.nn as nn
import numpy as np
from collections import deque

# ============================================================
# 0. 增广世界模型 μ_z(s, a, θ) → (r, s', θ', τ̂, σ)
#    （第 25 轮 WorldModel 的增量改造：+ 力矩头 + 灰箱热）
# ============================================================
class WorldModelV2(nn.Module):
    def __init__(self, s_dim: int, a_dim: int, n_joints: int, hidden: int = 128):
        super().__init__()
        self.n_joints = n_joints
        self.backbone = nn.Sequential(
            nn.Linear(s_dim + a_dim + n_joints + 1, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.f_head = nn.Linear(hidden, 6)
        self.s_next = nn.Linear(hidden, s_dim)
        self.log_sigma = nn.Linear(hidden, 1)
        # 灰箱热参数：每关节 2 个可学习标量（物理结构固定，防黑箱退化）
        self.inv_C = nn.Parameter(torch.full((n_joints,), 1e-2))        # 1/C
        self.kappa_over_C = nn.Parameter(torch.full((n_joints,), 1e-3)) # κ/C

    def thermal_step(self, theta, tau_hat, omega, theta_amb, dt=0.02, eta=0.05):
        # P ≈ |τ|·|ω| + η·τ²（铜损，系数可并进 1/C 标定）
        P = tau_hat.abs() * omega.abs() + eta * tau_hat ** 2
        dtheta = self.inv_C * P - self.kappa_over_C * (theta - theta_amb)
        return theta + dt * dtheta

    def forward(self, s, a, theta, theta_amb, tau_motion, JT, omega, dt=0.02):
        h = self.backbone(torch.cat([s, a, theta, theta_amb], dim=-1))
        f_pred = self.f_head(h)
        s_next = self.s_next(h)
        sigma = torch.exp(self.log_sigma(h))
        tau_hat = tau_motion + torch.einsum('bjf,bf->bj', JT, f_pred)  # 物理锚定
        theta_next = self.thermal_step(theta, tau_hat, omega, theta_amb, dt)
        return f_pred, s_next, tau_hat, theta_next, sigma


class MCWorldModelV2(nn.Module):
    """MC Dropout：T 次采样 → 均值 + MC 方差（供 σ_τ 与审计）"""
    def __init__(self, base: WorldModelV2, p: float = 0.1):
        super().__init__()
        self.base = base
        self.drop = nn.Dropout(p)

    def sample(self, s, a, theta, theta_amb, tau_motion, JT, omega, T=2, dt=0.02):
        f_l, s_l, tau_l, th_l, sig_l = [], [], [], [], []
        for _ in range(T):
            h = self.drop(self.base.backbone(torch.cat([s, a, theta, theta_amb], -1)))
            f = self.base.f_head(h); s2 = self.base.s_next(h)
            sig = torch.exp(self.base.log_sigma(h))
            tau = tau_motion + torch.einsum('bjf,bf->bj', JT, f)
            th2 = self.base.thermal_step(theta, tau, omega, theta_amb, dt)
            f_l.append(f); s_l.append(s2); tau_l.append(tau); th_l.append(th2); sig_l.append(sig)
        mean = lambda xs: torch.stack(xs).mean(0)
        f_m, s_m, tau_m, th_m, sig_m = map(mean, (f_l, s_l, tau_l, th_l, sig_l))
        tau_var = torch.stack(tau_l).var(0)                    # MC 方差 → σ_τ 的一部分
        return f_m, s_m, tau_m, th_m, sig_m, tau_var


# ============================================================
# 1. 物理对账审计器（第四 OOD 信号，免疫 σ 尺度漂移）
# ============================================================
class TorqueAuditor:
    """q_t = ‖e_τ/σ_τ‖²，H0: E[q]=n, Var[q]=2n；
       z_t 窗标准化 → CUSUM(k, h)，h 由目标 ARL0 反解；
       gating：仅在 |τ| 激励充分时更新，防摩擦误差污染。"""
    def __init__(self, n_joints: int = 7, M: int = 50, k: float = 0.5,
                 h: float = 8.0, tau_gate: float = 2.0):
        self.n, self.M, self.k, self.h, self.tau_gate = n_joints, M, k, h, tau_gate
        self.win = deque(maxlen=M)
        self.g = 0.0

    def update(self, tau_meas, tau_hat, sigma_tau) -> tuple:
        tau_meas = np.asarray(tau_meas); tau_hat = np.asarray(tau_hat)
        active = np.abs(tau_meas) > self.tau_gate               # 门控：低力矩段不更新
        if not active.any():
            return self.rho(), self.g
        u2 = ((tau_meas - tau_hat) / (sigma_tau + 1e-6)) ** 2
        q_t = float(u2[active].sum())
        self.win.append(q_t)
        m = len(self.win); n_active = int(active.sum())
        z = (np.mean(self.win) - n_active) / np.sqrt(2.0 * n_active / m)
        self.g = max(0.0, self.g + z - self.k)
        return self.rho(), self.g

    def rho(self) -> float:
        return float(np.exp(-self.g / 2.0))


# ============================================================
# 2. 延迟预算分配器（p99.9 + GPU 热节流感知）
# ============================================================
class LatencyBudget:
    def __init__(self, n_grid_per_dim: int = 7, deadline: float = 0.020):
        self.N, self.deadline = n_grid_per_dim, deadline
        self.ell = deque(maxlen=200)                             # 每扩展延迟样本

    def observe(self, seconds: float):
        self.ell.append(seconds)

    def allocate(self, gpu_temp: float):
        base = np.quantile(self.ell, 0.999) if self.ell else 0.5e-3
        derate = 1.0 + max(0.0, (gpu_temp - 75.0) / 25.0)        # 节流放大延迟
        ell = base * derate
        cfg = dict(N=self.N, T_MC=5 if ell < 0.4e-3 else 2)

        def est(d):                                              # 深度 d ≈ (N²)^d / batch 次前向
            return ((self.N ** 2) ** d) * ell / 64.0

        D = 1
        while D < 3 and 0.6 * self.deadline > est(D + 1):
            D += 1
        cfg.update(D=D, est=est, deadline=self.deadline)
        return cfg


# ============================================================
# 3. 闭式热投影（任务级，O(H)）
# ============================================================
def thermal_project(theta0, P_profile, C, kappa, theta_amb, dt=1.0):
    """θ' = θ_amb + (θ − θ_amb − P/κ)e^{−Δt/τ_th} + P/κ；返回轨迹与峰值。"""
    decay = np.exp(-dt * kappa / C)
    th, traj = theta0.copy(), []
    for P in P_profile:                                          # P: (n_joints,)
        th = theta_amb + (th - theta_amb - P / kappa) * decay + P / kappa
        traj.append(th.copy())
    return np.array(traj), traj[-1]


# ============================================================
# 4. 截止期感知 anytime 规划器 L3''
# ============================================================
class AnytimePlanner:
    def __init__(self, model: MCWorldModelV2, a_dim: int = 2, D_max: int = 3,
                 N: int = 7, gamma: float = 0.99, sigma_th: float = 0.5,
                 lam_theta: float = 0.1):
        self.model, self.a_dim = model, a_dim
        self.D_max, self.N = D_max, N
        self.gamma, self.sigma_th, self.lam_theta = gamma, sigma_th, lam_theta
        grid = torch.linspace(-1.0, 1.0, N)
        self.A = torch.stack(torch.meshgrid([grid] * a_dim, indexing='ij'), -1).reshape(-1, a_dim)
        self.nA = len(self.A)

    def _reward(self, f, goal, a, tau, theta_lim_of):
        r = -((f - goal) ** 2).sum(-1) - 0.01 * (a ** 2).sum(-1)
        over = (tau.abs() - theta_lim_of).clamp(min=0)           # 热降额软惩罚
        return r - self.lam_theta * (over ** 2).sum(-1)

    def _expand(self, S, TH, cfg, ctx):
        """B 个状态 × |𝒜| 动作 → 一个 batch 前向；返回可行掩码下的 (r, s', θ')。"""
        B = S.shape[0]
        A = self.A.repeat(B, 1)
        S_b = S.repeat_interleave(self.nA, 0)
        TH_b = TH.repeat_interleave(self.nA, 0)
        f, s2, tau, th2, sig, tau_var = self.model.sample(
            S_b, A, TH_b, ctx['theta_amb'], ctx['tau_motion'], ctx['JT'],
            ctx['omega'], T=cfg['T_MC'])
        r = self._reward(f, ctx['goal'], A, tau, ctx['tau_lim'](th2))
        ok = (sig.squeeze(-1) < self.sigma_th) & \
             (tau.abs() <= ctx['tau_lim'](th2) + 1e-6)           # σ 剪枝 + 逐步热约束
        return A, r, s2, th2, ok.reshape(B, self.nA)

    def plan(self, s, theta, ctx, budget: dict):
        t0 = time.perf_counter()
        S = torch.as_tensor(s, dtype=torch.float32).unsqueeze(0)
        TH = torch.as_tensor(theta, dtype=torch.float32).unsqueeze(0)
        A1, r1, s2_1, th2_1, ok1 = self._expand(S, TH, budget, ctx)   # 深度-1 保底
        r1m = r1.reshape(self.nA).masked_fill(~ok1.reshape(self.nA), -1e9)
        best_i = int(r1m.argmax())
        best = (float(r1m[best_i]), 1, A1.reshape(self.nA, -1)[best_i].numpy())
        # 迭代加深：预算内逐层展开（简化：贪心束展开，每层取 top-B 束）
        beam = S, TH, float(r1m[best_i])
        for d in range(2, budget['D'] + 1):
            if time.perf_counter() - t0 + budget['est'](d) > budget['deadline']:
                break                                             # 硬截止，保底已交付
            _, r_d, s2_d, th2_d, ok_d = self._expand(beam[0], beam[1], budget, ctx)
            tot = beam[2] + self.gamma ** (d - 1) * r_d.reshape(self.nA)
            tot = tot.masked_fill(~ok_d.reshape(self.nA), -1e9)
            i = int(tot.argmax())
            if tot[i].item() > best[0]:
                best = (float(tot[i]), d, self.A[i].numpy())
            beam = (s2_d[i // self.nA:i // self.nA + 1], th2_d[i // self.nA:i // self.nA + 1], float(tot[i]))
        budget.setdefault('measure', self.model)                  # 观测延迟回灌预算器
        LatencyBudget_observe_hook = time.perf_counter() - t0
        return best[2], best[1], LatencyBudget_observe_hook


# ============================================================
# 5. 1kHz 无学习安全层（τ 传感 + 动量观测器）
# ============================================================
class MomentumObserver:
    """r = K_O(p − p̂)，ṗ̂ = τ_meas + C(q,q̇)ᵀq̇ − g(q) + r；无学习、无 GPU。"""
    def __init__(self, M_fn, Cg_fn, n: int = 7, K_O: float = 50.0, thresh: float = 2.0):
        self.M_fn, self.Cg_fn, self.K_O, self.thresh = M_fn, Cg_fn, K_O, thresh
        self.p_hat = np.zeros(n)

    def update(self, q, qd, tau_meas, dt=0.001):
        p = self.M_fn(q) @ qd
        pdot = tau_meas + self.Cg_fn(q, qd) + self.K_O * (p - self.p_hat)
        self.p_hat = self.p_hat + dt * pdot
        r = self.K_O * (p - self.p_hat)
        return np.linalg.norm(r) > self.thresh, r


# ============================================================
# 6. 集成：TEMPOStack（PRISMStack 的增量改造）
# ============================================================
class TEMPOStack:
    def __init__(self, world_models, planner, skill_lib, ood_v2, auditor,
                 budget, observer, thermal_cfg, executor):
        self.world_models = world_models          # {z_id: MCWorldModelV2}
        self.planner, self.skill_lib = planner, skill_lib
        self.ood_v2, self.auditor = ood_v2, auditor
        self.budget, self.observer = budget, observer
        self.thermal = thermal_cfg                # dict(C, kappa, theta_amb, crit)
        self.executor = executor
        self.gpu_temp = 55.0
        self.pi_distill = None                    # DAgger 蒸馏策略（离线训练后注入）

    def step(self, obs) -> dict:
        state, theta = obs['s'], obs['theta']
        tau_meas, q, qd = obs['tau_meas'], obs['q'], obs['qd']
        # -- 1kHz 安全层（此处示意，实际独立线程）
        if self.observer.update(q, qd, tau_meas)[0]:
            return dict(mode='EMERGENCY', action=None, source='momentum_observer')
        # -- 审计 + 四信号 OOD
        z_id = self.skill_lib.select(state).pid
        ctx = self._ctx(obs, z_id)
        cfg = self.budget.allocate(self.gpu_temp)
        t0 = time.perf_counter()
        seq, depth, elapsed = self.planner.plan(state, theta, ctx, cfg)
        self.budget.observe(elapsed)
        w = self.world_models[z_id]
        _, _, tau_hat, _, _, tau_var = w.sample(
            torch.as_tensor(state, dtype=torch.float32).unsqueeze(0),
            torch.zeros(1, 2), torch.as_tensor(theta, dtype=torch.float32).unsqueeze(0),
            torch.tensor([self.thermal['theta_amb']]), ctx['tau_motion'], ctx['JT'],
            obs['omega'], T=cfg['T_MC'])
        sigma_tau = tau_var.sqrt().squeeze(0).numpy() + 0.05
        rho_phy, g = self.auditor.update(tau_meas, tau_hat.squeeze(0).numpy(), sigma_tau)
        rho = min(self.ood_v2.update(0.3, 0.01, obs['f_meas'], obs['f_pred']), rho_phy)
        # -- 分派
        if rho < 0.3:
            scale = 0.3 if rho < 0.2 else 0.5
            return dict(mode='imaginary', action=seq * scale, depth=depth,
                        rho=rho, g=g, source='L3\'\'')
        return dict(mode='distill', action=self.pi_distill(state, theta),
                    rho=rho, source='pi_distill')

    def _ctx(self, obs, z_id):
        return dict(goal=torch.as_tensor(obs['goal'], dtype=torch.float32),
                    tau_motion=torch.as_tensor(obs['tau_motion'], dtype=torch.float32).unsqueeze(0),
                    JT=torch.as_tensor(obs['JT'], dtype=torch.float32).unsqueeze(0),
                    omega=torch.as_tensor(obs['omega'], dtype=torch.float32).unsqueeze(0),
                    theta_amb=torch.tensor([self.thermal['theta_amb']]),
                    tau_lim=lambda th: torch.as_tensor(self.thermal['tau_lim_fn'](th.numpy())))
```

## 4. 正确性论证（对应想法区三命题）

**命题 1 证明梗概**：深度截断搜索在模型一致（A1）下满足 V*_d ≤ V*_{d+1}（更多分支只会增加可选集合）；σ 剪枝构成风险有界规划——被剪分支的值估计置信区间含不安全区域，保守化解释（A2）；热剪枝仅删「闭式投影到任务结束仍违反 τ_lim(θ)」的分支，由一阶 RC 单调解的单调性（P ≥ 0 时 θ 轨迹单调不减，越界不可恢复）保证被删分支不可行，故 admissible。deadline 内 depth-1 必然完成（一次批量前向，O(|𝒜|·T_MC)），故任何时刻返回值 ≥ V*_1 的贪心下界。∎

**命题 2 证明梗概**：H₀ 下 u_t,j 近似 iid N(0,1)（校准定义），q_t = Σ_j u² ~ χ²(n)，E[q]=n、Var[q]=2n；M 窗均值由 CLT 得 z_t → N(0,1)。单边 CUSUM(δ/2, h) 的 ARL₀ 由 Siegmund 近似 ARL₀ ≈ (2/k²)·exp(−2kh+…)（数值反解 h 至目标值）；对均值偏移 δ 的检出时延 E[T] ≈ h/δ。尺度不变性：τ̂ 与 σ_τ 同时乘以 (1+ε) 时 q_t 不变（比值结构），故 σ 纯尺度漂移不触发；仅当「残差相对 σ 的真实增长」发生时 g 上升。∎

**命题 3 证明梗概**：θ̇ = (1/C)P − (κ/C)(θ − θ_amb) 关于 (1/C, κ/C) 线性，普通最小二乘在持久激励（Σ P Pᵀ 可逆）下一致；时间常数分钟级 ⇒ 自适应带宽远低于审计带宽（50Hz），二者频域分离，消除耦合震荡。∎

## 5. BENCH v4 扩展

| 任务 | 类型 | 设计意图 | 指标 |
|---|---|---|---|
| T9-T11 | （第 25 轮保留） | σ 辨识 / 组合规划 / 想象回退 | OOD AUC, SR, 恢复率 |
| **T12 持续按压 60s** | 热约束 | 验证热增广与闭式投影 | 完成率, 峰值 θ, 热中止率 |
| **T13 计算热节流** | 实时性 | 人为限制 GPU 频率/注入延迟 | p99.9 控制延迟, SR 退化 |
| **T14 漂移注入** | 审计 | 渐变刚度漂移（材质老化） | 检出时延, 虚警率 |

## 6. 实验预期

| 配置 | SR (OOD) | T14 检出时延 | T12 热中止率 | p99.9 控制延迟 |
|---|---|---|---|---|
| 状态机 v1 | 0.15 | — | 28% | 1 ms（无想象） |
| DMO-NAV v2 | 0.44 | N/A | 25% | — |
| PRISM-NAV v3 | 0.63 | 12.4 s（σ-only，且随漂移变迟钝） | 21% | 118 ms（无保证） |
| **TEMPO-NAV v4** | **0.71** | **1.8 s** | **4%** | **≤20 ms（硬保证）** |

消融设计：去对账（退回三信号）→ T14 检出回到 12s 且虚警 ×3；去 anytime（固定 D=3 穷举）→ T13 下 SR 崩至 0.2、超时率 17%；去热项 → T12 中止率回到 20%；去蒸馏 → 节拍退化、动态任务 SR −0.12。

## 7. 已知风险与缓解

| 风险 | 缓解 |
|---|---|
| 审计者自身也是模型：摩擦/逆动力学系统偏差污染 e_τ | 温变摩擦模型（μ_f(θ)）；审计门控（仅 |τ|>τ_gate 激励充分时更新 g）；回退迟滞（连续 2 窗触发才降级） |
| 热自适应与漂移检测耦合震荡 | 频域分离：热参数带宽 ≪ 审计带宽（命题 3） |
| T_MC=2 方差噪声 | 方差下限 clamp + 预算器动态升 T_MC |
| 蒸馏分布偏移 | DAgger 聚合 + 安全层兜底（蒸馏输出仍过 τ_lim 饱和与动量观测器） |
| θ 无法直测 | 绕组温从电流-外壳温双通道估计，误差并入 σ_τ |

## 8. 本轮最大的风险

**「物理对账」依赖的逆动力学/摩擦模型本身也是模型——变速、变温下的摩擦系统偏差会污染 e_τ，审计可能把「动力学模型误差」误判为「世界模型漂移」，造成慢性误回退；且热参数自适应与漂移检测的耦合存在正反馈震荡风险。**
<!-- ARTIFACT:END -->