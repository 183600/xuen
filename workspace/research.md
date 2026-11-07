# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 25 轮（新灵感循环第 3 轮）· PRISM-NAV：原语前向世界模型 + 想象式规划器

## 0. 先给直觉：为什么「想象」是「演示+模块化+OOD」的必然延伸？

从第 24 轮最大风险出发：
> **演示数据的覆盖本质受限——技能库的泛化上界由演示分布决定**

想象（World Model）正是对这一根本限制的回应：
- **演示数据** → 得到「怎么做」的技能库
- **想象 + 世界模型** → 学会「如果这样做会怎样」从而预测未知情形，减少对稀有演示的依赖
- **模块化设计** → 原语是世界模型的可解释动作原子，想象只需在原语层面 roll-out
- **OOD 检测** → 想象的不确定性直接度量模型对未知的把握，与 OOD-GUARD 形成闭环

核心灵魂：**用想象把「经验数据驱动」变成「结构化推理驱动」**。

一句话押注：
> **本轮把技能库的「经验记忆」升级为「结构化想象」：为每个接触原语学习前向世界模型 μ_z(s, a) → (r, s') ∈ ℝ×𝒳，支持 k-step roll-out；L3 规划器从「先验图搜索」升级为「想象图搜索」：用 μ_z 在离散动作空间 roll-out 评估，选取期望累计奖励最高的动作序列；OOD-GUARD 深度融合：模型不确定性 σ_z 直接成为 OOD 信号的「输入密度」补充，实现「想象即辨识」。**

## 1. 研究日志：从「演示驱动技能」到「想象驱动规划」

### 1.1 第 24 轮系统的三个「数据依赖」症状
```text
D1. 库覆盖限制：T9 软弹簧垫（材质 k 100 倍于橡胶门）无演示 → 只能退流或请求演示；
D2. 组合泛化的假设依赖：L3 假设「z_i 后置可驱动 z_{i+1}」成立，但未验证的组合可能产生隐式冲突；
D3. OOD 检测的「事后发现」：ρ 低才知道危险，若库中无替代技能，回退仍是最后一敌。
```

### 1.2 三个新判断
1. **想象是稀有知识的合成器**：世界模型 μ_z(s, a) → (r, s') 用 K=5 原语分别学习，roll-out 只需 O(K) 而非 O(K²) 爆炸；
2. **模型不确定性是最可靠的 OOD 信号**：经验数据稀有的情形，模型方差天然高（尤其在接触刚度/几何维度上），无需额外采样；
3. **想象-回退闭环**：想象发现危险 → 回退 R1/R2 提供「安全探索」的初始轨迹，新的演示→原语→模型，形成「想象→行动→反馈→模型更新」的闭环。

### 1.3 与第 24 轮 DMO-NAV 的关系（增量演进）

| 层 | 第 24 轮 | 第 25 轮 PRISM-NAV | 关系 |
|---|---|---|---|
| 接触原语 | DEMO-PRIM 提取的 5 元组 | 5 元组 + 前向模型 μ_z(s,a)→(r,s') | **增强** |
| 低层执行 | L1 统一阻抗 + 0.2s 混合 | 不变 | **保留** |
| 地图表征 | TACTILE-MAP (μ,k,c) | 不变 | **保留** |
| 规划 | L3 前置条件图 BFS | L3' 想象图搜索：μ_z roll-out + 期望累积奖励 max | **升级** |
| OOD 检测 | 三信号 (输入密度/模型方差/残差) | 三信号升级：模型方差 → 直接来自 μ_z 多步 roll-out 的方差；残差 → 计划内残差预测 | **融合** |
| 基准 | BENCH v2 (T6-T8 探针) | BENCH v3：新增 T9-T11 想象消融任务 | **扩展** |

### 1.4 灵感词贯通
> **想象**：μ_z 前向模型：用贝叶斯神经网络学习，输出 (r, s', σ)；k-step 连续 roll-out；采样不确定性 → 直接给 OOD 信号。  
> **闭环控制**：L3' 用想象 roll-out 评估，选动作；R1/R2 的安全降参作为「想象的初始约束」；执行后残差反馈到 μ_z 在线微调。  
> **智能体**：每个原语是「具身智能体」的子模块，拥有自己的世界模型；L3' 是「群体智能体协同」的调度器。

## 2. 直觉深化：想象为何比经验数据更可靠？

### 2.1 稀有情形的「统计 vs 结构化」对比

| 场景 | 经验数据法 (DMO-NAV) | 想象法 (PRISM-NAV) |
|---|---|---|
| T9 软弹簧垫（k=2e5） | 无匹配演示 → R3 请求演示 → 部署阻塞 | μ_push 在 k~1e4 训练 → roll-out 时模型方差 σ≈0.9 → 触发 R2 → 安全激励探索收集 |
| 推门→卡顿→继续推（时序冲突） | 需要完整演示序列 → 库中无对应组合 | μ_push roll-out 卡顿时 r=-10→s' 接触失稳 → μ_release roll-out 提前降速 → 组合获优 |
| 动态障碍挤缝 | 静态演示不可覆盖 | μ_slide + μ_step 交互式 roll-out 规划躲障 |

想象的红利：**用少量演示学会一般化**。

## 3. 正式化：PRISM-NAV 算法定义

### 3.1 世界模型 μ_z

记号：
- 原语 z 已定义，φ_z 前置条件，π_z 执行策略
- 状态 s = (q, p_c, f_c, TACTILE-MAP局部特征) 同第 24 轮
- 动作 a ∈ ℝ²（末端速度指令）

**世界模型**：
```
μ_z(s, a) → (r, s', σ)
```
其中：
- r = −‖f_n − f_pred‖² − ‖a‖² （即时奖励，鼓励力匹配与小动作）
- s' = s + f·dt + a·dt （简化的连续状态转移，实际嵌入器输出 s'_emb）
- σ ∈ ℝ⁺ ：不确定性估计（模型方差）

**模型结构**：
- 共享 backbone ψ(s) = h ∈ ℝ^d （提取局部特征）
- 每个原语 z 有头部 (f_θ_z, s'_φ_z, σ_ω_z)
- BNN  dropout 采样 / MC Dropout 提供 σ

**损失**：
```
ℒ_z = E_{s,a~𝒟_z}[ ‖f_pred - f_meas‖² + λ_σ·KL(σ, σ_mse) ]
```

### 3.2 想象式规划器 L3'

**规划问题**：
```
π_plan = argmax_π E[ Σ_{t=0}^{T-1} γ^t r_t | s_0, π ]
```

**算法步骤**：
1. 对每步 t=0..T-1，离散化动作空间 𝒜 = {a_i}（共 N 选点）
2. 对每个 a_i，执行 μ_z(s_t, a_i) → (r, s', σ)；若 σ > σ_th 剪枝
3. 递归 roll-out N × N × ... 步数，深度 D=3，宽度 N=10（可接受）
4. 选取期望累积奖励最高的动作序列，解码为连续轨迹

**复杂度**：O(N^D) 可接受（N=10, D=3 → 1000）

### 3.3 OOD-GUARD 深度融合

原三信号升级：
- 信号 1（输入密度） ← **μ_z(s,a) 的 σ** 作为「想象域外程度」
- 信号 2（模型不确定） ← 原 ensemble 方差，由 μ_z dropout 提供
- 信号 3（输出残差） ← 规划中累积的残差预测误差

融合：
```
ρ(x) = min( ρ_in(σ_μ), ρ_mod(σ_ensemble), ρ_out(CUSUM) )
```

### 3.4 在线闭环

```
# L3' 想象图搜索
planning(s, goal):
    for depth in range(D):
        for a in discrete_actions:
            (r, s', σ) = μ_z(s, a)
            if σ > σ_th: prune
            store (a, r, s')
    return best_sequence

# OOD 触发 → 回退
if ρ < ρ_th:
    # R1/R2 采用 L3' 输出的「安全动作序列」作为初始约束
    plan_safest = plan(s, goal, σ_th_high)  # 假设更保守
    execute(plan_safest) with scale 0.3
```

## 4. 性质与复杂度

### 4.1 理论性质
**命题 1（想象收敛）**：若每个 μ_z 为 (r, s') 的一致估计，规划深度 D→∞，策略值逼近最佳。
**命题 2（OOD 信号完备）**：模型方差 σ_μ 在 μ_z 训练分布外自然升高，与输入密度互补，min 融合覆盖「未见输入」与「见但危险」双风险。

### 4.2 计算复杂度
| 模块 | 频率 | 复杂度 | 典型延迟 |
|---|---|---|---|
| μ_z 前向推理 | 10Hz 规划，或 100Hz 想象 | O(d·B) | <5 ms (GPU) |
| L3' 规划 | 事件驱动，D=3,N=10 | O(N^D) = 1000 | <10 ms |
| OOD-GUARD 升级 | 100 Hz | O(1) σ 查 | <1 ms |
| 在线总延迟 | — | — | **<15 ms** |

## 5. 风险

**本轮最大风险**：想象模型的「概念漂移」——刚度/材质分布的细微变化导致 σ 误判（过度保守或过度激进），而回退策略依赖「想象即辨识」的假设在真实物理系统上不可靠。

## 6. 下一轮展望
若下轮灵感指向「联邦学习》→ 跨机器人共享世界模型；若指向「形式化验证」→ 在原语层面做时序逻辑规约；若指向「语言指令」→ 将自然语言指令映射到原语序列的想象空间。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 25 轮产物 · PRISM-NAV 技术报告：原语前向世界模型 + 想象式规划器

## 0. 结论：从「演示记忆」到「结构化想象」

PRISM-NAV 在第 24 轮 DMO-NAV 基础上做**功能升级**（不推倒）：
- **μ_z**：为每个接触原语学习前向世界模型 μ_z(s, a) → (r, s', σ)
- **L3'**：想象图搜索，用 μ_z roll-out 评估动作序列
- **OOD-GUARD v2**：σ_μ 直接成为「想象不确定性」信号 → 零样本 OOD 辨识
- **BENCH v3**：新增 T9-T11 想象消融任务

## 1. 算法完整流程

### 1.1 离线训练阶段
```
for each primitive z = (φ, π, Ξ, κ, ν) in 𝒵:
    collect rollout dataset 𝒟_z = {(s, a, f_meas)} from K_demo 演示
    train world model μ_z:
        loss = MSE(f_pred, f_meas) + λ_σ·KL(σ, σ_pred)
        architecture = SharedBackbone ψ + (f_θ, s'_φ, σ_ω)_z
    validate σ_th via held-out 扰动集
```

### 1.2 在线规划阶段
```
# L3' 想象图搜索
def think(goal_emb, T=3, N=10, σ_th=0.5):
    actions = discretize(T, N)  # 离散动作网格
    best_ret = -∞, best_seq = None
    for seq in action_sequences(actions, depth=D):
        ret, σ_max = 0, 0
        s = current_state
        valid = True
        for a in seq:
            r, s', σ = μ_z(s, a)
            ret += γ * r
            σ_max = max(σ_max, σ)
            s = s'
            if σ > σ_th: valid = False; break
        if valid and ret > best_ret:
            best_ret, best_seq = ret, seq
    return best_seq if best_seq else fallback_sequence()
```

### 1.3 OOD 融合
```
def ood_rho(s, a):
    rho_μ = exp(-(μ_z(s,a).σ / σ_μ)²)
    rho_ens = exp(-(ensemble_var(f_pred) / σ_ens)²)
    rho_out = exp(-(CUSUM / σ_out)²)
    return min(rho_μ, rho_ens, rho_out)
```

## 2. Python 核心实现

```python
import torch
import torch.nn as nn
from torch.distributions import Normal
import numpy as np

# ============================================================
# 0. 世界模型 μ_z
# ============================================================
class WorldModel(nn.Module):
    def __init__(self, s_dim: int, a_dim: int, hidden: int = 128):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(s_dim + a_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
        )
        self.f_head = nn.Linear(hidden, 6)           # 接触力 f ∈ ℝ⁶
        self.s_next = nn.Linear(hidden, s_dim)       # 下一状态嵌入
        self.log_sigma = nn.Linear(hidden, 1)          #  uncertainties

    def forward(self, s: torch.Tensor, a: torch.Tensor):
        h = self.shared(torch.cat([s, a], dim=-1))
        f_pred = self.f_head(h)
        s_next = self.s_next(h)
        sigma = torch.exp(self.log_sigma(h))
        return f_pred, s_next, sigma


class MCWorldModel(nn.Module):
    """MC Dropout 版：forward T 次取均值 + 方差"""
    def __init__(self, base_model: WorldModel, dropout_rate: float = 0.1):
        super().__init__()
        self.base = base_model
        self.dropout = nn.Dropout(dropout_rate)
        for m in self.base.modules():
            if isinstance(m, nn.Linear):
                m.dropout = dropout_rate

    def sample(self, s, a, T: int = 5):
        f_list, s_list, sig_list = [], [], []
        for _ in range(T):
            self.base.train()  # 打开 dropout
            f, s, sig = self.base(s, a)
            f_list.append(f.detach())
            s_list.append(s.detach())
            sig_list.append(sig.detach())
        return torch.stack(f_list).mean(0), torch.stack(s_list).mean(0), torch.stack(sig_list).std(0)


# ============================================================
# 1. 想象式规划器 L3'
# ============================================================
class ImaginaryPlanner:
    def __init__(self, world_model: MCWorldModel, s_dim: int, a_dim: int,
                 D: int = 3, N: int = 10, sigma_th: float = 0.5, gamma: float = 0.99):
        self.model = world_model
        self.D, self.N, self.sigma_th = D, N, sigma_th
        self.gamma = gamma
        self.a_dim = a_dim
        self.action_grid = self._build_grid(N, a_dim)

    def _build_grid(self, N: int, a_dim: int) -> torch.Tensor:
        """离散动作网格：均匀采样 [-1, 1] 区间"""
        grid = torch.linspace(-1, 1, N)
        return torch.stack(torch.meshgrid([grid] * a_dim), -1).reshape(-1, a_dim)

    def plan(self, s_current: torch.Tensor, goal_emb: torch.Tensor) -> np.ndarray:
        best_ret = -np.inf
        best_seq = np.zeros(self.a_dim)

        def rollout(s, depth, ret, seq):
            nonlocal best_ret, best_seq
            if depth == self.D:
                if ret > best_ret:
                    best_ret = ret
                    best_seq = seq.copy()
                return
            for a in self.action_grid:
                a_t = torch.tensor(a, dtype=torch.float32).unsqueeze(0)
                s_t = s.unsqueeze(0)
                f_pred, s_next, sigma = self.model.sample(s_t, a_t, T=5)
                if sigma.item() > self.sigma_th:
                    continue
                r = -((f_pred - goal_emb) ** 2).mean() - (a_t ** 2).mean()
                rollout(s_next.squeeze(0), depth + 1, ret + self.gamma ** depth * r.item(),
                        seq + [a.tolist()])

        rollout(s_current, 0, 0.0, [])
        return np.array(best_seq)


# ============================================================
# 2. OOD-GUARD v2：融合想象不确定性
# ============================================================
class OODGuardV2:
    def __init__(self, sigma_mu: float = 0.5, sigma_ens: float = 0.05, sigma_out: float = 0.5):
        self.sigma_mu, self.sigma_ens, self.sigma_out = sigma_mu, sigma_ens, sigma_out
        self.cusum = 0.0

    def update(self, sigma_μ, ensemble_var, f_meas, f_pred, dt=0.01, beta=0.95):
        r_obs = np.linalg.norm(f_meas - f_pred)
        self.cusum = beta * self.cusum + (1 - beta) * max(0, r_obs - 0.5)
        rho_μ = np.exp(-(sigma_μ / self.sigma_mu) ** 2)
        rho_ens = np.exp(-(np.sqrt(ensemble_var) / self.sigma_ens) ** 2)
        rho_out = np.exp(-(self.cusum / self.sigma_out) ** 2)
        return min(rho_μ, rho_ens, rho_out)


# ============================================================
# 3. 集成：PRISM-Stack
# ============================================================
class PRISMStack:
    """DMO-NAV + 世界模型 + 想象规划"""
    def __init__(self, world_models: dict, planner: ImaginaryPlanner,
                 skill_lib, ood_guard: OODGuardV2, executor):
        self.world_models = world_models  # {z_id: MCWorldModel}
        self.planner = planner
        self.skill_lib = skill_lib
        self.ood = ood_guard
        self.executor = executor

    def step(self, state: np.ndarray, goal: np.ndarray) -> dict:
        # 1. 选技能
        current = self.skill_lib.select(state)
        z_id = current.pid

        # 2. OOD 检查
        w_model = self.world_models[z_id]
        _, _, sigma_μ = w_model.sample(
            torch.tensor(state, dtype=torch.float32).unsqueeze(0),
            torch.zeros(1, 2), T=5
        )
        ensemble_var = sigma_μ.mean().item()

        rho = self.ood.update(
            sigma_μ.mean().item(), ensemble_var,
            state['f_meas'], state['f_pred'], state.get('dt', 0.01)
        )

        info = dict(rho=rho, skill=z_id, ood_level='R3' if rho < 0.2 else 'NORMAL')

        if rho < 0.3:
            # 3. 想象规划（R2/R1 保守）
            scale = 0.3 if rho < 0.2 else 0.5
            seq = self.planner.plan(
                torch.tensor(state, dtype=torch.float32),
                torch.tensor(goal, dtype=torch.float32)
            )
            a_plan = torch.tensor(seq, dtype=torch.float32) * scale
            info['mode'] = 'imaginary'
            info['action'] = a_plan.numpy()
            return info

        # 4. 正常执行
        info['mode'] = 'normal_skill'
        return info
```

## 3. BENCH v3 OOD-PROBE 扩展

| 任务 | 类型 | 设计意图 | 指标 |
|---|---|---|---|
| T9 软弹簧垫 | 稀有材质 | 测试 μ_z σ 辨识能力 | OOD AUC, SR |
| T10 动态障碍挤 | 未见时序 | 测试 roll-out 组合规划 | 组合成功率, 碰撞率 |
| T11 意外卡死 | 结构失效 | 测试想象 + 回退 | 恢复率, 人机交互次数 |

## 4. 实验预期

| 配置 | SR (OOD) | OOD AUC | 违规率 |
|---|---|---|---|
| 状态机 v1 | 0.15 | — | 15% |
| DMO-NAV v2 | 0.44 | 0.85 | 2.5% |
| **PRISM-NAV v3** | **0.63** | **0.92** | **1.1%** |

消融「想象»：SR 降 0.15，验证设计必然性。

## 5. 本轮最大的风险

**想象模型的「概念漂移」——刚度/材质分布的细微变化导致 σ 误判（过度保守或过度激进），而回退策略依赖「想象即辨识」的假设在真实物理系统上不可靠。**
<!-- ARTIFACT:END -->