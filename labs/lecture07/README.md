# Lecture 07：GPU 架构与 CUDA 编程实验

配套教材：[第七章](../../textbook/07-gpu-cuda.md)。完整源代码亦收录于教材。

## 无 GPU：Python 语义模型（已运行）

```bash
python3 labs/lecture07/models.py
```

只需 Python 3 标准库，固定输出：

```text
avg3: cases=84 two_block_orders=pass tile_writers=pass outputs=pass
matrix: cases=18 exact_once=pass 11x5_launch=72 valid=55
grid_stride: cases=48 exact_once=pass
missing_barrier: uninitialized_neighbor_counterexample=detected
sector_model: aligned=4 offset_one_float=5 stride32=32
residency: toy_blocks_per_SM=2; register32=8 register64=4
cross_block: producer_first=complete consumer_first=deadlock; histogram_order=pass
all_checks=pass
```

三点平均采用 N 项输入、N 项输出、越界输入为 0；N=0/1/2/3/5/31/32/33/127/128/129/257，Block=1/2/7/32/64/128/256。每组按正序和倒序执行 Block，检查支持区单写者、阶段后有效读取、输出覆盖和参考结果。

二维索引为 6 种尺寸 × 3 种 Block；Grid-Stride 为 12 种 N × 4 种线程总数。模型还推演 32-byte 段计数、简化资源上界、删屏障的未初始化读取与单槽位跨 Block 等待。

这是确定性语义/算术模型，不执行 CUDA、不模拟 GPU 时钟或真实内存事务，也不穷举所有设备调度。反例检测不会真的启动无限循环。

## 有 NVIDIA GPU：CUDA 练习（本次未编译、未运行）

要求兼容的 NVIDIA GPU、驱动和 CUDA Toolkit；测试配置要求至少支持 256 线程/Block。

```bash
mkdir -p /tmp/cs149-l07-build
nvcc -O2 -std=c++17 labs/lecture07/cuda_basics.cu \
  -o /tmp/cs149-l07-build/cuda_basics
/tmp/cs149-l07-build/cuda_basics
```

设计预期输出，**非实测**：

```text
avg_cases=84 matrix_cases=18 histogram_cases=12 tail=pass correct=yes
```

包含直接与 Shared 三点平均、二维矩阵加法、原子直方图；按 CPU 参考逐项检查，浮点绝对误差容限 1e-6，输出末尾 8 项哨兵不应被改写。直方图输入限定整数 0…9。配置计数包含空输入的 Host 跳过路径，不是 Kernel 启动次数。

本机为 macOS ARM64，未检测到 nvcc，无 NVIDIA GPU 实机验证；不声称 CUDA 编译、设备同步或性能已通过。不把 Python 检查代替为 GPU 检查。

在具备 Compute Sanitizer 的目标环境进一步执行：

```bash
compute-sanitizer --tool memcheck /tmp/cs149-l07-build/cuda_basics
compute-sanitizer --tool racecheck /tmp/cs149-l07-build/cuda_basics
compute-sanitizer --tool synccheck /tmp/cs149-l07-build/cuda_basics
```

这些工具本次也未运行。先通过正确性，再扩大规模并使用正确的 Event/Stream 完成等待计时，预热和重复，分别报告 Kernel 与端到端时间。不要从标量读取次数直接推断真实 DRAM 流量或固定提速。
