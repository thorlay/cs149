# Stanford CS149 Fall 2023｜并行计算中文学习笔记

> **非官方、原创学习手册。** 面向有 C++ / 后端 / 分布式系统基础、希望深入 GPU、HPC 与 AI Infrastructure 的工程师。以 Stanford CS149 Fall 2023 为课程主线，结合工程实例解释概念；不是视频逐字稿，也不包含课程讲义的全文转载。

- [课程主页：Stanford CS149 Fall 2023](https://gfxcourses.stanford.edu/cs149/fall23/)
- [官方 Assignment 1（CPU 并行性能）](https://github.com/stanford-cs149/asst1)
- [官方 Assignment 3（CUDA Renderer）](https://github.com/stanford-cs149/asst3)
- [官方 Assignment 4（Transformer Attention）](https://github.com/stanford-cs149/cs149gpt)

## 中文教材（Transcript + Slides 路线）

新增 [中文教材目录](./textbook/README.md)：以 2023 官方 Slides 和可核对的录播资料为参考，原创编写连续正文。其中 L01–L06 已结合用户提供 Transcript 和官方 Slides 扩写为详细版，L07、L10 为自包含初稿；[完整 Slides / 视频来源索引](./sources/README.md) 覆盖 18 个主题讲次及期中复习课。L01–L06 文字稿已阅读但尚未与录音逐句校对；其余完整 Transcript 尚在核验，未获取的章节不标记完成。

## 自包含中文教材

- [第 1 章：为什么需要并行计算](./textbook/01-why-parallelism.md)
- [第 2 章：现代多核处理器——Cache、Multicore、SIMD、硬件多线程](./textbook/02-modern-multicore-processor.md)
- [第 3 章：多核架构进阶——延迟、带宽与 ISPC](./textbook/03-multicore-ispc.md)

- [第 4 章：并行编程基础——分解、同步与网格求解](./textbook/04-parallel-programming-basics.md)
- [第 5 章：工作分配与调度——负载平衡、任务粒度与工作窃取](./textbook/05-work-distribution-scheduling.md)
- [第 6 章：局部性、通信与竞争——幽灵行、分块、融合与 Roofline](./textbook/06-locality-communication-contention.md)

## 从这里开始

1. [4 周精简学习路线](./study-plan.md)
2. [Lecture 2：多核处理器、SIMD 与硬件线程](./notes/02-multicore-simd.md)
3. [Lecture 5：Work Distribution 与 Scheduling](./notes/05-work-distribution-scheduling.md)
4. [Lecture 6：Locality、Communication 与 Contention](./notes/06-locality-communication-contention.md)
5. [Lecture 7：GPU Architecture 与 CUDA](./notes/07-gpu-architecture-cuda.md)
6. [Lecture 8：Data-Parallel Thinking](./notes/08-data-parallel-thinking.md)
7. [Lecture 10：GPU 上的 DNN 优化](./notes/10-dnn-gpu-optimization.md)
8. [CUDA SAXPY 实验与 Benchmark](./labs/README.md)
9. [实验结果记录模板](./templates/benchmark-log.md)
10. [外部资料与后续学习路径](./resources.md)

## 学习目标

完成第一阶段后，应能用自己写的程序验证：

- 多核、SIMD、GPU SIMT 的执行模型区别，以及扩展性为什么存在上限；
- 什么是 **work、span、load imbalance、scheduling overhead**；
- 什么是 **arithmetic intensity、memory bandwidth、data locality、contention**；
- 如何把串行运算拆成 CUDA Grid / Block / Thread；
- 如何实现 Map、Reduction、Prefix Sum 等数据并行原语；
- 为什么 Transformer Attention 可以通过 **tiling、fusion、减少中间结果的内存流量** 提升性能。

## 课程导航（按 Fall 2023 官方顺序）

| Lecture | 主题 | 本仓库 |
| --- | --- | --- |
| 1 | Why Parallelism? Why Efficiency? | 官方材料 |
| 2 | A Modern Multi-Core Processor | [详细笔记](./notes/02-multicore-simd.md) |
| 3 | Multi-core Part II + ISPC | [自包含教材](./textbook/03-multicore-ispc.md) |
| 4 | Parallel Programming Basics | [自包含教材](./textbook/04-parallel-programming-basics.md) |
| 5 | Work Distribution and Scheduling | [自包含教材](./textbook/05-work-distribution-scheduling.md) · [速查笔记](./notes/05-work-distribution-scheduling.md) |
| 6 | Locality, Communication, and Contention | [自包含教材](./textbook/06-locality-communication-contention.md) · [速查笔记](./notes/06-locality-communication-contention.md) |
| 7 | GPU Architecture and CUDA | [详细笔记](./notes/07-gpu-architecture-cuda.md) |
| 8 | Data-Parallel Thinking | [详细笔记](./notes/08-data-parallel-thinking.md) |
| 9 | Spark | 官方材料（按需） |
| 10 | Efficiently Evaluating DNNs on GPUs | [详细笔记](./notes/10-dnn-gpu-optimization.md) |
| 11–13 | Cache Coherence、Memory Consistency、Lock-Free | 官方材料（按需） |
| 14–18 | DSL、Transactional Memory、Hardware、DRAM | 官方材料（按需） |

**阅读顺序不必和课程一致。** 对 AI Infra 优先 L2 → L5 → L6 → L7 → L8 → L10，之后再补 L11–13。

## 每篇笔记的固定结构

- 核心概念：它是什么；
- 成本模型：为什么快 / 为什么慢；
- 工程例子：如何体现；
- AI Infra 连接：和训练、推理、GPU 集群有什么关系；
- 自测与实践：能用实验验证什么。

## 正确性与适用范围

- **CS149 讲的是并行计算基础，不等于现代分布式训练完整课程。** NCCL、RDMA、FSDP、vLLM/SGLang 等需要在此基础上继续学习。
- Benchmark 结论必须附硬件型号、输入规模、代码版本、编译参数和重复次数；不能把不同机器的绝对速度直接比较。
- 本仓库的解释、例子和实验程序为独立撰写；Stanford 的课程材料及第三方资源归各自版权方所有。遇到版本差异，以 [Fall 2023 官方课程表](https://gfxcourses.stanford.edu/cs149/fall23/) 为准。

## 下一阶段

CS149（硬件与并行基础）→ CUDA / Triton → Stanford CS336（训练系统）→ PyTorch Distributed / NCCL → GPU Cluster 或 Inference Runtime。

欢迎通过 GitHub Issues 记录疑问；继续补充笔记时优先记录 **假设、实验、数据和结论**，而不是机械摘抄 Slides。
