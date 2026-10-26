# Lecture 10 — Efficiently Evaluating DNNs on GPUs

**对应课程：** [CS149 Fall 2023，Oct 26](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** GEMM、Tiling、Arithmetic Intensity、Fusion、Attention、GPU Memory

## 1. DNN 性能不只取决于参数量

推理 / 训练实际成本同时受这些因素影响：
- 算子 FLOPs；
- HBM / Cache / Shared Memory 中的数据移动；
- Kernel Launch 数量；
- Batch 与序列长度；
- Tensor Layout 与并行调度；
- 中间激活、Attention Score、KV Cache 的大小。

“模型计算量小”不自动意味着延迟低；大量小 Kernel、内存流量或同步，也会拖慢执行。

## 2. 为什么 GEMM（矩阵乘法）如此重要

矩阵乘法 C = A × B 是深度学习系统最基础的计算原语之一。很多 Linear Layer 都可以映射到 GEMM；卷积在某些实现中也会转换或组织为类似矩阵乘法的计算形式。

直接三层循环并不保证高性能，因为同一数据可能从慢内存层级重复加载。

### Tiling（分块）的核心逻辑

把 A、B、C 划成 Tile：
1. 把需要反复使用的输入 Tile 放到更快的存储层级；
2. 对 Tile 内多个乘加运算复用数据；
3. 累积局部结果；
4. 必要时再把输出写回慢内存。

这不是减少矩阵乘法理论上的总乘加次数，而是提高 **每字节数据的有用运算量**。

Tile 越大不一定越快：寄存器、Shared Memory 与 Occupancy 都会限制可选形状。

## 3. Fusion（融合）为什么经常有效

假设网络先计算 Z = A × B，再对 Z 做 Bias 和 ReLU。

朴素流水线：
1. GEMM 输出 Z 写到 HBM；
2. 单独 Kernel 读 Z 加 Bias，写回；
3. 单独 Kernel 再读 Z 做 ReLU，写回。

融合版本可能在计算 GEMM 输出时直接完成 Bias / Activation，只把最终结果写一次。

收益不仅包括减少中间内存流量，也可能减少 Kernel Launch。但复杂 Fusion 会增加资源使用和代码复杂度，并不总是更快。

## 4. Attention 的计算与内存结构

对于一层标准 Dense Self-Attention，概念上计算：

1. S = Q × K^T / sqrt(d)
2. P = softmax(S)
3. O = P × V

其中 Q、K、V 的行通常对应 Token；标准完整 Attention 的 S 和 P 大致是序列长度乘以序列长度的矩阵。

若序列长度为 L，中间分数矩阵的元素数量为 O(L²)。当 L 增大，显存与数据流量压力可能迅速上升（精确成本还取决于 Batch、Head、数据类型、实现等）。

## 5. FlashAttention 思想：少搬运中间矩阵

标准 Attention 计算可以按块处理 Query、Key、Value，避免把完整 Attention Score / Probability 大矩阵反复写入 HBM。

关键思路：
- 通过 Tiling 复用数据；
- 以分块、数值稳定的在线归一化方式计算 Softmax 相关统计；
- 尽可能在片上完成局部计算；
- 降低对慢内存层级的中间结果访问。

需要强调：
- 这并不意味着把 Dense Attention 的所有算术复杂度都从 O(L²) 降为 O(L)；
- 也不意味着任意形状、任意 GPU 上都必然加速；
- 端到端收益受 Kernel、Batch、序列长度、布局、硬件和数据类型影响。

## 6. Batch、Prefill、Decode 的差异

这是对课程内容面向现代 LLM Systems 的延伸：

**Prefill**：给定输入 Prompt，通常并行计算多个 Token 的表示，可能更接近大规模矩阵计算。

**Decode**：自回归生成时每步增加 Token，常受到 KV Cache 读取、Batch 结构、请求调度等因素影响。

因此同一个模型，在不同工作负载阶段可能拥有完全不同的性能瓶颈。Benchmark 必须区分 TTFT（Time To First Token）、TPOT（Time Per Output Token）、吞吐量与并发条件。

## 7. 如何分析一个 DNN 算子

建议依次回答：
1. 输入、输出 Tensor 的 Shape、dtype、Layout 是什么？
2. 理论 FLOPs 和最小内存流量是多少？
3. 中间 Tensor 是否可以避免物化？
4. Kernel 是否太小、启动太频繁？
5. Tiling 会不会增加寄存器 / Shared Memory 使用？
6. 是否需要同步或跨设备通信？
7. 真实性能数字是否由可复现的 Benchmark 支持？

## 8. 与官方 Assignment 4 的关系

[CS149 Fall 2023 的 Assignment 4](https://github.com/stanford-cs149/cs149gpt) 要求用 **C++ 优化 Transformer Attention（CPU 路径）**，重点包括数据局部性、Loop Blocking、Fusion、多核 / SIMD 等思路。

这对理解 FlashAttention 很有帮助，但不要把它误称为 GPU CUDA FlashAttention 作业。

建议分三个版本实现：
- V0：容易验证正确性的朴素 Attention；
- V1：Blocked Attention，减少内存层级之间的不必要往返；
- V2：尽量避免物化大中间 Tensor，并比较内存占用、性能和数值误差。

## 自测

1. 为什么 Tiling 改善 GEMM 的 Arithmetic Intensity？
2. Fusion 能减少哪些访存？为什么可能反而更慢？
3. Attention Score Matrix 的空间成本如何随 L 变化？
4. 为什么 Prefill Benchmark 不能直接推导 Decode 性能？

**后续路线：** GPU MODE / Triton → CS336 Systems → 分布式训练 / vLLM / SGLang。
