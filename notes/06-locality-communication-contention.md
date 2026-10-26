# Lecture 6 — Locality, Communication, and Contention

**对应课程：** [CS149 Fall 2023，Oct 12](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** Data Locality、Bandwidth、Arithmetic Intensity、Communication Overlap、Contention

## 1. 为什么仅看 FLOPs 不够

一个算子需要多少计算，并不唯一决定它能跑多快；数据从哪里来、移动多少次，往往更重要。

**Arithmetic Intensity (AI)** = FLOPs / Bytes moved

这里的 Bytes 应明确是哪个层级的移动量：DRAM ↔ Cache、GPU HBM ↔ SM，还是 Host ↔ Device。换了层级，AI 的数值与解释都可能改变。

一个常见的性能上界近似是：

Achievable FLOP/s ≤ min(Peak Compute FLOP/s, Effective Memory Bandwidth × Arithmetic Intensity)

这就是 Roofline 思维：有的工作负载主要受到算力上限约束，有的受到带宽上限约束。

## 2. SAXPY：一个典型带宽敏感算子

对 float32 数组执行 y[i] = a*x[i] + y[i]：
- 读取 x[i]：4 bytes；
- 读取 y[i]：4 bytes；
- 写回 y[i]：4 bytes；
- 算术：一次乘法 + 一次加法，约 2 FLOPs。

忽略缓存复用及额外访存，总流量约 12 bytes/element，AI ≈ 2/12 = 0.167 FLOP/byte。

对于大型数组，SAXPY 常常偏向带宽瓶颈。简单增加更多算术执行单元不保证显著加速。

**但不要机械套公式：** 若数据完全位于 Cache，或者编译器、硬件的实际访问方式不同，模型的分母就需要调整。

## 3. Locality：重用数据比反复搬运便宜

**Temporal Locality**：短时间内重用同一数据；例如把矩阵块留在 Cache / Shared Memory 里进行多次计算。

**Spatial Locality**：访问相邻地址；例如顺序扫描数组，便于 Cache Line 或 GPU 合并访存发挥作用。

矩阵乘法是典型例子。Naive 实现可能反复读取同一行 / 列；Blocking 把 A、B 分块并尽量复用，减少慢层级的数据移动。

注意 Blocking 不一定单调变快：Tile 太大可能挤占 Cache / Shared Memory、导致寄存器压力或并行度不足。

## 4. Communication：传输可能吞噬计算收益

可粗略把通信成本拆成：

Time ≈ Message Startup Latency + Bytes / Effective Bandwidth

因此：
- 频繁发送大量小消息可能受启动延迟影响；
- 大消息主要受带宽影响；
- 把通信和独立计算重叠（overlap）可能改善端到端时间；
- 但 overlap 并非免费，需要独立执行资源和正确同步。

在多 GPU 训练中，Gradient AllReduce 不只看带宽，也看参数分桶、collective 算法与通信计算重叠。CS149 建立成本模型，深入 NCCL 是后续学习任务。

## 5. Contention：共享资源不是无限容量

竞争可能出现在：
- 锁或共享工作队列；
- CPU Cache Line 的 False Sharing；
- 内存控制器 / 带宽；
- GPU Atomic 操作的热点地址；
- 网络链路或存储系统。

**False Sharing** 特别容易误判：两个线程更新不同变量，但变量恰好落在同一 Cache Line 上，造成不必要的缓存一致性流量。

优化方式依问题而定：局部聚合后合并、降低共享写入频率、分片队列、改善布局，而不是一味增加线程。

## 6. 如何判断瓶颈

1. 计算理论字节量与 FLOPs；
2. 用计时确认总耗时；
3. 查看吞吐量是否随输入规模和并行度变化；
4. 将热点拆成 Kernel、内存拷贝、同步与调度；
5. 只改一个变量，并复测。

例如：增加线程数后时间不降，可能是内存带宽饱和，也可能是任务太小或调度开销过高。**仅凭这一个现象不能定性。**

## 与 AI Infra 的连接

- Attention 的中间 Score Matrix 可能形成高额 GPU 内存流量；
- Operator Fusion 减少中间 Tensor 读写；
- Distributed Training 的 Collective Communication 属于跨设备通信成本；
- CPU Data Loader、PCIe、HBM、NVLink 可以形成不同层级的瓶颈；
- KV Cache 在推理阶段会影响显存容量与访存行为。

## 自测

1. SAXPY 的 AI 为什么很低？
2. Tiling 如何改变数据重用，而不改变数学结果？
3. 为什么 1000 次 1KB 消息不一定等价于 1 次 1MB 消息？
4. 你能构造一个受 Atomic Contention 限制的程序吗？

**下一篇：** [L7 GPU Architecture 与 CUDA](./07-gpu-architecture-cuda.md)。
