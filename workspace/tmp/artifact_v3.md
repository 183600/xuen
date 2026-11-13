# 第 3 轮产物 · UniBot 创新点清单 v3（UIP-01″~20）

> 承接 v2（UIP-01′~15）。本轮不是换赛道，而是把 v2 的「扰动恢复闭环」从**仿真依赖**改成**数据+运动学双引擎**：用公开数据集的时间反演造干扰数据（UIP-17），用运动学冗余做内环验证（UIP-19），用进度势对齐计分步（UIP-18），用绝对/相对表示吸收平移扰动（UIP-20）。
> 事实来源与复核日期见想法区 §0（2026-11-13）。排名口径=**平均成功率 + 步骤分**；接口约束=远程 `observation→action`、N 端口并发隔离、开环动作块、逐步延迟与动作规律性计入**可信度**；合规约束=**单模型多任务**。

## 0. 清单总表（v3）

| 编号 | 名称 | 状态 | 主要命中词 | 一句话动机 | 权限内? |
|---|---|---|---|---|---|
| **UIP-01″** | 运动学验证的滚动重做 RHPV-K | **旗舰·升级** | 运动学 | 每 k 步用 KCV 判 done/ongoing/regressed/fail，撤回即重做 | ✅ 纯 API 内 |
| UIP-02″ | 计分步安全网 SSG（对齐 KSS 子目标） | 升级 | 数据集 | 用 KSS 自动子目标替换手写阈值：保前置、搏末步 | ✅ |
| UIP-05 | 语言→可供性/关系分解 LCAG | 保留 | — | 未见物品/背景靠语义条件化 | ✅ |
| UIP-08′ | N 端口确定性延迟工程 LAT-ENG | 保留 | — | 共享骨干 + 批处理 + 每端口状态隔离 | ✅ 工程侧 |
| **UIP-09″** | 撤回检测-重做 DCR-K | **升级·次旗舰** | 数据集+运动学 | 用 KRA 合成数据训练「识别倒放→重做」 | ✅ |
| UIP-11′ | Gazebo 计分神谕 GSO（降级为接触抽查） | 降级 | — | 只校验 KRA/KRT 在接触丰富任务上的物理可信度 | ✅ 离线 |
| UIP-12′ | Gazebo 扰动-恢复工厂 DRF（降级为校验器） | 降级 | — | 从主数据源退为 KRA 的物理过滤器 | ✅ 离线 |
| UIP-13 | 自适应块长实时调度 ACS | 保留 | — | 按阶段/预算选 T_a + 投机预计算压方差 | ✅ |
| UIP-14 | 模块化技能图路由 MSGR | 保留 | — | 32 任务≈10 技能模块，单骨干+技能头 | ✅ |
| UIP-15 | 可信度安全阀 CSG | 保留 | — | 给重试/重做设延迟-抖动预算，防翻车 | ✅ |
| **UIP-16** | 运动学数据审计 KDA | **新增** | 数据集+运动学 | 用冗余 SE(3)/关节一致性审计 32 数据集并对齐接口 | ✅ 离线 |
| **UIP-17** | 运动学反演增强 KRA | **新增·旗舰** | 数据集+运动学 | 时间反演视频+关节轨迹，零仿真造撤回-恢复数据 | ✅ 离线 |
| **UIP-18** | 运动学子目标切分 KSS | **新增** | 数据集+运动学 | 用进度势自动切计分步，替代手写子目标 | ✅ 离线 |
| **UIP-19** | 运动学一致性验证器 KCV | **新增** | 运动学 | FK 残差 + 进度势 + 速度反向，内环零额外模型判撤回 | ✅ 纯 API 内 |
| **UIP-20** | 运动学相对目标 KRT | **新增** | 运动学 | 动作相对物体 keypoint 表示，吸收平移扰动 | ✅ |

---

## 1. 旗舰深潜：UIP-17 · KRA（Kinematic Reversal Augmentation）

### 1.1 机制

给定一条公开演示 episode：视频帧 `I_{0:T}`、关节/夹爪/pivot 动作 `a_{0:T}`、状态 `s_{0:T}`。选撤回点 `p` 与跨度 `h`（例如一个子目标完成点与其起点之间），合成：

- **观测序列**：`I_0 … I_p, I_{p-1} … I_{p-h}, I_{p-h+1} … I_T`（倒放段是原视频帧逆序）；
- **动作序列**：`a_0 … a_p, a_{p-1} … a_{p-h}, a_{p-h+1} … a_T`（关节目标逆序）；
- **状态标签**：`p` 处子目标 `done`，`p+h` 处（倒放结束）`regressed`，`T` 处 `done`。

这条合成 episode 的关键性质：

1. **运动学可行**：倒放段访问同一组关节角，关节限位不变、速度幅值不变（想法区 §1.2 命题）；
2. **视觉-动作对齐**：倒放视频帧对应的正是同一个关节构型，不需要图像生成；
3. **标签免费**：三态标签由拼接位置直接给出，不需要人工标注；
4. **接口兼容**：只用到数据集已有的 `action.left/right_arm`、夹爪、`pivot`，正好是接口子集。

### 1.2 适用范围（必须硬编码白名单/黑名单）

| 干扰类型 | 代表任务 | KRA 是否成立 | 原因 |
|---|---|---|---|
| 逆动作、准静态接触 | T14 拧盖/拧回、T16 叠/翻毛巾、T17 合/开笔盒、T19 拉/开拉链、T27 叠/取碗、T31 文具袋拉链 | **强成立** | 关节倒放≈物体逆过程，视觉可逆 |
| 刚体平移/旋转 | T01–T04、T06、T07、T13、T15、T18、T20–T23、T28、T30 | **部分成立** | 关节倒放本身可行，但物体被外部平移不由倒放产生；需 KRT 或 GSO |
| 物体被拿走/换位 | T05、T10、T12、T24–T26、T29 | **不成立** | 倒放只撤销机器人自身动作，不能重建「物体消失」 |
| 非可逆物理 | T32 液体、粉末、塑性变形、粘附 | **禁止** | 倒放会产生不存在的物理 |
| 底座/架子移动 | T08、T25 | **不成立** | 需重建场景，交给 GSO/DRF |

> 实现上把 32 任务先由 KDA 的文本+运动学分类器打上 `reversible / object-move / removal / non-reversible` 标签，KRA 只对 `reversible` 与部分 `object-move` 生效；其余仍由 UIP-11′/12′ 兜底。

### 1.3 合成伪代码

```python
def kda_classify(task_info, data):
    # 由 info.json 的 human_* 文本 + 动作可逆性统计给出类别
    if task_info.mentions_liquid_or_powder: return "non_reversible"
    if task_info.human_is_removal:        return "removal"
    if task_info.human_is_translation:    return "object_move"
    if is_quasi_static_reversible(data):  return "reversible"
    return "object_move"

def kRA_episode(ep, p, h, speed=1.0):
    # ep: dict(images=I[0:T+1], actions=a[0:T+1], states=s[0:T+1])
    assert 0 <= p - h < p <= len(ep.actions) - 1
    undo = slice(p - 1, p - h - 1, -1)          # p-1 ... p-h
    redo = slice(p - h + 1, None)               # p-h+1 ... T
    images = cat(ep.images[:p + 1], ep.images[undo], ep.images[redo])
    actions = cat(ep.actions[:p + 1], ep.actions[undo], ep.actions[redo])
    states = cat(ep.states[:p + 1], ep.states[undo], ep.states[redo])
    # 速度扰动：倒放段可下采样/上采样，模拟人手快慢
    images, actions, states = time_scale(undo_segment, speed)
    labels = subgoal_labels(len(images), p, p + h, len(images) - 1)
    return dict(images=images, actions=actions, states=states, labels=labels)

def filter_physical(ep_syn, task, oracle=None):
    if task.family == "non_reversible": return False
    if not joint_limits_ok(ep_syn.actions): return False
    if not velocity_limits_ok(ep_syn.actions): return False
    if oracle and task.family in ("reversible_contact",):
        return oracle.replay_ok(ep_syn)        # 仅抽检，非主路径
    return True
```

关键实现细节：

- **撤回点选择**：用 KSS（UIP-18）给出的子目标边界；只在「子目标完成后」撤回，最贴近 `human_*` 的「已完成再撤回」。
- **跨度选择**：`h` 覆盖一个完整子目标；过短（抖动）会被 KCV 当噪声，过长（跨两个子目标）会破坏计分步顺序。
- **速度扰动**：倒放段随机时间缩放 0.5×–2×，并在动作块内重采样，模拟人手快慢与不一致。
- **夹爪处理**：倒放段保持夹爪闭合（或按原序列反向），避免「机器人自己松手 undo」与「人拿走」混淆；对 `removal` 类任务不生成。
- **负样本**：把 `redo` 段替换为「继续 undo」或「停住」，训练 KCV 区分 `regressed` 与 `fail`。

### 1.4 与 v2 的差异

- v2 的 UIP-12 需要 Gazebo 场景、脚本化机械手、接触参数校准；KRA 只需要读数据集，**成本从「周级仿真搭建」降到「小时级数据拼接」**。
- v2 的 UIP-09′ 只能「检测撤回」，训练数据靠真机/Gazebo；KRA 提供大规模三态标签，直接监督 `done/regressed/redo`。
- KRA 的局限也被明确：它不是万能干扰机，只覆盖「可逆准静态」这一子集；其余仍交给 GSO/DRF。

---

## 2. UIP-16 · KDA（Kinematic Data Audit）

### 2.1 审计项

| 检查 | 数学形式 | 期望 | 失败含义 |
|---|---|---|---|
| 关节顺序 | 对候选排列 `π`，最小化 `mean_t d_SE3(F(q_t[π]), p_t)` | 唯一最小值 | 顺序错 → IK/验证器全错 |
| ee 坐标系复合 | `d_SE3(T_base_torso · T_torso_ee, T_base_ee)` | 接近 0 | 坐标系/外参错 |
| 腿-躯干冗余 | `‖lower_body − concat(left_leg,right_leg,waist)‖` | 接近 0 | 键重复但不同源 |
| ee 重算有效 | `recomputed_ee_valid == 1` 的比例 | 高 | FK 失败/坏帧 |
| 关节连续性 | `‖q_{t+1}−q_t‖/Δt` 的分位数 | 有界 | 帧率/单位错 |
| 接口投影 | `state/action` 子集形状与 README §2/§3 一致 | 完全一致 | 部署前即报错 |
| 相机映射 | 数据集 `head_stereo_left/right` ↔ 接口 `cam_left_high/right_high`；`wrist_*` ↔ `cam_*_wrist` | 逐路对齐 | 左右/高低接反 |

### 2.2 关节顺序发现（低成本搜索）

```python
import itertools

def discover_order(episodes, fk, cand_orders):
    best = None
    for pi in cand_orders:                     # 先验候选（URDF 顺序、数据集顺序、镜像）
        errs = []
        for ep in episodes:
            q = ep["observation.state.left_arm"][:, pi]
            p = ep["observation.state.left_ee_pose_gripper_base"]
            errs.append(mean(d_se3(fk(q), p)))
        score = mean(errs)
        if best is None or score < best.score:
            best = (pi, score)
    return best
```

若候选排列无法把残差压到阈值内，说明 FK 的 URDF 版本、连杆长度或相机外参不一致；此时**不要**继续训练，先修数据。

### 2.3 产物

- `data_audit.json`：32 任务 × 每任务的可用 episode 比例、坏段区间、关节顺序、单位/帧率、接口投影表；
- `interface_adapter.py`：把数据集键映射到接口键，显式声明 `left_arm` 顺序与 `head_stereo_*` 映射；
- `reversible_tasks.json`：KRA 白名单/黑名单与理由。

---

## 3. UIP-18 · KSS（Kinematic Subgoal Segmentation）

### 3.1 机制

对每个任务，用运动学信号构造进度势 `Φ_k(o_t)`：

- **接近型**：`Φ = −‖p_ee − p_target‖`（抓取/放置/插入）；
- **深度型**：`Φ = insertion_depth`（插网线/插头）；
- **闭合型**：`Φ = zip_closed_length`（拉链）；
- **堆叠型**：`Φ = stack_height`（碗/杯）；
- **旋转型**：`Φ = accumulated_signed_rotation`（拧盖/开锁）。

然后做**约束变点检测**：官方 `info.json` 给出每个任务的计分步数 `n ∈ {2,3,4,5}`，在 `Φ` 序列上找 `n−1` 个边界，使段内单调性最大、段间跳变最大；用动态规划求解：

```python
def segment(phi, n_steps, lam=1.0):
    # dp[i][k] = 前 i 帧分成 k 段的最优分数
    # 段分数 = 段内 Φ 单调上升的比例 − lam * 段内方差
    ...
    return boundaries   # n_steps-1 个切点
```

### 3.2 与计分点的对齐

- 官方计分步是离散的、有序的；KSS 只提供**候选边界**，最终由人工在 32 个任务上复核（半自动）。
- 用官方步数作为硬约束，能显著降低「把连续搬运切成多段」的错误。
- 输出直接供 UIP-01″ 的状态机与 UIP-02″ 的分值调度使用：`subgoal[g]`、`Φ` 的 done 阈值、`regressed` 的下降阈值。

### 3.3 评价

- 与人工标注边界比：boundary F1、IoU；
- 与官方计分步数比：切分数量必须精确相等；
- 跨 episode 稳定性：同一任务不同 episode 的边界时间归一化方差。

---

## 4. UIP-19 · KCV（Kinematic Consistency Verifier）

### 4.1 机制

KCV 是**解析验证器**，不引入外部大模型，满足单模型合规：

1. **FK 残差**：`r_t = d_SE3(F(q_t), p_t)`；若超阈值 → `kinematic_mismatch`（数据/接口/标定问题，不是策略问题）。
2. **进度势**：`Φ_k(o_t)` 由 KSS 给出；`Φ` 从局部极大下降超过 `δ` → `regressed`。
3. **速度反向**：夹爪闭合时，`q_t` 的末端速度与最近 `w` 帧的平均速度方向相反且持续 ≥ `m` 帧 → `backdriven`（被外力带回）。
4. **停滞**：动作持续变化但 `q_t` 几乎不动 → `stalled`（接触/限位/丢步）。
5. **滑移**（可选，需视觉 keypoint）：夹爪闭合且物体相对夹爪位移超阈值 → `slipped`。

输出状态机：`ongoing / done / regressed / fail`，以及 `confidence`（由残差、持续帧数、阈值裕度合成）。

### 4.2 伪代码

```python
class KCV:
    def __init__(self, fk, phi, delta=0.02, eps_fk=1e-3, back_w=8, back_m=3):
        self.fk, self.phi = fk, phi
        self.delta, self.eps_fk = delta, eps_fk
        self.back_w, self.back_m = back_w, back_m

    def reset(self):
        self.hist = []
        self.phi_max = -1e9
        self.state = "ongoing"

    def __call__(self, obs, g):
        q = obs["observation.state.left_arm"]      # 已按 KDA 对齐顺序
        p = obs["observation.state.left_ee_pose_gripper_base"]
        r = d_se3(self.fk(q), p)
        phi = self.phi(g, obs)
        self.hist.append((q, phi))

        if r > self.eps_fk:
            self.state = "kinematic_mismatch"
            return self.state, 0.99

        if phi > self.phi_max:
            self.phi_max = phi
        elif self.phi_max - phi > self.delta:
            self.state = "regressed"
            return self.state, min(0.99, (self.phi_max - phi) / (2 * self.delta))

        if self._sustained_reverse():
            self.state = "backdriven"
            return self.state, 0.8

        if phi >= self.phi_done(g):
            self.state = "done"
            return self.state, 0.9
        return "ongoing", 0.5 + 0.4 * (phi / max(self.phi_done(g), 1e-6))

    def _sustained_reverse(self):
        if len(self.hist) < self.back_w + self.back_m: return False
        qs = [h[0] for h in self.hist]
        v_now = qs[-1] - qs[-2]
        v_ref = mean([qs[-i] - qs[-i-1] for i in range(2, self.back_w + 1)], axis=0)
        return cos(v_now, v_ref) < -0.5 and norm(v_now) > 1e-4
```

### 4.3 为什么它比 VLM/Gazebo 更适合内环

| 维度 | KCV | 外部 VLM | Gazebo |
|---|---|---|---|
| 延迟 | 微秒–毫秒（FK + 阈值） | 数百毫秒–秒 | 数十毫秒–秒/步 |
| 合规 | 无额外模型 | 可能被判「非单模型」 | 离线，不进提交 |
| 可解释 | 残差/阈值/帧数 | 自然语言、不可复现 | 物理量，但 sim-to-real |
| 覆盖 | 关节/进度/速度 | 语义/物体状态 | 接触/物理 |
| 结论 | 内环判撤回 | 外环语义复核 | 离线抽查/校准 |

> KCV 不替代视觉：它只能看到「机器人自己」的运动学；物体是否真的被撤回，仍需视觉 keypoint 或 VLM 做外环复核。因此 v3 的组合是 **KCV 内环 + 轻量视觉 keypoint + 人工/离线抽检**。

---

## 5. UIP-20 · KRT（Kinematic Relational Target）

### 5.1 机制

把动作从「base 系绝对位姿」改成「相对当前 ee / 相对物体 keypoint 的增量」：

- 训练时，把演示动作 `a_t = (p_t, R_t)` 转成 `Δ_t = p_t ⊖ p_{t-1}`（相对位移）与 `ΔR_t = R_{t-1}^T R_t`；
- 测试时，给定物体平移 `G`（由视觉 keypoint 估计），目标动作变为 `G · p_t` 或 `p_{t-1} + G · Δ_t`；
- 对 joint 模式，用 IK 把相对 Cartesian 目标转回关节目标，并按关节限位/连续性过滤。

### 5.2 与「位置泛化轴」的关系

`info.json` 的 `human_*`/`unseen_object_*` 里大量是「物体向前/向右/向左移动」。若策略学的是绝对坐标，物体一移，动作就偏；若学的是相对坐标，平移被解析地吸收。**这不是数据增强，而是表示层的等变性**。

### 5.3 风险

- 需要物体/关键点位姿；感知误差会直接进入动作；
- 对关节模式，IK 可能无解或跳变；需连续性约束与回退（回退到绝对目标）；
- 对「物体旋转」比「平移」更难；先用平移验证。

---

## 6. 32 任务适用性矩阵（初判，需 KDA 复核）

| 类别 | 任务（示例） | KRA | KRT | 仍需 GSO/DRF |
|---|---|---|---|---|
| 可逆准静态 | T14、T16、T17、T19、T27、T31 | ✅ 强 | ✅ | 接触抽检 |
| 刚体平移为主 | T01–T04、T06、T07、T13、T15、T18、T20–T23、T28、T30 | ◐ 部分 | ✅ | 少量 |
| 移除/换位 | T05、T10、T12、T24–T26、T29 | ❌ | ✅ 重规划 | ✅ |
| 底座/场景移动 | T08、T25 | ❌ | ✅ 相对 | ✅ |
| 非可逆物理 | T32（液体）及任何粉末/塑性任务 | ❌ 禁止 | ◐ | ✅ |

> 这张表的用途不是替代 v2 的 32 任务计分表，而是给 KRA 划定**安全生成域**：宁可少造，不可造错。

---

## 7. 实验设计 E201–E208（v3）

| 实验 | 对照 | 指标 | 目标 / 判据 |
|---|---|---|---|
| E201 KDA | 数据集原始键 vs 审计后适配 | 关节顺序唯一性、ee 复合残差、`recomputed_ee_valid` 比例 | 32 任务全部可解释；坏帧率与坏段被定位 |
| E202 KRA | 无增强 vs 时间反演增强 | 撤回干扰下成功率 / 步骤分 | 步骤分显著提升；成功率不降 |
| E203 KRA 物理过滤 | 全量 KRA vs 白名单 KRA | 真机/ GSO 上恢复成功率 | 白名单 ≥ 全量；证明「少而准」优于「多而杂」 |
| E204 KCV | VLM 验证器 / GSO / KCV | 撤回检测 AUC、延迟、误重做率 | AUC 不低，延迟低 2 个数量级，误重做率 < 5% |
| E205 KSS | 手写子目标 vs KSS | 边界 F1、步数一致性、跨 episode 方差 | 步数 100% 一致，F1 ≥ 0.8 |
| E206 KRT | 绝对目标 vs 相对目标 | 物体平移轴成功率 | 平移扰动下显著提升 |
| E207 组合 | v2 闭环 vs v3 闭环 | 综合成功率 / 步骤分 / 延迟方差 | v3 在撤回+平移两轴均提升 |
| E208 负迁移 | KRA 全任务 vs 安全域 | 非可逆任务成功率 | 证明黑名单必要；全任务会掉点 |

> 所有真机结论提测前标注为 **KCV/GSO 代理**；KRA 生成数据必须经 E203 的物理过滤才能进训练集。

---

## 8. 合规、接口与风险

- **单模型合规**：KDA/KSS/KRA 均离线；KCV 是解析代码（FK+阈值），不是第二个模型；KRT 与主骨干共享视觉编码。唯一需要警惕的是「外部 VLM 外环复核」——它不进入提交，只用于离线标注。
- **接口红线**：`action_chunk_size` 握手固定；`(T_a,…)` 形状；`meta.token` 每步携带；`joint/ee` 二选一；无 torque。KRA 合成动作必须投影到接口子集，**不能把 `lower_body/base_command` 直接塞进动作**。
- **关节顺序红线**：接口只给 `[7]`，数据集顺序非直觉；部署前用 KDA 固化映射，并在服务端启动自检（用一小段已知轨迹验 FK 残差）。
- **物理红线**：KRA 只对白名单任务生效；非可逆任务禁止倒放；所有合成数据先过关节限位/速度/接触抽检。
- **延迟红线**：KCV 必须 O(1) 且可增量计算；不要把整段视频/大模型放进 `get_action` 内环。
- **手册仍未取到**：5 轴中的「位置/干扰物/背景」与评测轮次/时限/控制频率仍待飞书手册公开后核实；KRT 的平移幅度与 KRA 的撤回时机需按手册校准。

---

## 9. 资源与时间线（粗排）

- **第 1 周**：KDA 审计 32 数据集；锁定关节顺序、接口投影、坏段清单；产出 `data_audit.json` 与 `interface_adapter.py`。
- **第 2–3 周**：KSS 切分子目标；人工复核 32 任务；产出 `subgoals.json`。
- **第 3–5 周**：KRA 合成撤回-恢复数据；建立白名单/黑名单；用 UIP-11′ 对 3–5 个接触任务抽检。
- **第 5–6 周**：KCV 接入 UIP-01″ 状态机；E204 对比延迟与误重做率；UIP-15 护栏联调。
- **第 6–8 周**：KRT 相对目标 + IK 回退；E206 平移扰动实验；UIP-13/14 联调。
- **第 9 周起**：预约真机，用真实榜单/步骤分校准 KCV 阈值与 KRA 安全域。

---

## 10. 本轮最大风险 & 押注

**一句话**：KRA 的「倒放=撤回」只在可逆准静态任务上成立；若不做任务白名单与接触抽检，合成数据会把「液体倒流、布料自动复原」这类假物理灌进策略，真机上表现为高置信度的错误。

**→ 押注：UIP-17 KRA × UIP-19 KCV × UIP-18 KSS 的「数据-运动学闭环」**——它用公开数据集自身的时间反演补齐 v2 最大数据空白（人为撤回），用解析运动学把验证成本压到内环可承受，用进度势把合成数据对齐官方计分步；全部落在选手 API 权限与离线算力之内，且不依赖 Gazebo 的 sim-to-real 保真度。
