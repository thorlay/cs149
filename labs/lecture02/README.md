# Lecture 02｜可直接运行的 CPU 实验

这些程序是[第二章中文教材](../../textbook/02-modern-multicore-processor.md)中完整代码的单独文件版本。**教材本身已包含全部代码、定义、计算和预期结果**，不需要依赖此目录来理解原理。

## 1. Cache Line / LRU

要求 Python 3，无第三方包。

~~~bash
python3 labs/lecture02/cache_lines.py
~~~

应输出：

~~~text
A: hits=6, misses=2
B: hits=12, misses=5
~~~

后面还会输出每次访问的地址、Hit/Miss 与 Cache Line 状态。它不是对真实 CPU Cache 的完整模拟。

## 2. Multicore Taylor Sine

要求 C++17、线程支持（Linux 或 macOS）：

~~~bash
c++ -O2 -std=c++17 -pthread labs/lecture02/parallel_sine.cpp -o parallel_sine
./parallel_sine 1
./parallel_sine 2
./parallel_sine 4
./parallel_sine 8
~~~

每次最后应输出 correct=yes。测量数据与 Speedup 取决于具体机器；脚本的计时包含线程创建和 Join。不要把单次执行当成 Benchmark 结论。

## 3. AVX2 向量乘法

普通可移植版本：

~~~bash
c++ -O2 -std=c++17 labs/lecture02/avx2_multiply.cpp -o multiply_scalar
./multiply_scalar
~~~

**仅限确认支持 AVX2 的 x86/x86_64 CPU**：

~~~bash
c++ -O2 -mavx2 -std=c++17 labs/lecture02/avx2_multiply.cpp -o multiply_avx2
./multiply_avx2
~~~

对应预期：

~~~text
correct=yes n=19 vector_lane_width=1
correct=yes n=19 vector_lane_width=8
~~~

不支持 AVX2 的设备（包括 Apple Silicon）不应尝试执行第二个二进制文件。

## 测试与来源说明

三段代码源自我们的原创教程，已经在 Linux/x86_64 使用 Python 3 与 C++17 工具链运行，通过断言或正确性检查。AVX2 路径仅在支持 AVX2 的硬件上测试。测试**没有确认跨架构的性能优势**。

[第 02 章](../../textbook/02-modern-multicore-processor.md) · [来源核验记录](../../sources/lecture-02-audit.md)
