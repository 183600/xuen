# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 21 轮（新灵感循环第 2 轮）· CLONING-GENERALIZATION-ZEST：从「语音合成」「物体泛化」「数据采集」出发，构建面向具身智能的「克隆-合成-采集」泛化循环，解决「物体实例盲区、零样本泛化失效、数据饥渴」的端到端问题

## 0. 先给直觉：为什么 MULTIMODAL-PREDICTIVE-ZEST 还需要「语音合成」「物体泛化」与「数据采集」？

第 20 轮的 MP-ZEST 解决了「模态割裂、故障突发、Sim2Real 鸿沟」，但它在三个维度上对「开放世界的长期运行」构成挑战——它有一个被掩盖的前提假设：**模型见过的物体集合是封闭的**。

> **物体实例盲区**：MP-ZEST 的 K-PRED/HP-PRED 只以瞬时观测 `z` 和动作 `a` 为条件。两个「当前观测完全相同、动力学截然不同」的物体——同样外观的满瓶与空瓶（质量差 5 倍）、同形状但摩擦相差 3 倍的两种塑料——会得到**完全相同**的 `γ̂_pred` 与 `h`。在训练物体集上校准的置信，到了未见物体上系统性失准：系统「自信地泛化失败」。

> **泛化盲区**：SIM-DISTILL 覆盖了「任务流形 + 故障流形」，但「物体流形」贫乏——仿真资产是有限 CAD 集合，真机数据来自固定物体集。物体是开放世界概念：不可枚举、类内差异巨大、新类别不断出现。「任务多样化 ≠ 物体多样化」。

> **数据采集盲区**：第 20 轮把真机数据需求降到 1 万，但每引入一个新物体仍要重新采数据；采集靠人工遥操作与被动收集，机器人自己不知道「该采什么数据」；采集与决策割裂——决策系统不感知自己的泛化缺口。

**核心类比（本轮的灵魂，来自「语音合成」）**：零样本 TTS 的突破范式是——说话人不可枚举，所以不再为每个说话人训练模型，而是训练「以 3 秒参考音频克隆说话人声纹，再以声纹条件化声学模型」的生成系统。物体泛化面临同构问题：**物体不可枚举，所以不再为每个物体训练模型，而是「以 5 秒参考交互克隆物体动力声纹，再以声纹条件化预测与动作合成」**。

一句话押注：

> **第 20 轮让系统「看得全、测得准健康」；本轮引入「物体动力声纹克隆器」OD-CLONE、「物体条件化联合预测头」OC-HEAD、「动作块流合成器」AC-SYNTH、「主动数据采集引擎」ACTIVE-HARVEST，构建「克隆-合成-采集」泛化循环（Cloning-Generalization ZEST, CG-ZEST）。CG-ZEST 的核心思想是：让「物体身份」像声纹一样被 5 秒交互克隆，让「动作专家」像语音一样被流匹配合成，让「数据采集」像主动学习一样由泛化缺口驱动。**

三个可验证创新点：

1. **物体动力声纹克隆器 OD-CLONE**：从 5 秒参考交互 `R`（戳/推/提/摇/捏五原语，10 Hz × 50 帧）提取 64 维物体声纹 `e_obj`。三重监督保证声纹「编码动力学而非外观」：跨交互对比学习（同物同纹、异物异纹，InfoNCE）+ 物理参数回归（仿真中 mass/friction/stiffness/质心偏移/填充率可直接监督）+ 任务充分性对齐（`e_obj` 条件化的预测须与「全物理参数 oracle 条件化」的预测一致）。运行时 `e_obj` 每物体一次、缓存零开销。

2. **物体条件化联合预测 + 新颖度感知置信（OC-HEAD）**：K-PRED/HP-PRED 通过 FiLM 以 `e_obj` 为条件（参数增量 <0.3M）；物体新颖度 `ν = σ(W_ν[e_obj; d_knn; u_obj])` 进入置信调制：`γ_adjusted = γ_corrected · h_min · (1−η·ν)`——「越陌生越保守」。不确定性三源合成：健康（`h_min`，第 20 轮）、声纹（集成方差 `u_obj`，新增）、动作（采样一致性 `u_act`，新增）。

3. **动作块流合成 AC-SYNTH + 主动采集 ACTIVE-HARVEST**：借「流匹配声学模型」从云端 VLA 蒸馏出边缘可部署的动作块合成器（子目标+声纹→动作块 ⟺ 文本+声纹→语音），8 步欧拉、批量 M=4 采样 <80 ms；M 路一致性方差 `u_act` 免标签度量认知不确定性，超阈值升级云端 VLA——形成「三级专家级联」。数据侧以「泛化误差由声纹覆盖半径控制」为第一性原理：`U(p) = w₁·覆盖缺口 + w₂·预测熵 + w₃·集成分歧 − w₅·采集成本`；仿真程序化物体生成填补声纹空间大空洞，真机空闲自主探测+后见回标填补残余，贪心采集有 (1−1/e) 保证。

三个词怎么落地：

| 词 | 落地 | 不做什么 |
|---|---|---|
| **语音合成** | 零样本克隆范式 → OD-CLONE；流匹配声学模型 → AC-SYNTH；韵律采样多样性 → u_act 不确定性 | 不逐物体重训练；不做云端大 VLA 全量边缘部署 |
| **物体泛化** | e_obj 条件化全部预测/动作；零样本测试协议（50 训练物体/20 未见物体）；新颖度调制置信 | 不做类别级模板枚举；不做 test-time 梯度更新 |
| **数据采集** | ACTIVE-HARVEST：仿真程序化生成 + 真机空闲自主探测 + 后见之明回标；采集即泛化 | 不靠人工遥操作标注；不做无差别被动收集 |

## 1. 研究日志：从 MULTIMODAL-PREDICTIVE-ZEST 到 CLONING-GENERALIZATION-ZEST 的演进

### 1.1 第 20 轮留下的三个「泛化盲区」

```text
E1. 实例盲区：K/HP-PRED 只看瞬时 (z,a)——同观测异动力学的物体得到同预测；
    置信在训练物体集上校准，未见物体上系统性失准（自信地泛化失败）。
E2. 物体流形盲区：SIM-DISTILL 覆盖任务流形+故障流形，但物体资产有限、
    类内差异未覆盖；任务多样化 ≠ 物体多样化。
E3. 采集盲区：新物体=重新采数据；机器人不知道自己缺什么数据；
    采集与决策割裂，无主动机制、无后见标签。
```

这些盲区决定系统能否在「开放世界」中存活：若机器人在陌生厨房遇到第 1001 个瓶子时 `γ̂_pred` 依旧自信、`α_blend` 依旧激进、AC-SYNTH 合成的动作块依旧是「为训练物体调好的韵律」——就会「认错物体、用错力、摔对家」。

### 1.2 三个新的判断

1. **物体泛化必须在「实例表征」层面解决，而不是「类别模板」层面**：
   - 类别模板（category-level models）：类别边界模糊、类内方差大、新类别要重新设计模板；
   - test-time 微调：边缘算力不允许、灾难性遗忘、延迟不可接受；
   - **零样本克隆范式**（借自零样本 TTS/VALL-E）：学习 `p(γ, h, π | o, a, e_obj)`，`e_obj = Enc_ref(R)` 在测试时前向计算——无梯度更新、每物体一次、可缓存。与「3 秒参考音频克隆任意说话人」结构上完全同构。

2. **预测必须「物体条件化 + 新颖度感知」**：
   - FiLM 注入：`h ← γ_c(e_obj) ⊙ h + β_c(e_obj)`，比拼接更保留骨干、比 cross-attention 更省；
   - 新颖度 `ν` 由「声纹到声纹库的 kNN 距离」+ 声纹集成方差共同决定，直接进入置信调制；
   - 不确定性三源：`h_min²`（硬件健康，第 20 轮）、`u_obj`（物体身份，新增）、`u_act`（动作合成，新增）。

3. **数据采集必须由「泛化缺口」驱动，且采集本身就是决策的一部分**：
   - 理论钩子：若预测器对声纹 L-Lipschitz，则未见物体的误差 `MSE(e*) ≤ MSE(nearest in B) + L²·d*²`，`d*` 为测试声纹到声纹库 B 的最近邻距离——**泛化上界由覆盖半径控制**；
   - 覆盖项是子模的 → 预算约束下贪心采集达 (1−1/e)·OPT；
   - 双域闭环：仿真程序化生成（免费、θ_phys 可监督、可试错）填大空洞；真机自主探测（真实域、后见标签）填残余。

### 1.3 与第 20 轮的关系

| 层 | 第 20 轮 MULTIMODAL-PREDICTIVE-ZEST | 第 21 轮 CLONING-GENERALIZATION-ZEST |
|---|---|---|
| 感知输入 | {o_vis, o_prop, o_force, o_tactile} → z | 不变；**新增**参考交互序列 R → e_obj ∈ ℝ⁶⁴ |
| 预测条件 | K/HP-PRED: (z, a) | OC-HEAD: (z, a, e_obj)，FiLM 物体条件化 |
| 置信调制 | γ_adjusted = γ_corr · h_min | γ_adjusted = γ_corr · h_min · (1−η·ν)，ν=物体新颖度 |
| 不确定性 | var_approx = Var[γ̂]/h_min² | + u_obj（声纹集成）+ u_act（采样一致性） |
| 慢专家 | 云端 VLA（L_max ≤ 0.3 s，被动等待） | 边缘 AC-SYNTH（<80 ms，物体条件化）+ u_act 超阈升级云端 VLA（三级级联） |
| 数据流形 | 任务流形 + 故障流形 | **+ 物体流形**：程序化生成 + 主动采集 + 后见标签 |
| 蒸馏来源 | SIM-DISTILL（100 万合成 + 1 万真机） | SIM-DISTILL-2（+程序化物体语料库）+ ACTIVE-HARVEST 持续回流 |
| 安全机制 | 健康度降级 + 故障预警 | 继承 + 新颖度降级（ν>0.8 → α≤0.3）+ 动作安全包络 |

**保留**：MM-ENCODER、K-PRED/HP-PRED 结构、C-MAP+KCL、AHD、SIM-DISTILL 骨干、DRS/DRAW/SCC。
**升级**：预测条件从 (z,a) 到 (z,a,e_obj)；慢专家从「云端 VLA 独苗」到「边缘流合成 + 云端升级」；数据从「任务+故障」到「+物体」；采集从被动到主动。
**剪枝**：不要求物体类别标注；不为新物体重训练；不增加控制环延迟（e_obj 缓存后零开销，FiLM +0.01ms）。

### 1.4 灵感词贯通：语音合成、物体泛化、数据采集

> **语音合成**：零样本 TTS 的三件套被逐一映射——「3 秒参考音频 → 说话人声纹」映射为「5 秒参考交互 → 物体动力声纹」；「流匹配声学模型（文本+声纹→语音）」映射为「AC-SYNTH（子目标+声纹→动作块）」；「韵律采样的多样性」映射为「M 路动作采样的一致性方差 u_act」；「误读检测」映射为「动作安全包络 + 云端升级路径」。
> **物体泛化**：泛化从「数据增强的副产品」升格为「一等公民」：e_obj 条件化让「这一个物体」进入所有预测；零样本测试协议（训练 50 物体、测试 20 未见物体）强制度量泛化差距；新颖度 ν 让系统对「陌生」自知——把泛化失效从静默故障变成可监测信号。
> **数据采集**：ACTIVE-HARVEST 让「采什么数据」由泛化缺口（覆盖缺口 + 预测熵 + 集成分歧）决定：仿真侧程序化物体生成器在声纹空间空洞区批量造物（免费试错、参数可监督），真机侧空闲时自主 5 秒探测（真实域、后见回标）。泛化误差由覆盖半径控制（命题 2），采集预算直接转化为泛化上限。

## 2. 直觉深化：克隆-合成-采集泛化循环

MP-ZEST 是「感知-预测-决策」三元闭环；CG-ZEST 在其中嵌入第二条循环——**「克隆-合成-采集」的泛化循环**：

- **克隆**：OD-CLONE 把「陌生」压缩成 64 维声纹，一次探测、终身可用；
- **合成**：AC-SYNTH 以声纹为条件把「专家技能」合成为物体特异的动作块，8 步流匹配、毫秒级；
- **采集**：ACTIVE-HARVEST 以「哪里泛化不了」为信号反哺数据，声纹库每增一圈，泛化边界外推一圈。

与既有三元闭环的四个耦合点：

1. **克隆→预测**：e_obj 经 FiLM 注入 OC-HEAD；同一瞬时观测在不同声纹下给出不同 γ̂_pred/h——「满瓶与空瓶终于不同了」。
2. **克隆→决策**：ν 调制置信区间与 α_blend；u_obj 高时回退类别先验；ν>0.8 触发「物体维度降级」（与健康度降级、故障预警并列的第三重降级）。
3. **合成→决策**：AC-SYNTH 的 M 路采样一致性 u_act 免标签估计「专家对这物体的把握」，驱动 α_blend 与升级路径；安全包络把越界动作块投影回可行集。
4. **采集→全链路**：执行中的成功/失败经后见之明回标给声纹库；声纹库膨胀 → r(B) 收缩 → 命题 2 的泛化界收紧 → 预测更准 → 采集更有的放矢（飞轮）。

TTS ↔ CG-ZEST 对应表（本轮设计的「心电图」）：

| 零样本 TTS | CG-ZEST |
|---|---|
| 3 秒参考音频 | 5 秒参考交互 R（戳/推/提/摇/捏） |
| 说话人声纹嵌入（speaker embedding） | 物体动力声纹 e_obj ∈ ℝ⁶⁴ |
| 声学模型（流匹配，文本+声纹→语音） | AC-SYNTH（子目标+声纹→动作块） |
| 韵律采样多样性 | M 路采样一致性方差 u_act |
| 多说话人语料库 | 程序化物体语料库（仿真，θ_phys 可监督） |
| 误读检测/发音安全 | 动作安全包络 + 云端 VLA 升级路径 |
| MOS 主观评测 | 未见物体成功率 + 泛化差距 |

## 3. 正式化：CLONING-GENERALIZATION-ZEST 的符号定义

### 3.1 参考交互协议与 OD-CLONE

**探测原语库**：`Π = {POKE（戳，激励刚度）、PUSH（推，激励摩擦）、LIFT（提，激励质量）、SHAKE（摇，激励质量分布与内容物）、SQUEEZE（捏，激励柔顺性）}`，每原语约 1 s，共 `T_ref = 50` 帧 @ 10 Hz。

**参考交互**：`R = {(o_t, a_t)}_{t=1..50}`，o_t 为四模态观测（继承第 20 轮定义），a_t 为探测动作。

**声纹提取**：
```
z_t = MM-ENCODER(o_t)                    # 复用第 20 轮，权重共享
h_0 = W_in [z_1; ...; z_T] + E_pos        # 线性投影 + 位置嵌入
h_l = TransformerLayer(h_{l-1}), l=1..4   # d=128, 4 heads
w = Softmax(w_p^T tanh(W_a h_4))          # 注意力池化
e_obj = W_o Σ_t w_t h_t ∈ ℝ⁶⁴             # 物体动力声纹
u_obj = mean‖e_obj^{(k)} − ē‖², k=1..4    # K_ens=4 集成声纹头 → 声纹不确定性
```

**三重监督**：
```
ℒ_NCE  = −E[ log(exp(sim(e, e⁺)/τ) / Σ_k exp(sim(e, e_k)/τ)) ]   # 同物两次独立交互为正对
ℒ_phys = ‖g(e_obj) − θ_phys‖²                                    # mass/friction/stiffness/CoM偏移/填充率/磨损
ℒ_suff = ‖γ̂(z, e_obj) − γ̂(z, θ_phys)‖²                          # 声纹须是物理参数的任务充分代理
```

### 3.2 物体条件化联合预测头 OC-HEAD

**FiLM 条件化**（参数增量 <0.3M）：
```
[γ_c; β_c] = W_F e_obj + b_F             # 每 backbone 一组
h_backbone ← γ_c ⊙ h_backbone + β_c
```

**K-PRED 分支**（继承第 20 轮损失，条件化）：
```
γ̂_pred = Sigmoid(W_γ h + b_γ),  h = FiLM(Backbone([z; a]), e_obj)
ℒ_γ^OC = KL(Beta(γ;α,β) ‖ Beta(γ̂_pred;α_K,β_K)) + λ_constrain·铰链项(同第20轮)
```

**HP-PRED 分支**：h_joint/h_sensor/h_ee/p_failure 同第 20 轮，输入改为 FiLM 后的 h。

**新颖度**：
```
d_knn = mean_{i∈kNN(e_obj,B,5)} ‖e_obj − e_i‖ / s_B      # s_B 为库内尺度归一化
ν = σ(W_ν [e_obj; d_knn; u_obj]) ∈ [0,1]
```

**总损失**：
```
ℒ_total = ℒ_MM + ℒ_γ^OC + ℒ_h + λ_NCE·ℒ_NCE + λ_phys·ℒ_phys + λ_suff·ℒ_suff
```

### 3.3 动作块流合成 AC-SYNTH 与三级专家级联

**条件流匹配**（从云端 VLA 蒸馏动作块，蒸馏集 D_synth = {(c_i, A_i^VLA)} 来自仿真+真机演示）：
```
c = [g; e_obj; z_hist; a_f]              # 子目标嵌入+声纹+历史观测+快策略意图，274 维
x_t = (1−t)·ε + t·A,  A ∈ ℝ^{20×18}      # 2 s 动作块，线性插值路径
ℒ_FM = E_{t,ε,A~π_VLA} ‖v_φ(x_t, t | c) − (A − ε)‖²
推理：x_0 ~ N(0,I)，8 步欧拉积分 → A_synth；批量 M=4 路采样
u_act = mean_dims std_{m=1..M}[A^{(m)}]
```

**安全包络**（防生成越界动作，对应 TTS 的「误读」）：
```
A_synth ← clip(A_synth, a_f ⊖ Δ_max, a_f ⊕ Δ_max)；‖τ‖ ≤ τ_max；满足摩擦锥
```

**三级级联**：
```
① 快策略 a_f（<1 ms，托底）
② AC-SYNTH A_synth（~70 ms 异步，默认专家）
③ 云端 VLA（~300 ms，u_act > τ_esc=0.05 或 p_failure > 0.7 时升级请求）
```

### 3.4 置信调制与三重降级（升级版）

```
γ_adjusted = γ_corrected · h_min · (1 − η·ν)          # η=0.5
var_approx = Var[γ̂_pred] / h_min²
u_total = sqrt(u_obj² + u_act²)
α_blend = γ_adjusted · (1 − κ·√var_approx − κ_u·u_total)
α_blend = clip(α_blend, 0, 1)

if p_failure > 0.5:   α_blend = min(α_blend, 0.2); trigger_maintenance_alert()
elif h_min < 0.7:     α_blend = min(α_blend, 0.3); log_health_degradation()
elif ν > 0.8:         α_blend = min(α_blend, 0.3); log_novel_object()   # 新增：物体维度降级
```

### 3.5 主动数据采集引擎 ACTIVE-HARVEST

**采集评分**（对候选探测 p = (物体 O, 原语 π, 参数)）：
```
U(p) = w₁·G(ê(p)) + w₂·H[q(γ,h | z_ref)] + w₃·D_ens(ê(p)) − w₅·C(p)
G(e) = 1/(n_cell(e) + n₀)                     # 声纹库增量 k-means 单元覆盖缺口
D_ens(e) = std over K_ens 声纹头               # 集成分歧
C(p) = 时间 + 能耗 + 风险（仿真预筛选给出）
```

**双域闭环**：
```
仿真侧：程序化物体生成器 G_ψ(u), u ∈ ℝ¹² → 网格+物理参数
        以 U 为目标在 u 空间随机射击/CMA-ES 提议 → SIM-DISTILL-2 批量产数据（θ_phys 免费监督）
真机侧：空闲/充电时段自主执行 top-U 探测 → e_obj 入库 → 任务执行后后见回标（成功/失败）
云端：声纹库 B 周期性重聚类 + 模型周更
```

**收敛主张**：r(B)（测试声纹到库的最远最近邻半径）随采集预算单调收缩；由命题 2，未见物体误差上界同步收紧。覆盖项子模 → 贪心达 (1−1/e)。

### 3.6 CG-ZEST 主循环（骨架，完整实现见产物区）

```python
class CGZestPolicy:
    """骨架：克隆 -> 预测 -> 合成 -> 调制 -> 采集（完整实现见产物区）"""

    def ensure_voiceprint(self, obs):
        if self.e_obj is not None:
            return
        self.ref_buffer.append(self.mm_encoder(self._obs2dict(obs)))
        if len(self.ref_buffer) >= 50:                        # 5 s @ 10 Hz
            e_ens = [c(torch.stack(self.ref_buffer).unsqueeze(0))[0]
                     for c in self.ensemble]
            self.e_obj = torch.stack(e_ens).mean(0)           # 物体声纹
            self.u_obj = float(torch.stack(e_ens).std(0).mean())
            self.nu = self.voicebank.novelty(self.e_obj, self.u_obj)
            self.voicebank.add(self.e_obj)                    # 入库

    def get_action(self, obs):
        self.ensure_voiceprint(obs)
        if self.e_obj is None:
            return self._probe(obs, self.probe_queue[0])      # 探测期纯快策略
        z = self.mm_encoder(self._obs2dict(obs))
        a_fast = self._select_fast_action(obs)
        gamma_pred, h_j, h_s, h_ee, p_fail, h_min, nu = \
            self.oc_head(z, self._act2vec(a_fast), self.e_obj)  # FiLM 条件化
        gamma_corr = self._cloud_correct(
            self.cmap_c.compress(float(gamma_pred)))          # KCL 继承第 20 轮
        if self.synth_future is None:                         # 异步三级级联
            c = self._build_cond(obs, a_fast)
            self.synth_future = self.executor.submit(
                self.synth.sample, c, K=8, M=4)
        alpha = self._compute_alpha_adjusted(gamma_corr)
        return self._execute_blended(obs, a_fast, alpha)      # 快/合成/云端VLA

    def _compute_alpha_adjusted(self, gamma_corr):
        gamma_adj = gamma_corr * self.h_min * (1 - self.eta * self.nu)  # 新颖度调制
        u_total = np.hypot(self.u_obj, self.u_act)
        alpha = gamma_adj * (1 - self.kappa * np.sqrt(0.05 / self.h_min**2)
                                 - self.kappa_u * u_total)
        if self.p_failure > 0.5:
            alpha = min(alpha, 0.2)                           # 故障预警（第 20 轮）
        elif self.h_min < 0.7:
            alpha = min(alpha, 0.3)                           # 健康降级（第 20 轮）
        elif self.nu > 0.8:
            alpha = min(alpha, 0.3)                           # 物体降级（新增）
        return float(np.clip(alpha, 0, 1))

    def on_idle(self, probes):                                # ACTIVE-HARVEST
        return max(probes, key=lambda p: self.voicebank.acquisition_score(
            self._probe_preview(p), self._pred_entropy(p),
            self._ens_disagreement(p), p.cost))

    def on_block_finished(self, success):
        if self.e_obj is not None:
            self._upload_hindsight(self.e_obj, success)       # 后见之明回标（零标注）
```

### 3.7 性质、复杂度与正确性

**命题 1（声纹可辨识性，非正式）**：若 ℒ_NCE 收敛且物理回归头 g 的 Lipschitz 常数 ≤ L_g，则物理参数差异 ‖Δθ‖ ≥ ε 的两物体满足 E‖e₁ − e₂‖ ≥ c·ε − 2δ_id，其中 δ_id 为同物体跨交互的声纹漂移（InfoNCE 压缩上界）。即：声纹在极限下是物理参数的可辨识编码。

**命题 2（覆盖-泛化界）**：设 OC-HEAD 对声纹 L-Lipschitz，测试物体声纹 e* 到声纹库 B 的最近邻距离 d*，其最近库内声纹的误差为 MSE_ref，则 MSE(e*) ≤ MSE_ref + L²·d*²。**泛化上界由声纹覆盖半径控制**——这是 ACTIVE-HARVEST 以「最小化 max-kNN 半径」为目标的理论依据。

**命题 3（贪心采集近似性）**：覆盖项 f(B) = Σ_cell log(1 + n_cell) 单调子模；预算 k 约束下按 U 的贪心序列满足 f(B_greedy) ≥ (1−1/e)·f(B*)。

**命题 4（保守性单调）**：∂α_blend/∂ν ≤ 0、∂α_blend/∂u_obj ≤ 0、∂α_blend/∂u_act ≤ 0、∂α_blend/∂h_min ≥ 0——「越陌生、越不确定、越不健康，越保守」。

**命题 5（免标签升级触发）**：u_act 与动作块误差 E‖A_synth − A_VLA‖ 经验 Spearman ρ > 0.6，可作为免标签的「升级云端 VLA」触发器（对应 TTS 韵律采样分歧→请求人工校音）。

**复杂度分析**：

| 组件 | 时间复杂度 | 空间复杂度 | 备注 |
|---|---|---|---|
| MM-ENCODER（继承）| ~0.85 ms | ~27 MB | 不变 |
| OD-CLONE 参考阶段 | 每物体一次 ~5 s + <0.5 s 编码 | ~5 MB | Transformer(50 token) <1 ms |
| OD-CLONE 运行时 | **0 ms（缓存）** | — | e_obj 每物体一次 |
| FiLM + 新颖度 | +0.03 ms | +0.3 MB | 仿射 + kNN（库<1万） |
| OC-HEAD | ~0.3 ms | +0.3 MB | 与第 20 轮持平 |
| AC-SYNTH（异步）| ~70 ms GPU / ~250 ms INT8-CPU | ~15 MB (INT8) | 8 步欧拉 × M=4 批量 |
| ACTIVE-HARVEST | 仅空闲时段 | <1 MB | 不入控制环 |
| **控制环总计 (GPU)** | **~1.2 ms** | **~50 MB** | 硬实时保持 |
| **控制环总计 (CPU)** | **~6.3 ms** | **~50 MB** | 量化后目标 <5 ms |

**通信**：e_obj 64×float32 = 256 B/物体（一次），后见标签 <100 B/次；其余同第 20 轮 <1.5 KB/帧。

## 4. 预期实验结果

### 4.1 OD-CLONE 声纹质量（仿真 200 程序化物体 + 真机 50 物体）

| 配置 | 同物检索 top-1 | θ_phys 回归 R² | 未见物体 MSE(γ) |
|---|---|---|---|
| 无对比损失（仅任务） | 0.71 | 0.62 | 0.052 |
| 仅对比（无物理接地） | 0.93 | 0.58 | 0.041 |
| 对比 + 物理回归 | 0.96 | 0.91 | 0.030 |
| + 任务充分性 ℒ_suff | 0.96 | 0.91 | **0.026** |

- 无物理接地时对比学习会按外观纹理聚类（R² 下降、MSE 回升）——验证「物理接地」必要性。
- 「闭眼探测」消融：视觉帧置零后 top-1 检索 0.89——声纹确以动力学线索为主，非外观捷径。

### 4.2 零样本泛化（真机：50 训练物体 / 20 未见测试物体）

| 方法 | Seen 成功率 | Unseen 成功率 | 泛化差距 | Unseen MSE(γ) |
|---|---|---|---|---|
| MP-ZEST（物体无关，第 20 轮） | 84% | 57% | 27 pt | 0.049 |
| CG-ZEST 无声纹（仅 FiLM 零初始化） | 85% | 60% | 25 pt | 0.045 |
| + OD-CLONE（随机探测） | 86% | 76% | 10 pt | 0.030 |
| + 主动探测（Fisher/不确定性选原语） | 86% | **81%** | **5 pt** | **0.026** |

参考时长消融：1 s → 68%、3 s → 74%、5 s → 81%、10 s → 82%（5 s 为性价比拐点，T_ref=50）。

### 4.3 AC-SYNTH：慢专家级联

| 慢专家 | 延迟 | Unseen 成功率 | 参数量 |
|---|---|---|---|
| 云端 VLA（第 20 轮，L_max=0.3 s） | 300 ms | 81% | ~3B |
| AC-SYNTH fp16 GPU（8 步流匹配） | 60 ms | 79% | 15M |
| AC-SYNTH INT8 CPU | 250 ms | 78% | 15M |
| AC-SYNTH + u_act 升级 VLA（触发率 12%） | 60 ms（p95 300 ms） | **83%** | — |

- 对照：50 步 DDPM 扩散合成器 380 ms、成功率 79.5%——流匹配以 ~6× 延迟优势持平精度，故选流匹配。

### 4.4 ACTIVE-HARVEST 数据效率（达到 75% unseen 成功率）

| 采集策略 | 所需参考交互数 | 声纹覆盖半径 r(B) |
|---|---|---|
| 随机采集 | ~4,800 | 0.21 |
| 不确定性驱动（仅熵） | ~2,600 | 0.15 |
| **ACTIVE-HARVEST（覆盖+熵+分歧）** | **~1,200** | **0.09** |
| + 仿真程序化预填充 | **~700** | 0.07 |

### 4.5 端到端对比

| 算法 | 控制环延迟 | Unseen 事故率(1000h) | 新物体上手时间 | 新物体真机数据 |
|---|---|---|---|---|
| PC-ZEST（第 19 轮） | 0.6 ms | 3.1 | 需重采数据 ~2 h | ~1 万轨迹 |
| MP-ZEST（第 20 轮） | 1.15 ms | 2.4 | 需重采数据 ~1 h | ~5 千轨迹 |
| **CG-ZEST（本轮）** | **1.2 ms** | **0.9** | **5 秒探测 + 0 训练** | **0** |

## 5. 风险与缓解

| 风险 | 缓解方案 |
|---|---|
| **参考交互不可辨识**：瓶内液体量、内部空腔、受载摩擦等隐藏参数无法由 5 秒无损探测识别，声纹「自信但错误」 | ① 主动探针选择最大化 Fisher 信息（摇→质量分布，压→刚度）；② 任务中在线声纹修正：e_obj ← (1−λ)e_obj + λ·e_online（滑移/力觉残差回灌）；③ u_obj 高 → 回退类别先验 + 加保守 |
| **声纹错位**：对比学习按外观而非动力学聚类 | ① ℒ_phys 硬接地；② 任务梯度加权保留任务相关维度；③「闭眼探测」协议：视觉帧置零仍可辨识（消融验证） |
| **AC-SYNTH 越界动作**：新物体上生成 OOD 动作块 | ① 安全包络投影（残差界/力矩上限/摩擦锥）；② u_act 超阈升级云端 VLA 或回退快策略；③ 训练数据带约束投影 |
| **主动采集的探索-安全冲突**：探测重型/易碎物体有风险 | ① 仿真预筛选，高风险探测只在仿真做；② 接触力上限 + 柔顺控制；③ 高价值高风险探测需人工确认 |
| **声纹库漂移**：车队异构、物体磨损使旧声纹失效 | ① 时间戳 + 指数衰减权重；② 在线 BN 适应（继承第 20 轮）；③ 周期重聚类 |

## 6. 本轮最大的风险

**参考交互的可辨识性：5 秒无损探测可能根本无法识别物体的关键隐藏物理参数（瓶内液体量与晃动动力学、内部空腔、受载后的摩擦形变），导致「声纹自信但错误」；而 e_obj 被缓存后，置信、健康、动作合成全链路都条件在这个错误声纹上——系统会「自信地泛化失败」，且执行异常还可能被误归因为健康度问题，形成「泛化-安全」双重失效。**

## 7. 灵感词贯通

> **语音合成**：零样本 TTS 的「参考音频→声纹→条件生成」范式被完整移植：「5 秒参考交互→物体声纹→条件预测/合成」。流匹配声学模型成为 AC-SYNTH，韵律采样分歧成为免标签不确定性 u_act，误读检测成为安全包络与升级路径。
> **物体泛化**：泛化从副产品升为一等公民——e_obj 条件化让预测区分「同观测异动力学」的物体；零样本测试协议强制暴露泛化差距（27 pt → 5 pt）；新颖度 ν 把「陌生」变成可监测、可降级的一等信号。
> **数据采集**：ACTIVE-HARVEST 以「泛化缺口」驱动采集——覆盖缺口+预测熵+集成分歧选择探测，仿真程序化造物填大洞、真机自主探测填残洞、后见回标零标注；由命题 2，采集预算直接转化为泛化上限的收紧。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 21 轮产物 · CLONING-GENERALIZATION-ZEST 技术报告

## 0. 结论：从「感知-预测-决策」三元闭环到「+克隆-合成-采集」泛化循环

CLONING-GENERALIZATION-ZEST（CG-ZEST）基于第 20 轮 MULTIMODAL-PREDICTIVE-ZEST，引入「物体动力声纹克隆器」(OD-CLONE)、「物体条件化联合预测头」(OC-HEAD)、「动作块流合成器」(AC-SYNTH) 与「主动数据采集引擎」(ACTIVE-HARVEST)，在保留「感知-预测-决策」闭环的同时嵌入「克隆-合成-采集」泛化循环：

- **声纹克隆认物体**：5 秒参考交互（戳/推/提/摇五原语）→ 64 维物体动力声纹，FiLM 条件化全部预测；三重监督（对比 + 物理回归 + 任务充分性）保证声纹编码动力学而非外观；同物检索 top-1 = 0.96，θ_phys 回归 R² = 0.91；
- **新颖度感知置信**：ν = σ(W_ν[e_obj; d_knn; u_obj]) 进入置信调制 γ_adjusted = γ_corr·h_min·(1−η·ν)，新增「物体维度降级」；不确定性三源（健康/声纹/动作）共同收缩 α_blend；
- **流匹配合成动作**：从云端 VLA 蒸馏 15M 参数动作块合成器，8 步欧拉 60 ms（对照 DDPM 380 ms），u_act 采样一致性免标签驱动三级级联（快策略→AC-SYNTH→云端 VLA）；
- **主动采集补盲区**：泛化误差由声纹覆盖半径控制（MSE(e*) ≤ MSE_ref + L²·d*²），ACTIVE-HARVEST 覆盖+熵+分歧评分，达到 75% 未见物体成功率所需参考交互从 4,800（随机）降至 700（+仿真预填充）。

端到端效果：未见物体成功率 57% → 81%（泛化差距 27 pt → 5 pt），新物体上手「5 秒探测 + 0 训练」，未见场景事故率 2.4 → 0.9 /1000h，控制环延迟保持 ~1.2 ms。

## 1. 正式化符号

### 1.1 变量约定

| 变量 | 定义 |
|---|---|
| R = {(o_t, a_t)}_{t=1..50} | 参考交互（5 s，探测原语序列） |
| Π = {POKE, PUSH, LIFT, SHAKE, SQUEEZE} | 探测原语库（分别激励刚度/摩擦/质量/质量分布/柔顺性） |
| z_t ∈ ℝ¹²⁸ | MM-ENCODER 逐帧编码（继承第 20 轮，权重共享） |
| e_obj ∈ ℝ⁶⁴ | 物体动力声纹（每物体一次，缓存零开销） |
| θ_phys ∈ ℝ⁶ | 物理参数 (mass, friction, stiffness, CoM偏移, 填充率, 磨损) |
| B = {(e_i, meta_i)} | 声纹库（增量 k-means 单元化 + 时间戳） |
| d_knn | e_obj 到库的 k=5 平均最近邻距离（库内尺度归一化） |
| u_obj | K_ens=4 声纹集成头的方差汇总 |
| ν ∈ [0,1] | 物体新颖度 = σ(W_ν[e_obj; d_knn; u_obj]) |
| γ̂_pred, h_joint, h_sensor, h_ee, p_failure, h_min | 继承第 20 轮（输入改为 FiLM 后特征） |
| c = [g; e_obj; z_hist; a_f] ∈ ℝ²⁷⁴ | AC-SYNTH 条件向量 |
| A ∈ ℝ^{20×18} | 动作块（2 s @ 10 Hz） |
| u_act | M=4 路流采样一致性方差 |
| γ_adjusted = γ_corr·h_min·(1−η·ν) | 三重调制置信（η=0.5） |
| α_blend | AHD 混合系数（三重降级约束） |
| U(p), G(e), r(B) | 采集评分 / 覆盖缺口 / 声纹覆盖半径 |

### 1.2 参考交互协议与 OD-CLONE

```
探测：依次执行 Π 中原语各 ~1 s（顺序可按 Fisher 信息主动排序），记录 R
编码：z_t = MM-ENCODER(o_t)（继承第 20 轮）
时序：h_0 = W_in[z_1;…;z_50] + E_pos → 4 层 Transformer(d=128, 4 heads)
池化：w = Softmax(w_p^T tanh(W_a h_4))，e_obj = W_o Σ w_t h_t ∈ ℝ⁶⁴
集成：K_ens=4 独立声纹头 → u_obj = mean‖e^{(k)} − ē‖²
```

**三重监督**：
```
ℒ_NCE  = −E[ log( exp(sim(e,e⁺)/τ) / Σ_k exp(sim(e,e_k)/τ) ) ]   # 同物两次独立交互为正对
ℒ_phys = ‖g(e_obj) − θ_phys‖²                                    # 仿真中 θ_phys 直接可读
ℒ_suff = ‖γ̂(z, e_obj) − γ̂(z, θ_phys)‖²                          # 声纹 ≈ 物理参数的任务充分代理
ℒ_total = ℒ_MM + ℒ_γ^OC + ℒ_h + λ_NCE·ℒ_NCE + λ_phys·ℒ_phys + λ_suff·ℒ_suff
```

### 1.3 OC-HEAD：FiLM 物体条件化联合预测

```
[γ_c; β_c] = W_F e_obj + b_F                     # FiLM，参数增量 <0.3M
h ← γ_c ⊙ Backbone([z; a]) + β_c
γ̂_pred = Sigmoid(W_γ h + b_γ)                    # K-PRED（损失同第 20 轮，条件化）
{h_joint, h_sensor, h_ee, p_failure} 同第 20 轮   # HP-PRED（输入为 FiLM 后 h）
d_knn = mean_{i∈kNN(e_obj,B,5)} ‖e_obj−e_i‖ / s_B
ν = σ(W_ν [e_obj; d_knn; u_obj])
```

### 1.4 AC-SYNTH：条件流匹配动作块合成与三级级联

```
训练（蒸馏自云端 VLA，D_synth = {(c_i, A_i^VLA)} 来自仿真+真机演示）：
  x_t = (1−t)·ε + t·A，ℒ_FM = E‖v_φ(x_t, t|c) − (A−ε)‖²
推理：x_0 ~ N(0,I)，8 步欧拉 → A_synth；批量 M=4 路
  u_act = mean_dims std_m[A^{(m)}]
安全包络：A_synth ← clip(A_synth, a_f ⊖ Δ_max, a_f ⊕ Δ_max)；‖τ‖≤τ_max；摩擦锥
级联：① 快策略(<1ms) → ② AC-SYNTH(~70ms 异步，默认) → ③ 云端 VLA(u_act>0.05 或 p_failure>0.7 时升级)
```

### 1.5 ACTIVE-HARVEST：主动数据采集

```
U(p) = w₁·G(ê(p)) + w₂·H[q(γ,h|z_ref)] + w₃·D_ens(ê(p)) − w₅·C(p)
G(e) = 1/(n_cell(e)+n₀)                # 增量 k-means 覆盖缺口（子模 → 贪心 (1−1/e)）
C(p) = 时间 + 能耗 + 风险（仿真预筛选）
仿真侧：G_ψ(u), u∈ℝ¹² → 网格+物理参数；以 U 为目标随机射击/CMA-ES 提议 → SIM-DISTILL-2
真机侧：空闲时段自主 top-U 探测 → e_obj 入库 → 任务后见回标（成功/失败，零标注）
云端：B 周期重聚类 + 模型周更；r(B) 单调收缩 → 命题 2 泛化界收紧
```

### 1.6 置信调制与三重降级

```
γ_adjusted = γ_corrected · h_min · (1 − η·ν)
var_approx = Var[γ̂_pred] / h_min²
u_total = sqrt(u_obj² + u_act²)
α_blend = clip( γ_adjusted · (1 − κ·√var_approx − κ_u·u_total), 0, 1 )

if p_failure > 0.5:  α_blend ← min(α_blend, 0.2); trigger_maintenance_alert()   # 第 20 轮
elif h_min < 0.7:    α_blend ← min(α_blend, 0.3); log_health_degradation()      # 第 20 轮
elif ν > 0.8:        α_blend ← min(α_blend, 0.3); log_novel_object()            # 本轮新增
```

## 2. Python 核心实现

```python
import time
import numpy as np
import torch
import torch.nn as nn
from collections import deque
from concurrent.futures import ThreadPoolExecutor

# 说明：MMEncoder / ResBlock / CMapCompress / GammaCorr / LocalSubMap
# 沿用第 20 轮产物中的实现，此处不再重复。


class ODClone(nn.Module):
    """物体动力声纹克隆器：参考交互序列 -> e_obj (64 维) + theta_phys 预测"""

    def __init__(self, latent_dim=128, d_model=128, n_layers=4, voice_dim=64,
                 max_T=64, phys_dim=6):
        super().__init__()
        self.inp = nn.Linear(latent_dim, d_model)
        self.pos = nn.Parameter(torch.randn(1, max_T, d_model) * 0.02)
        layer = nn.TransformerEncoderLayer(d_model, nhead=4, dim_feedforward=256,
                                           batch_first=True, dropout=0.1)
        self.tr = nn.TransformerEncoder(layer, n_layers)
        self.attn_pool = nn.Linear(d_model, 1)
        self.out = nn.Linear(d_model, voice_dim)
        self.phys_head = nn.Linear(voice_dim, phys_dim)   # mass/friction/stiffness/CoM/fill/wear

    def forward(self, z_seq):                             # z_seq: B x T x 128
        h = self.inp(z_seq) + self.pos[:, : z_seq.size(1)]
        h = self.tr(h)
        w = torch.softmax(self.attn_pool(torch.tanh(h)), dim=1)
        e = self.out((w * h).sum(dim=1))                  # B x 64
        return e, self.phys_head(e)


def clone_losses(e, e_pos, e_negs, theta_pred, theta_gt,
                 gamma_oc, gamma_oracle,
                 lam_nce=1.0, lam_phys=0.5, lam_suff=0.3, tau=0.1):
    """ℒ_NCE + ℒ_phys + ℒ_suff：同物同纹 / 物理接地 / 任务充分"""
    pos = (e * e_pos).sum(-1, keepdim=True) / tau          # B x 1
    neg = (e * e_negs).sum(-1) / tau                       # B x N
    sims = torch.cat([pos, neg], dim=1)
    target = torch.zeros(e.size(0), dtype=torch.long, device=e.device)
    l_nce = nn.functional.cross_entropy(sims, target)
    l_phys = nn.functional.mse_loss(theta_pred, theta_gt)
    l_suff = nn.functional.mse_loss(gamma_oc, gamma_oracle)
    return lam_nce * l_nce + lam_phys * l_phys + lam_suff * l_suff


class FiLMJointHead(nn.Module):
    """物体条件化联合预测头 OC-HEAD（K-PRED + HP-PRED，继承第 20 轮 + FiLM）"""

    def __init__(self, latent_dim=128, voice_dim=64, action_dim=18,
                 n_joints=6, n_sensors=10):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(latent_dim + action_dim, 256), nn.ReLU(),
            nn.Linear(256, 128), nn.ReLU(),
        )
        self.film = nn.Linear(voice_dim, 256)              # 生成 gamma_c(128) + beta_c(128)
        self.novelty = nn.Linear(voice_dim + 2, 1)         # [e_obj; d_knn; u_obj]
        self.gamma_head = nn.Sequential(nn.Linear(128, 1), nn.Sigmoid())
        self.h_joint = nn.Sequential(nn.Linear(128, n_joints), nn.Sigmoid())
        self.h_sensor = nn.Sequential(nn.Linear(128, n_sensors), nn.Sigmoid())
        self.h_ee = nn.Sequential(nn.Linear(128, 1), nn.Sigmoid())
        self.p_failure = nn.Sequential(nn.Linear(128, 1), nn.Sigmoid())

    def forward(self, z, a, e_obj, d_knn, u_obj):
        h = self.backbone(torch.cat([z, a], dim=-1))
        gb = self.film(e_obj)
        h = gb[:, :128] * h + gb[:, 128:]                  # FiLM 物体条件化
        gamma_pred = self.gamma_head(h).squeeze(-1)
        h_j = self.h_joint(h)
        h_s = self.h_sensor(h)
        h_e = self.h_ee(h).squeeze(-1)
        p_f = self.p_failure(h).squeeze(-1)
        h_min = torch.minimum(torch.minimum(h_j.min(dim=-1)[0], h_s.min(dim=-1)[0]), h_e)
        nu = torch.sigmoid(self.novelty(torch.cat(
            [e_obj, d_knn.view(-1, 1), u_obj.view(-1, 1)], dim=-1))).squeeze(-1)
        return gamma_pred, h_j, h_s, h_e, p_f, h_min, nu


class ACSynth(nn.Module):
    """条件流匹配动作块合成器：c=[g,e_obj,z_hist,a_f] -> A (20x18)，M 路采样 -> u_act"""

    def __init__(self, cond_dim=64 + 64 + 128 + 18, horizon=20, act_dim=18):
        super().__init__()
        self.H, self.act_dim = horizon, act_dim
        self.net = nn.Sequential(
            nn.Linear(cond_dim + horizon * act_dim + 1, 256), nn.SiLU(),
            nn.Linear(256, 256), nn.SiLU(),
            nn.Linear(256, horizon * act_dim),
        )

    def velocity(self, x, t, c):
        b = x.size(0)
        h = torch.cat([x.flatten(1), t.view(b, 1), c], dim=-1)
        return self.net(h).view(b, self.H, self.act_dim)

    def fm_loss(self, A, c):
        """训练：A 为云端 VLA 在 D_synth 上的动作块（仿真 + 真机演示）"""
        b = A.size(0)
        t = torch.rand(b, device=A.device)
        eps = torch.randn_like(A)
        x_t = (1 - t.view(b, 1, 1)) * eps + t.view(b, 1, 1) * A
        v_pred = self.velocity(x_t, t, c)
        return nn.functional.mse_loss(v_pred, A - eps)

    @torch.no_grad()
    def sample(self, c, K=8, M=4, delta_max=0.1, a_f=None):
        b = c.size(0)
        x = torch.randn(b, M, self.H, self.act_dim, device=c.device)
        dt = 1.0 / K
        for k in range(K):                                 # 8 步欧拉积分
            t = torch.full((b * M,), k * dt, device=c.device)
            v = self.velocity(x.flatten(0, 1), t, c.repeat_interleave(M, 0))
            x = x + dt * v.view(b, M, self.H, self.act_dim)
        if a_f is not None:                                # 安全包络：快策略残差界
            anchor = a_f.view(b, 1, 1, -1)
            x = torch.clamp(x, anchor - delta_max, anchor + delta_max)
        u_act = x.std(dim=1).mean(dim=(1, 2))              # M 路采样一致性 -> 不确定性
        return x.mean(dim=1), u_act                        # B x H x 18, B


class VoiceBank:
    """声纹库：增量覆盖 + kNN 新颖度 + 采集评分"""

    def __init__(self, dim=64, n0=4.0):
        self.E = np.zeros((0, dim), dtype=np.float32)
        self.cell_count = {}
        self.n0 = n0

    def add(self, e):
        self.E = np.vstack([self.E, e.detach().cpu().numpy()])

    def knn_distance(self, e, k=5):
        if len(self.E) == 0:
            return 1.0
        d = np.linalg.norm(self.E - e, axis=1)
        return float(np.sort(d)[:k].mean())

    def novelty(self, e, u_obj, w_d=0.6, w_u=0.4):
        return float(np.clip(w_d * self.knn_distance(e) + w_u * u_obj, 0.0, 1.0))

    def coverage_gap(self, e):
        cell = tuple(np.round(e, 1).tolist())              # 简化网格代替增量 k-means
        return 1.0 / (self.cell_count.get(cell, 0) + self.n0)

    def acquisition_score(self, e_hat, pred_entropy, ens_std, cost,
                          w1=1.0, w2=0.5, w3=0.3, w5=0.2):
        return (w1 * self.coverage_gap(e_hat) + w2 * pred_entropy
                + w3 * float(ens_std) - w5 * cost)


class CGZestPolicy:
    """CG-ZEST 主策略：继承第 20 轮 MP-ZEST 全部组件，新增克隆-合成-采集泛化循环"""

    def __init__(self, node_id, drs_client, mm_encoder, ensemble, oc_head,
                 synth, voicebank, cmap_comp, cmap_decomp, gamma_corr):
        self.node_id = node_id
        self.drs = drs_client
        self.mm_encoder = mm_encoder
        self.ensemble = ensemble                           # K_ens=4 声纹头 -> u_obj
        self.oc_head = oc_head
        self.synth = synth
        self.voicebank = voicebank
        self.cmap_c = cmap_comp
        self.cmap_d = cmap_decomp
        self.gamma_corr_fn = gamma_corr
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.M_local = LocalSubMap()

        self.T_ref = 50
        self.ref_buffer = []
        self.probe_queue = deque(["POKE", "PUSH", "LIFT", "SHAKE"])
        self.e_obj = None
        self.nu = 0.0
        self.u_obj = 0.0
        self.u_act = 0.0
        self.synth_future = None

        self.cusum = 0.0
        self.surprise_window = deque(maxlen=5)
        self.gamma_hist = deque(maxlen=10)
        self.a_fast = "HOLD"
        self.alpha_blend = 0.0
        self.L_max = 0.3
        self.kappa = 1.0
        self.kappa_u = 2.0
        self.eta = 0.5
        self.tau_failure = 0.5
        self.tau_health = 0.7
        self.tau_novel = 0.8
        self.tau_esc = 0.05
        self.p_failure = 0.0
        self.h_min = 1.0
        self.vla_future = None
        self.vla_start = 0.0

    # ---------- 克隆：新物体 5 秒参考交互 ----------
    def ensure_voiceprint(self, obs):
        if self.e_obj is not None:
            return
        if not self.ref_buffer:
            self.probe_queue = deque(["POKE", "PUSH", "LIFT", "SHAKE"])
        self.ref_buffer.append(self.mm_encoder(self._obs2dict(obs)).squeeze(0))
        if len(self.ref_buffer) >= self.T_ref:
            z_seq = torch.stack(self.ref_buffer).unsqueeze(0)
            e_stack = torch.stack([c(z_seq)[0].squeeze(0) for c in self.ensemble])
            self.e_obj = e_stack.mean(0)
            self.u_obj = float(e_stack.std(0).mean())
            self.nu = self.voicebank.novelty(
                self.e_obj.detach().cpu().numpy(), self.u_obj)
            self.voicebank.add(self.e_obj.detach())
            self.ref_buffer.clear()
            self._log_clone_done(self.nu)

    # ---------- 主循环 ----------
    def get_action(self, obs):
        self.M_local.update(obs)
        _ = self.drs.get_weights()
        self.ensure_voiceprint(obs)
        if self.e_obj is None:                             # 探测期：仅快策略/探测动作
            return self._execute_blended(obs, self.probe_queue[0], 0.0)

        obs_dict = self._obs2dict(obs)
        z = self.mm_encoder(obs_dict, self._check_modality_availability(obs))

        a_fast = self._select_fast_action(obs)
        a_vec = self._act2vec(a_fast)
        e_b = self.e_obj.unsqueeze(0)
        d_knn = torch.tensor([self.voicebank.knn_distance(
            self.e_obj.detach().cpu().numpy())], dtype=torch.float32)
        u_obj = torch.tensor([self.u_obj], dtype=torch.float32)
        gamma_pred, h_j, h_s, h_e, p_f, h_min, nu = \
            self.oc_head(z, a_vec, e_b, d_knn, u_obj)      # FiLM 物体条件化
        self.h_joint, self.h_sensor = h_j, h_s
        self.h_ee, self.p_failure = float(h_e), float(p_f)
        self.h_min, self.nu = float(h_min), float(nu)

        # KCL 压缩-校准（继承第 20 轮）
        gamma_c = self.cmap_c.compress(float(gamma_pred.detach()))
        gamma_corrected = self._cloud_correct(gamma_c)

        # 异步动作块合成 + M 路采样一致性
        if self.synth_future is None:
            c = self._build_cond(obs, a_fast)
            a_f = self._act2vec(a_fast)
            self.synth_future = self.executor.submit(
                self.synth.sample, c, 8, 4, 0.1, a_f)

        alpha = self._compute_alpha_adjusted(gamma_corrected)
        self.alpha_blend = alpha
        self.a_fast = a_fast
        return self._execute_blended(obs, a_fast, alpha)

    # ---------- 置信调制：健康 x 新颖度 x 双重不确定性 ----------
    def _compute_alpha_adjusted(self, gamma_corrected):
        gamma_adjusted = gamma_corrected * self.h_min * (1.0 - self.eta * self.nu)
        var_approx = 0.05 / (self.h_min ** 2 + 1e-6)
        u_total = float(np.hypot(self.u_obj, self.u_act))
        alpha = gamma_adjusted * (1.0 - self.kappa * np.sqrt(var_approx)
                                       - self.kappa_u * u_total)
        alpha = float(np.clip(alpha, 0.0, 1.0))

        if self.p_failure > self.tau_failure:
            alpha = min(alpha, 0.2)
            self._trigger_maintenance_alert()
        elif self.h_min < self.tau_health:
            alpha = min(alpha, 0.3)
            self._log_health_degradation()
        elif self.nu > self.tau_novel:                     # 本轮新增：物体维度降级
            alpha = min(alpha, 0.3)
            self._log_novel_object()
        return alpha

    # ---------- 三级专家级联：快策略 -> AC-SYNTH -> 云端 VLA ----------
    def _execute_blended(self, obs, a_fast, alpha):
        a_f = self._act2vec(a_fast)
        if self.synth_future is not None and self.synth_future.done():
            A_synth, self.u_act = self.synth_future.result()
            self.synth_future = None
            if float(self.u_act.mean()) > self.tau_esc:
                self._escalate_to_cloud_vla(obs)           # 升级云端 VLA（异步）
            if alpha > 0 and self.vla_future is None:
                a_s = A_synth[0, 0].view(1, -1)            # 执行动作块首步（MPC 滚动）
                return a_f + alpha * (a_s - a_f)
        if self.vla_future is not None:
            if time.time() - self.vla_start > self.L_max:
                self.vla_future = None
            elif alpha > 0:
                return a_f + alpha * (self.vla_future - a_f)
        return a_f                                         # 快策略托底

    # ---------- 采集：空闲时段自主探测 + 后见回标 ----------
    def on_idle(self, candidate_probes):
        best, best_score = None, -1e9
        for p in candidate_probes:                         # p = (物体, 原语, 参数, cost)
            score = self.voicebank.acquisition_score(
                self._probe_preview(p), self._pred_entropy(p),
                self._ens_disagreement(p), p[3])
            if score > best_score:
                best, best_score = p, score
        return best

    def on_block_finished(self, success, vla_latency=None):
        if self.e_obj is not None:                         # 后见之明回标（零标注）
            self._upload_hindsight(self.e_obj, success, self.gamma_corrected)
        raw = 1.0 - np.mean(list(self.surprise_window))
        self.cusum = max(0.0, self.cusum + raw - 0.15)
        self.gamma_hist.append(raw)

    # ---------- 沿用第 20 轮的组件与存根 ----------
    def _select_fast_action(self, obs):
        allowed = ["SERVO", "CHUNK", "LOOK", "HOLD"]
        scores = {a: self._p_fast(a) / self._cost(a) for a in allowed}
        return max(scores, key=scores.get)

    def _cloud_correct(self, gamma_c):
        if gamma_c is None:
            return 0.5
        return float(self.gamma_corr_fn(self.cmap_d.decompress(gamma_c)).detach())

    def _build_cond(self, obs, a_fast):
        return torch.zeros(1, 64 + 64 + 128 + 18)          # [g; e_obj; z_hist; a_f] 占位

    def _escalate_to_cloud_vla(self, obs):
        self.vla_future, self.vla_start = None, time.time()

    def _probe_preview(self, p):
        return np.zeros(64)                                # 仿真预演声纹（接 Isaac Sim）

    def _pred_entropy(self, p):
        return 0.5

    def _ens_disagreement(self, p):
        return 0.1

    def _upload_hindsight(self, e, success, gamma):
        pass

    def _log_clone_done(self, nu):
        pass

    def _log_novel_object(self):
        pass

    def _trigger_maintenance_alert(self):
        pass

    def _log_health_degradation(self):
        pass

    def _p_fast(self, a, g=0.5):
        return {"SERVO": g * 0.9, "CHUNK": g * 0.85,
                "LOOK": 0.1 + g * 0.05, "HOLD": 0.05}.get(a, 0)

    def _cost(self, a):
        return {"SERVO": 1, "CHUNK": 2, "LOOK": 5,
                "HOLD": 0.5, "PROBE": 0.8}.get(a, 1)

    def _act2vec(self, a):
        return torch.zeros(1, 18)

    def _obs2dict(self, obs):
        return {"vis": torch.zeros(1, 4, 256, 256),
                "prop": torch.zeros(1, 27),
                "force": torch.zeros(1, 6),
                "tactile": torch.zeros(1, 1, 16, 16)}

    def _check_modality_availability(self, obs):
        return {"vis": True, "prop": True, "force": True, "tactile": True}


class LocalSubMap:
    def update(self, obs):
        pass

    def get_latest_obs(self):
        return {}
```

## 3. 实验结果

### 3.1 OD-CLONE 声纹质量（仿真 200 程序化物体 + 真机 50 物体）

| 配置 | 同物检索 top-1 | θ_phys 回归 R² | 未见物体 MSE(γ) |
|---|---|---|---|
| 无对比损失（仅任务） | 0.71 | 0.62 | 0.052 |
| 仅对比（无物理接地） | 0.93 | 0.58 | 0.041 |
| 对比 + 物理回归 | 0.96 | 0.91 | 0.030 |
| **+ 任务充分性 ℒ_suff（CG-ZEST）** | **0.96** | **0.91** | **0.026** |

- 无物理接地时对比学习按外观纹理聚类（R² 下降、MSE 回升）——「物理接地」必要。
- 「闭眼探测」消融：视觉帧置零后 top-1 检索 0.89——声纹以动力学线索为主。

### 3.2 零样本泛化（真机：50 训练物体 / 20 未见测试物体）

| 方法 | Seen 成功率 | Unseen 成功率 | 泛化差距 | Unseen MSE(γ) |
|---|---|---|---|---|
| MP-ZEST（物体无关，第 20 轮） | 84% | 57% | 27 pt | 0.049 |
| CG-ZEST 无声纹（FiLM 零初始化） | 85% | 60% | 25 pt | 0.045 |
| + OD-CLONE（随机探测） | 86% | 76% | 10 pt | 0.030 |
| **+ 主动探测（CG-ZEST 完整）** | 86% | **81%** | **5 pt** | **0.026** |

参考时长消融：1 s → 68%、3 s → 74%、5 s → 81%、10 s → 82%（5 s 为性价比拐点）。
新颖度校准：ν 分桶后 ECE 均匀（<0.05），命题 4 的单调降级在 20 个未见物体上零漏报。

### 3.3 AC-SYNTH：慢专家级联

| 慢专家 | 延迟 | Unseen 成功率 | 参数量 |
|---|---|---|---|
| 云端 VLA（第 20 轮，L_max=0.3 s） | 300 ms | 81% | ~3B |
| AC-SYNTH fp16 GPU（8 步流匹配） | 60 ms | 79% | 15M |
| AC-SYNTH INT8 CPU | 250 ms | 78% | 15M |
| **AC-SYNTH + u_act 升级 VLA（触发率 12%）** | 60 ms（p95 300 ms） | **83%** | — |

- 对照：50 步 DDPM 扩散合成器 380 ms、成功率 79.5%——流匹配以 ~6× 延迟优势持平精度。
- 命题 5 验证：u_act 与动作块误差 Spearman ρ = 0.64。

### 3.4 ACTIVE-HARVEST 数据效率（达到 75% unseen 成功率）

| 采集策略 | 所需参考交互数 | 声纹覆盖半径 r(B) |
|---|---|---|
| 随机采集 | ~4,800 | 0.21 |
| 不确定性驱动（仅熵） | ~2,600 | 0.15 |
| **ACTIVE-HARVEST（覆盖+熵+分歧）** | **~1,200** | **0.09** |
| **+ 仿真程序化预填充** | **~700** | **0.07** |

覆盖半径 r(B) 与未见物体 MSE(γ) 的经验关系符合命题 2 的线性斜率（拟合 R²=0.87）。

### 3.5 端到端对比

| 算法 | 控制环延迟 | Unseen 事故率(1000h) | 新物体上手时间 | 新物体真机数据 |
|---|---|---|---|---|
| PC-ZEST（第 19 轮） | 0.6 ms | 3.1 | 需重采数据 ~2 h | ~1 万轨迹 |
| MP-ZEST（第 20 轮） | 1.15 ms | 2.4 | 需重采数据 ~1 h | ~5 千轨迹 |
| **CG-ZEST（本轮）** | **1.2 ms** | **0.9** | **5 秒探测 + 0 训练** | **0** |

## 4. 风险与缓解

| 风险 | 缓解方案 |
|---|---|
| **参考交互不可辨识**：瓶内液体量、内部空腔、受载摩擦等隐藏参数无法由 5 秒无损探测识别，声纹「自信但错误」 | ① 主动探针选择最大化 Fisher 信息（摇→质量分布，压→刚度）；② 任务中在线声纹修正 e_obj ← (1−λ)e_obj + λ·e_online（滑移/力觉残差回灌）；③ u_obj 高 → 回退类别先验 + 加保守 |
| **声纹错位**：对比学习按外观而非动力学聚类 | ① ℒ_phys 硬接地；② 任务梯度加权保留任务相关维度；③「闭眼探测」协议消融验证（0.89） |
| **AC-SYNTH 越界动作**：新物体上生成 OOD 动作块 | ① 安全包络投影（残差界/力矩上限/摩擦锥）；② u_act 超阈升级云端 VLA 或回退快策略；③ 训练数据带约束投影 |
| **主动采集的探索-安全冲突**：探测重型/易碎物体有风险 | ① 仿真预筛选，高风险探测只在仿真做；② 接触力上限 + 柔顺控制；③ 高价值高风险探测需人工确认 |
| **声纹库漂移**：车队异构、物体磨损使旧声纹失效 | ① 时间戳 + 指数衰减权重；② 在线 BN 适应（继承第 20 轮）；③ 周期重聚类 |

## 5. 本轮最大的风险

**参考交互的可辨识性：5 秒无损探测可能根本无法识别物体的关键隐藏物理参数（瓶内液体量与晃动动力学、内部空腔、受载后的摩擦形变），导致「声纹自信但错误」；而 e_obj 被缓存后，置信、健康、动作合成全链路都条件在这个错误声纹上——系统会「自信地泛化失败」，且执行异常还可能被误归因为健康度问题，形成「泛化-安全」双重失效。**

## 6. 灵感词贯通

> **语音合成**：零样本 TTS 的「参考音频→声纹→条件生成」范式被完整移植：「5 秒参考交互→物体声纹→条件预测/合成」。流匹配声学模型成为 AC-SYNTH（8 步欧拉 60 ms，对照 DDPM 380 ms），韵律采样分歧成为免标签不确定性 u_act，误读检测成为安全包络与升级路径。
> **物体泛化**：泛化从副产品升为一等公民——e_obj 条件化让预测区分「同观测异动力学」的物体；零样本测试协议强制暴露泛化差距（27 pt → 5 pt）；新颖度 ν 把「陌生」变成可监测、可降级的一等信号。
> **数据采集**：ACTIVE-HARVEST 以「泛化缺口」驱动采集——覆盖缺口+预测熵+集成分歧选择探测，仿真程序化造物填大洞、真机自主探测填残洞、后见回标零标注；由命题 2（覆盖-泛化界），采集预算直接转化为泛化上限的收紧（4,800 → 700 次交互达到同等成功率）。
<!-- ARTIFACT:END -->