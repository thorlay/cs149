# Lecture 05：工作分配与调度实验

配套教材：[第五章](../../textbook/05-work-distribution-scheduling.md)。本目录是独立编写的教学实验，不是课程作业的完整实现，也不提供无锁运行时。

## Python 调度模型

只依赖 Python 3 标准库，从仓库根目录运行：

```bash
python3 labs/lecture05/scheduling_models.py
```

预期输出：

```text
static_block=[36, 4, 4, 4] static_cyclic=[12, 12, 12, 12]
long_task_last=16 long_task_first=13
dag_work=11 dag_span=8 two_worker_time=8
steal_trace_coverage=pass cycle_detection=pass
buffer_slot_arithmetic=pass all_checks=pass
```

时间都是抽象成本单位。Deque 模型是固定顺序的串行轨迹，用于检验区间分裂与覆盖，没有实现随机运行时、同步点或真实并发。槽位检查只验证算术关系，不替代并发协议证明。

## C++17 线程分配实验

需要 C++17 工具链，不需要 GPU、OpenCilk 或 ISPC。

```bash
mkdir -p /tmp/cs149-l05-build
c++ -O2 -std=c++17 -pthread labs/lecture05/scheduling.cpp \
  -o /tmp/cs149-l05-build/scheduling
/tmp/cs149-l05-build/scheduling --check
/tmp/cs149-l05-build/scheduling 4
```

固定正确性输出：

```text
cases=108 exact_once=pass outputs=pass all_checks=pass
```

检查覆盖 6 种规模（0、1、3、19、128、257），1/2/4 个 Worker，以及连续、循环与块长 1/4/16/64 的动态分配。验证模式启用原子访问次数统计，要求每项恰好执行一次，并逐项对照串行参考答案。

观察模式使用 128 项输入，前四分之一的内部计算为 120000 次迭代，其余为 4000 次；打印各 Worker 的工作量和时间。动态领取数包含每个 Worker 最后一次发现没有任务的操作，等于 ceil(N/g)+P。

`wall_ms` 包含线程创建与 join，输入初始化、串行参考答案与最终校验在计时之外。`task_ms` 是 Worker 内逐任务计时的累计值，不能把所有 Worker 的值相加后直接从墙钟中扣除。读时钟本身和系统抢占也会影响结果。

已验证环境：macOS ARM64、Apple Clang 16、`-O2 -std=c++17 -pthread`。108 种组合全部通过，并运行了 4 Worker 观察模式。时间因机器和负载变化；程序不规定固定加速比。若做性能结论，应另行预热、重复并报告中位数，保持输入、计时边界与计算任务一致。
