# Lecture 7 — GPU Architecture and CUDA Programming

**对应课程：** [CS149 Fall 2023，Oct 17](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** SIMT、Warp、SM、Grid、Block、Coalescing、Occupancy

## 1. CPU 与 GPU 的设计侧重点

CPU 通常把较多芯片资源用在复杂控制流、低延迟缓存与单线程性能。GPU 更强调高吞吐量，通过大量线程与算术单元处理数据并行。

GPU 并不意味着每个线程都运行得更快；它依赖 **大量独立工作** 来隐藏内存延迟和维持吞吐量。

### CUDA 逻辑层级

- **Thread**：执行一个 Kernel 的某个逻辑实例；
- **Block**：一组线程，能利用 Block 内共享内存和 Block 内同步；
- **Grid**：一次 Kernel Launch 包含的所有 Blocks；
- **Warp**：NVIDIA GPU 的线程执行分组，常见大小为 32；
- **SM（Streaming Multiprocessor）**：GPU 的硬件执行资源，调度驻留在其中的 Warps。

不要把 Block 当成一块固定的物理核心，也不要假设不同 Blocks 可用普通 Block Barrier 同步。

## 2. SIMT 和 Divergence

SIMT = Single Instruction, Multiple Threads。Warp 中线程执行同一指令流时效率较高。如果同一个 Warp 的部分线程进入 if 分支、另一部分进入 else，硬件可能需要分别执行路径并屏蔽不活跃线程。

例子：

```cpp
if (threadIdx.x % 2 == 0) {
    // heavy path
} else {
    // another heavy path
}
```

即使半数线程走一边，执行资源也未必能像两个独立任务那样充分使用。

并非所有分支都一定严重：关键在分支是否在同一 Warp 内发散，以及每条路径的计算成本。

## 3. Grid-Stride Loop

对于长度 N 的数组，不必假定网格只有一次覆盖所有元素。常见写法：

```cpp
__global__ void saxpy(int n, float a, const float* x, float* y) {
    for (int i = blockIdx.x * blockDim.x + threadIdx.x;
         i < n;
         i += blockDim.x * gridDim.x) {
        y[i] = a * x[i] + y[i];
    }
}
```

好处：Kernel 对 N 和 Launch Grid 的组合更通用；连续线程首先访问连续元素，有利于合并访存。

可运行完整示例见 [labs/saxpy.cu](../labs/saxpy.cu)。

## 4. GPU Memory Hierarchy

### Global Memory（通常是 HBM/GDDR）

容量大、跨 SM 可访问，但访存延迟和带宽有明确限制。优化重点常包括合并访问、减少重复读取、增加计算与传输的重叠。

### Shared Memory

Block 内线程协作使用的高速片上存储。适合 Tiling 与数据复用，使用时要正确同步，并关注 Bank Conflict。

### Register

线程的私有快速存储资源，但每个 SM 的总寄存器数量有限。使用过多寄存器可能降低同时驻留的线程 / Warps。

### Cache

不同 GPU 架构有不同的 L1 / L2 缓存结构与策略；不能简单照搬 CPU Cache 的全部假设。

## 5. Memory Coalescing

一个 Warp 的线程若访问相邻、对齐并且组织合理的地址，硬件往往能够使用较少 Memory Transactions 满足这些访问。反之，Strided 或 Scatter 访问可能显著增加实际内存流量。

示例：
- 较好：线程 t 访问 A[base + t]；
- 较差：线程 t 访问 A[base + t * 1024]。

具体事务数与硬件、Cache、地址对齐、数据类型有关，需用 Profiler 实测。

## 6. Occupancy 不是越高越好

Occupancy 常用来描述活动 Warps 相对于硬件允许最大值的比例；它受 Thread Block Size、Registers / Thread、Shared Memory / Block 等限制。

提高 Occupancy 有助于隐藏等待，但不直接保证性能提高：
- 更大 Block 不一定更快；
- 过度追求 Occupancy 可能增加寄存器溢出；
- Kernel 可能已经被内存带宽或指令吞吐限制。

真正目标是缩短 **有意义工作** 的完成时间，不是把单一硬件指标拉满。

## 7. CUDA 同步与常见错误

- `__syncthreads()` 是 Block 范围同步，不是整个 Grid 的跨 Block Barrier。
- 不同线程写入同一位置，除非有明确的无竞争设计或正确使用原子操作，否则可能出现数据竞争。
- Kernel Launch 通常是异步的；直接用主机端计时器围住 Launch 而不同步，会严重低估完成时间。
- 设备内存申请、H2D 传输、Kernel 执行、D2H 传输要分别计时，否则很难定位优化空间。

## 8. 实际实验顺序

1. 写最简单的正确 Kernel；
2. 测 Kernel-only 时间；
3. 测包括 H2D / D2H 的端到端时间；
4. 依次改变 N 与 threads/block；
5. 观察带宽估计值与吞吐量变化；
6. 再考虑更复杂优化。

**实验代码：** [CUDA SAXPY](../labs/README.md)。

## AI Infra 连接

- FlashAttention 利用 GPU 片上数据复用降低对 HBM 的访存压力；
- Triton 允许更直接地表达 Tile-based GPU Kernel；
- LLM Inference 的 Prefill / Decode 阶段可能出现不同的计算与访存行为；
- NCCL 和 NVLink 解决跨 GPU 数据传输，是 L7 之后的进阶主题，不是 CUDA Thread 模型本身。

## 自测

1. Warp 与 Block 为什么不是同义词？
2. 如何判断 Kernel 慢是 Launch Overhead 还是 HBM 带宽？
3. Coalescing 和 Shared Memory Tiling 是否解决同一种问题？
4. 为什么没有正确同步时的 GPU 计时可能看起来“快得不真实”？

**下一篇：** [L8 Data-Parallel Thinking](./08-data-parallel-thinking.md)。
