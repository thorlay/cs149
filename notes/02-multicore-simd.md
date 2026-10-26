# Lecture 2 — A Modern Multi-Core Processor

**对应课程：** [CS149 Fall 2023，Sep 28](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** Multi-core、SIMD、Hardware Multithreading、Latency、Throughput

## 1. 三种并行不是同一回事

**多核（core-level parallelism）**：不同物理核心执行不同指令流。适合任务级并行、请求并行、不同数据块并行。

**SIMD（single instruction, multiple data）**：一条向量指令操作多份数据。适合数组加法、矩阵块、图像像素等规则运算。SIMD 的困难通常是数据依赖、对齐 / 布局，以及控制流不规则。

**硬件多线程（hardware multithreading）**：一个物理核心上维护多个线程上下文，在某线程等待时切换或交错发射其他线程的指令，以隐藏停顿。它不等价于增加相同数量的物理计算核心。

例子：对长度 N 的数组执行 y[i] = a * x[i] + y[i]。
- 用 8 个 CPU 核心：把索引划分为 8 份，并行处理；
- 在每个核心上用 SIMD：一次处理多个浮点元素；
- 用硬件多线程：可能缓解资源停顿，但增加收益不保证线性。

## 2. Latency 与 Throughput

**Latency** 是一项任务从开始到完成的时长；**Throughput** 是单位时间完成的任务数量。

提高吞吐量不一定缩短单任务延迟。例如大 Batch 可以改善 GPU 利用率，但队列等待会增加请求首 token 时间。

并行架构要问：
- 独立工作够不够多？
- 单个处理单元是否经常在等待数据？
- 并行增加后，访存带宽或调度器是否先达到上限？

## 3. Amdahl's Law：串行部分的硬上限

若一项任务的串行比例为 s，理想情况下使用 P 个处理单元的最大加速比：

Speedup(P) = 1 / [s + (1 - s) / P]

例如 s = 0.10、P = 16：加速比约 6.4 倍，而不是 16 倍。该模型忽略通信和调度开销；真实结果通常更低。

与它互补的思路是 **problem scaling**：如果任务规模随机器规模增长，吞吐量可能仍然很好。不要只看固定 N 的加速比。

## 4. 为什么理论向量宽度不等于真实加速比

考虑同样的 SAXPY：
- 计算可向量化，但数据可能已经被内存带宽限制；
- 向量化不减少每个元素需要读取的 x、读取 / 写入的 y；
- 超过 Cache 容量后，更多算术能力不能自动带来带宽；
- 分支和稀疏索引可能阻碍有效向量化。

因此，编写 Benchmark 时要比较：小数据（Cache 内）与大数据（主存），而不是只用一个 N。

## 5. 和 AI Infra 的连接

- PyTorch CPU 算子会利用 SIMD、多核线程池和高性能数学库；
- GPU 的 SIMT 与 CPU SIMD 不相同，但都试图对规则数据并行高效执行；
- Batch Size、Tensor Layout、Vectorization 均在影响实际硬件利用率。

## 自测

1. 8 个硬件线程意味着 8 个物理核心吗？为什么？
2. 当程序受 DRAM 带宽约束，继续增加 CPU Worker 可能发生什么？
3. 为什么 99% 并行的任务，在很多机器上仍可能受最后 1% 约束？
4. 你会如何设计一个公平的 SIMD vs scalar Benchmark？

**建议下一篇：** [L5 Work Distribution](./05-work-distribution-scheduling.md)。
