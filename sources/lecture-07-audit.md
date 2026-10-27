# Lecture 07 来源核验记录（公开版）

**教材：** [第七章：GPU 架构与 CUDA 编程](../textbook/07-gpu-cuda.md)

**来源：** [官方课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/gpucuda/) · [73 页课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/gpucuda/07_gpuarch.pdf) · [录像](https://www.youtube.com/watch?v=qQTDF0CBoxE)

## 阅读与视觉核验

用户提供的无时间码英文自动文字稿全文已阅读，从开场图形历史到跨 Block 等待标志反例；有听不清、术语误识别和口述简化，未逐句核验原音。

课件全部文字结构已核对，视觉抽查第 28、30、37、38、50、53、60、69 页；未逐页视觉复核。Persistent Threads 为课件补充，不冒充文字稿详细讲过的内容。

| 页码 | 主题 | 教材处理 |
| --- | --- | --- |
| 4–24 | 图形负载、早期 GPGPU、Brook、Compute Mode | 原创历史概述，不复用图片、字幕或公司市值等时点说法 |
| 25–34 | Thread/Block、二维索引、Host/Device 与内存 | 独立覆盖证明、11×5 算例、作用域与物理位置分开 |
| 35–40 | 三点平均、Shared、同步 | 保留原教材零边界，并明确与课件 N+2 输入的对应 |
| 41–44 | 编译资源与 Block 调度 | 区分逻辑线程、驻留与当前执行 |
| 45–53 | Warp、V100 SM、乘加单元与峰值 | 按历史参数复算，区分吞吐、延迟、Block 与 SM 容量 |
| 55–64 | 假想双核 GPU 的资源分配 | 1536/520 与 384/128 分别计算，不能塞第三块 |
| 66–69 | Block 协作、原子直方图、跨 Block 忙等 | 使用语义模型与具体不进展调度，未运行死循环 |
| 70–73 | Persistent、总结与 Tensor Core 提示 | 明确补充材料和未实现范围，不发布有省略的伪代码 |

## 关键修正

1. 第 28 页“启动调用返回时线程全结束”、第 38 页相关简写不符合普通 CUDA Host 异步启动语义。完整代码显式检查发射错误并等待设备完成。
2. 130 个 float 为 520 byte；口述中的 512 byte 不沿用。
3. 每 SM 最多 2048 驻留线程不等于每 Block 可含 2048 线程；V100 的单 Block 上限是 1024。
4. V100 图的 128 KiB 为 L1/Shared 共用物理容量，不是任意 Block/SM 可申请的 Shared 配额；对照 Volta 指南区分最高 96 KiB Shared 与静态分配/显式选择限制。
5. Warp 有可见的 Warp 级接口，不能把基础模型中的“实现细节”理解为绝对不可观察。
6. Shared 不等于 ISPC uniform；线程私有变量也不保证都在物理寄存器，CUDA Local Memory 不等于最快本地存储。
7. UVA、Managed 和映射 Host 内存分开；不把任意普通指针都可用、或必走 PCIe 当作通用事实。
8. 第 40 页等示意缺少分配的 sizeof 乘数、部分后续版本省略除以 3；独立完整程序使用正确字节量与统一算术定义。
9. 直接版 384 与 Shared 版 130 是线程级标量读取量，不是物理指令/DRAM 事务计数或必然提速。
10. 第 70 页原子领取不能把 atomicInc 直接当作按块长 atomicAdd；仅说明 Persistent 思想，不发布该伪代码为正确程序。
11. Volta 独立线程调度不取消同步义务，不依据 PC 直觉声称可自动重组任意线程或安全锁步交换。

## 一手文档

- [CUDA C++ 入门](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/intro-to-cuda-cpp.html)：启动、索引、边界和完成等待。
- [SIMT Kernel](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html)：Shared 与 Block 同步。
- [统一与系统内存](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/understanding-memory.html)：统一地址、Managed 和 Host 内存支持。
- [Volta 调优指南](https://docs.nvidia.com/cuda/volta-tuning-guide/index.html)：寄存器、Warp、Shared 配额、独立线程调度。
- [高级 Kernel 编程](https://docs.nvidia.com/cuda/cuda-programming-guide/03-advanced/advanced-kernel-programming.html)：相关现代语义边界。

- [NVIDIA 官方架构比较表](https://developer.nvidia.com/blog/nvidia-ampere-architecture-in-depth/)：核对 V100 最大线程块 1024，区别每 SM 驻留 2048。

## 实际执行与未执行

| 项目 | 状态 |
| --- | --- |
| Python 标准库模型 | macOS ARM64 已运行，通过全部断言 |
| 三点平均 | 84 种配置，各验证正序/倒序 Block，支持区唯一写者、结果与参考通过 |
| 二维映射 | 18 组，合法坐标恰好一次，11×5 启动 72、有用 55 |
| Grid-Stride | 48 组，含空输入及线程数大于 N，覆盖恰好一次 |
| 同步与资源模型 | 检测缺屏障读取与单槽位忙等；寄存器、Shared、段计数和峰值算术通过 |
| cuda_basics.cu | 完整源代码人工对照模型检查，**未使用 nvcc 编译、未在 GPU 运行** |
| Compute Sanitizer | 未运行，不声称设备端无竞争或无越界 |
| GPU 性能 | 未计时、不提供实测速度或带宽 |

本机无 nvcc，Apple Silicon 不构成本章 NVIDIA CUDA 实机测试环境。预期 CUDA 输出只说明测试设计，不能当作已通过记录。模型不枚举真实设备全部交错，不验证驱动/编译器，不模拟真实 Cache。原始全文、官方 PDF 与临时图片保留仓库外；公开库仅提交原创文字、代码和来源链接。
