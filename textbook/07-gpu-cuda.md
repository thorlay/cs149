# 第 7 章｜CUDA：从线程抽象到 GPU 的真实执行

> 对应 Stanford CS149 Fall 2023 主题 Lecture 7（2023-10-17）。原创中文教材第一版，根据官方 Slides 编写，并用公开视频入口核对课程主题。公开 Transcript 页面仅提供短预览，**尚未逐段核对完整字幕**。

**原始资料：** [2023 官方 Slides PDF（73 页）](https://gfxcourses.stanford.edu/cs149/fall23content/media/gpucuda/07_gpuarch.pdf) · [Stanford Online Lecture 7](https://www.youtube.com/watch?v=qQTDF0CBoxE) · [Glasp 文字预览](https://glasp.co/youtube/qQTDF0CBoxE)

**先修知识：** 了解 C/C++ 数组、for 循环和函数即可；本章从头定义 CUDA 的执行单位与内存层级，不要求先看其他讲次。**若没有 NVIDIA GPU，先做第 5 节的手算实验，也能理解 Shared Memory 的协作原理。**

## 学习目标

本章结束时，应能够画出 Host、Device、Grid、Block、Thread、Warp、SM 的关系；实现一个正确的 CUDA Kernel；解释并行粒度与 GPU 资源约束的关系；区分 Kernel-only 与端到端性能；以及对 GPU 内存访问建立初步成本模型。

## 一、GPU 为什么要有这么多线程？

CPU 的设计长期强调单线程指令执行的低延迟、复杂控制流与缓存效率。GPU 相对强调大规模规则工作负载的吞吐量：同样的数据变换，要对数百万个独立元素执行，单个元素并不复杂，但总体工作量巨大。

例如，对一幅图像每个像素执行亮度映射。如果像素之间没有依赖，把每个像素分配给独立线程非常自然。GPU 可以并发安排很多此类工作，以隐藏访存延迟并利用多个算术单元。

这里必须避免一个误解：GPU 不是“单个 CUDA Thread 比一个 CPU Thread 强”，而是不同的芯片架构为了不同目标做出的资源分配选择。

## 二、CUDA 编程模型：Host、Grid、Block、Thread

Host 一般是 CPU 上发起 Kernel 的代码；Device 是 GPU。一个 Kernel Launch 在逻辑上产生 Grid，Grid 包含多个 Blocks，Block 又包含多个 Threads。

我们用一个自己编写的数组加法 Kernel 来理解线程编号：

~~~cpp
__global__ void add_vec(int n,
                        const float* a,
                        const float* b,
                        float* out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        out[i] = a[i] + b[i];
    }
}
~~~

Host 端可以这样配置启动参数（假设 d_a、d_b、d_out 已经是合法的 Device 指针）：

~~~cpp
int threads = 256;
int blocks = (n + threads - 1) / threads;
add_vec<<<blocks, threads>>>(n, d_a, d_b, d_out);
~~~

在此例中，threadIdx.x 表示线程在 Block 内的位置；blockIdx.x 表示 Block 的编号；blockDim.x 是每个 Block 的线程数。

如果 n=1000，每个 Block 有 256 个线程，那么需要 4 个 Blocks，总共 1024 个逻辑线程。最后 24 个线程的 i 超过有效范围，因此边界检查是正确性要求，而非可选性能优化。

这也说明逻辑线程与数据元素之间的映射是一种**软件决策**：可以一个线程处理一个元素，也可以一个线程处理多个元素。

### Grid-Stride Loop

当任务很大时，一个更通用的映射是：

~~~cpp
__global__ void add_stride(int n,
                           const float* a,
                           const float* b,
                           float* out) {
    int tid  = blockIdx.x * blockDim.x + threadIdx.x;
    int step = gridDim.x * blockDim.x;

    for (int i = tid; i < n; i += step) {
        out[i] = a[i] + b[i];
    }
}
~~~

这里 step 是 Grid 中的**逻辑线程总量**。由于每个线程每次跨越整个 Grid 大小，前一轮中相邻线程仍可以读取相邻元素，维持规则的访存模式。

官方 Slides 约第 27 页包含二维 Grid/Block 的图示。二维、三维线程索引非常适合图像、网格与其他自然多维的数据，并不意味着 GPU 的物理核心以同样的二维格子排列。

## 三、Warp、SM 与 SIMT：代码里的线程怎么被硬件执行？

Thread 是 CUDA 对程序员提供的抽象，不等同于一个独占的物理运算核心。在 NVIDIA 架构上，硬件通常将 32 个 CUDA Threads 分成一个 Warp，SM（Streaming Multiprocessor）以 Warp 为重要调度和执行单位。

SIMT（Single Instruction, Multiple Threads）的思想是：程序员以“每个线程的代码”表达工作，硬件借助 Warp 把相同指令应用于多个线程。

例如：

~~~cpp
if (threadIdx.x % 2 == 0) {
    heavy_A();
} else {
    heavy_B();
}
~~~

同一个 Warp 内可能一半线程进入 A，另一半进入 B。硬件可能分别执行这两条路径，并屏蔽不参与当前路径的线程，这就是 Warp Divergence。

但不能简单认为凡是出现 if 都不好。需要看条件是否在同一 Warp 内分歧、各路径代价是否显著，以及编译器最终生成何种执行形式。

GPU 还可以保留多个 Warps 的执行上下文：当一个 Warp 等待数据时，SM 可以选择另一组就绪线程执行。这叫**隐藏延迟**。等待的内存访问本身未必变快，而是等待期间有其他有用工作可做。

课件以 NVIDIA V100 的 SM、Warp 与寄存器映射作教学示例（约 pp.49–61）。那些数值是特定 GPU 的资源配置，不能无条件套用到新型号。

## 四、内存层级：为什么计算单元常在等数据？

对 GPU Kernel 做性能建模时，数据的位置通常和算术指令数量一样重要。

| 内存层级 | 主要用途 | 工程注意点 |
| --- | --- | --- |
| Registers | 保存线程自己的计算状态 | 太多可能压低并发驻留量或发生溢出 |
| Shared Memory | 同一个 Block 的协作、Tiling | 容量有限，正确同步，注意 Bank Conflict |
| Global Memory / HBM | 大型输入、输出和中间 Tensor | 带宽、访问模式、重复数据移动 |
| Cache | 硬件管理的近端数据复用 | 行为依赖架构与访问模式 |
| Host Memory | CPU 侧的数据 | 设备间拷贝可能主导端到端时间 |

最简单的数组运算就足以暴露算力与带宽的区别：

~~~text
C[i] = A[i] + B[i]
~~~

如果数据为 float32，按一种简化的数据流量模型，每个元素读取 A 4B、读取 B 4B、写入 C 4B，总共 12B，而只完成约一次浮点加法。Arithmetic Intensity 大约是 1/12 FLOP/byte，这类算子很容易受内存带宽而非 GPU 峰值算力约束。

这个估计不等于硬件实际 DRAM 事务计数；Cache、地址对齐和实现细节可能改变实际流量。

### 合并访存（Memory Coalescing）

对一个 Warp 而言，线程访问连续、对齐且组织良好的地址，通常更容易由较少内存事务处理。

~~~text
理想化的规则访问：
lane 0 -> A[0]
lane 1 -> A[1]
lane 2 -> A[2]
...
lane 31 -> A[31]

间隔访问：
lane 0 -> A[0]
lane 1 -> A[1024]
lane 2 -> A[2048]
...
~~~

两组都各自读取 32 个数，但实际所需内存事务、Cache 命中行为可能差得很多。不能光数“读取元素数量”，还必须看访问地址的分布。

## 五、Shared Memory 与 Thread Block 的协作

假设我们实现一个 3-tap 一维卷积，每个输出元素要访问三个相邻输入。独立线程之间读取的输入窗口有大量重叠。

一个常见优化是让同一个 Block 的线程先合作把输入 Tile 装入 Shared Memory，再在片上复用它。需要将两端的 Halo 元素也装入，确保所有消费者开始读取前输入已经就绪。

### 一份可以复算的 3-point Stencil

定义长度为 N 的输入 x 与输出 y。为了固定边界行为，我们规定越界元素的值为 0：

```math
y_i = \frac{x_{i-1} + x_i + x_{i+1}}{3},\quad x_j=0\ \text{when } j<0\ \text{or } j\ge N
```

例如 x = [1, 2, 3, 4, 5] 时，答案应是 y = [1, 2, 3, 4, 3]。以 2 个线程一组的 Block 分工：

~~~text
Block 0: 线程处理 x[0], x[1]；还要装入右邻 x[2] 和左边界 0。
Block 1: 线程处理 x[2], x[3]；还要装入左邻 x[1] 和右邻 x[4]。
Block 2: 线程处理 x[4]，另一个逻辑线程没有有效输出；
         仍需要把其 shared-memory 槽位设为 0，右边界也是 0。
~~~

为什么需要 Shared Memory？相邻输出会重复访问输入，例如 x[1] 同时参与 y[0]、y[1]、y[2] 的计算。让每个 Block 一次性协同装入自身的输入段以及左右 Halo，可以在片上复用数据。下方程序使用 **Block 内 Barrier** 确保全体线程完成数据加载后再读取。这里的设计是一个教学示例；不能保证对所有尺寸都比直接从 Global Memory 读取更快。

### 完整可编译的 CUDA 程序

将下面内容另存为 avg3.cu。要求一块支持 CUDA 的 NVIDIA GPU、驱动和 nvcc 工具链；如果没有 GPU，可以先用上面的数组和公式在纸上验证输出。

~~~cpp
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>

#define CUDA_CHECK(call) do {                                      \
  cudaError_t err = (call);                                        \
  if (err != cudaSuccess) {                                        \
    std::fprintf(stderr, "CUDA: %s\n", cudaGetErrorString(err));  \
    std::exit(EXIT_FAILURE);                                       \
  }                                                               \
} while (0)

// 边界外的 x 元素按零处理，输出为三点平均。
__global__ void avg3(const float* x, float* y, int n) {
  extern __shared__ float tile[];
  int t = threadIdx.x;
  int i = blockIdx.x * blockDim.x + t;

  tile[t + 1] = (i < n) ? x[i] : 0.0f;
  if (t == 0)
    tile[0] = (i > 0) ? x[i - 1] : 0.0f;
  if (t == blockDim.x - 1)
    tile[blockDim.x + 1] = (i + 1 < n) ? x[i + 1] : 0.0f;

  __syncthreads(); // 所有线程完成加载后，才能读取邻居的槽位。
  if (i < n)
    y[i] = (tile[t] + tile[t + 1] + tile[t + 2]) / 3.0f;
}

int main() {
  const std::vector<float> x{1, 2, 3, 4, 5};
  const int n = static_cast<int>(x.size());
  const int threads = 2; // 刻意使用两个线程，便于手工复算。
  const int blocks = (n + threads - 1) / threads;
  const size_t bytes = n * sizeof(float);
  float *dx = nullptr, *dy = nullptr;
  std::vector<float> y(n);

  CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&dx), bytes));
  CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&dy), bytes));
  CUDA_CHECK(cudaMemcpy(dx, x.data(), bytes, cudaMemcpyHostToDevice));

  // 每个 Block：threads 个中心元素 + 左右各 1 个 Halo。
  avg3<<<blocks, threads, (threads + 2) * sizeof(float)>>>(dx, dy, n);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  CUDA_CHECK(cudaMemcpy(y.data(), dy, bytes, cudaMemcpyDeviceToHost));

  bool correct = true;
  for (int i = 0; i < n; ++i) {
    float left = (i > 0) ? x[i - 1] : 0.0f;
    float right = (i + 1 < n) ? x[i + 1] : 0.0f;
    float reference = (left + x[i] + right) / 3.0f;
    correct &= std::fabs(reference - y[i]) < 1e-5f;
    std::printf("%.4f%s", y[i], i + 1 == n ? "\n" : " ");
  }

  CUDA_CHECK(cudaFree(dx));
  CUDA_CHECK(cudaFree(dy));
  std::printf("correct=%s\n", correct ? "yes" : "NO");
  return correct ? EXIT_SUCCESS : EXIT_FAILURE;
}
~~~

在安装好 CUDA Toolkit 的终端运行：

~~~bash
nvcc -O2 -std=c++17 avg3.cu -o avg3
./avg3
~~~

数学上预期的输出（不是声称已经在真实 GPU 上实测）：

~~~text
1.0000 2.0000 3.0000 4.0000 3.0000
correct=yes
~~~

这里故意让 N=5、Threads Per Block=2：最后一个 Block 包含一个越界线程，能检测 Shared Memory 中“无效中心元素必须清零”这一常见边界问题。

**注意：** 代码为原理演示，当前尚未在 NVIDIA GPU 上完成端到端实机测试。正式 Benchmark 需要更多输入、Warm-up 和重复测量；不能依据这段小程序判断哪种 Stencil 最快。

这里 __syncthreads() 是**一个 Block 内**的 Barrier。不同 Blocks 之间不能假定天然同步，也不能按 Block 编号假定它们在同一 Launch 中依次完成。

Shared Memory 的使用也有成本：它占用每个 SM 有限资源，可能减少同时驻留的 Blocks；若原本通过 Cache 已实现良好的复用，手写 Tile 甚至可能变慢。

## 六、Occupancy 不等于有效吞吐量

SM 能同时驻留多少 Warps，与 Threads Per Block、寄存器使用量、Shared Memory 占用、硬件限制有关。Occupancy 可以帮助估计隐藏延迟的并发工作是否充足，但不是总性能的直接指标。

举例：一个 Kernel 使用更多寄存器来保存局部中间结果，使 Occupancy 降低；若因此显著减少 Global Memory 读写，最终运行时间反而可能更短。

系统优化应先找出瓶颈再调整参数，而不是机械追求最高 Occupancy 或最大的 Block。

## 七、必须做的实验：Kernel-only 与 End-to-End

本项目已有原创 [SAXPY CUDA Lab](../labs/README.md)。可以尝试：

~~~bash
nvcc -O3 -std=c++17 labs/saxpy.cu -o saxpy
./saxpy 1048576 256
./saxpy 4194304 128
./saxpy 4194304 256
./saxpy 4194304 512
~~~

依次记录：

1. Kernel-only 时间（正确同步）；
2. 包含 H2D + D2H 内存传输的总时间；
3. 每个版本的 correctness；
4. N、Threads Per Block、GPU 型号、编译参数。

一个用来推理而不是声称实测的示意例子：

~~~text
原始：传输 120 us + Kernel 10 us = 130 us
优化：传输 120 us + Kernel  5 us = 125 us
Kernel 自身加速：2.0x
端到端加速：130/125 = 1.04x
~~~

这提醒我们：算子优化不等于系统优化。对实际推理系统而言，输入数据的驻留位置、Batch 与调度策略可能远比这个 Kernel 的单独耗时重要。

## 八、AI Infrastructure 的进一步联系（课外扩展）

在 LLM 系统中，本讲知识能直接用于理解：

- Triton 如何在 Tile 粒度表达 GPU 计算；
- FlashAttention 为什么重视片上数据复用和 Global Memory 流量；
- vLLM、SGLang 为什么除 Kernel 外还需要持续批处理与 KV Cache 管理；
- 多 GPU 训练为什么同时需要 NCCL、通信与计算重叠和跨节点网络。

这些是结合当前 AI Infra 生态的扩展，不是把现代系统细节冒充为 2023 年 Lecture 7 的原始教学内容。

## 九、练习（含简答）

**1. N=10001，threads=256，需要几个 Blocks？**  
答：ceil(10001/256)=40，总逻辑线程 10240，多出的 239 个由边界判断处理。

**2. Shared Memory 是否所有 Blocks 共用？**  
答：不是。每个 Block 使用自己的逻辑 Shared Memory 区域。要跨 Blocks 合并结果，需要设计全局存储、原子操作或适当分阶段执行。

**3. 更大的 Block Size 是否总让 GPU 更快？**  
答：否。它改变 Warp 分组与资源使用，有可能改善某些执行特征，也可能导致资源压力、占用率下降。必须测量。

**4. GPU FLOPs 翻倍但 SAXPY 没快，可能为什么？**  
答：SAXPY 可能已受内存带宽约束；此外还需排查数据规模、缓存、Launch、频率和传输成本。

## 术语小词典：不需要翻查前一讲

| 术语 | 本章中的含义 |
| --- | --- |
| Kernel | 在 GPU 上执行的函数，一次 Launch 创建一个 Grid |
| Thread | 程序员看到的最小逻辑执行实例 |
| Block | 一组可共享 Shared Memory、进行 Block 内同步的 Threads |
| Grid | 一次 Kernel Launch 中所有 Blocks 的集合 |
| Warp | NVIDIA GPU 执行与调度中的线程分组，通常包含 32 Threads |
| SM | Streaming Multiprocessor，调度并执行若干 Warps 的硬件单元 |
| SIMT | Single Instruction, Multiple Threads，按线程编程并以 Warp 执行的基本模型 |
| Occupancy | SM 活动 Warps 相对于硬件可支持最大数量的比例 |
| Coalescing | 将相邻线程的内存访问组织成高效 Memory Transactions |
| Halo | 分块计算时，为块边界上的输出而额外加载的邻近输入元素 |
| H2D / D2H | Host-to-Device 与 Device-to-Host 内存传输 |

**完整性自测：** 不打开 Slides，能否解释为什么我们的 avg3 程序需要两个 Halo、为什么调用 Barrier、为什么最后一个 Block 的越界线程不能随意读取内存，以及为何 Shared Memory 不保证提速？如果能说明这些原因，就已经掌握了这一部分最重要的概念。

## 来源核验

| 来源 | 用途 | 状态 |
| --- | --- | --- |
| [2023 L7 官方 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/gpucuda/07_gpuarch.pdf) | CUDA 线程层次、Warp/SM、Block 执行与资源约束 | 已查阅 PDF 关键文本和图页 |
| [Stanford Online 视频](https://www.youtube.com/watch?v=qQTDF0CBoxE) | 讲课视频 | 入口已核实 |
| [Glasp L7](https://glasp.co/youtube/qQTDF0CBoxE) | 截断的文字稿预览 | **不是完整 Transcript** |

> 本章内容为原创的教学解释和例子，不复制或逐页翻译官方 Slides，不代表 Stanford 官方立场。
