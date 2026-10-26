# Lecture 5 — Work Distribution and Scheduling

**对应课程：** [CS149 Fall 2023，Oct 10](https://gfxcourses.stanford.edu/cs149/fall23/)  
**关键词：** Work、Span、Load Balance、Static vs Dynamic、Work Stealing、Granularity

**完整教材：** [第五章：工作分配与调度](../textbook/05-work-distribution-scheduling.md)，包含推导、代码、习题与参考答案。

## 1. 并行性能的两个基本量

**Work (T1)**：整个任务需要执行的总工作量；通常可理解为在单个处理器上执行这份并行算法的成本。

**Span (T∞)**：依赖图中最长路径上的工作量，也称 critical path。在处理器数量无限时，依赖约束仍然无法突破这条路径。

P 个处理器上的时间 TP 满足两个下界：
- TP ≥ T1 / P：总工作需要被 P 个处理器消化；
- TP ≥ T∞：关键路径不可再被并行化。

因此理论并行度为 T1 / T∞。如果 T1 很大但 T∞ 也很大，堆更多核未必有效。

例子：100 个互不依赖任务，每个耗时 1 ms，另有串行收尾 20 ms。即使处理器数量无限，理想完成时间也不小于 21 ms。

## 2. 为什么 Load Balance 很重要

假设 4 个 Worker 得到的任务耗时分别为 [1, 1, 1, 9] 秒。
- 总工作量 = 12 秒；
- 理论完美平衡的下界 = 3 秒；
- 实际执行时间约 9 秒（忽略启动开销）。

问题不在总计算量，而在负载分配不均。典型来源有：
- Mandelbrot 中不同像素的迭代次数不同；
- 图算法的节点度数差异；
- 推理中不同请求的输入长度和生成长度不同；
- 并行文件处理中文件大小不同。

## 3. Static Scheduling 与 Dynamic Scheduling

**静态调度**：提前固定每个 Worker 的任务集。优点是调度开销小、数据局部性更可预测；缺点是任务成本不均时容易出现尾部 Worker。

**动态调度**：Worker 做完任务后继续取任务。优点是处理长尾更灵活；缺点是队列竞争、任务分发、同步开销更高。

**Chunk Size 是核心旋钮**：
- Chunk 太大：调度便宜，但可能分配不均；
- Chunk 太小：负载平衡好，但调度成本高、局部性可能变差。

找最佳 Chunk 不是拍脑袋，而是控制变量、重复测量。

## 4. Work Stealing 的直觉

每个 Worker 有自己的本地任务队列。
1. Worker 优先执行本地工作；
2. 本地队列为空时，从其他 Worker 的队列“偷”一部分任务；
3. 偷取使空闲处理器重新获得工作，缓解不规则任务造成的失衡。

它适合动态生成依赖图的任务，如递归 Fork-Join。缺点包括队列管理成本、偷取导致的局部性损失，以及内存竞争。它不保证所有工作负载都最优。

## 5. 任务粒度：什么时候值得并行

创建一个 Task 本身有成本：入队、唤醒、同步、状态管理。若任务只做几十纳秒的工作，调度开销可能比计算还高。

经验原则：先估计“有用计算 / 调度开销”比例，再考虑分片。对于微小数组，串行或向量化方案可能优于多线程。

## 6. 与 AI Infra 的连接

**GPU Kernel**：每个 Thread / Block 的工作分布与数据布局决定负载均衡、占用率及内存行为。

**Inference Scheduler**：请求长度、Batch 动态变化，决定了 GPU 是否持续有足够的有效工作；但推理的调度目标还包括 TTFT、TPOT、公平性和 SLA，不能只追求最大吞吐。

**Training Pipeline**：输入 Pipeline、Data Loader、CPU preprocessing、GPU compute 可能构成流水线；任一阶段长尾都会降低整体利用率。

## 实验设计

以 Mandelbrot 或一组耗时随机的 CPU Task 为对象：

| 方案 | 控制参数 | 预期 |
| --- | --- | --- |
| Static | 每 Worker 固定 N/4 | 任务成本均匀时开销低 |
| Dynamic-large | 大 Chunk | 调度成本较低，可能有尾部空闲 |
| Dynamic-small | 小 Chunk | 更平衡，但抢队列更频繁 |

除了总耗时，建议记录每个 Worker 的实际工作量和等待时间。

## 自测

1. 为什么工作总量很大不代表并行度很高？
2. 工作窃取什么时候会破坏 Cache Locality？
3. 哪些指标能区分“任务太少”与“负载不均”？
4. 对长度不等的 LLM 请求，你会怎样设计公平的推理调度？

**下一篇：** [L6 Locality、Communication、Contention](./06-locality-communication-contention.md)。
