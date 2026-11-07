# 第 26 轮产物 · 创新点清单 v2：SLAM-MAP 四件套 / SWARM-DECODE / COST-LADDER

## 0. 结论

第 25 轮清单 v1（8 项）本轮完成一次「深化 + 新增 + 去重」迭代，产出 v2（10 项）：

- **IP-1 升级 SEM-MAP → SLAM-MAP（P0）**：物体级语义工作区地图补齐 SLAM 四件套——在线外参估计、干扰后重定位、腕-头闭环、关键帧+协方差。每件有开源组件与文献锚点，直接对应五类泛化场景中最难的三类（位置变化/未见物品/人为干扰）。
- **IP-9 新增 SWARM-DECODE（P1）**：训练侧 LoRA population→model soup→蒸馏（合规单模型）；推理侧离散目标投票+连续动作择优的自洽解码；评测侧 N 端口拓扑的容错与赛后群体分析。
- **IP-10 新增 COST-LADDER（P0，纪律性）**：算力/数据/评测时段三账户记账，每个 IP 强制标注边际分预期；拒绝清单（不训底座、不买真机、不自采大数据）。
- 其余七项微修订（§6）；IP-6 并入 IP-1 闭环，无删除项。

路线无关原则不变：IP-2/IP-3/IP-4/IP-10 不依赖语义地图路线成立；IP-1 以可消融的附加 token 源接入，不绑死系统。

## 1. 事实卡更新（检索日期 2026-11-07）

F1-F8 与第 25 轮一致（本轮重验 F7：排行榜/运行记录页仍 Coming Soon [R1/R2]）。新增：

| # | 事实 | 来源 |
|---|---|---|
| F9 | 评测相机键 `cam_left_high/cam_right_high`（README 描述"Upper-left/Upper-right camera"）与数据集键 `head_stereo_left/right`（卡片明示 rectified）映射未确认；评测流是否立体校正未说明 | [R3][R4] |
| F10 | N 台测试机器人确切数量「由主办方另行公布」→ 部署拓扑须 N 可配置 | [R3] |
| F11 | 评测动作目录与数据集动作键一一对应：共享{left/right_gripper[1], pivot[7]} + joint{left/right_arm[7]} 或 ee{left/right_ee_pose_gripper_base[6]}；数据集 action.pivot 恰为 7 维 → 训练可直接对齐评测动作空间，无映射猜测 | [R3][R4] |
| F12 | 评测观测目录不含 state_torso / state_d435 / torso 系 ee pose / 腿部状态（腰在 lower_body[15] 内）；数据集含 state_torso[6] 与 state_d435[6] → 头部相机外参评测时不可直接读取，需自估 | [R3][R4] |
| F13 | 运行记录页承诺每条运行详情附"完整评测视频"；榜单支持按用户/模型/任务筛选 | [R2] |
| F14 | HangCup：1.04k episodes / 194,564 行 / 8.8 GB；collection 32 项更新于 2026-09-11 | [R4] |

行动项更新：A1 人工查阅飞书参赛手册（不变）；A2 注册流程（不变）；A3 榜单监控**升级**——上线后第一优先扒运行记录评测视频做逐任务×逐场景对手拆解（F13）；**A4（新增，P0）**：取得评测访问后第一时间用真实帧验证 cam_high 双路极线几何（估计 fundamental matrix，残差小=已校正立体对）；A5（新增）：邮件向主办方确认 N（F10）与"单模型"边界表述。

## 2. 创新点清单 v2 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2 | 语义地图补齐 SLAM 四件套 | P0 | 无 | SLAM | 算力(轻)+数据(伪标注近零) | 位置/未见/人为干扰三类 +5~15pt | 深化 |
| IP-2 | SCORE-ALIGN | 得分点→过程奖励+进度裁判 | P0 | 无 | 评测指标(25轮) | 数据(重标注近零) | 步骤分+部分分利用 | 维持 |
| IP-3 | LOCAL-EVAL | 零真机迭代闭环+群体探针 | P0 | IP-2 | 低成本×群体 | 算力(1 GPU) | 迭代速度=生命线 | 深化 |
| IP-4 | SUBMISSION-OPS | N端口/延迟/校验/容错 | P1 | 无 | 竞赛×群体 | 算力(部署机) | 免费工程分层 | 深化 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 开放词汇+先看后抓 | P1 | IP-1 | SLAM(闭环) | 与IP-1共享 | 未见物品场景 | 并入闭环 |
| IP-7 | DISTURB-AUG | 干扰回放合成+前后图像对 | P1 | 无 | 25轮 | 数据(合成近零) | 人为干扰场景 | 维持 |
| IP-8 | STEP-EFF | 步骤分效率工程 | P1 | A1 | 25轮 | 零额外 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票 | P1 | IP-2 | 群体智能 | 算力(LoRA×K, 一次性) | 全场景 +2~5pt | 新增 |
| IP-10 | COST-LADDER | 三账户记账+拒绝清单 | P0(纪律) | 无 | 低成本方案 | 全账户 | 防负 ROI 投入 | 新增 |

## 3. 重点展开一：IP-1 SLAM-MAP v2 技术方案

### 3.1 四件套与五类场景的对应

| SLAM 件 | 桌面化定义 | 服务的泛化场景 | 开源/文献锚点 |
|---|---|---|---|
| 在线外参估计 | lower_body[15]+pivot.height → 头部相机位姿前向模型（数据集 state_torso 监督）；每 chunk 首步刷新 | 全部（3D 定位的前提） | 数据集 state_torso/state_d435 作监督 [R4] |
| 重定位 | 跟踪丢失/突变后：外观描述子×位置先验×马氏距离 → 匈牙利重关联 | 人为干扰、位置变化 | LiSTA [R5e]、LT-mapper [R5f] |
| 腕-头闭环 | 腕部近景检测 → 经 ee 外参（评测直接下发 *_gripper_base）配准进头部地图 → 高精度更新 | 未见物品（先看后抓）、抓取精度 | Kimera [R5c]、ConceptGraphs [R5g] |
| 关键帧+协方差 | 全量感知仅 chunk 首步+关键帧；slot 带协方差（深度误差∝d²/b），匹配与门控用马氏距离 | 全部（省算力=IP-10 联动） | Kimera 概率估计 [R5c] |

### 3.2 在线外参估计：为什么必须做

评测 obs 只给 ee pose（gripper_base 系）+ lower_body[15]，不给头部相机位姿（F12），而 G1 头部随躯干升降/腰部转动而动——静态外参假设在躯干高度变化时直接错位。方案：

1. 离线：数据集每帧有 state_torso（躯干位姿）+ 头双目图像；回归「lower_body(15) + ee 位姿 → head→base 平移（≈ f(torso height, waist joints)）」的解析式+残差 MLP（残差很小，模型可极轻）。
2. 在线：评测时 lower_body 可得 + 我方自己下发的 pivot.height 已知 → 前向模型输出头位姿；pivot.height 命令值做有效域门控（超出训练域→协方差放大）。
3. 验证：本地探针注入躯干运动序列，比较地图 3D 误差（E9）。

### 3.3 重定位状态机（v1→v2 更新）

```
TRACKING ──(突变/丢失/干扰事件)──► LOST
   ▲                                 │ 每 slot 维护 EMA crop embedding（外观描述子库）
   │    ┌────────────────────────────┘
   │    ▼
   └── RELOC: 匈牙利匹配(代价 = α·外观余弦距离 + β·马氏距离(位置先验))
        ├─ 匹配成功 → slot 更新(协方差重置放大) → TRACKING
        ├─ 部分匹配 → 新 slot(appeared) + 旧 slot 标记 vanished(tombstone)
        └─ 全图重扫兜底(每 T_detect 帧) → RELOC 超时失败 → REMAP
```

与 v1 差异：v1 只有「位置贪心匹配 + 4cm 阈值」，干扰把物体挪 10cm 就误判为"消失+新增"；v2 的外观描述子使重关联在 20cm 级位移下仍成立——这正是"人为干扰"的真实位移量级（第 25 轮 G5 注入器口径 5-10cm）。锚点：LiSTA 的物体级几何变化检测 [R5e]、LT-mapper 的终身建图重映射 [R5f]。

### 3.4 腕-头闭环伪代码

```python
def wrist_loop_closure(self, wrist_obs, ee_pose, head_frame):
    dets = open_vocab_detect(wrist_obs)              # 近景检测，精度高于头部远距
    for d in dets:
        # 腕部无深度通道 → 桌面平面先验：已知 ee 高度与桌面高度，单目反投影到平面
        # （SLAM 平面约束单目尺度恢复的桌面特例）
        p_wrist = backproject_to_plane(d.bbox, plane_z=TABLE_Z, cam=ee_pose @ T_gripper_cam)
        p_base = ee_pose @ T_gripper_cam @ p_wrist
        j = hungarian_match(p_base, d.emb, self.slots)   # 配准进头部地图（闭环）
        if j is not None:
            self.slots[j].refine(p_base, conf_boost=0.2)  # 高精度位置更新
        else:
            self.spawn(d, p_base, src="wrist")            # 头图没见过的物体（未见物品）
```

IP-6 的"先看后抓"由此实现：抓取前一步状态触发腕部近景重定位，确认目标 slot 后再闭合。

### 3.5 延迟预算更新（对比第 25 轮 v1 表）

| 环节 | v1 预算 | v2 预算 | 手段 |
|---|---|---|---|
| 双目深度 | 40ms/首步 | 40ms/关键帧 | 关键帧降频（chunk 首步+RELOC 时才跑） |
| 外参前向模型 | — | <1ms | 残差 MLP，CPU 可跑 |
| 检测+跟踪 | 50ms/首步 | 50ms/关键帧 + 8ms/中间步 | 中间步只做轻量跟踪校验，不做检测 |
| 腕-头闭环 | — | 15ms/抓取前一步 | 仅"即将抓取"状态触发 |
| VLA 推理 | 150ms | 150ms（K 路采样 batch 并行，见 IP-9） | fp16/int8 + CUDA graph |

### 3.6 地图服务骨架增量（接第 25 轮 3.4 代码）

```python
@dataclass
class Slot:   # v2 增量字段
    emb_ema: np.ndarray          # 外观描述子（crop embedding EMA）
    cov: np.ndarray              # 3D 位置协方差（深度误差∝d²/b + 检测噪声）
    src: str = "head"            # 观测来源 head / wrist（闭环标记）

def relocate(self, dets, depth_xyz):
    """LOST → RELOC：匈牙利匹配（外观余弦 × 马氏位置先验），锚点 LiSTA/LT-mapper"""
    cost = [[ALPHA * (1 - cos(d.emb, s.emb_ema))
             + BETA * mahalanobis(depth_xyz[d.bbox].mean(0), s.pos_xyz, s.cov)
             for s in self.slots] for d in dets]
    rows, cols = linear_sum_assignment(np.asarray(cost))
    return [(dets[r], cols) for r, c in zip(rows, cols) if cost[r][c] < RELCO_TH]
```

## 4. 重点展开二：IP-9 SWARM-DECODE 技术方案

### 4.1 训练侧：population → soup → distill

```
1. 底座: 社区开源 VLA 3B 级（IP-10 §5.3 决策树）+ LoRA
2. population: K=8 个 LoRA，差异化 {种子, 数据顺序, 图像增强档位, chunk 长度}
3. soup: 按逐任务本地探针分做贪心加权合并（Model soups 贪心版 [R5a]；
   LoRA 同底座同 rank 线性可加）
4. distill: soup 作教师，在 32k 官方演示上蒸回单一 fp16 权重
   → 交付物 = 单一 policy 类 + 单一权重文件，满足"单模型"
成本: LoRA×8 ≈ 单次微调算力的 1/3 倍增量（LoRA 显存小可并行），一次性投入
```

### 4.2 推理侧：自洽投票（离散目标层投票 + 连续层择优）

```python
def get_action(obs):
    cands = model.sample_batch(obs, map_tokens, K=SAMPLE_K)   # K=2~4，batch 维并行
    # 离散目标层投票：每候选解码 {抓取 slot id, 放置 slot id}（Self-Consistency [R5b] 的操作版）
    goals = [discretize(c, sem_map.slots) for c in cands]
    best_goal = majority_vote(goals)          # 平票 → 进度预测器（IP-2）打分破平
    act = argmax_progress([c for c, g in zip(cands, goals) if g == best_goal])
    return sanitize(act)
```

合规与可信度设计（对应 README §6 [R3]）：投票只发生在**离散目标层**，最终连续动作来自**单一选中分支**——返回动作分布不因投票出现多峰混叠，不制造"不规则交互模式"；K 路采样在 batch 维并行，延迟≈单路（E7 验证）。

### 4.3 系统侧：N 端口群体（合规边界）

- **允许（工程）**：端口级容错——某端口进程崩溃，请求由副本接管（Kimera-Multi 鲁棒分布式估计思想 [R5d]；N 端口拓扑在结构上就是分布式多机器人系统）；赛后跨端口遥测聚合：失败签名 = (任务, chunk 步号, 场景特征, 事件序列) 聚类 → 下次提交定向修复。
- **不做（合规红线）**：episode 运行中跨端口共享任何任务状态/地图信息（状态隔离铁律 [R3]）；用 N 台机器人互喂信息协同解题。

### 4.4 与其他 IP 的接口

进度预测器（IP-2 得分点骨架）= 投票裁判；本地群体探针（IP-3）= soup 成分筛选与 K 值扫描；动作 sanitize 与延迟预算（IP-4）约束 K 的上限。

## 5. 重点展开三：IP-10 COST-LADDER（纪律性 IP）

### 5.1 三账户与记账规则

| 账户 | 单位 | 预算 | 记账规则 |
|---|---|---|---|
| 算力-训练 | GPU·天 | ≤ 40（4×A100 级 ×10 天或等价） | 每个 IP 立项申报；超支 20% 需消融证明必要性 |
| 算力-推理 | 单步延迟 + 显存 | <300ms/步，N 端口共享后端 | 任何 +延迟 的 IP 必须给出省延迟配对项（如关键帧降频） |
| 数据 | 真机自采小时数 | **0（红线）** | 只允许：官方 32k / 伪标注 / 视频合成 / 公开数据集 |
| 评测时段 | 预约次数 | 首月 ≤6 次 | 每次提交：过冒烟 CI + 单变量 + 48h 校准报告 |

### 5.2 拒绝清单（本轮明确不做）

1. 不预训练/不大改底座——只做 LoRA 级适配；
2. 不买/不租真机自采数据——迭代全部走离线闭环（IP-3）；
3. 不做像素级 3D 重建/全套 SLAM 系统——SLAM 只取四件套思想；
4. 不用 >3B 底座（除非伪标注流水线证明官方数据信息量不足）；
5. 不在本地-官方指标相关性 <0.5 的维度上批量调参；
6. 不部署违反"单模型"精神的运行时外挂（待 A1/A5 澄清）。

### 5.3 底座选择的成本-分数决策树

```
候选（社区开源 VLA，均支持多路 RGB+语言+动作 chunk）: π0 系(3B) / OpenVLA 系(7B) / GR00T N 系 / RDT(1B)
规则: ① 显存×N 端口可容纳者优先（低成本×IP-4）→ 3B 级起步
      ② 双腕相机输入支持好者优先（腕部视角对 32 任务关键）
      ③ ee 空间动作头现成者优先（与 F11 对齐）
→ 首选 3B 级；7B 仅在 ① 满足时进入对比
```

## 6. 其余 IP 修订摘要（v1→v2 增量）

- **IP-2**：进度预测器新增第二消费者——SWARM-DECODE 投票裁判（§4.2）；得分点骨架发现流程不变（待 A1 回填官方定义）。
- **IP-3**：新增"群体探针"模式：一次视频回放成本评估 K 个 checkpoint（回放与模型解耦）；新增外参标定探针（E9）。
- **IP-4**：新增容错要求（端口崩溃 <2s 接管，E11）；新增赛后遥测聚合报告模板（失败签名聚类）。
- **IP-5**：冻结（P2，合规未明）；"参数头监督提取"与 IP-1 伪标注流水线共用资产，不额外投入。
- **IP-6**：并入 IP-1 腕-头闭环；本条目保留为指针，不再单独展开。
- **IP-7**：新增产出"干扰前后图像对"（干扰注入前后的双目帧+伪标注），直接作重定位模块训练/验证集。
- **IP-8**：维持；若手册确认步骤分=完成效率，"关键帧降频+确定性解码"已由 IP-1/IP-9 覆盖大半。

## 7. 实验设计（新增 E7-E11，接第 25 轮 E1-E6）

| 实验 | 设置 | 指标 | 预期 |
|---|---|---|---|
| E7 自洽解码 | K∈{1,2,4}；投票层{仅目标层, 目标+动作} | 本地探针成功率 / 延迟 / 返回动作分布熵 | 目标层投票 +2~5pt；延迟增幅 <10%；分布不双峰 |
| E8 soup/蒸馏 | 单 LoRA vs 8-LoRA-soup vs 蒸馏回单模型 | 本地探针均分/方差 | soup ≥ 单 LoRA +2pt；蒸馏损失 <0.5pt |
| E9 外参估计 | 静态外参 vs 前向模型，躯干运动序列注入 | 地图 3D 误差 / 成功率 | 躯干运动场景误差 -50% |
| E10 重定位 | 干扰位移{5,10,20}cm；位置贪心 vs 匈牙利+外观 | 重关联成功率 | 20cm 位移下 +30pt+ |
| E11 N 端口容错 | 运行中 kill 端口进程 | 其他端口延迟分布 / 接管时间 | 接管 <2s；其他端口 P99 延迟无变化 |

提交纪律不变：冒烟 CI + 单变量 + 48h 校准报告；E7 的分布熵检查纳入冒烟 CI（可信度条款预防）。

## 8. 风险登记簿（增量；第 25 轮其余行继续有效）

| 风险 | 等级 | 缓解 |
|---|---|---|
| F9 相机映射/校正未确认 → SLAM-MAP 深度链路重来 | **高（本轮最大）** | A4 最高优先；预研桌面平面先验的单目备份路径 |
| 自洽投票触发"动作统计规律"疑虑（[R3] §6） | 中 | 只在离散目标层投票；连续动作单分支输出；E7 分布熵监控纳入 CI |
| 外参前向模型漂移（躯干大幅运动） | 中 | pivot.height 命令值门控 + 协方差放大降权 |
| soup/蒸馏小数据负迁移 | 中 | E8 本地探针先行；无增益即弃（成本已付，不绑架） |
| 评测时段排期不可预测（F10，N 未公布） | 中 | 拓扑 N 可配置；N=3 与 N=8 两档预案 |

## 9. 来源清单（全部检索于 2026-11-07）

- R1 排行榜页（Coming Soon；榜单口径与筛选功能）：https://unibot.unitree.com/leaderboard.html
- R1a 挑战赛页（32 任务/32000 演示/169h；提交流程七步；得分点 100 分口径）：https://unibot.unitree.com/challenges.html
- R2 运行记录页（Coming Soon；"完整评测视频"承诺）：https://unibot.unitree.com/runs.html
- R3 提交接口规范（README §2 观测目录 / §3 动作目录 / §5 N 端口与两种部署方式 / §6 延迟与动作统计可信度条款；repo 共 2 commits）：https://github.com/unitreerobotics/unibot_submission
- R4 数据集卡片（head_stereo rectified、state_d435、动作键全表、1.04k episodes / 194,564 行 / 8.8 GB）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup ；collection（32 项，更新 2026-09-11）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- R5 文献锚点（arXiv API 核实，2026-11-07）：
  - R5a Model soups: https://arxiv.org/abs/2203.05482
  - R5b Self-Consistency Improves Chain of Thought: https://arxiv.org/abs/2203.11171
  - R5c Kimera（语义 SLAM→3D 动态场景图）: https://arxiv.org/abs/2101.06894
  - R5d Kimera-Multi（分布式多机器人 SLAM）: https://arxiv.org/abs/2011.04087
  - R5e LiSTA（物体级变化检测）: https://arxiv.org/abs/2403.02175
  - R5f LT-mapper（终身建图）: https://arxiv.org/abs/2107.07712
  - R5g ConceptGraphs（开放词汇 3D 场景图）: https://arxiv.org/abs/2309.16650
- 第 25 轮来源 1/2/3/6/7（赛事启动报道与任务清单佐证）本轮未逐一重抓，口径以第 25 轮记录为准；官方页面重验部分见 R1/R1a/R2/R3/R4。

## 10. 清单迭代规则（增补，继承第 25 轮 §9）

0.（继承）每轮先核对事实卡——本轮新增 F9-F14；F7/F8 任一解除即触发强制修订；
7.（新增）每个 IP 立项/修订必须过 COST-LADDER 记账：申报主成本账户与边际分预期；连续两轮「高成本低边际分」的项降级或合并；
8.（新增）榜单上线后的"对手锚定"字段以运行记录评测视频为第一证据源（F13），逐任务×逐场景拆解后全面修订清单。
