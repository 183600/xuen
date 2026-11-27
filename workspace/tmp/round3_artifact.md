# UniBot-V1 参赛创新点清单（第 3 轮 v1.2）

> 检索日期：2026-11-26（第 1 轮）、2026-11-27（第 2/3 轮）；来源见 §5。承接 v1.1：I1/I2/I4/I5/I6/I8/I9 深化或维持，I3 收窄，I7 裁撤，新增 I10–I12。清单只增改不重置。

## 0. 创新点清单（每点：动机 / 与现有方案差异 / 技术可行性 / 所需资源 / 落地步骤 / 风险）

### I1 考纲校准五轴增广引擎 ★★★★★（维持 v2）
- **动机**：计分的 320 次真机评测每次都在 5 轴上偏离训练分布（P2），泛化缺口是全局乘性损失。
- **差异**：用官方考纲卡把增广参数分布对准计分轴，把「零样本泛化」转化为「分布内泛化」，而非盲目随机化。
- **可行性**：高；考纲卡 = LLM 解析 wiki + 人工校对（32 × ~10min）；每轴 3 档剂量-响应。
- **资源**：分割/inpainting 1×24GB GPU；增广输出 ≈2TB。
- **步骤**：①32 张考纲卡；②背景/干扰物轴放量；③外观/位置轴 L0 先行；④剂量-响应定档；⑤轴间析因。
- **风险**：考纲卡与真实评测偏差；位置重拼接物理不可行（L0「不可行动作占比」>5% 即降级为平移不变增广）。

### I2 数据引擎 2.0：110 语料孪生迁移 + 加权共训 ★★★★★（维持 v2）
- **动机**：单模型平均分被最弱任务支配（P1）；示教语料与质量双重浪费（P8）。
- **差异**：孪生任务定向入训 + patch 官方 loader 的族级权重（官方 weight 不生效）+ 示教质量 per-episode 加权。
- **可行性**：高（frozen-VLM/LoRA 单卡起步；全参 action expert 4–8 卡）。
- **资源**：孪生子集 ≈1–2TB + 32 任务 ≈2TB；训练 1×24GB 起步。
- **步骤**：①孪生表；②下载子集；③loader patch + batch 频率单测；④首轮共训；⑤族级 L0 验证正迁移后放量。
- **风险**：孪生任务动态相反导致负迁移（家族级 L0、低权重起步、退步即裁剪）；跨集 schema adapter 必须与 I10 的抓取帧定义对齐。
- **本轮新增约束**：共训数据的相位/抓取帧标注要与 I10 的抓取事件定义一致，否则 I2 的质量分与 I5/I10 的标签不可复用。

### I3 接触插入族关键点视觉伺服 ★★★（收窄）
- **动机**：插入/对齐段（PlugCharger、PlugInEthernet、DisconnectEthernet、Unlock、SyringeWaterTransfer、ZipUp）在 chunk 盲执行时最易卡死；需要高频几何反馈。
- **本轮变化**：原 I3 的「抓取段」整体移交 I10；I3 只负责**非抓取的插入/对齐段**。机制同 v1.1：关键点开放词汇检测 + 几何伺服 + 触发滞回 + 低置信回退；`ee` 控制空间 + per-step 调用天然支持。
- **差异**：与 I10 分工——I10 管「夹住没有」，I3 管「对准没有」；两者共用同一相位状态机与 I12 的 `T_a` 调度器，不新增推理实体。
- **可行性**：中；开放词汇检测零训练起步；混合推理的单模型边界仍需书面确认，降级预案 I3'（训练时辅助监督，推理纯端到端）保留。
- **资源**：1×24GB GPU；关键点检测 1 人周。
- **步骤**：①6 任务关键点定义；②伺服环与滞回；③与 I10 状态机合并；④单任务通道抽测。
- **风险**：混合推理被裁定违规（I3' 兜底）；关键点在透明/反光物体上漂移（置信门控 + 退回 VLA）。

### I4 人手干预门控 + 自适应 chunk ★★★★（维持 v2）
- **动机**：5 类泛化含人为干扰（P3）；干预时继续执行 chunk 会伤人或伤物。
- **差异**：手部检测 + `obs_delta_indices` 历史栈判别干预（<50ms）；INTERFERED→停持→重估→续做状态机；干预态短 chunk / 稳定态长 chunk。
- **本轮修正**：由于 `T_a` 固定（F20），「自适应 chunk」改为**自适应重查询**——干预态在下一个 chunk 边界立即重估，而不是改变 `T_a`；稳定态允许 I12 的边界平滑延长等效执行长度。
- **可行性/资源**：高 / 低。
- **步骤**：①手部检测；②状态机；③与 I12 联调；④真机标定停持动作。
- **风险**：误检导致频繁停持（滞回 + 最小停持时间）。

### I5 失败示教合成器 ★★★★（v3 升级）
- **动机**：数据集全成功（P8），而抓取失败不可观测（P10）；I10 的重抓环需要「偏离→修正」样本。
- **本轮变化**：在 v2（扰动重放/跨段缝合/WMA 生成）上增加**抓取失败注入**四式：①空闭合（预抓取侧向偏移 > 半开口）；②错位闭合（抓取位姿旋转 ±10–20°）；③早闭/晚闭；④恢复拼接（失败段后接另一条成功示教的「后退-重对准-再抓」段）。
- **自动标注**：用 I10 的开口+腕相机验证器给合成段打 success/fail；只有「失败被检测到且恢复成功」的段才入训——从「造偏离」升级为「造可验证的闭环纠正」。
- **差异**：v1.1 的恢复原语是手工脚本，会引入新动作分布；v3 的恢复动作来自示教分布内，并由官方/I10 验证器过滤。
- **可行性**：中-高；纯数据工程 + 轻量验证器。
- **资源**：1×24GB GPU；数据工程 2 人周；验证器训练 1 GPU 日/族。
- **步骤**：①抓取帧自动定位；②四式注入；③拼接与验证器过滤；④LoRA 增量训练；⑤3 任务 A/B。
- **风险**：合成失败与真实失败分布失配（扰动幅度从 I1 考纲卡采样，真机先验 20 条）；验证器误差污染标签（置信门控 + 抽检 5%）。

### I6 双率低延迟服务 ★★★★★（v2 升级）
- **动机**：PR6 表明延迟直接决定反馈带宽；I12 要 `T_a=1–2` 时每步延迟必须远小于 66ms。
- **本轮变化**：在 v1.1（共享 backend、每端口独立队列与 episode 隔离、fp8/INT8、torch.compile/CUDA Graph、obs 预取、`image_resize`、断线重连）上增加**双率推理**：
  - 慢环：VLM/视觉编码每 K 步（或每 K 个 chunk）更新一次，缓存 token；
  - 快环：动作头每步（或每 `T_a`）只读缓存 + 当前本体/腕相机，输出 chunk；
  - 高相机与腕相机可不同频率（高相机 5–10Hz，腕相机 15Hz，因为接触段腕视角变化最快）；
  - `T_a` 作为启动参数可配，供 I12 的 L1 析因。
- **差异**：官方 model_server 单率；本点把「视觉慢、动作快」的采样率差显式化，复用官方 msgpack/websocket 模式（F12）。
- **可行性**：高；量化/编译/CUDA Graph 均是成熟工程。
- **资源**：2×A100 80G 共享 backend；serving 1 人。
- **步骤**：①profile 视觉 vs 动作头延迟；②双率缓存；③`T_a` 参数化；④run_client 全流程 + p99；⑤并发隔离压测。
- **风险**：特征缓存导致视觉滞后（腕相机始终走快环，缓存只用于高相机/语言）；小 `T_a` 下调用过密触发延迟告警（I12 的边界平滑 + 保底 `T_a`）。
- **门禁**：p99 < 40–50ms；0 拒绝动作；动作统计规律性通过。

### I7 世界模型测试时前瞻（裁撤）
- **裁撤理由**：测试时 rollout 直接增加 τ，按 PR6 迫使 `T_a` 变大或降低反馈带宽；它和 I10 争夺同一批高险节点，而 I10 的收益/成本比更高、可观测性更好。
- **资产去向**：WMA-0 的世界模型**转为 I5 离线合成**（仿真模式生成失败/恢复段），不再上计分通道。裁撤不等于废弃。

### I8 评测运营闭环 + 分级消融注册表 ★★★★（维持 v2，新增维度）
- **动机**：真机通道稀缺 + 待验证组合爆炸（P7）。
- **机制**：L0 in-silico（I1 增广器复用；代理指标 = Δprog / Δact / Δkp）→ L1 分数因子设计 → L2 真机只测 top 2–3；注册表滚动记录「离线预测 vs 真机增益」，相关性 >0.6 的代理才可单独准入 L2。
- **本轮新增维度**：`T_a ∈ {1,2,4,8,16}`、双率 {on/off}、验证器 {on/off}、重抓 {on/off}；代理指标新增「抓取验证器 F1」与「重抓触发延迟」。
- **可行性/资源**：高 / 1 人周 + 表格与评测脚本。
- **步骤**：①代理指标；②注册表 schema；③首个用例 = I12 的 `T_a` sweep；④每月复盘相关性。
- **风险**：离线代理与真机增益相关建立慢（先用 3–4 个已知真机结果回填）。

### I9 reset 期检索类比迁移 ★★★★（维持 v2）
- **动机**：未见物品轴（同类不同外观）全面出现；纯参数化泛化对新外观方差大。
- **机制**：`reset()`（每 episode 恰好一次，F18）用 VLM/DINOv2 嵌入把首帧物体映射到「物体-技能库」，episode 全程复用检索到的动作参数先验；零权重更新。
- **本轮分工**：I9 检索「物体→技能/动作参数」的粗先验；I11 检索「物体→抓取位姿」的细先验；二者共用同一嵌入索引与置信门控。
- **可行性/资源**：中-高 / 1 GPU 日 + FAISS + 1 人周。
- **步骤**：①物体库；②嵌入索引；③先验参数化；④reset 检索 + 软注入；⑤未见轴 L0 + 真机抽测。
- **风险**：误检索伤原本会的任务（软偏置 + 距离阈值门控）；reset 期检索合规性需书面确认。

### I10 抓取相位闭环 + 自监督验证 + 有界重抓（新） ★★★★★
- **动机**：抓取是唯一可自标注成败的环节（F24：开口 1.47 vs 0.04），也是失败最不可逆的环节（抓空后继续提升 = 白走一个 chunk）。无 force/tactile（F20）使抓取失败在掉落前「沉默」，必须靠开口/视觉补上观测。
- **与现有方案差异**：基线把「接近-闭合-提升」当作一条开环轨迹；本点把它显式建模为带终止条件的 option：`APPROACH → ALIGN → CLOSE → VERIFY → LIFT/TRANSFER`，失败则 `RETREAT → RE-ALIGN → CLOSE`。不是加第二个策略，而是**同一 VLA 在相位 token 条件下的重查询**。
- **技术可行性**：高。验证器先用阈值（开口 <0.3 = 空；>0.3 = 夹住；F24 的间隔约 1.4），再融合腕相机「物体相对夹爪位移」判滑落；重抓动作来自示教/I5，不引入新动作分布。
- **所需资源**：验证器 1 人周 + 1 GPU 日；状态机 1 人周；无额外大模型。
- **落地步骤**：①在 32 任务补全抓取 rows，按任务/物体/材质标定开口阈值；②实现相位状态机；③用 I5 注入失败，训练相位 token 条件；④单任务通道 3 任务 A/B（抓取成功率、重抓次数、步骤分）；⑤与 I12 联调。
- **风险**：透明/反光/软物体上开口与视觉信号噪声大（材质分组阈值 + 置信不足退回 VLA + 真机抽检）；重抓浪费 180s（R≤2，按剩余时间动态关闭重抓）。

### I11 示教抓取位姿库 + 检索式抓取规划（新） ★★★★
- **动机**：1-DoF 平行爪的抓取是低维、多模态问题；示教已给出每个物体的成功抓取位姿分布，端到端 VLA 却把它平均化。
- **与现有方案差异**：不训练几何抓取网络（无深度，F20），而是从示教抽 `g^obj = T_obj^{-1} T_ee(t_g)`，建「物体嵌入 → 抓取位姿分布」库；推理期检索 top-k，作为预抓取先验 + 期望开口。与 I9 的区别：I9 给技能先验，I11 给抓取几何先验。
- **技术可行性**：中-高。抓取帧可由 gripper 动作/开口自动定位（F24 已验证）；物体相对表示可先用「检测框中心 + 尺度」近似，再升级类别级 6D pose。
- **所需资源**：示教抽帧 1 GPU 日；嵌入 + FAISS 1 人周；无新训练大模型。
- **落地步骤**：①抽抓取帧与 `g^obj`；②按物体/任务聚类；③reset/首帧检索 + 置信门控；④把先验注入 I10 的预抓取与期望开口；⑤留一物体评估位姿误差 + 真机抽测。
- **风险**：物体位姿估计误差传播（只用相对位姿 + I3/I10 视觉伺服修正，不要求绝对精度）；检索错时退回 VLA。

### I12 反馈预算控制：`T_a` 选择 + 双率 + 边界平滑（新） ★★★★★
- **动机**：F20 使有效反馈率 = `15/T_a` Hz；基线 `T_a=16` ≈0.94Hz，接触任务可能不够。`T_a` 是免费但被忽视的控制旋钮。
- **严谨定义**：见 §1.1。核心公式 `T_a* = max(ceil(τ/Δt), (1/(λΔt))·ln(ε_max/ε_0))`；延迟下界与容差上界共同决定可行区间。
- **与现有方案差异**：多数队伍固定基线 `T_a`；本点把 `T_a`、双率、边界平滑作为联合设计，并用离线 λ 估计选值，而不是拍脑袋。
- **技术可行性**：高。先做延迟测量与 `T_a` sweep；双率复用 I6；边界平滑无需训练。
- **所需资源**：延迟 profiling 3 人日；双率原型 1 人周；离线 λ 估计 1 人周。
- **落地步骤**：①profile 视觉/动作头延迟；②离线 replay 估 λ（按任务族）；③`T_a` 候选表；④双率 + 边界平滑；⑤L1 析因 → L2 真机。
- **风险**：小 `T_a` 触发延迟/规律性门禁（p99 目标 + 边界平滑 + 保底 `T_a=4`）；若门禁仍不过，退回 `T_a=8` 并把收益转移到 I10/I11。
- **重要修正**：评测端执行完整个 chunk（F20），所以 ACT 式「重叠 chunk 时序集成」**不可用**（下一次调用时上一 chunk 已被完整消费，没有可集成的未来步）。替代方案是**跨 chunk 边界一阶低通 + 首动作连续性约束**（见 §1.4），不要误用 ACT 的 ensemble。

## 1. 关键伪代码与推导

### 1.1 反馈带宽与 `T_a` 的可行区间

设 Δt=1/15s。评测器在第 k 次调用后执行 `u_k ∈ A^{T_a}`（零阶保持），下一次观测在 `t_{k+1}=t_k+T_a·Δt`。故闭环采样周期 `T_s=T_a·Δt`，反馈带宽 `f_b=15/T_a` Hz。

任务的开环发散率定义为：执行名义 chunk 时，由扰动引起的状态偏差 `δx_t` 满足 `λ = lim_{t→0} (1/t)·E[log(‖δx_t‖/‖δx_0‖)]`。容差 `ε_max` 由成功判据/得分点决定。则盲窗内偏差约 `ε(T_s)≈ε_0·e^{λT_s}`，可容许的 chunk 上界为 `T_a ≤ ln(ε_max/ε_0)/(λ·Δt)`。

延迟约束：单次推理延迟 τ 必须满足 `τ ≤ T_s=T_a·Δt`，否则吞吐下降；故 `T_a ≥ ceil(τ/Δt)`。于是：

```python
import math
DT = 1 / 15.0

def feasible_Ta(lam, eps0, eps_max, tau, dt=DT):
    """返回 (下界, 上界, 推荐值)。lam 单位 1/s。"""
    lower = math.ceil(tau / dt)                      # 延迟下界
    if lam <= 0:
        upper = 10**9
    else:
        upper = math.floor(math.log(eps_max / eps0) / (lam * dt))
    rec = max(lower, min(upper, 16))                 # 不超过基线 horizon
    return lower, upper, rec

# 示意（λ、ε 待本轮 L0-E2 实测，不可当结论）：
# 自由空间搬运 λ≈1/s, ε0=1mm, εmax=20mm -> upper≈44, rec=16
# 一般接触   λ≈5/s, ε0=1mm, εmax=5mm  -> upper≈4,  rec=4
# 精细插入   λ≈15/s,ε0=1mm, εmax=2mm  -> upper≈0,  rec=lower
```

**结论**：`T_a` 不是一个调参细节，而是「容差上界 ∩ 延迟下界」的可行区间；若 `lower > upper`，说明该任务的精度要求与部署延迟不匹配，必须靠双率把 τ 降下来（I6 v2）或靠 I10/I11 把任务变成「可重试」而非「一次成功」。

### 1.2 抓取相位状态机与自监督验证器

```python
class GraspOption:
    """同一 PolicyService 内的 option；不是第二个模型。"""
    def __init__(self, arm, lib, vla, max_retry=2):
        self.arm, self.lib, self.vla = arm, lib, vla
        self.retry = 0

    def step(self, obs, phase):
        w = float(obs[f"observation.state.{self.arm}_gripper"][-1])
        if phase == "APPROACH":
            prior = self.lib.pregrasp_prior(obs)          # I11；None=退回 VLA
            return self.vla.chunk(obs, prior=prior, phase="approach")
        if phase == "ALIGN":
            return self.vla.chunk(obs, prior=self.lib.last_prior, phase="align")
        if phase == "CLOSE":
            return self.vla.chunk(obs, phase="close")
        if phase == "VERIFY":                             # 闭合后稳定 c 帧
            verdict = grasp_verdict(
                w_settle=w,
                w_expected=self.lib.expected_width,
                wrist_flow=wrist_object_flow(obs, self.arm),
            )
            if verdict in ("empty", "slip"):
                if self.retry < self.max_retry:
                    self.retry += 1
                    return self.vla.chunk(obs, phase="retreat")   # 后退+张开
                return self.vla.chunk(obs, phase="fallback")      # 放弃重抓
            return self.vla.chunk(obs, phase="hold")              # 进入提升/搬运
        if phase == "RETREAT":
            return self.vla.chunk(obs, phase="re_align")
        raise ValueError(phase)


def grasp_verdict(w_settle, w_expected, wrist_flow,
                  tau_empty=0.30, tau_slip=0.50):
    if w_settle < tau_empty:                 # F24: 空闭合中位 0.04
        return "empty"
    if wrist_flow > tau_slip:                # 物体相对夹爪滑移
        return "slip"
    # 开口停在物体宽度附近 = 夹住；w_expected 来自 I11 检索
    return "hold"
```

**验证器为什么可行**：F24 的探针显示，成功抓取的稳定开口中位 1.47（0.38–3.33），空闭合中位 0.04，阈值 0.30 处有约 1.4 的间隔；腕相机相对位移补上「夹住了但滑落」的第二种失败。两者都不需要力/触觉，符合 PR7。

### 1.3 示教抓取位姿库（I11）

```python
def extract_grasp(demo):
    g = demo.gripper_state
    t_g = first_close_frame(g)                 # F24 的越阈检测
    T_ee = demo.ee_pose[t_g]                   # 特权状态，离线可用
    T_obj = estimate_object_pose(demo, t_g)    # 先 bbox+尺度，后 6D
    return {
        "emb":   embed_object(demo, t_g),      # DINOv2/CLIP + 语言
        "g_obj": inv(T_obj) @ T_ee,            # 物体相对抓取位姿
        "width": g[t_g],                       # 期望开口
        "task":  demo.task,
    }


def pregrasp_prior(obs, lib, tau=0.35):
    obj = detect(obs["observation.images.cam_left_high"],
                 obs["observation.language"])
    if obj is None:
        return None
    hits = lib.search(embed_object(obs, obj), k=5)
    hits = [h for h in hits if h.dist < tau]
    if not hits:
        return None                            # 置信不足 -> 纯 VLA
    g = robust_mean([h.g_obj for h in hits])   # 旋转用四元数/李代数平均
    T_obj = estimate_object_pose(obs, obj)
    return {"T_pregrasp": T_obj @ g,
            "width": median([h.width for h in hits])}
```

### 1.4 双率调度与跨 chunk 边界平滑（I12）

```python
class DualRatePolicy:
    def __init__(self, vlm, head, K=4, alpha=0.3):
        self.vlm, self.head, self.K, self.alpha = vlm, head, K, alpha
        self.feat, self.prev_a, self.t = None, None, 0

    def get_action(self, obs):
        self.t += 1
        if self.t % self.K == 0 or self.feat is None:
            self.feat = self.vlm.encode(obs)          # 慢环：每 K 步
        chunk = self.head(self.feat, obs, self.phase)  # 快环：每步
        if self.prev_a is not None:                    # 边界一阶低通
            chunk[0] = (1 - self.alpha) * chunk[0] + self.alpha * self.prev_a
        self.prev_a = chunk[-1]
        return chunk
```

**注意**：这不是 ACT 的 temporal ensembling。评测端执行完整个 chunk（F20），下一次调用时上一 chunk 已无剩余未来步，无法做重叠平均；能做的是让新 chunk 的首步与上一 chunk 的末步连续（`alpha` 低通）并约束 jerk，从而在 `T_a=1–2` 时仍保持动作统计规律性。

### 1.5 抓取失败注入（I5 v3）

```python
def inject_grasp_failure(demo, mode, delta):
    t_g = first_close_frame(demo.gripper_state)
    if mode == "empty":                       # 侧向偏出半开口
        demo = shift_ee(demo, t_g, lateral=delta)
    elif mode == "misalign":                  # 旋转抓取位姿
        demo = rotate_ee(demo, t_g, yaw=delta)
    elif mode == "early":
        t_g -= delta
    elif mode == "late":
        t_g += delta
    rec = nearest_success_demo(demo, t_g)     # 同物体/同布局的恢复段
    seq = demo[:t_g] + rec.recovery_segment(t_g)
    return seq if i10_verifier_detects_failure_and_recovery(seq) else None
```

## 2. 实验设计

### 2.1 已完成的离线探针（F24，方向性证据）

| 指标 | 数值 |
|---|---|
| 缓存覆盖 | 15/32 任务，91 eps，每任务 3000 帧窗口 |
| 物体闭合（成功）稳定开口 | 中位 **1.47**（0.38–3.33），n=118 |
| 空闭合稳定开口 | 中位 **0.04**，n=62 |
| 可分性 | 阈值 0.30 → 两类间隔约 1.4（粗探针下） |
| ≥2 次闭合循环的 episode | **43%**（39/91） |
| 闭合时长（越阈→最小） | 中位 **24 帧 = 0.8s**；≤16 帧仅 **34%** |
| 结论 | 开口可做零成本验证器；抓取事件常长于 `T_a=16` chunk |

> 复现：`python exp/grasp_loop_stats.py`（读 `exp/duo_rows_cache`）。限制：仅 15/32 任务、3000 帧窗口、粗阈值，不能当完整普查；下轮补全 32 任务 rows 后重跑。

### 2.2 分级消融协议 v3

| 级别 | 实验 | 通道/成本 | 通过判据 |
|---|---|---|---|
| L0-E1 | 开口验证器：32 任务抓取事件，空/物体分布 + 合成扰动；分组报告刚性/透明/反光/软 | 离线免费 | 刚性 F1 ≥0.95；透明/软单列，不达标则对这些物体关闭重抓 |
| L0-E2 | λ 估计：留出示教在 chunk 边界注入扰动，测 `T_a` 步后偏差 | 离线免费 | 输出每族 λ 与 `T_a` 上/下界（§1.1） |
| L0-E3 | 抓取位姿检索：留一物体，位姿/开口误差 | 离线免费 | 检索位姿误差 < VLA 隐式基线（代理） |
| L0-E4 | 失败注入：验证器检出率 + 恢复段保留率 | 离线免费 | 检出 ≥0.9，假阳性 ≤0.05 |
| L1 | 2^(k-p)：`T_a` {1,2,4,8,16} × 双率 {on/off} × 验证器 {on/off} × 重抓 {on/off} | 离线 + 少量真机 | 主效应显著的 ≤3 组合进 L2 |
| L2 | 3 任务真机：PlugCharger（插入/I3/I12）、HangCup 或 StackBowls（抓取/I10/I11）、ZipUp（接触/I3/I10） | 单任务通道 | 成功率或步骤分↑；p99<50ms；无规律性告警 |
| 门禁 | PR4：run_client 全流程 + p99 + 动作健康度 | 本地 stub | 0 拒绝动作、p99<50ms、无离群 |

**L2 预算分配**：①`T_a` sweep（I12）→ ②开口验证器 + 重抓（I10）→ ③抓取位姿检索（I11）→ ④插入族 I3 复核。每候选 ≥2 任务 × 各 2 次。

## 3. 资源预算（本轮增量）

| 项 | 配置 | 变化说明 |
|---|---|---|
| 训练 | 维持 1×24GB 起步（frozen-VLM/LoRA）；8×A100 上限 | I10/I11 不新增大模型；I5 增量训练同 v1.1 |
| 部署 | 2×A100 80G 共享 backend + 双率 | I6 v2；p99 目标 40–50ms（`T_a=1–2`） |
| 验证器/检索 | 1 GPU 日 + FAISS + 1 人周 | I10/I11 新增，成本低 |
| 真机 | 3 任务 × 10 次单任务通道 | 新增 L2 |
| 人力 | 原 serving 1 人兼任控制/系统（`T_a`/双率） | 不新增编制 |

## 4. 伦理合规 checklist（更新）

- [ ] **同一模型**：I10/I11/I12 都是同一 `PolicyService` 内的组件/重查询，无第二任务模型；仍建议向组委会书面确认「抓取验证器 + 重抓状态机」是否算同一模型（**新增确认项**）。
- [ ] 不在评测时段做任何在线学习/适应；验证器阈值、检索库、抓取位姿库均离线构建，推理期只读。
- [ ] `T_a=1` 的合规性与延迟/规律性测量口径需书面确认；确认前按 `T_a=4` 保底设计。
- [ ] 动作健康度：边界一阶低通 + 平滑损失；每次提交过 PR4 门禁。
- [ ] 人手在场 → 降速/停持/让位（PR3）；停持动作界内平滑。
- [ ] 数据使用：32 任务 + 110 语料 + DiverseManip 均 apache-2.0；共训注明来源。

## 5. 来源清单（检索日期 2026-11-26 / 2026-11-27）

1. 官网挑战页（32 任务、32,000 eps / 169h、得分点制、参赛流程）：https://unibot.unitree.com/challenges.html （2026-11-27 复核）
2. 参赛手册（同一模型、5 类泛化 ×2、远程 API、排名规则）：https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh （r.jina.ai 渲染复核）
3. 提交模板与接口规范（`T_a` 固定、整 chunk 执行、观测/动作 catalog、N 端口、延迟与规律性）：https://github.com/unitreerobotics/unibot_submission （2026-11-27 复核）
4. Unitree Dex1-1 产品页（1 DoF 平行爪、90mm、5–120N、0.24s、1000Hz、腕相机/D405 选项）：https://www.unitree.com/Dex1-1
5. Dex1-1 规格交叉核对（两指、1 DoF、20kg 形锁/5kg 摩擦、V1/V2/V3）：https://sonnyrobotics.com/products/unitree-g1-dex1-1-hands
6. 挑战数据集合集（32 任务全名，HF API）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset-6a3138a00ea492d60df023c8
7. 110 任务共训语料合集：https://huggingface.co/collections/unitreerobotics/unifolm-g1-dex1-dataset-68bae98bf0a26d617f9983ab
8. 官方基线与训练文档（单卡微调/LoRA/loader 混采行为）：https://github.com/unitreerobotics/unifolm-wla （docs/train_action_expert_en.md）
9. 世界模型基线（WMA-0 双模式；已转为 I5 离线资产）：https://github.com/unitreerobotics/unifolm-world-model-action
10. 任务描述 wiki（飞书表格，得分点/泛化细节，仍待逆向）：https://scnhkkqlu12w.feishu.cn/wiki/XoHWwZq3Hi4yVlkX22ucWrmunOg
11. 本机抓取事件探针（F24）：`exp/grasp_loop_stats.py` / `exp/grasp_loop_stats.json`（2026-11-27）
12. 榜单（仍「即将发布」）：https://unibot.unitree.com/leaderboard.html

## 6. 本轮最值得押注（一句话）

**押「反馈预算 × 抓取锚点」：I12 用 `T_a`/双率把闭环带宽买回来，I10 用开口验证器把抓取失败变成可学习信号，I11 用示教位姿库把抓取先验从平均化变成检索化——三者都在同一策略服务内、不需要力/触觉、也不需要新的世界模型。**
