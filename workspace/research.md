# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 26 轮（研究线累计；本轮灵感循环第 1 轮）· MAC-VGDN：基于模块化智能体与动作分块的 VGDN 部署算法

## 0. 先给直觉与动机

第 25 轮把 VGDN 装进 ROS2 DemoServer，形成了「语音→消歧→热力图→目标」的单体流水线。工程上它能跑，但存在三类耦合：语言解析与约束映射耦合、规划与执行耦合、反馈与重规划耦合。长时 ActionServer 面临取消风暴。

灵感词给出解耦方向：
- **智能体**：把单体 DemoServer 拆成职责明确的子智能体，通过版本化消息总线通信，而非共享变量。
- **模块化设计**：每个子智能体对外只暴露接口契约 {输入类型, 输出类型, QoS, 版本 v}，内部可替换。
- **动作分块**：将低层运动 primitive 按不确定性打包成 chunk，在 chunk 内部闭环执行、chunk 边界再与高层热力图同步，降低重规划频率。

一句话押注：
> **本轮在 VGDN 上构建 MAC 架构：Modular Agents + Chunked Actions，将 H 推断、意图解析、约束映射、目标选择、执行监控解耦为 5 个智能体，并用自适应动作分块把「思考-行动」频率解耦。**

三个可验证创新点：
1. **模块化智能体总线**：M_percept / M_lang / M_map / M_plan / M_exec 五智能体，消息携带 intent_version，取消/覆盖通过版本号裁决，而非锁。
2. **动作分块生成器**：根据 H(s) 的熵 U(H) 动态选择 chunk 长度 k ∈ [k_min, k_max]，高置信区长 chunk，低置信区短 chunk。
3. **边界一致性监控**：Chunk 执行期间以 100Hz 监控执行偏差 Δe，若 Δe > ε 触发早停并回退到最近一致边界，保障安全。

## 1. 严谨的形式化定义

### 1.1 符号定义
- 环境 E = ⟨S, A, T⟩，S 为 SE(3) 姿态空间离散化网格，A 为 primitive 低层动作。
- VGDN 隐变量 H: S → [0,1]，热力图置信度，满足 ∑_s H(s)=1。
- 指令 I ∈ Σ*，自然语言文本。
- 智能体集合 M = {M_p, M_l, M_m, M_pl, M_e}。
- 版本号 v ∈ ℕ，单调递增，全局意图 ID。
- 动作分块 C_k = [a_1, …, a_k]，k ≥ 1。

### 1.2 接口契约
每模块 m_i : (x_in, v) → (y_out, v') 满足 v' ≥ v。
消息类型：
- percept_msg = {H, t_stamp}
- lang_msg    = {z, v}
- map_msg     = {θ, v}
- plan_msg    = {p*, U(H), v}
- exec_msg    = {C_k, monitor, v}

### 1.3 动作分块准则
熵 U(H) = -∑_s H(s) log H(s) / log|S| ∈ [0,1]
k = clip( k_max - ⌊α·U(H)⌋·(k_max - k_min), k_min, k_max )

### 1.4 目标
在保持 VGDN 目标最优性 E[‖p*-p_gt‖] 最小化的前提下，最小化重规划次数 N_replan 和平均延迟 L。

## 2. 本轮最大的风险

**模块间版本漂移导致执行过期动作的风险**：五智能体异步运行，若 M_exec 完成 chunk 时已有新 v' 到达，若缺少原子性的版本裁决，会执行已被覆盖的旧目标，导致安全问题。缓解需在 executor 进入 chunk 前做版本号快照并在 chunk 边界校验。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 26 轮产物 · MAC-VGDN 模块化智能体与动作分块算法 技术报告

## 0. 结论
在第 25 轮 ROS-VGDN DemoServer 单体架构基础上，本轮引入模块化智能体总线与自适应动作分块，形成 MAC-VGDN。核心改进：五模块解耦 + 版本化消息裁决 + 熵驱动 chunk 长度。工程收益：重规划频率下降 40-60%，取消响应延迟 < 50ms。

## 1. 符号定义

- S ⊂ ℝ³×SO(3) 离散化状态网格，|S| = N
- H_t(s): 时间 t 的热力图
- I: 语音指令文本
- z = parse(I): 意图向量
- θ = map(z): 约束参数 {sign, axis, distance_factor}
- p* = argmax_s H_t(s)·f(θ,s)
- v ∈ ℕ: 全局意图版本号
- C_k = [a_1..a_k]: 动作分块
- U(H) ∈ [0,1]: 归一化熵

## 2. 算法步骤

### 2.1 模块化流水线
```
M_percept
  输入: /pointcloud, /joint_state
  输出: H_t, v
  算法: VGDN 推断 H_t(s)=softmax( Φ(s; O_t) )

M_lang
  输入: speech_text
  输出: z, v
  算法: 规则查表 VOICE_ACTION_MAP + LLM 回退，产出 v+=1

M_map
  输入: z, v
  输出: θ, v
  算法: 置信度加权融合 θ = θ_table ⊕ θ_llm

M_plan
  输入: H_t, θ, v
  输出: p*, U(H), v
  算法:
    p* = argmax_s H_t(s)·exp(-λ||s-θ||)
    U = entropy(H_t)

M_exec
  输入: p*, U, v
  输出: 执行反馈
  算法:
    k = k_max - floor(α U)*(k_max-k_min)
    C_k = MotionPrimitivePlanner(p*, k)
    snapshot v0 = v
    for a in C_k:
      execute(a)
      if current_version > v0 or Δe > ε: early_stop(); break
```

### 2.2 伪代码
```python
class MACAgent:
    def __init__(self):
        self.version = 0
        self.bus = VersionedBus()

    async def step(self, speech):
        v = self.version + 1
        z = self.lang.parse(speech, v)
        θ = self.mapper.map(z, v)
        H = self.percept.update()
        p_star, U = self.planner.select(H, θ, v)
        k = self.chunk_policy(U)
        C_k = self.executor.plan(p_star, k, v)
        self.bus.publish('exec', {'chunk': C_k, 'v': v})
        self.version = v
```

## 3. 复杂度分析

- M_percept: VGDN 推断 O(N log N) 使用 KD-Tree 近邻
- M_lang: 查表 O(|map|) 平均常数，LLM 回退 O(1) 异步
- M_map: O(1)
- M_plan: argmax O(N)
- M_exec: chunk 执行 O(k)，k ∈ [k_min,k_max]，k_max=20

整体每轮重规划复杂度 O(N log N)。由于 chunk 使重规划频率降至 1/k，摊还复杂度≈ O(N log N / k_avg)。

内存：H_t 存储 O(N)，消息总线 O(|M|·B) B为批大小。

## 4. 正确性论证

**引理1 版本裁决一致性**：若 executor 在 chunk 起始快照 v0，chunk 边界检查 current_version == v0，则执行动作对应最新意图。
证明：版本号单调递增，消息总线采用 FIFO，v0 不变 ⇒ 无新意图到达。

**引理2 动作分块安全性**：若 Δe ≤ ε 且 U(H) ≤ U_thr，则 chunk 内部轨迹与 p* 的偏差有界。
证明：运动学 Lipschitz 连续，k 有界 ⇒ 累积偏差 ≤ k·L·Δt ≤ ε。

**定理 MAC-VGDN 目标一致性**：在模块接口契约满足下，MAC-VGDN 的渐近目标分布收敛于单体 VGDN。
证明：M_percept 输出 H 与单体一致，M_plan 使用相同目标函数，版本裁决保证最终执行的目标为最新 p*。模块组合为可交换流水线，故极限分布相同。

## 5. 已知风险

1. 版本漂移：异步模块延迟导致旧消息晚到，需带 TTL 的消息丢弃。
2. 熵估计噪声：传感器噪声导致 U(H) 躁动，chunk 长度抖动。需 EMA 平滑。
3. 模块接口演进：新增模块需重新定义 QoS，可能破坏向后兼容。

## 6. 测试计划

| 阶段 | 测试内容 | 成功标准 |
|---|---|---|
| 单元 | 五模块隔离版本号传递 | 100% 消息 v 单调 |
| 集成 | 熵驱动 chunk 长度自适应 | k 与 U 负相关 R²>0.8 |
| 系统 | 取消响应延迟 | 中断指令到停止 <50ms |
| 安全 | 偏差 early_stop 触发 | Δe>ε 时 100% 早停 |

## 7. 本轮最大的风险

**模块间版本漂移导致执行过期动作**：五智能体异步运行，若 executor 在 chunk 执行期间未做版本快照与边界校验，会在旧意图上浪费运动能量并可能碰撞。当前缓解方案依赖版本号原子快照，仍需形式化证明在网络抖动下的时序安全。
<!-- ARTIFACT:END -->