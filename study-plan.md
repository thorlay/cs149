# 4 周高效学习计划

**适合读者：** 熟悉 C++、Linux 和普通分布式系统；GPU 硬件、CUDA、性能建模基础较弱。

**预算：** 每周 6–8 小时，共约 24–32 小时。这是选择性学习和做小实验的预算，**不是完整完成课程全部作业** 的承诺。Assignment 3 和 4 如完整实现，可能需要额外几周。

## Week 1 — 从「能并行」转到「能解释速度」

阅读 [L2](./notes/02-multicore-simd.md)、[L5](./notes/05-work-distribution-scheduling.md)、[L6](./notes/06-locality-communication-contention.md)，对照官方讲义。

学习输出：
- 理解多核 vs SIMD vs 硬件多线程；
- 会算 Speedup、Efficiency、Work / Span，并识别 load imbalance；
- 会用 bytes moved / FLOPs 估算一个算子是否偏向带宽瓶颈；
- 尝试官方 [Assignment 1](https://github.com/stanford-cs149/asst1) 的 Mandelbrot、SAXPY 环节。

实践问题：为什么动态调度改善负载均衡时，反而可能因调度开销降低性能？

## Week 2 — CUDA 编程模型

阅读 [L7](./notes/07-gpu-architecture-cuda.md)、[L8](./notes/08-data-parallel-thinking.md)。

学习输出：
- 分清 Thread / Warp / Block / Grid / SM 的概念；
- 用 Grid-Stride Loop 编写 SAXPY；
- 比较只测 Kernel 与同时包括 H2D / D2H 传输的耗时；
- 解释 Memory Coalescing 和 Branch Divergence。

实践：运行 [独立 CUDA SAXPY 程序](./labs/README.md)，记录至少 3 个不同输入规模。

## Week 3 — GPU 并行算法与 Renderer

继续 [官方 Assignment 3](https://github.com/stanford-cs149/asst3)。优先完成 CUDA warm-up 和 Renderer 的 correctness，再针对一个明确瓶颈做优化。

建议实验：
- 64 / 128 / 256 / 512 threads per block；
- 修改数据布局与访存模式；
- 比较有无大量线程分支、竞争或同步。

**成功标准：** 有至少一张能复现的性能表，以及“为什么快 / 为什么慢”的解释。没有数据的“优化”不算完成。

## Week 4 — 从 DNN 算子走向 LLM Systems

阅读 [L10](./notes/10-dnn-gpu-optimization.md)，学习矩阵乘法、Blocking、Fusion、Attention 内存成本。

实践：在 [官方 Assignment 4](https://github.com/stanford-cs149/cs149gpt) 上实现 CPU/C++ Naive Attention，进一步做 Loop Blocking 和减少中间 Tensor 的优化。

注意：Fall 2023 Assignment 4 的核心是 **CPU/C++ Attention 优化**，与在 GPU 上实现 FlashAttention 并不相同；算法思想相通，但实现与性能瓶颈不完全一致。

## 单次 2 小时怎么用

| 分配 | 任务 | 输出 |
| --- | --- | --- |
| 15 分钟 | 浏览官方 Slides 与本仓库笔记 | 写 2–3 个待回答的问题 |
| 45 分钟 | 阅读关键概念 / 选看视频 | 不复制原文，画一张概念图 |
| 50 分钟 | 编码、跑基准、改变一个变量 | 产出实测数据 |
| 10 分钟 | 用自己的话解释结果 | 记录下一步实验 |

## 测量的最小规范

1. 写出 **Prediction**（预期瓶颈与优化依据）。
2. 确认 correctness；变快但结果错误没有意义。
3. 明确测量边界（仅 Kernel、含数据传输、还是端到端）。
4. 预热，重复运行，并保留中位数与离散情况。
5. 写出 **Measurement**（单位、N、设备、编译选项）。
6. 写出 **Explanation**（是计算、访存、调度、同步还是测量噪声）。
7. 保留失败实验，因为它有助于校正成本模型。

模板：[benchmark-log.md](./templates/benchmark-log.md)

## 何时进入 Stanford CS336

通过下列三个检查点就可以：
- 对一个给定算子，能列出 FLOPs、粗略 bytes moved，并讨论潜在瓶颈；
- 能独立编写一个 CUDA Kernel，正确比较不同输入规模、Block size；
- 能解释 Attention 的大中间结果为什么会形成内存压力，以及 Tiling / Fusion 如何减少流量。

无需先把 CS149 的全部 Lectures 完整看完。
