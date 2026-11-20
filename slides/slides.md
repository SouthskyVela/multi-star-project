---
theme: default
title: 空间天文小卫星群相关调度机制与算法开发
info: |
  课程作业汇报 · Multi-Star 0.3.4
class: text-slate-800
transition: fade
mdc: true
layout: cover
paginate: true
colorSchema: light
---

# 空间天文小卫星群相关调度机制与算法开发

<div class="mt-6 text-slate-500">
课程作业汇报 · Multi-Star / <code>multi-star-sim</code> 0.3.4
</div>

<div class="pt-12 text-sm text-slate-500">
汇报人：李达航（23009101011）　王振鹏（22009101331）　　2026 年 11 月

<div class="mt-2 text-xs text-slate-400">开源地址：github.com/SouthskyVela/multi-star-project</div>
</div>

<style>
h1 { font-size: 2.0rem; }
h2 { font-size: 1.35rem; margin-bottom: 0.6rem; }
 table { font-size: 0.82rem; }
figcaption { font-size: 0.72rem; color: #64748b; margin-top: 0.35rem; }
table th:first-child, table td:first-child { white-space: nowrap; }
.small { font-size: 0.85rem; }
.tiny { font-size: 0.72rem; color: #64748b; }
</style>

---

# 汇报结构

<div class="grid grid-cols-2 gap-8 mt-8 text-sm">

<div>

**一、问题与方案**

- 选题背景：低频射电、超大视场、小卫星群
- 研究目标、范围与边界
- 需求分析与软件工程实施方案

**二、系统设计**

- 总体架构与集群架构
- 调度机制、运行模式、数据流
- 阵列构型与成像指标

</div>

<div>

**三、实现与验证**

- Headlamp 资源全景（逐层展开）
- Pod 构成与虚拟卫星参数
- 三类测试与故障注入实测

**四、总结**

- 工程化实践与局限
- 后续工作与参考文献

</div>

</div>

---

# 选题背景：为什么要“小卫星群 + 调度”

<div class="grid grid-cols-3 gap-5 mt-6 text-sm">

<div class="p-4 border rounded">

**低频射电的物理需求**

30–240 MHz 是观测宇宙黑暗时代、射电瞬变与太阳活动的关键窗口，但波长长、单口径难以获得高分辨率。

</div>

<div class="p-4 border rounded">

**超大视场与瞬时覆盖**

低频阵列视场可达数十平方度，需要大量天线单元同时工作，形成瞬时、宽视场的采样。

</div>

<div class="p-4 border rounded">

**分布式小卫星群**

以多颗小卫星替代单一大型平台，可扩展口径、降低成本，但带来选主、同步、故障与任务编排问题。

</div>

</div>

<div class="mt-4 p-4 border-l-4 border-teal-600 bg-teal-50 text-sm">

**可拓展性**：多颗卫星组成的卫星群在调度算法上有很大的设计空间——可以把成像采样质量（uv 覆盖、PSF）作为奖励，用强化学习去优化阵列构型与观测编排。

</div>

<div class="mt-3 p-4 rounded bg-slate-100 text-sm">

本课题不追求真实的轨道动力学与全链路成像，而是把“**分布式调度机制**”做成可运行、可复现、可观测的原型：三颗主星 + 九颗小卫星，运行在本地 Kubernetes 集群上。

</div>

<div class="tiny mt-3">参考：LOFAR 的低频阵列设计与 SKA 的科学目标，见文末文献 [1][3]。</div>

---

# 研究目标与边界

<div class="mt-4 text-sm">

### 要做的事

- **主控竞选与接管**：同一时刻只有一个主控，故障后自动切换
- **任务编排**：巡天、定源、定标三种模式的状态机
- **命令可靠性**：幂等、围栏、重放保护、不可逆变轨不重发
- **阵列评估**：构型、uv 覆盖、dirty beam / PSF
- **可观测性**：实时面板、审计日志、资源全景
- **可复现**：单机从零创建集群，版本化镜像与脚本

</div>

<div class="mt-6 p-3 border-l-4 border-teal-600 bg-teal-50 text-sm">

**设计原则**：先把分布式系统最容易出错的部分（选主、幂等、故障恢复）做成真实可验证的机制，再叠加天文业务语义。

</div>

---

# 最初构想：一张草图

<div class="grid grid-cols-5 gap-6 mt-1">

<div class="col-span-2">
<img src="/img/sketch/initial-idea.jpg" class="w-full rounded border border-slate-300" />
<div class="tiny mt-2">课题启动时的原始设想：控制面 / 节点 / 主副星 / 测试项 / 可视化。</div>
</div>

<div class="col-span-3 text-sm">

**草图里的几个要点**

- 天基射电干涉成像：**控制面为主星，节点为子星**
- 子星按 uv 采样最优调整构型与波束；主、副卫星可以互切
- 星间通信依靠激光 / 微波，减少对地面补网的依赖
- 测试三条线：常规功能切换、事件触发、主星与子星故障
- 可视化三件事：调度终端面板、阵列可视、输入输出响应
- 拓展设想：增加子星数量、引入 AI 辅助调度

</div>

</div>

---

# 需求分析

<div class="text-[0.8rem]">

| 类别 | 需求 | 验收方式 |
|---|---|---|
| 功能 | 三颗主星竞选主控（Kubernetes Lease）<br/>同一时刻只有一颗生效，故障后 30 s 内接管 | 暂停主控 22 s，观察主控与 epoch 变化 |
| 功能 | 九小星编队，支持故障注入与显式恢复 | 注入后健康 8/9、基线 36→28；恢复后回到 9/36 |
| 功能 | 天文事件触发定源观测，事件去重 | 相同 event_id 重复提交不增加计划版本 |
| 功能 | 巡天 / 定源 / 定标模式切换 | 面板按钮与审计日志一致 |
| 非功能 | 命令幂等与旧主控围栏 | 单元测试覆盖 epoch / plan / command_id |
| 非功能 | 可复现部署 | 单机脚本从零创建集群并部署 |
| 非功能 | 可观测 | 面板 1 s 快照、审计日志、Headlamp 资源视图 |
| 非功能 | 可移植 | 仓库不含主机绝对路径，换路径可直接运行 |

</div>

<div class="tiny mt-3">完整验收记录见 <code>runtime/results/</code> 与 74 项自动化测试。</div>

---

# 软件工程实施方案

<div class="grid grid-cols-4 gap-3 mt-5 text-xs">

<div class="p-3 border rounded">
<div class="font-bold text-sm mb-2">① 需求与原型</div>
明确三种模式、九个验收场景；先跑通单机容器，再上集群。
</div>

<div class="p-3 border rounded">
<div class="font-bold text-sm mb-2">② 迭代开发</div>
0.2.x 完成调度与面板；0.3.x 修复过期事件、日志刷屏与确认交互。
</div>

<div class="p-3 border rounded">
<div class="font-bold text-sm mb-2">③ 测试策略</div>
单元测试 74 项；静态检查；真实集群端到端验收；失败场景优先。
</div>

<div class="p-3 border rounded">
<div class="font-bold text-sm mb-2">④ 交付与复现</div>
公开仓库、版本化镜像、相对路径脚本、<code>start.cmd</code> 一键恢复。
</div>

</div>

<div class="grid grid-cols-2 gap-6 mt-6 text-sm">

<div>

**质量门禁**

- 提交前必须通过 74 项测试与 JS 语法检查
- 面板与服务必须经真实快照验证，不接受“看起来对”
- 版本号同时写入 <code>pyproject.toml</code>、镜像标签与部署清单

</div>

<div>

**风险与对策**

- 单机资源有限 → 限制副本与镜像大小，PVC 仅 64 MiB
- 重启后 SQLite 初始化慢 → 启动器等待真实就绪，不凭容器 Running
- 演示不确定 → 固定脚本 + 可重复的故障注入流程

</div>

</div>

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/01-architecture.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
三层职责：展示层只读快照与资源；控制面由 Lease 决定唯一 leader，只有 leader 能下发命令；
数据面九颗小星各自持有 PVC 并分块回传。
-->

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/02-cluster.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
Node 是虚拟主机（k3d 容器），Pod 才是调度单位；Namespace 隔离业务；Service 提供稳定 DNS。
K3s 默认用 SQLite（kine），不需要单独部署 etcd。
-->
---

# 为什么选 k3d，而不是 k8s 或 k3s

<div class="text-sm mt-2">

| 方案 | 形态 | 资源占用 | 与本课题的匹配度 |
|---|---|---|---|
| Kubernetes（k8s） | 完整控制平面，面向多机生产集群 | 高 | 功能齐全，但单机演示过重 |
| K3s | 轻量发行版，一个进程即可运行 | 低 | 够轻，但默认只有一个节点 |
| k3d | 用 Docker 容器承载 K3s 节点 | 低–中 | 一条命令起 1 server + 3 agent，最接近真实多节点 |

</div>

<div class="grid grid-cols-3 gap-4 mt-5 text-xs text-slate-600">

<div><b>可复现</b>：集群、镜像、PVC 都落在项目目录，换机器同样能起。</div>

<div><b>可观测</b>：k3d 的节点就是容器，<code>docker ps</code> 与 <code>kubectl</code> 能一一对应，便于讲清 Node 与 Pod。</div>

<div><b>代价</b>：节点是容器而非真机，网络时延与存储都是模拟，不能替代星间链路验证。</div>

</div>

<div class="mt-8 p-3 border-l-4 border-teal-600 bg-teal-50 text-sm">

**取舍**：本课题真正需要的是“多节点拓扑 + 单机可复现 + 可观测”，k3d 正好落在这三者的交集上。

</div>

---

# 资源全景：Headlamp 里的真实集群（1/2）

<div class="grid grid-cols-2 gap-4 mt-2">

<figure>
<img src="/img/headlamp/00-map-home.png" class="w-full rounded border border-slate-300" />
<figcaption>Map 视图按 Namespace 分组：multi-star 下是 small-sat、main-sat 与 dashboard。</figcaption>
</figure>

<figure>
<img src="/img/headlamp/04-pods.png" class="w-full rounded border border-slate-300" />
<figcaption>Namespace 之下的 Pod 列表：3 主星、9 小星、1 面板代理。</figcaption>
</figure>

</div>

<div class="tiny mt-3">节点 4/4 就绪、Pod 17/17 运行；图中重启计数来自多次版本迭代，而非当前故障。</div>

---

# 资源全景（2/3）：small-sat 的九个实例

<img src="/img/headlamp/07-map-small-sat.png" style="max-height:64vh;width:auto;" class="mx-auto rounded border border-slate-300" />

---

# 资源全景（3/3）：main-sat 的三颗主星

<img src="/img/headlamp/08-map-main-sat.png" style="max-height:64vh;width:auto;" class="mx-auto rounded border border-slate-300" />

---

# 每颗“虚拟卫星”由什么构成

<div class="grid grid-cols-2 gap-5 mt-2 text-sm">

<div>

<figure>
<img src="/img/headlamp/09-small-sat-container.png" class="w-full rounded border border-slate-300" />
<figcaption>小星容器：镜像 <code>multi-star-satellite:0.2.0</code>，环境变量注入身份与容量。</figcaption>
</figure>

</div>

<div>

**一个 Pod = 一个业务容器 + 一个数据卷**

- 容器端口：小星 8080，主星 8081
- 环境变量：<code>SATELLITE_ID</code> 取 Pod 名；<code>SNAPSHOT_PATH=/data/snapshot.json</code>
- 请求 / 上限：小星 20m/32Mi → 500m/256Mi；主星 50m/64Mi → 500m/512Mi
- 数据卷：每 Pod 一块 64 MiB PVC，挂载到 <code>/data</code>
- 探针：就绪 2 s 周期，存活 10 s 周期

</div>

</div>

<div class="tiny mt-2">注：Pod 是 Kubernetes 的调度单位，不是“节点”；节点是承载 Pod 的虚拟主机（k3d 容器）。</div>

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/03-scheduling.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
Lease 决定唯一主控；epoch 单调递增，旧主控命令被拒绝；command_id 保证幂等。
-->
---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/04-modes.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
切换前校验健康小星不少于 2 颗且没有 UNKNOWN 在途任务；FIXED_SOURCE 需要未过期事件，事件到期自动回退 SURVEY；每次切换生成新的 plan_version。
-->
---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/05-dataflow.png" class="max-w-full max-h-full object-contain" />
</div>

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/06-operation-flow.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
操作流：打开面板 → 选择目标 → 选择操作 → 页面内二次确认（15 s）→ 主控校验 → 下发命令 → 快照刷新 → 反馈与审计。
一致性：command_id 幂等、epoch 围栏、plan_version 只增不减。
-->

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/diagrams/07-fault-response.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
主控故障：停止续约 → Lease 过期 → 其他主星接管（epoch+1）→ 重建计划。
小星故障：健康检查失败 → 标记 FAILED → 计划重构（plan+1）→ 阵列重构。
恢复后健康检查通过、重新纳入、plan 再 +1，全过程写入审计。
-->

<!--
小星只向主控出站；主控之间靠 Lease 与 ConfigMap 协调；面板只读快照，无 leader 时返回 503。
-->
---

# 阵列构型与成像指标

<img src="/img/panel/00-formation-preview.png" class="w-full mt-1 rounded border border-slate-200" />

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>构型</b>：环形 / Y 形 / 螺旋，半径 5 km，9 星共 36 条基线。</div>

<div><b>uv 覆盖</b>：远场采样加共轭点，中心空洞与最大半径决定分辨率。</div>

<div><b>PSF</b>：dirty beam 的峰值旁瓣与 FWHM，用于比较不同构型。</div>

</div>

---

# 前期工作：六星编队的成像仿真

<div class="grid grid-cols-2 gap-4 mt-1">

<figure>
<img src="/img/imaging/fig_uv_coverage.png" class="w-full rounded border border-slate-300" />
<figcaption>10 个轨道周期的 uv 覆盖：左 10 MHz，右 40 MHz，轨迹自然填充成环带。</figcaption>
</figure>

<figure>
<img src="/img/imaging/fig_rime_image.png" class="w-full rounded border border-slate-300" />
<figcaption>RIME 可见度仿真与脏图：四个输入源都回到正确位置。</figcaption>
</figure>

</div>

<div class="grid grid-cols-3 gap-4 mt-2 text-xs text-slate-600">

<div><b>构型</b>：6 星（1 主 5 从），Callisto 500 km 极轨，10 轨内基线 109–1982 km。</div>

<div><b>分辨率</b>：10 MHz 约 2.48″，40 MHz 约 0.62″。</div>

<div><b>结果</b>：峰值恢复约 80%，损失主要来自 uv 中心空洞的短基线缺失。</div>

</div>

---

<div class="absolute inset-0 flex items-center justify-center bg-white">
  <img src="/img/imaging/fig_4tool_compare.png" class="max-w-full max-h-full object-contain" />
</div>

<!--
RIME：4 个源位置正确，峰值恢复约 80%。
OSKAR：120 个随机快照联合成像，恢复率 75%，与短基线缺失一致。
pyuvsim：归一化通过、保持相位闭合；OmniUV：真实开普勒轨道生成 FITS-IDI。
附带结论：均匀快照会产生规则栅瓣，随机化观测时刻后消除，已写回阵列设计。
-->

---

# 前期工作：CASA 端到端成像

<div class="grid grid-cols-5 gap-5 mt-1">

<div class="col-span-3">
<img src="/img/imaging/fig_casa_image.png" class="w-full rounded border border-slate-300" />
<div class="tiny mt-2">左：脏图；右：Högbom 清洗后。红圈为注入源的真值位置。</div>
</div>

<div class="col-span-2 text-sm">

**定量结果**

- 四个源位置误差 ≤ 0.6″（约四分之一合成波束）
- 流量恢复率 99.3%–99.9%
- 角域动态范围约 1490

**与本课题的关系**

前期工作验证了“阵列几何 → 可见度 → 成像”的正向链路；本课题补上调度、故障与重构这一层，让阵列在运行中始终可成像。

</div>

</div>

---

# 测试体系与总览

<div class="grid grid-cols-4 gap-4 mt-6 text-center">

<div class="p-4 border rounded">
<div class="text-3xl font-bold text-teal-700">74</div>
<div class="text-xs mt-1">单元与服务测试</div>
</div>

<div class="p-4 border rounded">
<div class="text-3xl font-bold text-teal-700">3</div>
<div class="text-xs mt-1">端到端验收场景</div>
</div>

<div class="p-4 border rounded">
<div class="text-3xl font-bold text-teal-700">9+3</div>
<div class="text-xs mt-1">小星 / 主星实例</div>
</div>

<div class="p-4 border rounded">
<div class="text-3xl font-bold text-teal-700">1 s</div>
<div class="text-xs mt-1">面板快照周期</div>
</div>

</div>

<div class="mt-8 text-sm">

**四类实测**（本页之后逐一给出界面与结果）

1. 主星故障：暂停当前主控 22 s，验证接管与 epoch 递增
2. 小星故障：注入 / 恢复，验证健康数、基线与构型重构
3. 天文事件：提交事件，验证自动进入定源模式与去重
4. 常规功能：模式切换与任务重分配，验证 plan_version 单调

</div>

---

# 测试一：主星故障与接管

<div class="grid grid-cols-2 gap-4 mt-1">

<figure>
<img src="/img/panel/01-initial.png" class="w-full rounded border border-slate-300" />
<figcaption>切换前：主控 main-sat-0，epoch 16，plan 161。</figcaption>
</figure>

<figure>
<img src="/img/panel/02-failover-after.png" class="w-full rounded border border-slate-300" />
<figcaption>切换后：主控 main-sat-1，epoch 17，plan 161；旧主恢复后不再抢回。</figcaption>
</figure>

</div>

<div class="mt-3 text-sm">

点击“暂停当前主控 22 秒”后，原主控停止续约与下发；租约到期后由其他主星接管。接管发生在租约到期后的数个轮询周期内（本次实测约 20 s 内完成）。

</div>

---

# 测试一：接管日志与围栏效果

<div class="grid grid-cols-5 gap-4 mt-2">

<div class="col-span-3">

<img src="/img/panel/03-failover-log.png" class="w-full rounded border border-slate-300" />

</div>

<div class="col-span-2 text-sm">

**日志证据**

- <code>leader epoch changed; plan 161</code>：接管触发重构
- 旧主控恢复后仍持 epoch 16；按设计其命令会被 epoch 围栏拒绝（单元测试覆盖）
- 面板始终只有一个 leader，未出现双主控写状态

<br>

**为什么不会脑裂**

- Lease 由 apiserver 保证原子性
- 每次续约前检查 holder 身份
- 命令携带 epoch，执行端只接受不低于本地最高 epoch 的命令

</div>

</div>

---

# 演示：主控故障切换（8× 加速）

<video controls preload="metadata" poster="/media/clips/01-poster.jpg?v=2" style="width:100%;max-height:62vh;">

<source src="/media/clips/01-failover-8x.mp4" type="video/mp4">

</video>

<div class="tiny mt-2">完整录屏：<code>public/media/full/01-failover.mp4</code>（105 s）。</div>

---

# 测试二：小星故障注入（操作与确认）

<div class="grid grid-cols-2 gap-5 mt-2">

<figure>
<img src="/img/panel/04-fault-armed.png" class="w-full rounded border border-slate-300" />
<figcaption>页面内二次确认：按钮变为“再次点击确认：注入故障”，15 s 内有效。</figcaption>
</figure>

<figure>
<img src="/img/panel/05-fault-result.png" class="w-full rounded border border-slate-300" />
<figcaption>注入结果：健康 failed、基线 36→28；状态区只显示关键字段。</figcaption>
</figure>

</div>

<div class="mt-3 text-sm">

早期版本使用浏览器原生 <code>confirm</code>，会阻塞自动化并打断演示；现改为页面内二次确认，既保留防误触，也能被脚本稳定复现。

</div>

---

# 测试二：故障后的阵列重构与恢复

<div class="grid grid-cols-2 gap-5 mt-2">

<figure>
<img src="/img/panel/06-fault-array.png" class="w-full rounded border border-slate-300" />
<figcaption>故障态：9 颗在编，健康 8；UV 采样 28 点 + 28 共轭。</figcaption>
</figure>

<figure>
<img src="/img/panel/07-fault-recovered.png" class="w-full rounded border border-slate-300" />
<figcaption>恢复后：健康 9，基线回到 36；恢复不改写历史任务。</figcaption>
</figure>

</div>

<div class="mt-2 text-xs text-slate-600">

故障星用红色标出；健康数从 9 降为 8，基线从 36 降为 28（C(8,2)=28）。恢复采用显式操作，避免“Pod 重启即自动痊愈”掩盖真实故障。

</div>

---

# 演示：小星故障注入与恢复（8× 加速）

<video controls preload="metadata" poster="/media/clips/02-poster.jpg?v=2" style="width:100%;max-height:62vh;">

<source src="/media/clips/02-fault-8x.mp4" type="video/mp4">

</video>

<div class="grid grid-cols-2 gap-4 mt-2 text-xs text-slate-600">

<div>选择 small-sat-5 → 二次确认注入 → 健康数 9→8、基线 36→28 → 显式恢复回到 9/36。</div>

<div class="text-right">完整录屏：<code>public/media/full/02-fault-injection-v2.mp4</code></div>

</div>

---

# 测试三：天文事件触发定源观测

<div class="grid grid-cols-2 gap-5 mt-2">

<figure>
<img src="/img/panel/08-event-submit.png" class="w-full rounded border border-slate-300" />
<figcaption>提交事件：频率 110 MHz、通量 18 Jy、谱指数 −0.7，请求已接受。</figcaption>
</figure>

<figure>
<img src="/img/panel/09-fixed-source.png" class="w-full rounded border border-slate-300" />
<figcaption>模式自动进入 FIXED_SOURCE，生成新计划版本。</figcaption>
</figure>

</div>

<div class="mt-2 text-sm">

事件携带 <code>event_id / target_id / 频率 / 通量 / 置信度 / 谱指数 / 有效期</code>；相同 <code>event_id</code> 重复提交会被去重，不会反复抬升计划版本。面板右侧的合成频谱仅用于输入预览，明确标注“非快照实测”。

</div>

---

# 演示：天文事件触发定源（8× 加速）

<video controls preload="metadata" poster="/media/clips/03-poster.jpg?v=2" style="width:100%;max-height:62vh;">

<source src="/media/clips/03-event-8x.mp4" type="video/mp4">

</video>

<div class="grid grid-cols-2 gap-4 mt-2 text-xs text-slate-600">

<div>填写事件（110 MHz、18 Jy、谱指数 −0.7）→ 提交 → 自动进入 FIXED_SOURCE，并生成新的计划版本。</div>

<div class="text-right">完整录屏：<code>public/media/full/03-event-final.mp4</code></div>

</div>

---

# 测试四：模式切换与任务分配

<div class="grid grid-cols-2 gap-5 mt-2">

<figure>
<img src="/img/panel/10-calibration.png" class="w-full rounded border border-slate-300" />
<figcaption>切换到 CALIBRATION：标定任务替换巡天任务，plan 166→167。</figcaption>
</figure>

<figure>
<img src="/img/panel/11-mode-sequence.png" class="w-full rounded border border-slate-300" />
<figcaption>审计序列：event accepted → FIXED_SOURCE → CALIBRATION → SURVEY，版本逐次递增。</figcaption>
</figure>

</div>

<div class="mt-2 text-xs text-slate-600">

每次模式切换都会重新生成所有在编小星的任务，未执行完的任务按 plan_version 作废；已 verified 的任务保留在各自 PVC 的任务历史中。

</div>

---

# 演示：模式切换与任务重分配（8× 加速）

<video controls preload="metadata" poster="/media/clips/04-poster.jpg?v=2" style="width:100%;max-height:62vh;">

<source src="/media/clips/04-mode-8x.mp4" type="video/mp4">

</video>

<div class="grid grid-cols-2 gap-4 mt-2 text-xs text-slate-600">

<div>CALIBRATION ↔ SURVEY 切换，计划版本逐次递增，审计事件流同步记录。</div>

<div class="text-right">完整录屏：<code>public/media/full/04-mode-switch.mp4</code></div>

</div>

---

# 工程化实践、局限与后续

<div class="grid grid-cols-2 gap-8 mt-4 text-[0.95rem]">

<div>

### 工程化

- 30 余个脚本由自身位置推导仓库根目录，配置只存相对路径
- 面板只读快照，Headlamp 观察资源；审计日志连续去重
- 部署脚本幂等，失败停在上一步并打印真实原因
- 镜像分离：<code>main:0.3.4</code> 与 <code>satellite:0.2.0</code>，避免小星无谓重启

</div>

<div>

### 局限与后续

- 阵列几何为简化远场模型，未含近场与电离层扰动
- 调度以轮询与固定优先级为主，未做能耗 / 可见性优化
- 单机 K3s 无法验证真实星间链路时延与丢包
- 后续：可见性约束、OSKAR 复核、网络分区注入、多集群联邦

</div>

</div>

<div class="mt-6 p-3 rounded bg-slate-100 text-xs text-slate-600">

版本与交付：0.3.4 为本次汇报版本；小星镜像仍为 0.2.0，主星与面板按需升级。

</div>

---

# 结论

<div class="mt-6 text-base leading-8">

1. 用**真实容器编排**承载虚拟卫星，把主控竞选、幂等、故障恢复做成可验证机制，而不是纸面流程。
2. 通过 **主控竞选（Lease）+ epoch + plan_version** 形成一套简单但有效的围栏体系：同一时刻只有一个写者，旧主控无法“复活”。
3. 面板、Headlamp 与审计日志构成三层可观测性，测试过程可以被截图、复现与审计。
4. 74 项测试与四类实测表明：系统在故障、事件与模式切换下行为可预测，计划版本始终单调。

</div>

<div class="mt-10 p-4 rounded bg-teal-50 border-l-4 border-teal-600 text-sm">

**一句话**：把分布式系统最难的部分做真，把天文业务做成可插拔的语义层。

</div>

---

# 参考文献

<div class="text-[0.8rem] leading-7">

\[1\] van Haarlem, M. P., Wise, M. W., Gunst, A. W., et al. (2013). **LOFAR: The LOw-Frequency ARray**. *Astronomy & Astrophysics*, 556, A2. DOI: [10.1051/0004-6361/201220873](https://doi.org/10.1051/0004-6361/201220873)

\[2\] Ferrari, B., Cordeau, J.-F., Delorme, M., Iori, M., & Orosei, R. (2024). **Satellite Scheduling Problems: A survey of applications in Earth and outer space observation**. *Computers & Operations Research*, 173, 106875. DOI: [10.1016/j.cor.2024.106875](https://doi.org/10.1016/j.cor.2024.106875)

\[3\] Thompson, A. R., Moran, J. M., & Swenson, G. W. (2017). **Interferometry and Synthesis in Radio Astronomy** (3rd ed.). Springer. DOI: [10.1007/978-3-319-44431-4](https://doi.org/10.1007/978-3-319-44431-4)

\[4\] Kubernetes Documentation. **Leases** (coordination.k8s.io). https://kubernetes.io/docs/concepts/architecture/leases/

\[5\] K3s Documentation. **Lightweight Kubernetes**. https://docs.k3s.io/

\[6\] k3d Documentation. **k3s in Docker**. https://k3d.io/

\[7\] Headlamp. **Kubernetes UI**. https://headlamp.dev/

</div>

<div class="tiny mt-4">以上文献均可在 DOI 或官方文档站点检索；阵列与调度结论不依赖未公开数据。</div>

---

# 开源地址

<div class="mt-10 text-center">

<div class="text-sm text-slate-500 mb-2">项目源码（公开仓库）</div>

<div class="text-2xl font-mono text-teal-700"><a href="https://github.com/SouthskyVela/multi-star-project" target="_blank">github.com/SouthskyVela/multi-star-project</a></div>

<div class="mt-6 text-sm text-slate-600">
版本 0.3.4 · 74 项测试 · 单机 K3s 可复现
</div>

<div class="mt-16 text-3xl font-bold">谢谢，欢迎提问</div>

</div>
