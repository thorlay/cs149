# Lab 01 — CUDA SAXPY：从正确性到性能解释

这是一份**独立撰写**的简化练习程序，与 Stanford 官方 Assignment 3 的代码不同。用途是帮助学习 Kernel Launch、合并访存和计时边界。

## 环境

需要 NVIDIA GPU、兼容的 NVIDIA Driver 与 CUDA Toolkit（含 nvcc）。macOS Apple GPU 不能直接运行原生 NVIDIA CUDA 代码。

检查：

```bash
nvidia-smi
nvcc --version
```

编译与运行（从仓库根目录）：

```bash
nvcc -O3 -std=c++17 labs/saxpy.cu -o saxpy
./saxpy 1048576 256
./saxpy 4194304 128
./saxpy 4194304 256
./saxpy 4194304 512
```

参数分别是 N 和 Threads Per Block。程序会验证输出，并显示：
- Kernel-only 时间（CUDA Events）；
- H2D + Kernel + D2H 总时间（主机 Steady Clock）；
- Kernel-only 有效带宽估计（按每元素 12 bytes，**模型值而非设备实际读写计数**）。

## 实验 1：输入规模

在相同 Block Size 下运行 N=1024、65536、1048576、4194304。解释为什么小 N 的 Kernel 耗时不容易随 N 成比例增长，以及端到端耗时为什么可能显著高于 Kernel-only。

## 实验 2：Block Size

固定 N=4194304，比较 64、128、256、512 threads/block。提前写出预测，再看数字。

Block Size 影响线程分组和资源使用，但“更大一定更快”是错误的。

## 实验 3：为什么是 Memory-bound

用估算流量 12 × N bytes 除以测得的 Kernel 秒数，得到粗略有效带宽（GB/s）。

这个值只用于初步诊断；它假设每个元素读取 x、读取 y、写 y，不包含 Cache 或实际硬件事务的复杂情况。若测量时间极短，结果可能受计时精度和运行状态影响。

## 正确 Benchmark 的注意事项

- 首次 CUDA 上下文初始化可能非常慢，不应与稳态结果混合；
- GPU 温度、频率、电源模式、其他进程负载都会改变结果；
- Kernel-only 不包括内存分配、Host↔Device 传输；
- 单次运行不足以支持优化结论，扩展时应做 Warm-up + 多次重复；
- 如果使用云 GPU，请记录实例类型、GPU 型号、驱动、CUDA 版本。

结果可以直接复制到 [Benchmark 模板](../templates/benchmark-log.md)。

官方完整课程作业：[Stanford CS149 Assignment 3](https://github.com/stanford-cs149/asst3)。

## Lecture 02：CPU Cache / Multicore / SIMD

[三段可运行实验与编译命令](./lecture02/README.md)。正文同样包含完整代码，实验目录仅供方便执行。

## Lecture 03：延迟、带宽与 ISPC

[Python 模型与 ISPC 三种分配实验](./lecture03/README.md)：包含可直接在 Apple Silicon 上运行的 NEON 版本与边界校验。

## Lecture 04：并行编程基础

[Python 语义模型、ISPC 归约与完整 C++17 红黑求解器](./lecture04/README.md)：覆盖数值差异、阶段同步与残差检查。

## Lecture 05：工作分配与调度

[Python 调度模型与 C++17 多线程实验](./lecture05/README.md)：对照连续分块、循环分配和动态块，包含依赖图与区间偷取推演。

## Lecture 06：局部性、通信与竞争

[消息协议、Halo、缓存模型与 C++ 融合实验](./lecture06/README.md)：无需 GPU 或集群，包含模型假设、正确性检查与可选计时。

## Lecture 07：CUDA 语义模型与基础练习

[CPU 推演与完整 CUDA 练习](./lecture07/README.md)：Python 模型已运行；CUDA 程序含三点平均、二维加法和直方图，尚未编译或在 NVIDIA GPU 实测。
