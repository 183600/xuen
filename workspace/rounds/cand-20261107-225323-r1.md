# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮 · UniBot-V1 通才操作挑战：从「LoRA-SFT 通才」到「闭环进展最大化」

> 本轮为针对「宇树 UniBot 世界挑战赛」（unibot.unitree.com）的新研究循环第 1 轮（灵感词：**UniBot-V1 / 泛化能力 / 场景理解**），整体覆盖前序循环内容（前序第 30 轮 SERVO-ADAPT-LITE 属另一赛题语境，其"分层评测/回退链"方法论局部复用）。全部赛事事实经联网核实，来源与检索日期见产物区第 9 节。

## 0. 直觉锚点与动机链条（三个灵感词各自命中什么）

- **「UniBot-V1」→ 约束即杠杆**。逐条读提交接口（github.com/unitreerobotics/unibot_submission，2026-11-07 核实，2 commits），别人当"麻烦"的地方恰是差异化杠杆：(a) `action_chunk_size` 是 metadata 静态申报 → chunk 长度选择本身是一个延迟-抗干扰的帕累托决策；(b) `obs_delta_indices` 自选观测键与帧偏移 → 历史堆叠免费提供速度/一致性线索；(c) `action.pivot[7]`（vx,vy,angle_z,…,height）共享动作通道暴露了全身控制，但 SFT 微调惯例是置零 → 全身工作空间被白送、又被白丢；(d) README §6 明确"逐步响应延迟与波动、动作统计规律会被记录并可能随结果公布" → **推理工程是计分项**，不是工程杂务。
- **「泛化能力」→ 5 类泛化 ≠ 1 种泛化**。位置/背景/干扰物是纯视觉 OOD（增强可解）；未见物品是语义 OOD（VLM backbone 原生可解）；人为干扰是时序 OOD（闭环可解）。三种病因三种药——而均值回归的行为克隆 SFT 一味药都治不了：它在训练分布上插值，而泛化评测考的就是分布外。
- **「场景理解」→ 几何先于语义**。32 任务数据集里接触丰富/插孔类任务密集：PlugCharger（插充电器）、PlugInEthernet（插网线）、SyringeWaterTransfer（注射器）、ZipUp（拉拉链）、RemovePinnedNote（拔图钉）、Unlock——这类任务成败在毫米级对准，VLA 的 8~10Hz 动作块均值化输出对它结构性无能。关键事实（F7）：**评测接口只发 RGB 四路（无深度），而训练数据含已校正立体相机对** → 单目深度蒸馏是"从数据白捡的几何"，末段视觉伺服是"从几何白捡的成功率"。

## 1. 赛事事实卡（2026-11-07 检索，详细引用见产物区）

- F1 官网：32 项真实桌面任务（抓取/放置/双手协调）、32,000 episodes、169 小时；评分=平均成功率+步骤分（每任务得分点满分 100）。
- F2 泛化评测：官网愿景明示"跨任务、跨物品、抗干扰"；5 类泛化（位置/干扰物/背景/未见物品/人为干扰）为用户提供先验，与官网口径一致（规则全文在飞书、需登录，未能核实原文——诚实标注）。
- F3 接口：PolicyService(websockets+msgpack)；metadata{control_space: joint|ee 互斥、obs_delta_indices、image_resize、action_chunk_size、token}；观测=4×RGB(480×640)+双臂 7-DoF+EE pose(base)+夹爪+lower_body[15]+language；动作=joint(双臂 14)或 ee(EE 6+6)+共享{双夹爪、pivot[7]}；token 双检（握手+每步）。
- F4 部署：N 台评测机器人→N 个连续端口 8765..8765+N−1（端口数必须精确匹配）；模式 A 每端口独立实例（N 份显存），模式 B 共享后端+并发调度+状态隔离。
- F5 可信度考核：延迟稳定性与动作统计规律被记录，可能随成绩公布。
- F6 数据集（HF collection，32 items，LeRobot v3.0，AV1 480×640@30fps，apache-2.0，非 gated）：32 任务名已全部列获；每任务约 0.97k–1.53k episodes（HangCup train=194,564 帧）。
- F7 数据字段 > 接口字段：数据含 head_stereo_left/right（**已校正**立体对）、torso/d435 位姿、action_torso/action_d435/base_command；评测接口只发 RGB——**数据可训深度、接口不可传深度**。
- F8 头部方案唯一可证样本：ezhoureal/lingbot-vla-v2-unibot-lora——LingBot-VLA 2.0（Qwen3-VL-4B-Instruct + Qwen2 action expert + MoE，6.3B），LoRA r64 于 q/v/o_proj（65M 可训练），全量 32 任务 33,276 episodes，10K steps，**单卡 RTX 4090**，val/loss 0.085，joint 空间、arm=state-relative delta。
- F9 生态：LingBot-VLA（arXiv:2601.18692，20k 小时真机预训练，含 Depth 版本、RoboTwin 后训练、RLinf RL 支持）；宇树自家 UnifoLM-VLA / UnifoLM-WMA-0（gated 世界模型）/ UnifoLM-WLA-1.0 / UnifoLM-ER-1。
- F10 排行榜：官网 leaderboard/runs 均"即将发布"（2026-11-07）；**"榜首成功率 <30%"为用户先验**（榜单未公开、无法直接核实），但与 F8"loss 极低 vs 真机操作成功率"的公开证据链方向一致——按"弱证据、高置信"采用，榜单公开后复核。

## 2. 头部方案画像与六个结构性瓶颈

以可证样本（F8）代表当前主流打法——「开源 VLA + 全量数据 LoRA-SFT + 单卡训练 + 接口直连」：

- **B1 损失-成功鸿沟**：SFT val/loss 0.085 ≠ 真机成功。行为克隆的复合误差在接触丰富任务上爆炸：8Hz 动作块是对连续伺服行为的低频均值采样。
- **B2 深度缺失**：RGB-only 接口 + image_resize 下采样进一步抹掉精细视觉特征；插孔对准缺乏几何信息。
- **B3 全身闲置**：pivot/腰/底盘通道被丢弃 → 工作空间受限 → 远处/低处物品任务直接失格，而这恰是"位置泛化"的部分来源（数据集里下肢+腰的移动就是位置多样性）。
- **B4 块内开环**：T_a 步内无感知修正；人为干扰/干扰物场景的响应滞后上限=整个 chunk。
- **B5 任务互扰**：单模型 32 任务参数共享，精细任务（低数据权重、高精度需求）的梯度被淹没；而榜单按平均成功率排序——**短板任务决定名次**。
- **B6 步骤分无人优化**：所有注意力在终点成功率；得分点是"进展分"——失败 episode 也有分可拿，"把 EE 挪近目标、摆对姿态"本身就是期望得分。

## 3. 策略主线：三条护城河 + 两块地基

- **M1 进展最大化**（打 B6/B1）：从数据集 episode 自动挖掘"得分点阶段结构"，训练轻量进展模型；推理时用于 best-of-n 动作块选择与失败保底。
- **M2 几何场景理解**（打 B1/B2）：立体对蒸馏单目深度头（策略内部前向，零接口改动）+ ee 空间末段伺服残差修正。
- **M3 时序闭环**（打 B4）：T_a 帕累托申报 + 块间偏差检测与恢复策略编译进块内。
- **D1 服务工程地基**（F4/F5）：共享后端、量化、延迟稳定性预算——资格性优先级。
- **D2 本地评测地基**：步骤分代理 + 5 类泛化变换库——迭代速度即生命线。

## 4. 设计决断（诚实版）

- **单模型合规边界**：所有创新点落在"单权重+内部模块+语言条件化"，不做外部多模型路由（规则细则未读到，保守处理）；内部混哪个模块不改变"单模型"语义。
- **接口红线**：不新增 obs 键、不改评测方任何行为——深度/几何特征全部在 get_action 内部计算；所有增强层可独立开关（ablation 全保留），关闭即回退基线，无负收益。
- **pivot 通道**：仅在"手臂工作空间外"门控下启用，低速小步+夹紧，避免躯干运动引发视觉外参漂移这一新失败模式。
- **合规红线**：进展模型只用于优化我们自己的期望动作选择，得分手仍由评测方计算——不做任何评测操纵。
- **修正记录**：初版设想"动态 chunk（运行中缩短块长）"与接口 metadata 静态申报 `action_chunk_size` 冲突（评测器按申报形状执行），已在本轮修剪为「T_a 申报扫描 + 块间恢复」——清单迭代原则的第一次自我执行。

## 5. 本轮最大风险一句话

**新增策略内前向（深度头、进展模型、修正器）吃掉延迟稳定性预算（F5 可信度考核）**，且评测端 480×640（可能 resize）输入与训练分布存在偏移——必须以"小模型+量化+固定毫秒预算"落地，每项增强独立可关，E1–E5 本地验证通过后方可合并，任一不过即回退基线，无负收益。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 1 轮产物 · UniBot-V1 创新点清单 v1：闭环进展最大化参赛方案

## 0. 结论

新建清单 10 项（IP-1…IP-10），围绕「三条护城河 + 两块地基」：

- **默认 backbone**：LingBot-VLA 2.0 (6.3B) LoRA——唯一经证据链核实的参赛打法（F8），先复现再超越。
- **P0（资格与生命线）**：IP-8 服务工程、IP-9 本地评测自举、IP-4 泛化增强管线。
- **P1（得分主力）**：IP-2 GEOSERVE（深度蒸馏+末段伺服）、IP-5 块间闭环恢复、IP-1 PROGRESS（进展模型）、IP-6 语言条件化路由、IP-10 失败恢复库。
- **P2（差异化期权）**：IP-3 全身 pivot 激活、IP-7 RL 后训练。
- 成本：LoRA 基线复现 1×RTX 4090 可行（F8 佐证）；全部策略内前向预算 ≤25ms/步；无任何接口变更。
- 修剪记录：初版"动态 chunk"与接口静态申报冲突，已修剪为 IP-5「T_a 扫描 + 块间恢复」（想法区 §4）。

## 1. 创新点清单 v1 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 资源 | 预期边际 | 风险 |
|---|---|---|---|---|---|---|---|---|
| IP-8 | SERVE-N | N 端口共享后端+并发调度+量化+延迟稳定性预算 | **P0** | 无 | UniBot-V1 | 1×A100/2×4090 | 可信度口径不掉分、资格保障 | 低 |
| IP-9 | LOCAL-BENCH | 步骤分代理+5 类泛化变换库+任务难度谱系 | **P0** | IP-1(弱) | UniBot-V1/泛化 | 1 GPU+人工抽检 | 迭代速度=生命线 | 中 |
| IP-4 | AUG-PANO | 视频级增强×3 病因（视觉 OOD/语义 OOD/EE 重定向） | **P0** | 无 | 泛化能力 | ~0.5 GPU·天 | 3/5 泛化类直接受益 | 中 |
| IP-2 | GEOSERVE | 立体对蒸馏深度头+ee 末段伺服残差修正 | **P1** | IP-9 | 场景理解 | ~1 GPU·天 | 插孔类任务（≥5 个）成功率主攻 | 中高 |
| IP-5 | CHUNK-RESCUE | T_a 帕累托申报+块间偏差检测+恢复编译进块 | **P1** | IP-1,IP-9 | UniBot-V1/泛化 | 近零 | 人为干扰/干扰物类受益 | 中 |
| IP-1 | PROGRESS | 自动挖掘得分点阶段→轻量进展模型→best-of-n | **P1** | IP-9 | UniBot-V1 | ~0.3 GPU·天 | 步骤分+失败保底 | 中 |
| IP-6 | ROUTE-LANG | 指令→32 任务原型软路由（单权重内部 MoE） | **P1** | IP-4 | 泛化能力/场景理解 | 近零 | 未见物品+任务互扰缓解 | 低 |
| IP-10 | RESCUE-LIB | 数据集重试片段挖掘+卡住检测+恢复库 | **P1** | IP-1,IP-5 | 泛化能力 | 近零 | 平均成功率短板修复 | 低 |
| IP-3 | PIVOT-GATE | 全身 pivot 门控激活（工作空间外低速步进） | P2 | IP-9 | UniBot-V1 | 近零 | 远/低处任务解锁 | 中高 |
| IP-7 | RL-PROG | 进展奖励的 RL/DPO 后训练（RoboTwin/WMA-0） | P2 | IP-1,IP-9 | UniBot-V1/泛化 | 4–8 GPU·天 | SFT→RL 第二级增益 | 高 |

## 2. 重点展开 A：IP-2 GEOSERVE（深度蒸馏 + 末段伺服，攻插孔类任务）

### 2.1 动机与差异
- 动机：32 任务中 PlugCharger/PlugInEthernet/SyringeWaterTransfer/ZipUp/RemovePinnedNote/Unlock 为接触丰富任务；行为克隆在毫米级对准上复合误差爆炸（B1）+ RGB 无深度（B2）。这两条决定平均成功率的下限。
- 与现有方案差异：可证头部方案（F8）直接 LoRA 微调 RGB 策略，无任何几何中间表示；本方案用**数据集自带已校正立体对**（F7）生成深度伪标签蒸馏单目深度头，全部在策略内部前向——接口零改动。

### 2.2 训练管线（离线 ~1 GPU·天）
```python
# 步骤 1：立体→深度伪标签（head_stereo 已 rectified，F7）
for seq in unibot_32tasks():                       # LeRobot v3.0 parquet + AV1 视频
    D_head = stereo_depth(L, R, method="RAFT-Stereo+SGBM 融合")   # 校正对→稠密深度
# 步骤 2：腕部深度自举（腕相机无立体对）
#   head 深度 + 数据集外参链（state_d435 / torso / base 位姿）→ 投影到腕视锥
#   有效位（recomputed_ee_valid=1 且遮挡率<阈值）入训练集  [开放问题 F-O1：外参待核实]
# 步骤 3：单目深度头蒸馏
depth_head = finetune(DepthAnything-V2-S, src=wrist_rgb+head_rgb, tgt=pseudo_depth)
# 步骤 4：末段伺服残差修正器（ee 控制空间）
#   样本：每 episode 末段 10 步；标签：Δee* = ee_{t+1} − ee_t（数据真值）
#   输入：(wrist_rgb, D_wrist, ee_pose, gripper)；输出：Δee 修正
refine = train_residual_head(policy_features, Δee*, focus="对准段", loss=Huber)
```

### 2.3 推理（get_action 内部，预算 ≤25ms）
```python
def get_action(obs):
    D   = depth_head(obs["wrist"], obs["head"])        # ~12ms（256×320 + 量化）
    a   = vla.forward(obs, depth_feat=D)               # 基线 VLA（LoRA 后）
    a_ee = refine(a_ee, obs["wrist"], D, ee_state)     # ~6ms，仅对准段激活（进展模型门控）
    return format(a, T_a, token)                       # 逐位可关：refine=None → 基线
```

### 2.4 风险
- 深度头在评测端光照/背景 OOD 下伪标签域差 → 增强（IP-4）同步作用于深度训练集；
- 外参链不确定（F-O1）→ 腕部自举失败则降级为"仅 head 深度特征条件化"（仍可关）；
- 延迟 → depth 头 INT8 + 每 k 步复用。

## 3. 重点展开 B：IP-5 CHUNK-RESCUE（块间闭环，攻人为干扰/干扰物）

### 3.1 设计（接口内合法）
- **T_a 帕累托申报**：扫描 T_a∈{4,8,16}，权衡 [网络往返延迟方差（F5 可信度）] × [块内开环时长（抗干扰）]；E4 决定。
- **块间偏差检测**：obs_delta_indices 申报 proprio 历史堆叠（如 [-3,-2,-1,0]），每次调用计算执行偏差 e_t = ‖s_obs − s_pred(上一块)‖ + 视觉流残差 → 干扰信号（κ-free）。
- **恢复编译进块**：检测到偏差/干扰 → 本块前 2 步注入"减速+重瞄"动作模式（从 IP-10 恢复库检索），后 T_a−2 步交 VLA 正常输出；恢复行为编译在返回的动作块内——**不依赖评测器任何配合**。

### 3.2 与现有差异
F8 方案把 get_action 当纯函数；本方案把每次调用视为"块间闭环点"——所有可感知状态（历史堆叠是免费的）都用于下一块的条件化。人为干扰类评测的本质是"执行中被推一把后能不能回来"。

## 4. 重点展开 C：IP-1 PROGRESS（进展模型，攻步骤分与失败保底）

- **阶段自动挖掘**：每任务 1000 集（F6），用 EE-目标距离曲线拐点 + 进度分位自动切分 ~5 阶段（接近/对准/抓取/搬运/放置），VLM 零样本抽检 50 帧校准（人工预算极小）。
- **进展模型**：P_φ(阶段, s_t, task) —— 轻量（ViT-S + 状态 MLP），输出"进展期望"。
- **用途**：(a) best-of-n：VLA（扩散/流动作头）采样 n=4 块，按 P_φ 期望选块；(b) 失败保底：进展持续不涨 → 触发 IP-10 恢复；(c) IP-9 得分点代理与 IP-7 RL 奖励共用同一 P_φ（一份投入三处回收）。
- 合规：得分手仍由评测方计算，P_φ 只优化我方动作选择。

## 5. 其余创新点简表

| 编号 | 动机 | 与现有差异 | 落地步骤 | 主要风险 |
|---|---|---|---|---|
| IP-8 SERVE-N | F4：N 端口必须精确匹配；F5：延迟稳定性入可信度 | F8 类方案多为单实例思维 | 共享后端（权重共享+连续批处理+CUDA Graph）、W8A8 量化、per-port 状态隔离（reset/KV 隔离）、延迟遥测 | 并发阻塞→延迟方差；吞吐压测 E0 |
| IP-9 LOCAL-BENCH | 迭代速度=生命线；本地无真机 | 现有方案依赖线上预约评测（高摩擦） | 步骤分代理（P_φ 复用）+5 类泛化变换库（颜色/背景/干扰物 inpainting/贴图替换/合成手部遮挡）+32 任务难度谱系表 | 本地是视觉层代理，物理泛化不可代理——仅作回归信号非上线门槛 |
| IP-4 AUG-PANO | 5 类泛化中 3 类是视觉 OOD（B 系） | F8 方案原样用数据 | 帧级颜色/剪切/模糊；SAM2+inpainting 干扰物注入；EE 相对坐标重定向（位置泛化，ee 空间下可行性高）；指令同义改写；贴图替换（未见物品） | 增强过强→特征漂移；消融定档 |
| IP-6 ROUTE-LANG | 32 任务互扰（B5）+未见物品 | F8 单一 LoRA 全任务混训 | 指令嵌入→任务原型库（task_index）→内部软门控（单权重）；未见物品走 VLM 原生语义 | 门控塌缩到高频任务；熵正则 |
| IP-10 RESCUE-LIB | 失败 episode 也有步骤分；重试行为已在数据中 | SFT 只学成功段 | 挖掘"速度翻转+重接近"重试片段→卡住检测（P_φ 不涨+proprio 振荡）→恢复库（退-重瞄-再进；插孔 wiggle） | 恢复行为误触发→抖振；滞回门限 |
| IP-3 PIVOT-GATE | pivot[7] 白送工作空间（B3） | SFT 惯例置零 | 先统计 32 任务数据 pivot/腰使用率（数据驱动立项）；门控：目标在工作空间外→低速小步 pivot；外参漂移监测 | 躯干运动引入视觉漂移新失败模式；P2 谨慎 |
| IP-7 RL-PROG | SFT 天花板（B1）；WMA-0/RoboTwin 可用 | F8 停在 SFT | 奖励=P_φ 进展；RoboTwin(G1) 或申请 UnifoLM-WMA-0 世界模型 rollout；GRPO 在线/离线 DPO（成功-失败对比 1000 集/任务） | 算力 4–8 GPU·天；sim-real 差距；P2 期权 |

## 6. 实验设计（本地，接 IP-9）

| 实验 | 设置 | 指标 | 门槛 |
|---|---|---|---|
| E0 吞吐与延迟 | 3 端口并发 × 满载请求 | P99 延迟与抖动、吞吐 | 抖动 <10ms；无互阻塞 |
| E1 基线复现 | LingBot-VLA LoRA 于 HangCup+PlugCharger 小规模 | 本地代理成功率、loss 曲线 | 对齐 F8 量级（val/loss≈0.09） |
| E2 增强消融 | AUG 各轴 on/off × 本地 OOD 集 | 各泛化类代理成功率 | 每轴不劣化、至少 2 轴显著提升 |
| E3 GEOSERVE | 插孔 5 任务，深度/修正器 on/off 消融 | 末段对准成功率、延迟增量 | 成功率提升显著；延迟 ≤25ms |
| E4 chunk 扫描 | T_a∈{4,8,16} × E0 延迟 × OOD 干扰集 | 帕累托前沿 | 选定申报值并记录理由 |
| E5 PROGRESS | P_φ vs 人工标注 50 帧/任务 | 得分点检测 AUC、best-of-n 增益 | AUC≥0.85；best-of-n 增益>0 |

降级机制：每项增强独立开关；E2–E5 任一不过 → 对应层关闭，逐位回退基线，无负收益。

## 7. 风险登记簿

| 风险 | 等级 | 缓解 |
|---|---|---|
| 策略内新增前向吃延迟稳定性预算（F5） | **高（本轮最大）** | 小模型+量化+固定预算；每层独立开关；E0/E3 门禁 |
| 榜单未公开，"榜首<30%"为用户先验（F10） | 中 | 以可证样本（F8）+公开证据链设计；榜单公开后复核画像 |
| 规则细则未读（飞书需登录）：得分点定义、泛化场景官方口径、单模型边界 | 中 | 邮件/ Discord 获取手册；保守合规边界（想法区 §4） |
| 立体深度自举的外参链不确定（F-O1） | 中 | 降级为 head 深度条件化；E3 消融 |
| 本地评测与真机物理泛化的代理鸿沟 | 中 | 本地仅回归信号；关键节点线上小规模评测 |
| 6.3B×3 端口显存/并发 | 中 | 共享后端+量化；E0 压测 |
| 增强导致特征漂移 | 低 | 强度消融定档（E2） |
| 单 LoRA 任务互扰残留 | 低 | IP-6 软路由；难度谱系加权采样 |

## 8. 开放问题（下轮优先）

- F-O1 数据集外参链（head→wrist 投影可行性）——下载样例数据实测。
- F-O2 官方手册获取：得分点定义、5 类泛化场景官方口径、N 的取值、单模型判定细则。
- F-O3 T_a 与 image_resize 的联合最优（分辨率↑精度↑延迟↑的权衡）。

## 9. 来源清单（全部检索/核实于 2026-11-07）

1. UniBot 官网首页/挑战赛/排行榜/运行记录：https://unibot.unitree.com/ （challenges.html：32 任务、32000 episodes、169 小时、得分点满分 100；leaderboard.html 与 runs.html：均"即将发布"）
2. 提交模板与接口规范：https://github.com/unitreerobotics/unibot_submission （README：§1–§6 全文核实；obs/action 目录、metadata、N 端口、可信度考核）
3. 数据集 collection（32 items）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset ；数据结构样例 https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup （README：LeRobot v3.0、AV1 480×640@30、head_stereo 已校正、全身字段；HF API：train=194,564 帧）
4. 参赛方案可证样本：https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora （模型卡：LingBot-VLA 2.0 6.3B、LoRA r64/65M、32 任务 33,276 episodes、10K steps、单卡 RTX 4090、val/loss 0.085、joint 空间）
5. LingBot-VLA：https://huggingface.co/robbyant/lingbot-vla-4b （README：arXiv:2601.18692，20k 小时真机数据、9 种双臂构型、Depth 变体）
6. 宇树生态模型：https://huggingface.co/unitreerobotics （UnifoLM-WMA-0-Base/Dual 为 gated；UnifoLM-VLA/WLA/ER 系列，HF API 核实）
7. 规则文档（未能抓取，需登录）：https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh （中）/ https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh （英）——诚实记录：仅获 JS 壳，内容未核实
8. "榜首成功率<30%"：用户提供先验；官网榜单未公开无法直接核实（F10，弱证据高置信采用）

## 10. 清单迭代规则（第 1 轮设定）

1. 每项创新点必含：动机/与现有差异/可行性/资源/落地步骤/风险六要素；
2. 接口红线：不新增 obs 键、不改评测方行为、所有增强独立可关（逐位回退基线）；
3. 合规红线：不做评测操纵，进展模型只优化我方期望；
4. 先证后立：头部方案画像仅基于可证样本与公开文献，推断必须标注；
5. 修剪优先：每轮先深化/修剪/修正（如本轮动态 chunk→T_a 扫描），再新增。
<!-- ARTIFACT:END -->
