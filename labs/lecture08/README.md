# Lecture 08：数据并行原语与 Scan 实验

配套教材：[第八章](../../textbook/08-data-parallel-thinking.md)。两份完整源代码也收录于教材，无需 GPU。

## Python：算法与应用流水线（已运行）

```bash
python3 labs/lecture08/primitives.py
```

只需 Python 标准库，顺序执行各逻辑阶段，不是 GPU 模拟器或并行性能测量。

完整实现：保持顺序的树形 Reduce、Hillis–Steele 风格 Inclusive、Blelloch Exclusive、稳定 Compaction、通过结合二元组实现的 Segmented Inclusive、Gather、唯一目标 Scatter、CSR SpMV、粒子坐标映射、排序分桶、加权 Scatter Sum。

固定输出：

```text
exclusive= [0, 2, 3, 6] inclusive= [2, 3, 6, 10]
scan_cases=340 integer_and_noncommutative_strings=pass
random_pipelines=200 compact_three_predicates=pass segmented=pass bins=pass scatter_sum=pass
spmv_random=100 empty_rows_example=[6, 0, 4, 12, 54, 0] invalid_inputs=pass
N=8: Hillis combines=17 rounds=3; Blelloch combines=14 rounds=6
all_checks=pass
```

- 340 组 Scan/Reduce：70 种长度的整数/字符串各一次，加 200 组随机整数；包含空输入、非二次幂、127/128/129/257。字符串连接验证结合但不交换的操作顺序。
- 200 组随机应用：三种筛选谓词、分段、分桶与加权聚合；固定种子 149。
- 100 组随机 SpMV 对照稠密乘法，另测连续与末尾空行、空矩阵。
- 检查单写者位置、空桶、全挤到一桶、负 Gather、重复 Scatter、非法 CSR 起点、非法 cell 等边界。

操作数与轮数是算法模型的计数，不是 CPU/GPU 指令或时钟。浮点数值稳定性、真实 GPU 同步与全部代数结构不在这些测试结论范围内。

## C++17：真实线程分块 Scan（已运行）

```bash
mkdir -p /tmp/cs149-l08-build
c++ -O2 -std=c++17 -pthread -Wall -Wextra -pedantic \
  labs/lecture08/chunk_scan.cpp -o /tmp/cs149-l08-build/chunk_scan
/tmp/cs149-l08-build/chunk_scan
```

macOS ARM64、Apple Clang 16 实际输出：

```text
exclusive: 0 2 3 6
cases=220 integer_and_string=pass empty_partitions=pass invalid_workers=pass correct=yes
```

三个逻辑阶段是局部 Exclusive/total、按块生成 bases、并行左合并 bases。两次 join 建立完成关系。12 种固定长度×5 种 Worker×整数/字符串，共 120，再加 100 组随机整数；另检查非法 Worker 数。

本次 ThreadSanitizer 构建亦实际运行，通过且无竞争报告：

```bash
c++ -O1 -g -std=c++17 -pthread -fsanitize=thread \
  labs/lecture08/chunk_scan.cpp -o /tmp/cs149-l08-build/chunk_scan-tsan
/tmp/cs149-l08-build/chunk_scan-tsan
```

程序使用小范围 int64 整数避免溢出，字符串只用来检验顺序，不把字符串操作当作常数时间。每阶段重新建线程、块摘要顺序扫描，工作量为 O(N+P)，不声称 O(log N) Span 或固定加速。一次无竞争报告不是所有调度的证明。

本章未编译/运行 CUDA Scan、Thrust/CUB，未做 GPU/分布式测试或性能 Benchmark。构建放仓库外。
