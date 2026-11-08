# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 34 轮 · 三灵感落地：四足先验 × 步骤分最大化 × LoRA 专家银行

> 承接第 33 轮（v10 现实校准版）。本轮不做推倒重来，而是用新灵感词「四足机器人 / 步骤分 / LoRA」**深化三条主链 + 诚实修剪一条伪线**。

## 0. 联网核实（先事实后推理；检索口径 2026-11-08）

本轮用 curl 直取官方仓库、HF 元数据与 arXiv，新增/复核以下事实：

- **事实 A（接口，github README §6 复核）**：策略以 websocket + msgpack-numpy 远程接入，评测方客户端 / 选手服务端（`PolicyService`，端口 8765 起）。**§6 一手确认**：整个评测逐步记录每次 `get_action` 的**时延、时延波动、返回动作的统计规律**，并可能在展榜结果旁展示为**可信度指标**。
- **事实 B（榜单）**：`unibot.unitree.com` 是 ~7KB 纯静态占位页（无 JS bundle、无 API、无 `fetch`），`/challenges`、`/leaderboard` 返回同一页。**排行榜仍不可得**；用户前提"榜首<30%""5 类泛化"仍**无法核实**（诚实标注）。
- **事实 C（数据 schema，HF `meta/info.json` 直取）**：`robot_type=unitree_g1`、LeRobot v3.0、30fps、480×640。obs 相机 `head_stereo_left/right` + `wrist_left/right`；本体 `left/right_arm[7]`、`left/right_gripper`、`lower_body[15]`(=左右腿各 6 + waist 3)、`left/right_leg[6]`、`*_ee_pose_gripper_base[6]`、`*_ee_pose_gripper_torso[6]`、`state_torso[6]`、`state_d435[6]`、`waist_state_joint[3]`、`recomputed_ee_valid[1]`；动作 `left/right_arm`、`grippers`、`lower_body`、`left/right_leg`、`ee_pose(base/torso)`、`waist_action_joint`、**`base_command[4]=[vx,vy,angle_z,height]`**、**`pivot[7]=[vx,vy,angle_z,pivot_3,pivot_4,pivot_5,height]`**、`gripper_controls[4]=[L_trig,L_sqz,R_trig,R_sqz]`。
- **事实 D（★本轮最关键：基座近乎静止）**：直取 HangCup / ConveyorSorting / FruitCollection / OrganizeBookshelf / PourOutMedicine 的 `meta/stats.json`：`pivot` 的 `vx,vy,angle_z,pivot_3,pivot_5 ≈ 0`，`pivot_4 ≈ 0.15` 恒定，`height ≈ 0.735–0.740`（std 仅 0.003–0.016）。**结论：这 32 个桌面任务实质是"定基座（fixed-base）操作"**，自由度几乎全在双臂 + 夹爪 + 腰/高度微调；运动/步态/落脚控制在本赛道**无需求**。
- **事实 E（夹爪）**：量程 0–4.5；左右手使用强度因任务而异（PourOutMedicine 左手均值 2.5 / 右手 4.18；ConveyorSorting 双手均高 ~3.7–4.0），提示**非对称双臂角色**。
- **事实 F（仓库结构）**：`unibot_submission` 仅 `README(.zh).md` + `example/*`(4) + `policy/*`(3)，**无评分/任务清单文档**；评分口径只能求诸参赛手册（feishu，登录墙）。
- **事实 G（数据集开放）**：`unitreerobotics/G1_Dex1_HangCup` 等**非 gated**（`gated:false`），可直连下载；collection 恰为 32 个 `G1_Dex1_*`。

## 1. 灵感词 → 三条落地线（含一条伪线的诚实裁剪）

- 「**四足机器人**」→ 先做**现实校准**：官方平台是**双足** G1，且**事实 D 证明基座静止**，运动/步态/落脚控制**零需求**。因此"四足"只能以两种**遗产**方式合法进入：**(i) 跨形态（body-agnostic）表征/世界模型**——四足机群积累的 sim-to-real、域随机化、teacher-student、身体无关表征，用于提升**未见物/背景泛化**；**(ii) "低维命令式（command-conditioned）基座控制"的抽象**——在本赛仅退化为 `pivot`/`height` 的**微稳定器**。→ **IP-27 QUAD-PRIOR（P2，仅部分保留）**。**明确不引入任何四足硬件/仿真通道**（遵守第 27 条"通道诚实"）。
- 「**步骤分**」→ **IP-28 PROGRESS-CRITIC（P0）**：排名=成功率+步骤分。步骤分最可能是**按 rubric 子步骤的部分分**（解释 A；解释 B"每步交互质量"与 IP-25 重叠）。做一个**不依赖 rubric 文本**的自监督进度/子步骤估计器，同时提供：稠密训练信号、卡住检测→重试/重规划、**"部分分最大化"降级**（任务不可挽回时，优先把当前 rubric 步做完以拿部分分）。**吸收上轮 IP-8 的运行期"省步"**。
- 「**LoRA**」→ **IP-29 LoRA-EXPERT-BANK（P0）**：赛道要求"**单模型**完成全部任务"，但 32 技能异构。以参数高效方式在共享 VLM 上挂 **K 个能力型 LoRA 专家 + 语言/首帧路由器**：推理只激活少数专家（省显存、低时延、低频路由不伤动作统计规律），另设一个由 IP-24 触发的**恢复 LoRA**。与多端口 Approach 2（共享基座 + 逐端口状态隔离）天然契合。

## 2. 三线耦合与关键决断

- **耦合**：`语言+首帧 → 路由 → 激活 LoRA 专家`（IP-29）→ System-2 出子目标 `z_t`（IP-23）→ IP-28 进度头给 `z_t` 时序**稠密进度监督 + 卡住检测** → System-1 少步流匹配出**双臂+夹爪**动作块 → IP-24 触发时切**恢复 LoRA**/重规划 → IP-25 保时延 SLO。IP-27 只在**表征侧**做跨形态预训练（可选、可关）。
- **关键决断**：
  1. **`pivot` 默认冻结**：按事实 D 直接用各任务 `pivot` 常值（height≈0.738、`pivot_4`=0.15、其余≈0），预测时只在**观测区间内**微调 height/angle_z（`clip` 防分布外）。
  2. **步骤分=可微的进度对齐**：训练损失加 `L_prog = ‖p_t − p̂_t‖`，`p̂_t` 由示范**自监督**生成（夹爪开合事件 + 腕部运动基元变点 + 物体位移/光流变点）。
  3. **LoRA 路由低频**：每 episode 定一次，必要时每 `K_plan` 步复核；避免逐步抖动（呼应 §6 的"动作统计规律"）。
  4. **恢复 LoRA 只增不减**：恢复动作幅度不超过正常策略包络（呼应第 30 条规则）。
  5. **诚实裁剪**：IP-27 的 (ii) 基座控制分量在本赛近似**零边际分**——降级为"仅遥测 + 边界裁剪"，不投算力。

## 3. 本轮最大风险

**灵感-现实的错配**：事实 D 把"四足=运动控制"这条直觉几乎清零，若误投算力到基座/运动将**零收益**。真正的可执行风险有二：**IP-28 的步骤分口径未核实**（rubric 登录墙）与 **IP-29 路由错误导致跨任务干扰**；两者都必须先在本地回放闭环（IP-3）用小规模消融证伪，再谈真机。

## 4. 一句话结论

本轮最值得押注：把 UNIBOT-RFM 的 System-2 改为**语言路由的 LoRA 能力专家银行（IP-29）**，并用**自监督进度/子步骤估计（IP-28）**同时提供稠密训练信号、卡住重试与"部分分最大化"降级；"四足"仅保留为**跨形态表征先验**（IP-27，P2，明确不做运动控制）。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 34 轮产物 · 创新点清单 v11：三灵感落地 —— 四足先验 × 步骤分最大化 × LoRA 专家银行

> 承接 v10（第 33 轮，现实校准版）。本轮**新增 3 项（IP-27/28/29）、合并 1 项（IP-8→IP-28）、其余保留**，并从"三灵感"各深化一条。

## 0. 结论

- **旗舰仍为 IP-21 UNIBOT-RFM**（单模型双系统 VLA 覆盖 32 任务），但本轮把它的 **System-2 升级为"LoRA 能力专家银行"（IP-29）**，把 **训练/运行时监督升级为"进度-子步骤"（IP-28）**。
- **新增**：**IP-29 LoRA-EXPERT-BANK（P0）**、**IP-28 PROGRESS-CRITIC（P0）**、**IP-27 QUAD-PRIOR（P2，仅表征先验，明确不做运动控制）**。
- **合并**：`IP-8 STEP-EFF` 的"少步/早停/平滑"并入 IP-28（运行期步骤分口）+ IP-25（时延口），登记为合并项。
- **诚实裁剪**：事实 D 证明**定基座**，"四足/运动"路线在官方赛道**零需求**；IP-27 的基座控制分量降级为"遥测 + 边界裁剪"，不投算力。
- **路线无关原则（继承）**：任何新想法**不得依赖官方未暴露的通道**（力/触觉/社会/运动学底盘指令）；"假设能读到/能控到 X"一律视为未成立。

## 1. 事实卡（联网核实，检索日期 2026-11-08）

- **F24（官方接口 / github unitreerobotics/unibot_submission，README 复核）**：obs 键 = 4 相机（`cam_left/right_high` 480×640×3 u8、`cam_left/right_wrist`）+ `left/right_arm[7]` + `left/right_ee_pose_gripper_base[6]` + `left/right_gripper[1]` + `lower_body[15]` + `observation.language`(str)。动作：`control_space` 二选一（`joint`→`action.left/right_arm[7]`；`ee`→`action.*_ee_pose_gripper_base[6]`）+ 共享 `action.left/right_gripper[1]` + `action.pivot[7]`；`action_chunk_size=T_a` 前导时间轴；`obs_delta_indices`（offset≤0、严格递增、缺帧首帧补齐）决定"发哪些键 + 时序堆叠"；`image_resize` 决定分辨率；`token` 双向校验；N 机器人→端口 `8765..8765+N-1`，须并发 + 逐端口状态隔离；**§6：逐步记录时延、时延波动、动作统计规律为可信度指标**。
- **F25（数据集结构）**：LeRobot `v3.0`，`robot_type=unitree_g1`，30 fps，480×640 AV1；HangCup = 1043 episodes / 194564 帧（~13.7s 均值）。
- **F26（32 任务清单，HF collection 直取，恰 32）**：HangCup、ArrangePlates、ArrangeTestTubes、ZipUp、ColorArrangement、Unlock、DisconnectEthernet、ConveyorSorting、FruitCollection、FoldTowel、OrganizeBookshelf、FruitSorting、SpellRobot、OrganizePencilCase、OrganizeStationery、StackBowls、StoreCups、OrganizeTools、PackDoll、PackBag、PackPhone、StoreEarphones、StorePaddle、PaperCupStacking、PickOutBatteries、ToolboxStorage、PlugCharger、SyringeWaterTransfer、PlugInEthernet、PlacePhotoFrame、RemovePinnedNote、PourOutMedicine。总量口径 32000 episodes / 169 h（challenges.html）。
- **F30（★动作 schema，HF meta/info.json 直取）**：`action.pivot[7]=[vx,vy,angle_z,pivot_3,pivot_4,pivot_5,height]`；`action.base_command[4]=[vx,vy,angle_z,height]`；`lower_body[15]`=left_leg(6)+right_leg(6)+waist(3)；obs/act 均含 `ee_pose_gripper_base` 与 `ee_pose_gripper_torso`；`waist_*_joint[3]=[yaw,roll,pitch]`；`gripper_controls[4]=[L_trig,L_sqz,R_trig,R_sqz]`。
- **F31（★定基座：跨任务 pivot stats，直取 5 任务）**：`vx,vy,angle_z,pivot_3,pivot_5≈0`，`pivot_4≈0.15` 恒定，`height≈0.735–0.740`（std 0.003–0.016）。**桌面任务实质定基座**；运动/步态无需求。
- **F32（夹爪分布）**：量程 0–4.5；左右手强度差异显著（非对称双臂角色）。
- **F33（repo/HF 结构）**：`unibot_submission` = README×2 + example/*(4) + policy/*(3)，**无评分文档**；`G1_Dex1_*` **非 gated**。
- **F34（榜单/规则，未核实）**：官网为 7KB 静态占位页，无榜单 API；feishu 参赛手册返回 `code:5 Login Required`。"榜首<30%""5 类泛化"为**用户口径/待验假设**。
- **F35（文献，arXiv API 实时检索 2026-11-08）**：见 §6。

**行动项**：A14 全 32 任务 `pivot`/`base_command`/夹爪分布扫描（确认定基座普适性 + 非对称角色）；A15 获取**步骤分/ rubric 定义**（登录墙，IP-28 前置，最高优先）；A16 取 `meta/tasks.parquet` 得 32 条语言指令（指令泛化前置）；A9/A11/A13 沿用（相机映射 / 节拍与 pivot 语义 / 本地回放闭环）。

## 2. 创新点清单 v11 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-21 | **UNIBOT-RFM** | 单模型双系统 VLA 覆盖 32 任务（System-2 规划 + System-1 少步流匹配动作头） | **P0** | A9,A13 | 机器人基础模型 | 算力(重,一次性) | 主成功率 | 旗舰（继承） |
| **IP-29** | **LoRA-EXPERT-BANK** | 共享 VLM 上挂 K 个能力 LoRA 专家 + 语言/首帧路由器 + 恢复 LoRA | **P0** | IP-21 | **LoRA** | 算力(中,推理省) | 全域成功率 + 省显存 | **新增** |
| **IP-28** | **PROGRESS-CRITIC** | 自监督进度/子步骤估计：稠密监督 + 卡住重试 + 部分分最大化 | **P0** | A15,IP-3 | **步骤分** | 数据(标注轻) | 步骤分 + 长程成功率 | **新增** |
| IP-22 | TRI-FUSE | 多视图×本体×语言 token 级融合 + 立体伪深度 + world-model 辅助 | P0 | IP-21 | 技术融合 | 算力(中) | 未见物/位置泛化 | 继承 |
| IP-23 | TASK-DAG | 得分点驱动子目标分段 + 分层策略 | P1 | IP-28,IP-21 | 任务分解 | 数据(轻) | 步骤分 + 长程 | 继承 |
| IP-24 | FAILURE-MONITOR | 可观测状态失败预警 + 触发恢复（含恢复 LoRA） | P1 | IP-21,IP-29 | 泛化监控×安全 | 算力(轻) | 鲁棒性/可信度 | 继承 |
| IP-25 | LATENCY-SLO | 推理时延 SLO + 少步动作头 + QAT + N 端口并发 + 动作平滑 | P0 | IP-4,A11 | 接口工程 | 算力(部署机) | 掉请求→0、可信度 | 继承 |
| IP-26 | GENERALIZE-SUITE | 位置/干扰/背景/未见物/人为干扰五轴增广与评测 | P1 | IP-2,IP-3 | 泛化能力 | 数据(近零) | 全场景 | 继承 |
| **IP-27** | **QUAD-PRIOR** | 跨形态(body-agnostic)表征/世界模型先验（**不做运动控制**） | P2 | IP-22 | **四足机器人** | 算力(低) | 未见物泛化 | **新增(部分)** |
| IP-2 | SCORE-ALIGN v5 | 对齐 32 任务得分点与步骤分（喂给 IP-28） | P0 | 无 | 评测指标 | 数据(近零) | 步骤分 | 继承 |
| IP-3 | LOCAL-EVAL | `run_server/run_client` 本地闭环 + 回放复现 | P0 | IP-2,A13 | 评测基准 | 算力(1 GPU) | 迭代速度=生命线 | 继承 |
| IP-4 | SUBMISSION-OPS v3 | 多端口（Approach1/2）+ 单元状态隔离 + 版本回滚 | P0 | 无 | 接口工程 | 算力(部署机) | 掉请求→0 | 继承 |
| IP-8 | STEP-EFF | 少步/早停/平滑 | — | — | 步骤分 | — | — | **合并入 IP-28/IP-25** |
| IP-9 | SWARM-DECODE | 集成/自洽投票 + 蒸馏到单模型 | P1 | IP-2 | 泛化能力 | 算力(一次性) | 全场景 +2~5pt | 继承 |
| IP-10 | COST-LADDER | 三账户记账（训练/服务/工程） | P0(纪律) | 无 | 成本控制 | 全账户 | 防负 ROI | 继承 |
| IP-1 | SLAM-MAP | 桌面任务无 SLAM | — | — | SLAM | — | — | 退役 |
| IP-11/13/16/17/18/19/20 | 社交/力觉/触觉/对话 | 接口不可达 | — | — | — | — | — | 退役（原因见 v10） |

## 3. 重点展开

### 3.1 IP-29 LoRA-EXPERT-BANK（灵感：LoRA）

**动机**：赛道要求"单模型完成全部 32 任务"，但技能高度异构（倒水/插拔/折叠可变形/堆叠/分拣/装包）。全参微调既贵又易灾难性遗忘；**参数高效专家化**是合规的折中。

**设计**：
- 共享冻结 VLM backbone；挂 **K 个能力型 LoRA**（建议 K≈6：`pour`、`insert/plug`、`deformable-fold`、`stack`、`sort/organize`、`pack/container`），可自动聚类确定。
- **路由器** `g(language, first-frame CLS) → w∈Δ^{K}`：低频决策（每 episode 一次，必要时每 `K_plan` 步复核）；支持 top-1 或加权 soft-merge（`Σ w_k ΔW_k`）。
- **恢复 LoRA** `ΔW_rec`：由 IP-24 触发时叠加，训练自"语义干预"式纠错数据（对标 OopsieRecover 2611.08462）。
- **合并/任务算术**：对未见任务，尝试 `ΔW_a ⊕ ΔW_b` 组合以增强 OOV 泛化；路由熵高（不确定）时**回退纯基座**。
- **与多端口协同**：Approach 2 下共享基座 + 逐端口 LoRA/状态 → 省 N 份显存。

**与现有方案差异**：v10 只有"单 LoRA 微调 VLM"；本项把"模型容量"问题转为"**路由 + 专家组合**"问题，并显式引入恢复专家。

**可行性/资源**：训练一次性（LoRA 参数量小，~2–4 GPU·周内）；推理每步仅激活 ≤2 个 LoRA。数据用现成 32 任务库。风险：路由错误→跨任务干扰。

**落地步骤**：① 技能聚类定 K；② 训练基座 + 全专家 LoRA（多任务）；③ 训练路由器（load-balance + descent-aligned routing 2610.00493）；④ 恢复 LoRA；⑤ 消融 E36。

```python
class LoRABank(nn.Module):
    def __init__(self, backbone, K, rank):
        self.base = freeze(backbone)
        self.experts = nn.ModuleList([LoRA(rank) for _ in range(K)])
        self.recovery = LoRA(rank)
        self.router = Router(in_dim=backbone.cls_dim + lang_dim, K=K)
    def forward(self, x, lang, fail_flag=False):
        w = softmax(self.router(cls(x), lang))          # 低频
        if w.max() < TAU:  return self.base(x)          # 不确定→纯基座
        dW = sum(w[k]*self.experts[k].delta() for k in topk(w))
        if fail_flag: dW = dW + LAM_REC * self.recovery.delta()
        return self.base(x, lora_delta=dW)
```

### 3.2 IP-28 PROGRESS-CRITIC（灵感：步骤分）

**动机**：排名=成功率+**步骤分**。若步骤分是"按 rubric 子步骤的部分分"，则**部分完成也值钱**；且稠密进度信号能治长程任务（OrganizeBookshelf、PackBag、FoldTowel）。

**设计（rubric 无关，自监督）**：
- 由示范生成弱标签 `p̂_t∈[0,1]` 与步索引：夹爪开合事件（`gripper` 0↔4.5 跳变）+ 腕部运动基元变点（速度/曲率）+ 物体位移/光流变点 → change-point 对齐 → 单调化。
- 训练 **进度头** `p_t`、**步头**、**卡住头**（`Δp` 窗口内 < ε）。
- 三处使用：(a) 训练期稠密损失 `L_prog` 与 `z_t`(IP-23) 进度条件化；(b) 运行期卡住 → 重试/重规划；(c) **部分分最大化降级**：IP-24 预测任务不可挽回时，切换到"完成当前 rubric 步"的保守策略（而非直接放弃）。
- **省步**：进度门控早停；对示范按"步数/成功率"重加权，偏好干净快例（吸收 IP-8）。

**与现有方案差异**：v10 的 IP-23 依赖"得分点 rubric 文本"（不可得）；本项**不依赖 rubric 文本**，用示范结构自监督，可离线证伪，并用同一信号同时服务**训练、重试、降级**。

**可行性/资源**：数据侧近零额外标注；一个轻量头。风险：自监督分段噪声；降级策略可能过早放弃。缓解：E37 用"截断 episode 的部分分"验证；阈值保守。

```python
def train_progress(demos):
    for ep in demos:
        p_hat = monotonic_pseudo_progress(ep)         # change-point 融合
        p_t   = progress_head(ep.feats)
        loss_prog = mse(p_t, p_hat) + mse(diff(p_t), clipped(diff(p_hat)))
    return progress_head
def act(obs, state):
    p  = progress_head(feat(obs))
    if stuck(p, state.window):  state.mode = "retry_or_replan"
    if failure_monitor(obs) > TAU_FAIL:               # IP-24
        state.mode = "partial_credit" if p < P_DONE else "recover"
    return policy(obs, mode=state.mode)
```

### 3.3 IP-27 QUAD-PRIOR（灵感：四足机器人，诚实部分保留）

**现实校准**：平台是双足 G1，且 F31 证明**定基座**——运动/步态/落脚控制**零需求**。因此本项**不做**任何底盘/步态控制器，只保留两处合法落点：
1. **跨形态表征/世界模型先验**：用 body-agnostic 表征（对标 Cross-Embodiment Motion Planning 2610.41330；AIRoA-0 跨形态 2611.03815）与四足机群成熟的 sim-to-real/域随机化配方，预训练视觉/本体编码器，目标是**未见物/背景泛化**（实质是 IP-22/IP-26 的补强）。
2. **低维命令式基座抽象 → `pivot` 微稳定器（P2，仅边界裁剪）**：按 F31 直接冻结 `pivot` 常值，仅允许 `height`/`angle_z` 在观测区间内微调（`clip`），并作遥测。

**差异**：明确**反向**于直觉——四足之所以有用不在"腿"，而在"**跨形态表征 + 域随机化**"这套**方法论**。

**风险**：跨形态数据/权重的可得性与许可未确认 → 若不可得，本项可**整条关闭**，无负收益（降级机制）。

### 3.4 与 IP-21 的整合（v11 架构）

```
输入: 4×RGB ─┐
     本体(arms/ee/grip/lower_body) ┤→ TRI-FUSE (IP-22, 可选 + QUAD-PRIOR 预训练)
     语言指令 ────────────────────┘
              │
   System-2 = VLM backbone + LoRA-EXPERT-BANK (IP-29) → 子目标 z_t (IP-23)
              │                         ▲
              │                  PROGRESS-CRITIC (IP-28): p_t, 步头, 卡住头
              ▼
   System-1 = 少步流匹配动作头（joint/ee 双表示）→ 动作块 T_a×(双臂+夹爪)
              │        + pivot 冻结头（IP-27，仅微调 height/angle_z，clip）
              ▼
   FAILURE-MONITOR (IP-24) → 触发 恢复 LoRA / 重试 / 部分分最大化降级
              │
   LATENCY-SLO (IP-25): 少步 + QAT + 平滑/限幅 + N 端口并发
```

### 3.5 训练/服务伪代码（增量）

```python
def build_v11():
    base = load_pretrained_vlm()
    fuse = TriFuseEncoder(...)                       # IP-22
    bank = LoRABank(base, K=6, rank=LORA_R)          # IP-29
    system2 = SubgoalPlanner(bank)                   # IP-23
    system1 = FlowActionExpert(steps=4, chunk=T_a, dual=("joint","ee"))
    prog = ProgressHead()                            # IP-28
    pivot_head = FrozenPivotHead(mean=task_pivot)    # IP-27 (clip only)
    for batch in D:                                  # D 已按 A9 统一 schema
        f = fuse(batch.images, batch.proprio, batch.lang)
        z = system2(f, batch.lang)                   # 路由器低频选专家
        a = system1.sample_train(f, batch.proprio, z, batch.action)
        loss = flow_loss(a, batch.action) \
             + LAM_PROG * prog_loss(prog(f), batch.pseudo_progress) \
             + LAM_CONS * consistency(system1.joint, system1.ee) \
             + LAM_ROUT * router_lb(bank)                       # 负载均衡
        update(bank.experts, bank.router, fuse, system2, system1, prog, loss)
    bank.recovery = train_recovery_loras(bank, semantic_interventions(D))
    return fuse, bank, system2, system1, prog, pivot_head
```

## 4. 实验设计（新增 E36–E39）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E36 LoRA 专家银行 | 单 LoRA vs K 专家；top-1 vs top-k；有无恢复 LoRA | 32 任务成功率、路由准确、显存 | 专家银行 ≥ 单 LoRA；显存下降 |
| E37 进度-步骤分 | 截断 episode 的"部分分"；卡住检测 AUROC | 部分分、卡住 AUROC、长程成功率 | AUROC ≥ 0.85；部分分↑ |
| E38 跨形态表征 | 有无 body-agnostic 预训练的未见物成功率 | OOD 未见物成功率 | OOD↑（若数据不可得则关闭） |
| E39 pivot 消融 | 冻结常数 vs 预测微调 vs 完全放开 | 成功率、pivot 离群、可信度 | 冻结≈预测；完全放开有风险（验证 F31） |
| E30–E35 | 沿用（数据统一/闭环/泛化/时延/失败预警/消融） | — | — |

**降级机制**：A15 rubric 不可得 → IP-28 仅用自监督 + 保守阈值；LoRA 路由不稳 → 退化为单全域 LoRA；跨形态数据不可得 → 关闭 IP-27；进度头不过 → 仅遥测不介入降级；pivot 放开有风险 → 回冻结常值。

## 5. 风险登记簿（新增/更新）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **步骤分口径未核实（A15）→ IP-28 目标错配** | **高** | A15 拿手册；IP-28 设计为 rubric 无关 + 保守阈值；E37 离线证伪 |
| **LoRA 路由错误 → 跨任务干扰** | 中高 | 软合并 + 路由熵高回退基座 + load-balance + E36 |
| 灵感错配：误投"运动控制"（F31 已否定） | 中高 | IP-27 明确不做运动控制；只保留表征先验；E39 验证 |
| 自监督进度标签噪声 | 中 | 多线索变点融合 + 单调化 + E37 |
| 定基座假设不普适（个别任务需动基座） | 中 | A14 全 32 任务扫描；pivot 头保留小范围微调 |
| 跨形态数据/许可不明 | 中低 | IP-27 可整体关闭，无负收益 |
| 恢复 LoRA 引入异常动作（伤可信度） | 中低 | 动作包络约束 + 只增不减 + 平滑（IP-25） |
| （沿用 v10 高/中风险）相机映射错位、时延异常、算力、多端口隔离等 | 高/中 | 见 v10 §6 |

## 6. 来源清单（引用口径：2026-11-08）

**官方/数据（一手）**
- S1 挑战赛官网 `https://unibot.unitree.com`（首页/challenges/leaderboard，2026-11-08 抓取）——静态占位页，榜单未上线。
- S2 提交模板 `https://github.com/unitreerobotics/unibot_submission`（README.md、README.zh.md、example/*、policy/*、requirements.txt，2026-11-08 抓取）——接口契约、控制空间、多端口、可信度指标（§6）。
- S3 数据集 collection `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset`（32 仓，2026-11-08 直取）；单任务仓 `unitreerobotics/G1_Dex1_HangCup` 等 `meta/info.json` + `meta/stats.json`（含 `pivot`/`base_command`/夹爪分布）。仓 `gated:false`。
- S4 参赛手册（feishu `...Uz7OdFBcDoqP1dxgH62cHW1CnMh`）——**Login Required，未获取**。

**文献（arXiv API 实时检索，2026-11-08；标题+编号）**
- R52 Failure Prediction and Classification in VLA via Calibrated Latent Probing, arXiv:2611.08425。
- R53 OopsieRecover: Learning Transferable VLA Corrections from Semantic Interventions, arXiv:2611.08462。
- R54 Cross-Embodiment Motion Planning by Coupling Body-Agnostic World Model with Differentiable Ego-Dynamics, arXiv:2610.41330。
- R55 AIRoA-0: Long-Horizon, Precise, Cross-Embodiment Manipulation from Handheld Data, arXiv:2611.03815。
- R56 Score the Update, Not the Token: Descent-Aligned Routing for Combinatorial LoRA Experts, arXiv:2610.00493。
- R57 Uncertainty Is Not Enough: Value-of-Information Routing for Mixtures of LoRA Experts, arXiv:2608.02528。
- R58 Two-Stage Mixture-of-LoRA for Multi-Task Medical Vision-Language Learning, arXiv:2609.14350。
- R59 Macaron-V1: Towards Open Continual Learning with Self-Improvement and Mixture-of-LoRA, arXiv:2608.09819。
- R60 HAF-VLA: Hierarchical Action Flow Framework for Humanoid Vision-Language-Action Control, arXiv:2610.26584。
- R61 HITCH: Teaching a Vision-Language Model to Operate a Humanoid through a Whole-Body Harness, arXiv:2611.08039。
- R62 MAST-VLA: Skill-Conditioned Adaptation with Trajectory-Affordance Priors for Multi-Skill Robots, arXiv:2610.32312。
- R63 La-JEPA: Compact Robot Policies with Latent World Modeling, arXiv:2611.08156。
- R64 From Teleoperation to Long-Horizon Dexterity: Evaluating Visuomotor Skills and Offline Proxies, arXiv:2610.40828。
- （R41–R51 沿用 v10：GR00T N1 2503.14734、GR00T N1.7 2609.18108、G0.5 2608.11739、Concertina 2611.07513、DSWAM 2607.04927、Beyond Flat Policies 2608.05999、HAF 2608.16837、CoEvolve 2610.23288、OpenVLA 失败探针 2606.29699、推理时延/量化 2611.06710 & 2611.05093、EyeRobot 2.0 2610.03710。）

**诚实记录**：S1 榜单与 S4 手册均不可得；"榜首<30%""5 类泛化""步骤分=rubric 部分分"为**待验假设**；R52–R64 仅为 arXiv API 检索所得标题/编号，未逐篇读全文。

## 7. 清单迭代规则（继承 + 第 34 轮增补）

- 继承规则 27（通道诚实）、28（映射验证纪律）、29（时延-可信度 SLO）、30（失败预警 fail-safe）。
- **31（新增）：灵感-现实校验**——任何由灵感词引入的路线，先用**官方数据/接口**证伪其前提（如本轮用 F31 证伪"运动控制"需求）；前提不成立的分量**降级或退役**，并登记证据。
- **32（新增）：单模型合规的专家化**——多任务只能以"共享基座 + 参数高效专家 + 低频路由"实现，禁止"每任务一份完整模型"绕过"通才赛道"规则。
- **33（新增）：步骤分双解释登记**——涉及"步骤分"的设计须同时登记 A（rubric 部分分）与 B（每步交互质量）两种解释，并在 A15 前按更保守者(P0)实现。
- **34（新增）：稠密监督不依赖 rubric**——训练期进度/子步骤监督优先取自示范自监督结构；rubric 文本仅作可选增强，不得成为主链单点依赖。

**本轮最大风险一句话**：事实 D 把"四足=运动控制"的直觉清零，最大的可执行风险转为 **IP-28 步骤分口径未核实**与 **IP-29 路由错误导致跨任务干扰**；二者必须先经 IP-3 本地闭环小规模消融证伪，再上真机。

**当前最值得押注**：把 UNIBOT-RFM 的 System-2 改为**语言路由的 LoRA 能力专家银行（IP-29）**，并以**自监督进度/子步骤估计（IP-28）**同时驱动稠密训练、卡住重试与"部分分最大化"降级；"四足"仅保留为跨形态表征先验（IP-27，P2）。
<!-- ARTIFACT:END -->
