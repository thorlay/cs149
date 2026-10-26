# Lecture 8 — Data-Parallel Thinking

**对应课程：** [CS149 Fall 2023，Oct 19](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** Map、Reduce、Scan、Prefix Sum、Scatter、Gather、Compaction

## 1. 为什么数据并行原语重要

许多 GPU 算子不是从算法零件开始，而是由少量可组合的并行模式构成：

- **Map**：每个输入独立映射为一个输出；
- **Reduce**：把多个输入合并成一个值（例如 sum、max）；
- **Scan / Prefix Sum**：生成每个前缀的聚合结果；
- **Gather / Scatter**：按索引读取 / 写入；
- **Filter / Compaction**：只保留满足条件的元素。

独立映射容易并行；带依赖的聚合通常需要树形分解或分层计算。

## 2. Map

给定数组 x 和纯函数 f，输出 y[i] = f(x[i])。各元素互不依赖，是理想的数据并行问题。

注意两个性能限制：
1. f 很小且读取 / 写入很多数据时，可能受内存带宽限制；
2. 每个元素计算开销很小时，Kernel Launch Overhead 可能不容忽视。

将连续的 Map 操作融合为一个 Kernel，可以避免不必要的中间结果写回。

## 3. Reduction

求和 S = sum(x[i]) 看似顺序依赖，但在数值允许的条件下可以构造成树：

- 第 1 层：每对元素合并；
- 第 2 层：合并上一层结果；
- 直到剩余一个值。

理想平衡树的 Span 约为 O(log N)，总 Work 为 O(N)。实际 GPU 通常先在 Block 内部分归约，再归约 Block 的结果。

**浮点注意：** 浮点加法不严格满足数学实数的结合律。改变归约顺序可能导致尾数有微小变化。测试应使用合理误差容忍，而不是要求任意规模严格 Bitwise 相等。

## 4. Scan（Prefix Sum）

给定输入 [2, 1, 3, 4]：

- Inclusive Scan → [2, 3, 6, 10]
- Exclusive Scan → [0, 2, 3, 6]

Scan 不只是“算几个前缀和”。它是并行内存分配和位置计算的基础。

例如对 [T, F, T, T] 进行布尔 Compaction：
1. 把布尔标志转成 [1, 0, 1, 1]；
2. Exclusive Scan 得到 [0, 1, 1, 2]；
3. 对每个 True 元素，用对应前缀位置把元素写入紧凑输出。

这样就能为保留的元素计算无冲突目的位置。

## 5. Parallel Scan 的算法权衡

**Hillis–Steele 风格的并行 Scan**：各轮按照 1、2、4、8… 个位置的距离聚合，Span 为 O(log N)，但总 Work 通常为 O(N log N)。

**Blelloch 风格（Up-sweep / Down-sweep）**：可得到 O(N) Work 和 O(log N) Span 的并行 Scan，但需要多阶段读写与同步。

大数组通常还需要跨 Block 的层次化算法；只实现单 Block Scan 并不意味着已经解决全局 Scan。

## 6. Scatter、Gather 与访问模式

**Gather**：output[i] = input[index[i]]，目标写入通常简单，但输入读取可能离散。

**Scatter**：output[index[i]] = input[i]，写入可能离散，且当 index 重复时需处理写冲突。

若多个线程写同一位置，必须明确聚合语义、原子操作或其他无冲突分配机制。

## 7. 和 AI Infra 的连接

- LayerNorm / Softmax 涉及 Reduction；
- GPU 数据筛选、Prefix Sum、Token Packing 可以使用 Scan / Compaction；
- Attention 的 Softmax 需要稳定数值处理（例如先减去最大值）；
- Kernel Fusion 旨在减少中间存储和额外启动成本；
- Sparse 算子经常涉及 Gather / Scatter 和不规则访存。

## 一个值得动手的实验

使用官方 [Assignment 3 的 Scan Warm-up](https://github.com/stanford-cs149/asst3)：
1. 先写一个正确版本；
2. 检查 inclusive / exclusive 定义；
3. 测小数组和大数组；
4. 记录同步次数、Work、Span 和占用的临时存储；
5. 分析为什么更少的数学操作不一定等于更短的执行时间。

## 自测

1. Reduce 与 Scan 的输出形状如何不同？
2. 为什么 GPU 上的并行求和可能与 CPU 结果略有差异？
3. Prefix Sum 如何帮助把“筛选结果”写入连续输出？
4. Scatter 发生地址冲突时，哪种方案能保证正确性？

**下一篇：** [L10 DNN GPU 优化](./10-dnn-gpu-optimization.md)。
