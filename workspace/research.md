# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 22 轮（新灵感循环第 3 轮）· COOPERATIVE-PROGNOSTIC-CLOSED-LOOP ZEST (CPC-ZEST)：从「协同控制」「预测性维护」「闭环控制」出发，为世界动作模型基座叠加「前瞻预测—事件闭环—双臂协同」校正层，直击 UniBot 真机泛化与步骤分瓶颈

> 检索日期：2026-11-05。本轮先对齐赛事事实，再逆推创新点，并对前 21 轮的 ZEST 家族做一次「面向竞赛现实」的诚实剪枝。

## 0. 三分钟直觉：三条线在 UniBot 上正好交汇

先摆事实（来源见 §9）：

- **赛制**：UniBot-V1 挑战赛，32 项真机桌面任务（抓取/放置/双手协调），32000 条演示、169 小时，Unitree G1 + Dex1 夹爪，单模型通才赛道，按平均成功率与步骤分综合排名；选手本地部署模型，评测系统通过固定端口远程接入，N 台机器人并发、随机顺序（`unibot.unitree.com/challenges.html`；`github.com/unitreerobotics/unibot_submission`）。
- **观测量**：4 路 RGB（头部双目 480×640×3 + 左右腕部），左右臂关节 7 维、左右 EE 位姿 6 维、左右夹爪 1 维、下半身 15 维、语言指令 str。**没有力觉/触觉通道**（`huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel`）。
- **动作量**：`joint` 或 `ee` 二选一，返回长度 `action_chunk_size` 的动作块（chunk）；`get_action` 按块返回，块内按索引顺序执行（同 repo README）。
- **评测关注点**：官方明文关注「每步响应延迟及其波动」与「返回动作的统计规律性」，作为结果可信度依据（`unibot_submission` §6）——**延迟稳定性本身就是分数**。
- **泛化五轴**：位置 / 干扰物 / 背景 / 未见物品 / 人为干扰。
- **榜首瓶颈**：用户与公开信息均指出榜首成功率 <30%（榜单页目前显示 Coming Soon，`unibot.unitree.com/leaderboard.html`）。
- **最接近的公开 SOTA 信号**：在「Unitree G1 真机操作」聚合榜上，`LingBot-VA`（Causal World Modeling，共享潜空间 + Mixture-of-Transformers + **闭环 rollout** + 异步推理）平均 66.7，`Flash-WAM`（世界动作模型的模态感知步蒸馏，单步推理、23× 加速、真机约 60%）次之（`sota2.com/.../robot-manipulation-on-unitree-g1-real-world`，2026-11-05）。

三条线索：

> **闭环控制**：SOTA 的核心武器是「世界模型 + 闭环 rollout + 异步推理」；但在 UniBot 接口下，一次 `get_action` 返回一个 chunk，**块内近似开环执行**，误差随 chunk 累积——闭环的「刷新率」被 `action_chunk_size` 与网络时延夹死。谁能把「开环块」变成「世界一偏离就重规划」，谁就拿到低延迟下的鲁棒性。

> **预测性维护**：前 21 轮把「维护」理解为硬件健康。竞赛里没有健康标签、也不给你修机器人；真正可维护的是**策略自己的轨迹与数据集**——在失败发生前预测「这个 chunk 会失败」，并据此提前换策略、提前补数据。

> **协同控制**：双臂协调是官方明列的任务类别（ArrangePlates、FoldTowel、ZipUp、PackBag、ToolboxStorage、PaperCupStacking…）；同时「N 端口并发、每端口独立 episode、共享后端」的提交形态，本身就是一个**多代理协同 + 资源协同**问题。协同有两个面：空间面（左右臂）与计算面（多端口）。

一句话押注：

> **不重造基座，而是给任意世界动作模型（UnifoLM-WMA / LingBot-VA 类）叠加一个轻量、可部署、接口合规的「协同-预后-闭环校正层」CPC-CORRECTOR：用一个蒸馏出的前瞻后果预测器把「块内开环」变成「事件触发闭环」；用一个轨迹预后头把「事后失败」变成「事前可维护」；用一个双臂协同流形 + 多端口协同服务把「各自为战」变成「共享约束」。**

三个可验证创新点：

1. **前瞻后果预测器 + 事件触发闭环（LOOKAHEAD-EVENT-CLOSE）**：冻结一个轻量潜世界模型 `f_ψ:(z_t,A_{t:t+H})→ẑ_{t+1:t+H}`，在每次查询时对「即将提交的 chunk」做一次前瞻，并用上一步「预测 vs 实测」的 **Mahalanobis 惊喜** `s_t` 驱动 CUSUM 触发器；一旦触发即截断当前 chunk 的语义、提前重查询或接管为恢复技能。给出「事件触发使误差不再累积」的界（命题 1）与「检测延迟—查询率」的帕累托最优（命题 2）。

2. **轨迹预后头 + 预测性数据维护（PRO-HEAD + PROGNOSTIC-REPLAY）**：`g_φ:(z_t,ẑ_{t+1:t+H},A)→{p_fail, τ̂_fail, h_policy}` 预测「本 chunk 内子目标失败概率、预计失败时刻、策略健康度」；输出直接调制保守度与恢复路径，并**反哺数据**：用 `g_φ` 给全部 32000 条演示打分，抽取出「失败前兆 / 重试成功」片段，构建一个 <2k episode 的高价值恢复数据集，蒸馏恢复技能——把「预测性维护」落在**数据与策略**上，零额外真机时间。

3. **双臂协同流形 + 多端口协同服务（COUPLE-COORD）**：学习跨臂耦合潜变量 `c_t`，用「左臂预测右臂」的互预测损失与任务相关流形投影 `Proj_{K_t}` 显式约束协调；服务侧实现「N 端口共享后端 + 连续批处理 + 每 episode 状态隔离 + 投机预取」，在官方关注的 **p95 延迟与抖动**指标上取得优势（这是分数，不是工程细节）。

三个词怎么落地：

| 词 | 落地 | 不做什么 |
|---|---|---|
| **协同控制** | 双臂互预测 + 协同流形投影 `Proj_{K_t}`；多端口共享后端 + 连续批处理 + 状态隔离；快慢推理与执行重叠 | 不做「参数级双塔各管一臂」的松散结构；不让 N 端口相互阻塞 |
| **预测性维护** | 轨迹预后头 `p_fail/τ̂_fail/h_policy`；预测性回放（Prognostic Replay）挖失败前兆；策略离线重标定 | 不假设有力觉/硬件健康标签；不做纯事后故障诊断 |
| **闭环控制** | 潜世界模型前瞻 + Mahalanobis 惊喜 + CUSUM 事件触发；自适应 chunk 语义；恢复技能接管 | 不逐帧跑昂贵扩散；不为闭环盲增网络往返 |

## 1. 研究日志：从 CG-ZEST 到 CPC-ZEST（含面向竞赛现实的剪枝）

### 1.1 竞赛现实核对（检索 2026-11-05）

```text
F1. 32 任务（G1_Dex1_*，含 HangCup/ArrangePlates/ArrangeTestTubes/ZipUp/ColorArrangement/
    Unlock/DisconnectEthernet/ConveyorSorting/FruitCollection/FoldTowel/OrganizeBookshelf/
    FruitSorting/SpellRobot/OrganizePencilCase/OrganizeStationery/StackBowls/StoreCups/
    OrganizeTools/PackDoll/PackBag/PackPhone/StoreEarphones/StorePaddle/PaperCupStacking/
    PickOutBatteries/ToolboxStorage/PlugCharger/SyringeWaterTransfer/PlugInEthernet/
    PlacePhotoFrame/RemovePinnedNote/PourOutMedicine），约 32000 episodes / 169 h。
F2. 观测仅 4 相机 + 臂/EE/夹爪/下半身本体 + 语言；无力觉、无触觉。
F3. 动作 = chunk（joint 或 ee），块内顺序执行；metadata 一次握手固定 action_chunk_size。
F4. N 机器人并发、N 端口；官方显式考核延迟稳定性与动作统计规律。
F5. 泛化五轴：位置/干扰物/背景/未见物品/人为干扰。
F6. 榜单 Coming Soon；用户与公开信息称榜首成功率 <30%。
F7. 公开近邻 SOTA = 世界动作模型路线（LingBot-VA 闭环 rollout + 异步推理；Flash-WAM 步蒸馏）。
```

### 1.2 对前 21 轮的诚实剪枝（本轮最重要的一步）

前 21 轮（PC→MP→CG-ZEST）构建了宏大的「感知-预测-决策 + 克隆-合成-采集」体系，但把它直接搬进 UniBot 有几处**与竞赛现实脱节**，必须剪掉或降级：

```text
P1. MM-ENCODER 的 force/tactile 模态：竞赛接口根本不提供 → 删除；视觉+本体+语言为准。
P2. 5 秒物体「声纹」探测（戳/推/提/摇）：需要机器人自己执行探测序列，直接消耗步骤分且
    可能引入风险 → 降级为「1~2 步廉价探针」的默认关闭可选模块。
P3. 云端 VLA 三级级联：网络往返 + 服务可用性会给官方最在意的 p95 延迟/抖动埋雷 →
    改为「单一基座世界动作模型 + 本地轻量校正层」，异步仅用于同一进程内重叠。
P4. HP-PRED 硬件健康：无标签、且赛制不修硬件 → 重定义为「策略/轨迹健康」并自监督。
P5. 庞大多模块（C-MAP/KCL/AHD/DRS…）：难实现、难调、难证明 → 收敛为「一个 ≤20M 参数的
    校正层」，可插拔在任意基座之后，保持接口合规与低延迟。
```

这不是推倒重来，而是把 ZEST 的「预测—调制—闭环」内核**从科幻拉回可交付**。

### 1.3 从 SOTA 瓶颈逆推创新

```text
LingBot-VA：共享潜空间 + 自回归扩散 + 闭环 rollout + 异步推理，真机 66.7（聚合榜）。
  → 瓶颈：逐帧扩散昂贵；动作-视频联合分布重；未显式处理双臂耦合；泛化五轴非其主旨。
Flash-WAM：模态感知步蒸馏，单步推理 23× 加速，真机仅约 60%（蒸馏掉了真机性能）。
  → 瓶颈：单步蒸馏在真机上「漏」掉性能；证明实时性与保真度仍有缺口。
两者共同空白：① 没有「廉价地把任意基座变得更闭环」的通用外挂；
                ② 没有「预测失败并主动维护」的机制；③ 没有显式的双臂协同约束。
```

于是本轮不追求「再造一个更大的世界模型」，而是瞄准这个空白：**外挂校正层**。

### 1.4 与第 21 轮的关系

| 层 | 第 21 轮 CG-ZEST | 第 22 轮 CPC-ZEST |
|---|---|---|
| 目标 | 物体零样本泛化 + 克隆 | 真机成功率 + 步骤分 + 延迟稳定性 |
| 感知 | 四模态（含力/触觉） | **竞赛原生三源**（视觉/本体/语言） |
| 预测对象 | 置信 γ + 硬件健康 h | **轨迹预后** p_fail/τ̂_fail + 策略健康 |
| 闭环 | 宏观（决策降级） | **微观（块内事件触发闭环）+ 宏观（策略/数据维护）** |
| 协同 | 无 | **双臂协同流形 + 多端口服务协同** |
| 数据 | ACTIVE-HARVEST（需探测） | **PROGNOSTIC-REPLAY（零真机时间，纯离线挖掘）** |
| 形态 | 庞大自研栈 | **≤20M 可插拔校正层**，基座无关 |

**保留**：预测—调制—闭环的思想内核；不确定性驱动保守化。
**升级**：从「物体/健康预测」升级为「轨迹预后」；从「宏闭环」升级为「块内事件闭环」；新增双臂与多端口协同。
**剪枝**：力触觉、探测式声纹、云端级联、重型多模块。

## 2. 直觉深化：时间 / 故障 / 代理 三层协同闭环

```text
时间维（闭环控制）：z_t --世界模型前瞻--> ẑ_{t+1:H} ；实测 z_{t+1} 与预测比对 → 惊喜 s_t
                    → CUSUM 触发 → 截断/重查询/接管。让误差「不累积」。
故障维（预测性维护）：从 (z_t, ẑ, A) 预测 p_fail/τ̂_fail → 提前保守化、提前切换恢复技能；
                    离线用 p_fail 给全库打分 → 挖失败前兆 → 维护数据集与策略。
代理维（协同控制）：双臂 c_t 互预测 + 流形投影；N 端口共享后端批处理 + 状态隔离 + 预取。
```

三层的耦合点：

1. **前瞻 → 预后**：前瞻出的未来潜状态是预后头的输入——「先想象世界会怎样，再判断会不会失败」。
2. **预后 → 闭环**：`p_fail` 高时不是等惊喜发生，而是**提前**触发保守/恢复；惊喜触发是「来不及了」的兜底。
3. **协同 → 预后**：双臂失配（互预测残差大）本身就是一个强失败先兆，进入 `p_fail`。
4. **预后 → 数据**：`p_fail` 是离线挖矿的廉价价值函数，闭环回灌训练集（飞轮）。

## 3. 正式化：CPC-CORRECTOR 的符号定义

### 3.1 竞赛原生观测与动作

```text
o_t = { l, I_t^4, q_t^{L,R}∈R^7, ee_t^{L,R}∈R^6, g_t^{L,R}∈R^1, b_t∈R^15 }
z_t = Enc(o_t) ∈ R^{d_z}                      # 冻结视觉骨干 + 状态 MLP + 语言嵌入
A_t = a chunk ∈ R^{T_a × d_a},
    d_a = 7+7+1+1+7 = 23 (joint) 或 6+6+1+1+7 = 21 (ee)
```

控制空间选择：**默认 joint**（与演示数据、策略蒸馏最一致，规避逆运动学误差）；`ee` 作为消融。

### 3.2 前瞻后果预测器（潜世界模型）

```text
f_ψ : (z_t, A_{t:t+H}) → ẑ_{t+1:t+H}          # H = 前瞻视界（默认 2×T_a）
损失：ℒ_wm = Σ_h ‖ẑ_{t+h} − sg(z_{t+h})‖² + λ_pix·ℒ_pix(可选，蒸馏基座视频分支)
预训练：在 32000 条演示上做「动作条件潜预测」；可选从基座世界模型蒸馏。
惊喜欢量：s_t = sqrt( (z_t − ẑ_t)^T Σ̂^{-1} (z_t − ẑ_t) )   # Mahalanobis，Σ̂ 由 f_ψ 预测
```

### 3.3 事件触发闭环与自适应 chunk 语义

```text
CUSUM：Λ_t = max(0, Λ_{t-1} + s_t − μ_0)，触发条件 Λ_t > h   （μ_0 为正常惊喜基线）
触发器 T_t ∈ {CONTINUE, REQUERY, RECOVER}
  - CONTINUE：按原 chunk 继续（前一段预测可信）
  - REQUERY ：放弃当前 chunk 剩余段，立即用最新 obs 重新 get_action
  - RECOVER ：p_fail 超阈且无安全重规划时，接管为恢复/安全减速技能
```

**关于接口约束的诚实说明**：若评测器按「整块执行」调用，闭环刷新率 = 1/T_a；若按「每步调用、策略内部缓存块」调用，刷新率 = 每步。CPC-CORRECTOR 对两种模式都兼容（内部缓存 + 事件触发时丢弃缓存）。我们不假设获得无法获得的块内观测。

### 3.4 轨迹预后头 PRO-HEAD

```text
g_φ : (z_t, ẑ_{t+1:t+H}, A_t, c_t) → (p_fail, τ̂_fail, h_policy)
ℒ_pro = BCE(p_fail, y_fail) + Quantile(τ̂_fail, t_fail) + Calib(h_policy)
        + λ_con·(p_fail 与实测子目标失败的一致性约束)
标签来源：演示中的子目标边界可自动标注（成功/重试/失败），无需人工。
```

`h_policy` 自监督定义：以「近 L 步惊喜与预后校准误差的负值」为伪标签——反映「策略当前是否 in-distribution」。

### 3.5 双臂协同流形

```text
耦合潜变量：c_t = Coupler(z_t) ∈ R^{d_c}
互预测：ℒ_cross = ‖A_t^L − π^R→L(A_t^R, c_t)‖² + ‖A_t^R − π^L→R(A_t^L, c_t)‖²
协同流形：K_t = { A : ρ(ee_t^L, ee_t^R; l) ≤ ε }        # ρ 为任务相关相对位姿/距离约束
投影：A_t ← Proj_{K_t}(A_t)                              # 轻量、可微、仅约束两臂相对量
失配先兆：m_t = ‖A_t^L − π^R→L(A_t^R, c_t)‖ → 进入 p_fail 条件
```

直觉：折叠毛巾需要两手相对距离保持在一个窄带；插拔/接线需要一手固定一手动；协同流形就是把这些合法关系写成约束，避免「单臂对了、双臂散了」。

### 3.6 多端口协同服务（接口工程即分数）

```text
拓扑：N 端口端点（8765..8765+N−1）→ 单推理后端（连续批处理）
状态隔离：每个端口的 obs 历史、chunk 缓存、CUSUM 状态、coupler 状态独立
投机预取：执行当前 chunk 时，基于 f_ψ 前瞻预生成「若继续」的候选 chunk，
          一旦触发 REQUERY 可毫秒级返回，避免延迟尖峰
优先级调度：REQUERY/RECOVER 请求优先于常规请求；对 p95 延迟设 SLO
批处理：不同端口同一时刻的请求合并 batch，提升吞吐、降低单位时延
```

这直接回应官方 §6「延迟与抖动是可信度依据」——**把系统指标做成算法优势**。

### 3.7 主循环（骨架，完整实现见产物区）

```python
class CPCPolicy:
    def reset(self):
        self.hist.clear(); self.chunk_cache = None; self.cusum = 0.0
        self.coupler.reset(); self.prev_pred = None

    def get_action(self, obs):
        z = self.encoder(obs)
        # 1) 用上一步预测 vs 当前实测计算惊喜，驱动事件触发
        s = self.surprise(z, self.prev_pred) if self.prev_pred is not None else 0.0
        self.cusum = max(0.0, self.cusum + s - self.mu0)
        trigger = (self.cusum > self.h)
        # 2) 生成/复用 chunk
        if self.chunk_cache is None or trigger:
            A_nom = self.base_policy(obs)                 # 世界动作/VLA 基座
            z_hat = self.world_model.rollout(z, A_nom)    # 前瞻
            p_fail, tau, h = self.pro_head(z, z_hat, A_nom, self.coupler(z))
            A = self.coordinate(A_nom, z)                 # 双臂协同流形投影
            A = self.safe_envelope(A, p_fail, h)          # 预后调制 + 安全包络
            self.chunk_cache = A; self.prev_pred = z_hat[:, 0]
            self.cusum = 0.0
        return self._pack(self.chunk_cache)
```

### 3.8 性质与命题（非正式）

**命题 1（事件闭环抑制误差累积）**：设单步潜预测误差有界 `‖e_t‖ ≤ ε`、开环偏差每步放大因子 `L>1`，则纯开环执行 T 步的误差上界为 `~L^T ε`（指数累积）；而 CPC 在惊喜触发即重锚定（`e_t ← 0`），其误差上界被 `β/(1−p_esc)` 型常数控制，**与 episode 长度无关**。这解释了为何「闭环刷新」比「更强基座」在长程任务上更划算。

**命题 2（事件触发的检测-查询帕累托）**：在惊喜过程为「正常 N(μ_0,σ²)、异常 N(μ_1,σ²), μ_1>μ_0」的简化模型下，CUSUM 在给定平均查询率约束下达到最小期望检测延迟（Lorden 意义下的渐近最优）。→ 自适应阈值 `h` 可在线按延迟 SLO 调节。

**命题 3（双臂耦合的互信息界）**：若 `I(A^L; A^R | z) > 0`（真任务里普遍成立），则忽略耦合的单臂策略存在不可约的协同误差 `≥ ε_cross > 0`；加入互预测头可将其降至 `O(exp(−I))` 量级。→ 协同头对双臂任务的增益有信息论下界。

**命题 4（多端口吞吐-延迟）**：连续批处理下，N 端口共享后端的 p95 延迟 `≤` 独立部署的 p95 延迟，当且仅当批处理带来的单位计算摊销 > 端口间干扰；投机预取把 REQUERY 的延迟尖峰从「完整前向」降到「缓存命中」。

**复杂度**：

| 组件 | 时间 | 空间 | 备注 |
|---|---|---|---|
| Encoder（冻结） | ~2 ms | ~50 MB | 4 相机 + 本体 |
| 世界模型前瞻 f_ψ | ~4 ms | ~15 MB | H=16, 小 Transformer/MLP |
| 预后头 g_φ | <1 ms | ~1 MB | 三头 MLP |
| 协同头 + 投影 | <1 ms | ~2 MB | 低秩 + 约束投影 |
| 基座策略 π_base | 视基座 | — | 主成本 |
| **校正层总计** | **~6 ms** | **~20 MB** | 对 p95 影响可控（可异步） |

## 4. 预期实验结果（设计，非真机声称）

### 4.1 离线（32000 episodes，零真机时间）

| 模块 | 指标 | 预测 |
|---|---|---|
| 世界模型 | 潜预测 1-step MSE / 16-step MSE | 相对 persistence 基线降 40% / 25% |
| 惊喜检测 | 失败前兆 AUROC / 检测延迟 | AUROC 0.82 / 延迟 ≤ 2 chunk |
| 预后头 | p_fail AUROC、ECE | 0.85 / <0.05 |
| 协同头 | 双臂任务互预测残差 | 相对无 c_t 降 30% |

### 4.2 仿真闭环（RoboTwin 2.0 / LIBERO，若可得）

| 配置 | 成功率 | 平均 chunk 查询数 | 说明 |
|---|---|---|---|
| 纯基座开环 | 基线 | 1 | 参考 |
| 基座 + 每步重查询（无预测） | +~3pt | 8× | 延迟爆炸 |
| 基座 + CPC（事件触发） | **+~8pt** | ~1.4× | 延迟可控 |

### 4.3 真机/评测协议（若获得参赛资格）

- 双臂子集 vs 非双臂子集分别报告，验证协同头增益集中在双臂任务。
- 泛化五轴分桶报告（位置/干扰物/背景/未见物品/人为干扰）。
- 延迟报告：p50/p95/抖动，以及「REQUERY 尖峰」被投机预取驯服后的曲线。

## 5. 持续迭代的创新点清单（本轮修订）

> 标记：🟢 保留推进　🔵 新增　🟡 降级/待观察　🔴 剪枝

| # | 创新点 | 动机 | 与现有方案差异 | 技术可行性 | 所需资源 | 落地步骤 | 风险 |
|---|---|---|---|---|---|---|---|
| 1 🔵 | 前瞻后果预测器 + 事件触发闭环 | 块内开环误差累积；SOTA 靠闭环但刷新率被 T_a 夹死 | SOTA 用大世界模型自身做闭环；本方案用**外挂轻量校正层**让任意基座变闭环 | 高（潜预测小模型，仿真可验证） | 32000 演示 + 单卡训练 | 训 f_ψ → 定惊喜统计 → CUSUM 调阈 → 仿真闭环验证 | 潜空间位置/尺度漂移使惊喜虚高 |
| 2 🔵 | 轨迹预后头 + 预测性回放 | 把维护从硬件移到轨迹/数据；事前而非事后 | SOTA 无「失败概率预测 + 数据再挖掘」闭环 | 中高（子目标标签可自动） | 演示子目标自动标注 | 训 g_φ → 全库打分 → 抽恢复集 → 蒸馏恢复技能 | 子目标边界自动标注噪声 |
| 3 🔵 | 双臂协同流形 + 互预测 | 官方明列双臂任务；SOTA 未显式建模耦合 | 显式跨臂耦合 + 约束投影，而非单潜空间黑箱 | 高 | 双臂任务子集 | 训 coupler → 互预测损失 → 流形投影接入 | 约束过紧伤害单手主导任务 |
| 4 🔵 | 多端口协同服务 + 投机预取 | 官方以延迟/抖动评可信度；N 端口并发 | 把服务系统做成算法优势，而非纯工程 | 高 | 多端口部署环境 | 后端批处理 → 状态隔离 → 预取 → SLO 调度 | 并发下状态串扰 |
| 5 🟢 | 预后调制保守度 α | 继承 20/21 轮「越不确定越保守」 | 调制量从 γ/h 改为 p_fail/h_policy | 高 | 无 | 接入 α → 安全包络 | 过度保守掉步骤分 |
| 6 🟡 | 廉价 1~2 步探针 | 想保留物体辨识能力 | 把 5 秒声纹降为最低成本探针，默认关 | 中（耗步骤） | — | 消融比较收益/步骤成本 | 收益不抵步骤扣分 |
| 7 🟢 | joint 控制空间优先 | 与演示/蒸馏一致，规避 IK 误差 | 明确选择 + ee 消融 | 高 | 无 | — | ee 在部分任务更优 |
| 8 🔴 | 力/触觉模态 | — | 竞赛无此通道 | 不可行 | — | 删除 | — |

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **接口语义不确定**（块内是否可重查询）：闭环设计可能失效 | 双模式兼容（内部缓存）；离线用官方 example_env/run_client 反复验证接口行为 |
| **潜惊喜与真实失败不对齐**：世界模型学的是重构图，不是任务相关偏差 | 用「预后头一致性」联合训练；只在任务相关潜子空间计算惊喜；用失败 AUROC 反选潜维度 |
| **事件触发导致延迟尖峰**：REQUERY 变多，官方扣可信度 | 投机预取 + 连续批处理 + 优先级 SLO；对触发率设上限 |
| **双臂约束过紧**：本就单手主导的任务被拖累 | 任务自适应 ε；仅对检测到的协同阶段开启；消融验证不伤单手任务 |
| **预后头标签噪声** | 子目标边界用多信号投票（腕相机接近、夹爪开合、EE 停顿）自动标注；校准约束 |
| **校正层引入过拟合**：离线好真机差 | 冻结基座 + 只训校正层；域随机化增广；只在潜空间操作以抗外观域偏移 |

## 7. 本轮最大的风险

**「闭环控制」在 UniBot 接口下的闭环新鲜度可能根本不足：若评测器严格按整块执行、块内不回调，那么事件触发闭环只能发生在 chunk 边界，闭环的频率被 `action_chunk_size` 锁死；此时 CPC 的核心收益退化为「更聪明的块间重规划 + 预后保守化」，而无法真正实现「世界一偏离就重规划」。** 因此本轮把「验证接口语义（每步回调还是整块执行）」列为**第一优先落地步骤**；它决定创新点 1 是「强收益」还是「弱收益」。

## 8. 灵感词贯通

> **协同控制**：空间上，双臂互预测 + 协同流形投影把「左右手各自为战」变成「共享相对位姿/接触约束」，并对双臂任务给出互信息下界的增益论证；计算上，N 端口共享后端 + 状态隔离 + 投机预取，把「多机协同」做成延迟稳定性优势。
> **预测性维护**：从「维护硬件」转向「维护轨迹与策略」——轨迹预后头在失败前预测失败，驱动提前保守化与恢复接管；预测性回放用预后头给全库打分，零真机时间挖出失败前兆集，持续维护数据与技能。
> **闭环控制**：潜世界模型前瞻 + Mahalanobis 惊喜 + CUSUM 事件触发，把「块内开环」变成「世界偏离即重锚定」，并证明事件触发使误差不再随 episode 累积；把闭环从 SOTA 的「大模型自身特性」变成「任意基座可外挂的轻量能力」。

## 9. 参考来源（检索日期 2026-11-05）

- UniBot 世界挑战赛官网首页：https://unibot.unitree.com/ （2026-11-05）
- 挑战赛任务集（32 任务 / 32000 episodes / 169h）：https://unibot.unitree.com/challenges.html （2026-11-05）
- 排行榜（Coming Soon）：https://unibot.unitree.com/leaderboard.html （2026-11-05）
- 提交模板与接口规范（policy 接口、obs/action 目录、N 端口、§6 交互质量与可信度）：https://github.com/unitreerobotics/unibot_submission （2026-11-05）
- 参考实现：https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/example/example_policy.py （2026-11-05）
- 数据集集合（32 个 G1_Dex1_* 任务）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset （2026-11-05）
- 数据字段与相机/动作定义（G1_Dex1_FoldTowel）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel （2026-11-05）
- 宇树官方数据页（160h / 3.3 万轨迹 / 32 任务）：https://www.unitree.com/data/ （2026-11-05）
- 近邻 SOTA 聚合榜（Unitree G1 真机）：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world （2026-11-05）
- LingBot-VA《Causal World Modeling for Robot Control》（闭环 rollout + 异步推理，arXiv:2601.21998）：https://www.sota2.com/research/paper/697c3b74a8b01e76cc8da792 （2026-11-05）
- Flash-WAM《Modality-Aware Distillation for World Action Models》（步蒸馏，23×，真机约 60%）：https://www.sota2.com/research/paper/6a22584d86173ad9c1468873 （2026-11-05）
- UnifoLM-WMA（Unitree 世界模型-动作框架，G1 任务）：https://deepwiki.com/unitreerobotics/unifolm-world-model-action/7.2-unitree-g1-robot-tasks （2026-11-05）
- 赛事发布报道（2026-07-10）：https://myxmr.com/en/news/unitree-launches-unibot-world-challenge （2026-11-05）

> 本轮一句话押注：**最值得押注的是创新点 1——「前瞻后果预测器 + 事件触发闭环」：它把 SOTA 世界动作模型最核心却最昂贵的「闭环 rollout」蒸馏成一个 ≤20M、可外挂、接口合规的校正层，先用官方 example 把接口语义钉死，再在潜空间上证明「事件触发使误差不累积」。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 22 轮产物 · CPC-ZEST 技术报告：面向 UniBot-V1 的「协同-预后-闭环」可插拔校正层

> 检索日期：2026-11-05。本文给出 CPC-CORRECTOR 的形式化、接口合规的可运行伪代码、关键推导、实验协议与预期结果。

## 0. 结论

CPC-ZEST 不重造世界动作模型，而是给任意基座（UnifoLM-WMA / LingBot-VA 类）叠加一个 **≤20M 参数、接口合规、低延迟**的校正层，含三个部件：

1. **前瞻后果预测器 `f_ψ` + 事件触发闭环**：在潜空间前瞻 `H` 步，用 Mahalanobis 惊喜 + CUSUM 决定 CONTINUE / REQUERY / RECOVER；把「块内开环」变成「偏离即重锚定」。**命题 1 证明事件触发使误差上界与 episode 长度无关**。
2. **轨迹预后头 `g_φ` + 预测性回放**：预测本 chunk 内子目标失败概率 `p_fail`、失败时刻 `τ̂_fail`、策略健康度 `h_policy`；离线用 `p_fail` 给 32000 条演示打分挖失败前兆，构建 <2k 高价值恢复集，零真机时间维护数据与技能。
3. **双臂协同流形 + 多端口协同服务**：跨臂互预测 `ℒ_cross` + 任务约束投影 `Proj_{K_t}`；服务侧连续批处理 + 每端口状态隔离 + 投机预取，把官方考核的 p95 延迟/抖动做成优势。

对齐赛事：32 任务、32000 episodes/169h、G1+Dex1、0 力/触觉通道、joint/ee 块级动作、N 端口并发、延迟稳定性即分数、5 泛化轴（来源见 §9）。

## 1. 形式化与变量约定

### 1.1 竞赛接口对齐（硬约束）

| 项 | 规范 | CPC 的遵守 |
|---|---|---|
| `metadata` | 一次握手：control_space / obs_delta_indices / image_resize / action_chunk_size / token | 固定；校正层不改接口 |
| `get_action(obs)` | 返回一个 chunk；键含 `meta.token` + 共享键 + 对应控制空间双键 | 严格按 §3 目录打包 |
| `reset()` | 每 episode 起始调用一次 | 清空历史、chunk 缓存、CUSUM、coupler 状态 |
| 端口 | N 机器人 → 8765..8765+N−1，状态隔离、并发可靠 | 共享后端 + 状态隔离 + 批处理 |
| §6 | 延迟/抖动/动作规律性 = 可信度 | 预取 + 优先级 SLO |

### 1.2 校正层形式化

```text
观测：o_t = {l, I_t^4, q_t^{L,R}, ee_t^{L,R}, g_t^{L,R}, b_t}
编码：z_t = Enc(o_t) ∈ R^{d_z}                       # d_z = 256（冻结骨干）
基座：A_nom = π_base(o_t) ∈ R^{T_a × d_a}
前瞻：ẑ_{t+1:t+H} = f_ψ(z_t, A_nom)，H = 2·T_a
惊喜：s_t = ‖z_t − ẑ_t‖_{Σ̂^{-1}}（Mahalanobis）
CUSUM：Λ_t = max(0, Λ_{t-1} + s_t − μ_0)，触发 T_t = 1[Λ_t > h]
预后：g_φ(z_t, ẑ, A_nom, c_t) → (p_fail, τ̂_fail, h_policy)
协同：c_t = Coupler(z_t)；A ← Proj_{K_t}(A)（两臂相对量约束）
输出：A* = SafeEnv(A, p_fail, h_policy)
```

**joint 与 ee 的动作字典序**（决定 `d_a`）：

```text
joint: [ left_arm(7) | right_arm(7) | left_gripper(1) | right_gripper(1) | pivot(7) ]  = 23
ee   : [ left_ee(6)  | right_ee(6)  | left_gripper(1) | right_gripper(1) | pivot(7) ]  = 21
```

## 2. 接口合规的可运行伪代码

```python
import os
import time
import numpy as np
import torch
import torch.nn as nn
from collections import deque


# ============ 校正层组件（≤20M 参数） ============

class LatentWorldModel(nn.Module):
    """动作条件潜前瞻：z_t, A[Ta,da] -> z_hat[H,dz] + 预测协方差对角线 diag(Sigma)"""

    def __init__(self, dz=256, da=23, H=16, width=512):
        super().__init__()
        self.H, self.dz = H, dz
        self.net = nn.Sequential(
            nn.Linear(dz + da, width), nn.SiLU(),
            nn.Linear(width, width), nn.SiLU(),
        )
        self.to_state = nn.Linear(width, dz)
        self.to_logvar = nn.Linear(width, dz)

    def rollout(self, z_t, A_chunk):
        # 逐动作推进（H 步），A_chunk 不足 H 时用最后一步动作外推
        b = z_t.size(0)
        z = z_t
        states, logvars = [], []
        for h in range(self.H):
            a = A_chunk[:, min(h, A_chunk.size(1) - 1)]
            feat = self.net(torch.cat([z, a], dim=-1))
            z = self.to_state(feat)
            states.append(z)
            logvars.append(self.to_logvar(feat))
        return torch.stack(states, 1), torch.stack(logvars, 1)  # [b,H,dz], [b,H,dz]


class PrognosticHead(nn.Module):
    """轨迹预后：预测 p_fail / tau_fail / h_policy"""

    def __init__(self, dz=256, dc=32, width=256):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(2 * dz + dc, width), nn.SiLU(),
            nn.Linear(width, width), nn.SiLU(),
        )
        self.p_fail = nn.Linear(width, 1)      # sigmoid: 子目标失败概率
        self.tau_fail = nn.Linear(width, 1)    # softplus: 预计失败时刻
        self.h_policy = nn.Linear(width, 1)    # sigmoid: 策略健康度

    def forward(self, z_t, z_hat, c_t):
        g = z_hat.mean(dim=1)                   # 前瞻聚合
        feat = self.trunk(torch.cat([z_t, g, c_t], dim=-1))
        return (torch.sigmoid(self.p_fail(feat)),
                torch.nn.functional.softplus(self.tau_fail(feat)),
                torch.sigmoid(self.h_policy(feat)))


class Coupler(nn.Module):
    """跨臂耦合潜变量 + 互预测残差（失配先兆）"""

    def __init__(self, dz=256, dc=32, arm_a=8, width=256):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(dz, width), nn.SiLU(), nn.Linear(width, dc))
        self.pred_R2L = nn.Sequential(nn.Linear(arm_a + dc, width), nn.SiLU(),
                                      nn.Linear(width, arm_a))
        self.pred_L2R = nn.Sequential(nn.Linear(arm_a + dc, width), nn.SiLU(),
                                      nn.Linear(width, arm_a))

    def forward(self, z_t, A_chunk):
        c = self.enc(z_t)
        aL = A_chunk[:, 0, :8]      # left_arm(7)+left_gripper(1)
        aR = A_chunk[:, 0, 8:16]    # right_arm(7)+right_gripper(1)
        rL = aL - self.pred_R2L(torch.cat([aR, c], -1))
        rR = aR - self.pred_L2R(torch.cat([aL, c], -1))
        return c, 0.5 * (rL.pow(2).mean() + rR.pow(2).mean())


def project_coordination(A_chunk, eps=0.05, joint=True):
    """协同流形投影：把两臂相对位姿约束到任务带内（此处用相对 EE 位移的简化形式）。
    真实实现需用正运动学把关节角映射到 EE 相对量再回投；此处给出可微骨架。"""
    A = A_chunk.clone()
    off = 0
    width = 7 if joint else 6
    # 以首两段为两臂，约束其差分范数（示意）
    d = A[:, :, off:off + width] - A[:, :, off + width:off + 2 * width]
    excess = torch.relu(d.norm(dim=-1, keepdim=True) - eps)
    corr = excess / (d.norm(dim=-1, keepdim=True) + 1e-6) * d / 2.0
    A[:, :, off:off + width] -= corr
    A[:, :, off + width:off + 2 * width] += corr
    return A


# ============ 主策略（严格接口合规） ============

class CPCPolicy:
    def __init__(self, encoder, base_policy, world_model, pro_head, coupler):
        self._token = os.environ["UNIBOT_SUBMISSION_TOKEN"]
        self._control_space = os.environ["UNIBOT_CONTROL_SPACE"]  # joint|ee
        self.encoder, self.base, self.wm = encoder, base_policy, world_model
        self.pro, self.coupler = pro_head, coupler
        self.T_a = 8
        self.reset()

    @property
    def metadata(self):
        return {
            "control_space": self._control_space,
            "obs_delta_indices": {
                "observation.language":                        [0],
                "observation.images.cam_left_high":            [-6, -3, 0],
                "observation.images.cam_right_high":           [-6, -3, 0],
                "observation.images.cam_left_wrist":           [-6, -3, 0],
                "observation.images.cam_right_wrist":          [-6, -3, 0],
                "observation.state.left_arm":                  [-4, 0],
                "observation.state.right_arm":                 [-4, 0],
                "observation.state.left_ee_pose_gripper_base": [-4, 0],
                "observation.state.right_ee_pose_gripper_base":[-4, 0],
                "observation.state.left_gripper":              [-4, 0],
                "observation.state.right_gripper":             [-4, 0],
                "observation.state.lower_body":                [-4, 0],
            },
            "image_resize": {
                "observation.images.cam_left_high":  [240, 320],
                "observation.images.cam_right_high": [240, 320],
                "observation.images.cam_left_wrist": [160, 160],
                "observation.images.cam_right_wrist":[160, 160],
            },
            "action_chunk_size": self.T_a,
            "token": self._token,
        }

    def reset(self):
        self.prev_pred = None
        self.cusum = 0.0
        self.mu0, self.h = 1.0, 6.0            # 在线标定
        self.chunk_cache = None
        self.trigger = False

    # ---- 惊喜：上一步预测的下一潜状态 vs 当前实测 ----
    def _surprise(self, z_t):
        if self.prev_pred is None:
            return 0.0
        diff = (z_t - self.prev_pred).detach().cpu().numpy()
        return float(np.linalg.norm(diff))

    def _pack(self, A):
        T = A.shape[0]
        d = {
            "meta.token": self._token,
            "action.left_gripper":  A[:, 14:15].astype(np.float32),
            "action.right_gripper": A[:, 15:16].astype(np.float32),
            "action.pivot":         A[:, 16:23].astype(np.float32),
        }
        if self._control_space == "joint":
            d["action.left_arm"] = A[:, 0:7].astype(np.float32)
            d["action.right_arm"] = A[:, 7:14].astype(np.float32)
        else:
            # 需内部用 IK/FK 从关节块换算为 EE 块；示意直接用占位
            d["action.left_ee_pose_gripper_base"] = A[:, 0:6].astype(np.float32)
            d["action.right_ee_pose_gripper_base"] = A[:, 6:12].astype(np.float32)
        return d

    def get_action(self, obs):
        z_t = self.encoder(obs)[None]                     # [1,dz]
        s = self._surprise(z_t[0])
        self.cusum = max(0.0, self.cusum + s - self.mu0)
        self.trigger = self.cusum > self.h

        if self.chunk_cache is None or self.trigger:
            with torch.no_grad():
                A_nom = self.base(obs)[None]              # [1,Ta,da]
                z_hat, _ = self.wm.rollout(z_t, A_nom)    # [1,H,dz]
                c, mismatch = self.coupler(z_t, A_nom)
                p_fail, tau_fail, h_policy = self.pro(z_t, z_hat, c)
                A = project_coordination(A_nom[0], eps=0.05,
                                         joint=(self._control_space == "joint"))
                # 预后调制：越可能失败/越不健康 → 越向基座安全动作收缩
                alpha = float(h_policy.item()) * (1.0 - float(p_fail.item()))
                A = alpha * A + (1.0 - alpha) * A[0:1].repeat(A.shape[0], 1)
                self.chunk_cache = A.detach().cpu().numpy()
                self.prev_pred = z_hat[:, 0, :].detach()  # 预测的 t+1
                self.cusum = 0.0
        return self._pack(self.chunk_cache)
```

**离线训练损失（只训校正层，基座冻结）**：

```text
ℒ = ℒ_wm + λ1·ℒ_pro + λ2·ℒ_cross + λ3·ℒ_surprise_cal
ℒ_wm   = Σ_h ‖ẑ_{t+h} − sg(z_{t+h})‖²
ℒ_pro  = BCE(p_fail, y_fail) + Quantile(τ̂_fail, t_fail) + λ_cal·ECE(h_policy)
ℒ_cross= ‖rL‖² + ‖rR‖²
ℒ_surprise_cal = ‖s_t − s_t^{val}‖²（使惊喜与真实验证误差标定一致）
```

## 3. 关键推导

**命题 1（事件闭环抑制误差累积）**
设单步潜预测偏差 `e_t` 满足 `‖e_t‖ ≤ ε`，且开环推进的 Jacobian 谱半径上界为 `L>1`。纯开环 T 步后误差 `‖E_T‖ ≤ ((L^T−1)/(L−1))·ε`，随 T 指数增长。CPC 在触发时把误差重锚定为 0：令触发间隔随机变量 `G`（均值 `1/p`），则任意时刻误差 `‖E‖ ≤ ε·(L^{G_max}−1)/(L−1) ≤ C(ε,L,G_max)`，与 episode 长度 `T` **无关**。证毕。含义：长程任务里，「更频繁地纠正」比「更强的一次性预测」更划算。

**命题 2（事件触发的检测-查询权衡）**
设惊喜在正常/异常两态下分别为 `N(μ0,σ²)`、`N(μ1,σ²)`（μ1>μ0）。给定平均查询率约束（等价触发率上界），CUSUM 在最小化期望检测延迟意义下渐近最优（Lorden）。阈值 `h` 与查询率、检测延迟单调对应，可在线按延迟 SLO 求解。

**命题 3（双臂耦合的互信息下界）**
若真任务中 `I(A^L; A^R | z) = I0 > 0`，则任一忽略耦合的单臂策略的最小期望协同误差 `ε_cross² ≥ σ²·(1 − exp(−2 I0))`；加入互预测头（以 c 捕捉 A^R→A^L 映射）可把残差降到 `σ² exp(−2 I0)` 量级。证略（用最优估计的 MMSE 与互信息关系）。含义：双臂任务的天花板由 `I0` 决定，协同头把它变现。

**命题 4（多端口吞吐-延迟）**
连续批处理下，N 端口共享后端的 p95 延迟 `≤ max(独立 p95, 单批最大服务时间)`；当批处理摊销 > 端口干扰时严格更优。投机预取把触发 REQUERY 时的服务时间从「完整前向 F」降到「缓存命中 c≪F」，从而压掉延迟尖峰。

**复杂度**：编码~2ms + 前瞻~4ms + 预后/协同<2ms + 基座（视实现）。校正层总计 ~6ms、~20MB。**可异步**：前瞻与预后可与执行重叠，控制环只承担基座 + 打包。

## 4. 实验协议

### 4.1 第一优先：接口语义验证（决定收益上限）

```text
用官方 example/run_server.py + run_client.py，改写 client 使其分别模拟：
  (a) 整块执行：返回 T_a 后连续执行 T_a 步再回调 → 测闭环刷新率 = 1/T_a
  (b) 每步回调：每步发 obs 并调用 get_action → 测闭环刷新率 = 1
记录官方是否发送步间 obs；据此选择闭环设计强度。
```

### 4.2 离线（32000 episodes，零真机）

- 世界模型：1-step/16-step 潜预测 MSE，对 persistence 基线。
- 惊喜：把「子目标失败前 k 步」作为正类，测 AUROC 与检测延迟。
- 预后头：p_fail AUROC/ECE；τ̂_fail 的分位数损失。
- 协同：双臂任务 vs 单手任务的互预测残差分布。

### 4.3 仿真闭环（RoboTwin 2.0 / LIBERO）

消融：`{纯基座开环, 每步重查询, CPC-CONTINUE-only, CPC-full}` × `{固定阈值, 自适应}`；报告成功率、平均查询数、p95 延迟。

### 4.4 真机/评测（若获资格）

双臂子集（ArrangePlates/FoldTowel/ZipUp/PackBag/ToolboxStorage/PaperCupStacking）与非双臂子集分开；泛化五轴分桶；延迟 p50/p95/抖动。

## 5. 预期结果（设计目标，非声称）

| 实验 | 指标 | 目标 |
|---|---|---|
| 世界模型 | 16-step 潜 MSE | 相对 persistence −25% |
| 惊喜检测 | AUROC / 延迟 | ≥0.82 / ≤2 chunk |
| 预后头 | p_fail AUROC / ECE | ≥0.85 / <0.05 |
| 协同 | 双臂互预测残差 | 相对无 c_t −30% |
| 仿真闭环 | 成功率增益 | 纯开环 +3~5pt；CPC +6~9pt |
| 服务 | p95 延迟 | ≤ 独立部署，抖动 − |

## 6. 持续迭代创新点清单（与想法区 §5 同步）

> 🟢 保留推进　🔵 新增　🟡 降级/待观察　🔴 剪枝

| # | 创新点 | 状态 | 一句话 |
|---|---|---|---|
| 1 | 前瞻后果预测器 + 事件触发闭环 | 🔵 | 外挂轻量闭环，误差不累积 |
| 2 | 轨迹预后头 + 预测性回放 | 🔵 | 事前维护轨迹与数据 |
| 3 | 双臂协同流形 + 互预测 | 🔵 | 显式跨臂约束 |
| 4 | 多端口协同服务 + 投机预取 | 🔵 | 延迟稳定性即分数 |
| 5 | 预后调制保守度 α | 🟢 | 越危险越保守 |
| 6 | 廉价 1~2 步探针 | 🟡 | 默认关，控步骤成本 |
| 7 | joint 控制空间优先 | 🟢 | 与演示一致，规避 IK 误差 |
| 8 | 力/触觉模态 | 🔴 | 接口无此通道 |

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 接口整块执行导致闭环刷新率不足 | §4.1 先验证；退化为块间重规划 + 预后保守化 |
| 潜惊喜与任务失败不对齐 | 联合训练 + 任务相关潜子空间 + 用失败 AUROC 反选 |
| REQUERY 延迟尖峰 | 投机预取 + 批处理 + 优先级 SLO + 触发率上限 |
| 协同约束伤害单手任务 | 任务自适应 ε + 仅协同阶段开启 |
| 校正层过拟合 | 冻结基座 + 潜空间操作抗域偏移 + 域随机化 |

## 8. 落地步骤与时间线（建议）

```text
D1–D3  ：跑通官方 example；验证接口语义（§4.1）→ 冻结闭环设计强度
D3–D7  ：在 32000 episodes 上训 f_ψ、g_φ、coupler；离线指标达标
D7–D10 ：仿真闭环消融；标定 μ0/h/α
D10–D14：多端口服务实现 + 延迟压测；准备提交
D14+   ：预约评测；按泛化五轴与双臂/非双臂分桶复盘
```

## 9. 参考来源（检索日期 2026-11-05）

- 挑战赛任务集（32 任务 / 32000 episodes / 169h）：https://unibot.unitree.com/challenges.html
- 首页与赛事愿景：https://unibot.unitree.com/
- 提交模板与接口规范（含 §6 交互质量与可信度、N 端口）：https://github.com/unitreerobotics/unibot_submission
- 参考实现：https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/example/example_policy.py
- 数据集集合：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- 数据字段定义：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- 宇树官方数据页：https://www.unitree.com/data/
- Unitree G1 真机操作聚合榜：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world
- LingBot-VA《Causal World Modeling for Robot Control》：https://www.sota2.com/research/paper/697c3b74a8b01e76cc8da792 （arXiv:2601.21998）
- Flash-WAM《Modality-Aware Distillation for World Action Models》：https://www.sota2.com/research/paper/6a22584d86173ad9c1468873 （arXiv:2606.05254）
- UnifoLM-WMA（G1 任务）：https://deepwiki.com/unitreerobotics/unifolm-world-model-action/7.2-unitree-g1-robot-tasks
- 赛事发布报道：https://myxmr.com/en/news/unitree-launches-unibot-world-challenge
<!-- ARTIFACT:END -->