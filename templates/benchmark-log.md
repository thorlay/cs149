# Benchmark 实验记录模板

> 每次仅改变一个主要变量，并把性能数字和测试边界绑定。不要把单次运行误当作结论。

## 1. 假设（Prediction）

- 需要回答的问题：
- 预计瓶颈：Compute / Bandwidth / Latency / Scheduling / Synchronization / 不确定
- 修改点：
- 为什么预计会改善：

## 2. 环境（Reproducibility）

- 日期：
- Repo Commit SHA：
- CPU / GPU：
- GPU Driver / CUDA Toolkit：
- OS：
- 编译器与 Flags：
- 输入 N / Shape / dtype：
- 数据位置：Cache / DRAM / HBM / Host↔Device
- 计时边界：Kernel-only / Transfers-included / End-to-end
- Warm-up 次数：
- 测试重复次数：

## 3. 结果（Measurement）

| 方案 | 输入 | Block/Threads | 中位数 ms | P95 ms | 相对基线 Speedup | 正确性 |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline |  |  |  |  | 1.00x |  |
| Variant A |  |  |  |  |  |  |
| Variant B |  |  |  |  |  |  |

Speedup = Baseline time / Variant time。时间更小才是更快。

## 4. 分析（Explanation）

- 实测是否符合 Prediction？
- 如果不符合，有哪些替代解释？
- 测量噪声、GPU 时钟变化、Cache 热度、编译选项是否可能影响结论？
- 下一次实验要改哪个变量？

## 5. 结论与局限

用 3–5 句话描述：在什么环境、什么输入、什么测量边界下，观察到了什么结果；哪些结论不能外推。
