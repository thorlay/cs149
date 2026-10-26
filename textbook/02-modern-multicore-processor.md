# 第 02 章｜现代多核处理器：Cache、Multicore、SIMD 与硬件多线程

> Stanford CS149 · Fall 2023 · **Lecture 2 — A Modern Multi-Core Processor**
>
> **状态：Self-contained 中文原创教材（第一版）**。本章依据用户提供的英文自动转写（YouTubeToTranscript，**Timestamp OFF**）以及 Stanford 官方 103 页 Slides 编写。已核对 Slides 的文本、案例和章节顺序，尚未把全部 PDF 图页逐张视觉复核，也未将自动字幕与原始音频逐句校验；不能将本文视作 Stanford 授权教材或完整逐字稿。

**先修知识：** 掌握变量、数组、for 循环、基础 C/C++ 语法即可。不需要先阅读 Lecture 1。本章会解释所有核心术语，并提供可手算的例题和不依赖 GPU 的实践。  
**学习时间：** 2–3 小时阅读与练习，约 1–2 小时完成编程。  
**来源：** [Stanford Lecture 2 页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/multicore/) · [103 页官方 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/multicore/02_basicarch_xX3ssOi.pdf) · [课程视频](https://www.youtube.com/watch?v=CKmNpAO5rS4)

**配套实验：** [三个可运行程序与运行说明](../labs/lecture02/README.md)。全部核心代码也完整放在本章正文中；该链接只是方便直接执行，不是必读前提。

## 0. 本章的问题与学习目标

假设你要对一百万个浮点数执行相同的复杂计算。一台机器拥有多个 CPU Core，每个 Core 还有向量执行单元；为什么一个普通 for 循环未必能使用这些资源？为什么算术单元已经足够多，程序仍可能被内存访问拖慢？

本讲的三条主线分别是：

1. **Multicore**：让多个 Core 同时运行不同指令流，处理不同的工作。
2. **SIMD（Single Instruction, Multiple Data）**：让一条指令在不同数据元素上同时进行相同的操作。
3. **Hardware Multithreading**：一个 Core 维护多个硬件线程上下文；某个线程等待慢内存时，切换去执行另一个线程。

课程同时回顾 **Superscalar（超标量）**，它利用同一指令流里的独立指令。理解本章以后，你应当能够算出 Cache 的 Hit/Miss、SIMD Lane 的有效利用率、隐藏一段访存等待所需的线程数，并写出能验证正确性的多核 / SIMD 程序。

## 1. 先区分“程序要求的语义”与“硬件怎么实现”

从处理器的角度，程序最终体现为指令和状态。**指令（Instruction）**可以做算术、读取或修改寄存器、Load/Store 内存、跳转到下一段代码；**程序状态**包括寄存器值以及可访问的内存。

一个极简的 Core 可以画成：

~~~text
       Instruction Stream（指令流）
                   |
          +----------------+
          | Fetch / Decode |  选择下一步指令
          +----------------+
                   |
          +----------------+
          | Execution Unit |  算术 / Load / Store
          +----------------+
                   |
              Registers
                   |
                 Memory
~~~

这只是教材模型，不是完整的 CPU 微架构。真实处理器还有流水线、缓存、分支预测、寄存器重命名与 Out-of-Order Execution。

### 1.1 什么是 Instruction-Level Parallelism？

考虑：

~~~text
A = x * x
B = y * y
C = A + B
~~~

计算 A 与 B 互不依赖，所以某个 Core 如果拥有多个执行单元，可以在允许的资源和时序下并行执行；C 必须等待 A、B 的结果。这叫 **ILP（Instruction-Level Parallelism，指令级并行）**。

**Superscalar** 主要在一个指令流里寻找这种独立性并利用多个执行单元。它不等于多个 Core：一个 Core 即使能同周期执行多条独立指令，仍然在处理同一指令流里的工作。

### 1.2 为什么两个 Core 不一定比一个 Core 快？

多核芯片给不同 Core 提供各自的指令获取、执行与寄存器上下文。开发者需要提供可以并发运行的任务。如果程序只创建一个线程，那么第二个 Core 可能闲着；假如新 CPU 的单核性能还比较弱，原有串行程序甚至可能变慢。

课程强调一个贯穿全章的事实：**硬件提供并行能力，软件需要暴露可并行的工作。**

## 2. 为什么先讲 Cache？因为计算单元会等待数据

### 2.1 Memory 与 Cache 不应混为一谈

对程序而言，Memory 是“地址 → 值”的抽象。**DRAM** 是实现大容量内存的一种硬件技术。**Cache** 是容量较小、访问更快的存储层级，它保存主存中一部分数据的副本。

理想且正确的 Cache 实现改变程序运行时间，不改变程序要求的结果。

### 2.2 Cache Line 的含义

Cache 通常不是一次只搬一个字节，而是按 **Cache Line（缓存行）**搬运和管理数据。官方课件使用一个简化示例：

- 主存地址从 0x0 到 0xF，共 16 字节；
- Cache 总容量 8 字节；
- 每条 Cache Line 保存 4 字节；
- Cache 最多保留两条 Line；
- 使用 LRU（Least Recently Used，最近最少使用）逐出策略；
- 为了手算，假定两条 Line 可以保存任意两块地址区域。

地址按 4 字节对齐：

| Cache Line 起始地址 | 包含地址 |
| --- | --- |
| 0x0 | 0、1、2、3 |
| 0x4 | 4、5、6、7 |
| 0x8 | 8、9、10、11 |
| 0xC | 12、13、14、15 |

如果一条 Cache Line 有 L 字节，非负地址 a 所属行的起点是：

```math
\operatorname{line}(a)=\left\lfloor \frac{a}{L}\right\rfloor L
```

所以在本例中访问地址 5，会加载起点为 4 的一整行，而不是单独加载一个字节。真实 x86 处理器的 Cache Line 常为 64 字节；**4 字节只为便于讲解**。

### 2.3 什么是 Hit、Miss 和 LRU？

**Hit**：目标地址所在行已经在 Cache 中，可以从当前层级取到数据。  
**Miss**：当前层级没有该行，需要从较慢的层级获取。  
**Eviction**：Cache 满后需要逐出旧行。  
**LRU**：优先逐出最长时间没访问过的行。

**例子 A：** 按顺序读取：

~~~text
0, 1, 2, 3, 2, 1, 4, 1
~~~

| 访问地址 | 结果 | Cache 当前行 |
| --- | --- | --- |
| 0 | Cold Miss，加载行 0 | 0 |
| 1 | Hit，同一行 | 0 |
| 2 | Hit | 0 |
| 3 | Hit | 0 |
| 2 | Hit，重复使用 | 0 |
| 1 | Hit，重复使用 | 0 |
| 4 | Cold Miss，加载行 4 | 0、4 |
| 1 | Hit，行 0 未被逐出 | 0、4 |

**结论：8 次访问、6 Hit、2 Miss。**

这展示了两种数据局部性：

- **Spatial Locality（空间局部性）**：访问 0 后很可能访问相邻的 1、2、3，一条 Line 带来多个 Hit。
- **Temporal Locality（时间局部性）**：刚使用过的 1、2 又被重复访问。

**例子 B：** 顺序访问整个 16 字节区域，再访问 0：

~~~text
0, 1, 2, 3, 4, 5, 6, 7,
8, 9, 10, 11, 12, 13, 14, 15, 0
~~~

只看造成缓存状态变化的访问：

| 访问 | 结果 | 需要逐出 | Cache 里保留的行 |
| --- | --- | --- | --- |
| 0 | Cold Miss | 无 | 0 |
| 4 | Cold Miss | 无 | 0、4 |
| 8 | Cold Miss | 0 | 4、8 |
| 12 | Cold Miss | 4 | 8、12 |
| 最后再次访问 0 | Capacity Miss | 8 | 12、0 |

其他访问都是 Hit，得到 **17 次访问、12 Hit、5 Miss**。

### 2.4 三种 Cache Miss 必须分清

课堂中教授在问答时曾短暂混淆 **Capacity Miss** 与 **Conflict Miss**，随后自己更正。这里保留正确定义：

- **Cold / Compulsory Miss（冷 / 强制未命中）**：第一次访问某条缓存行，即使 Cache 大到能保存全部数据，也不能凭空让它已经在 Cache 里。
- **Capacity Miss（容量未命中）**：总 Cache 容量不足以保存需再次使用的工作集。例子 B 最后一次读 0 属于这种情况；若 Cache 可以保存全部四条 Line，它就会 Hit。
- **Conflict Miss（冲突未命中）**：Cache 总容量本可能足够，但 Set Associativity / 地址映射限制使不同数据争用同一个位置。我们在本章的简化全相联模型中不模拟它。

Miss 分类帮助解释成因，不意味着 CPU 会给每个 Miss 一个独立的“类型标签”再决定是否从主存读取。

### 2.5 亲自运行 Cache 模拟器

下面是一份仅依赖 Python 标准库的完整 LRU 模拟器。保存为 **cache_lines.py**：

~~~python
from collections import OrderedDict

def simulate(addresses, line_bytes=4, capacity_lines=2):
    resident = OrderedDict()
    seen = set()
    hits = misses = 0
    log = []

    for address in addresses:
        line = (address // line_bytes) * line_bytes
        if line in resident:
            hits += 1
            kind = "hit"
            resident.move_to_end(line)
        else:
            misses += 1
            kind = "cold miss" if line not in seen else "miss after eviction"
            if len(resident) == capacity_lines:
                resident.popitem(last=False)
            resident[line] = None
        seen.add(line)
        log.append((address, kind, list(resident.keys())))
    return hits, misses, log

case_a = [0, 1, 2, 3, 2, 1, 4, 1]
case_b = list(range(16)) + [0]
for name, case, expected in [
    ("A", case_a, (6, 2)),
    ("B", case_b, (12, 5)),
]:
    hit, miss, log = simulate(case)
    assert (hit, miss) == expected
    print(f"{name}: hits={hit}, misses={miss}")
    for address, kind, lines in log:
        print(f"  addr={address:>2} | {kind:<19} | lines={lines}")
~~~

运行：

~~~bash
python3 cache_lines.py
~~~

应看到：

~~~text
A: hits=6, misses=2
B: hits=12, misses=5
~~~

**模型边界：** 代码中的 “miss after eviction” 不自动区分 Capacity 与 Conflict；模拟器不含 Set Associativity、预取、写回、CPU 时钟、访问延迟和多核一致性协议。它只让你验证 Locality、LRU 与 Hit/Miss 的关系。上述代码已在 Python 3 上运行并通过断言。

### 2.6 Cache 层级的性能差距有多大？

官方课件举出 Kaby Lake CPU、4 GHz 的教学数字：

| 访问位置 | 约需 Cycles | 4 GHz 下约需时间 |
| --- | ---: | ---: |
| L1 Cache | 4 | 1 ns |
| L2 Cache | 12 | 3 ns |
| L3 Cache | 38 | 9.5 ns |
| DRAM（较好条件） | 248 | 62 ns |

4 GHz 相当于每个 Cycle 约 0.25 ns。这是**课件中的特定 CPU 示例**，不是最新处理器的统一实测值。

假如某条运算必须先完成 Load，而数据暂时只在 DRAM，后续依赖指令可能等待很多周期。因此优化数据访问模式、让有用数据常驻近端 Cache，有时比增加 ALU 数量重要得多。

**Prefetching（预取）**是另一种手段：硬件预测未来要访问的地址并尝试提前加载。顺序数组容易预测；链表追踪或由刚计算出的数据决定地址则可能不容易预测。预取错误也可能浪费带宽并污染 Cache。

---

## 3. 一条贯穿整章的计算任务：逐元素近似 sin(x)

为了比较 Multicore、SIMD、Hardware Multithreading，课程使用同一个数组计算问题：

~~~text
for i in 0..N-1:
    y[i] = approximate_sin(x[i])
~~~

每个输出 y[i] 仅依赖对应的输入 x[i]。这意味着**不同 i 之间天然可以并行**；同一个元素内部的计算则可能存在依赖链。

### 3.1 Taylor Series 的完整定义

正弦函数在 0 附近可以展开为：

```math
\sin(x)=x-\frac{x^3}{3!}+\frac{x^5}{5!}-\frac{x^7}{7!}+\cdots
```

n! 表示阶乘，例如 3!=6，5!=120。保留有限项便得到近似。

定义 term₀=x。对 k≥1：

```math
\operatorname{term}_k = \operatorname{term}_{k-1}\cdot\frac{-x^2}{(2k)(2k+1)}
```

取 K 个额外项的近似是：

```math
s(x)=\sum_{k=0}^{K}\operatorname{term}_k
```

用 x=1、保留前三项手算：

~~~text
term0 = 1
term1 = -1/6    = -0.16666667
term2 = +1/120  = +0.00833333
s(1)  = 0.84166667
sin(1) ≈ 0.84147098
~~~

误差来自截断，不能误以为三项已经精确得到 sin(1)。课件原始示例采用不同的循环变量和分母写法；后续可运行代码使用 double 中间结果的递推形式，避免某些整数阶乘分母溢出问题。

### 3.2 为什么有并行工作，却未必被一个 Core 自动发现？

~~~text
计算 y[0]: term0 -> term1 -> term2 -> ...
计算 y[1]: term0 -> term1 -> term2 -> ...
计算 y[2]: term0 -> term1 -> term2 -> ...
           （行与行独立，行内有依赖）
~~~

Superscalar Core 可以在指令窗口内寻找某些独立指令，但它不保证会自动识别复杂循环里所有输入元素之间的独立性。程序员或编译器明确表达“外层循环各迭代独立”，能够帮助硬件获得更多并行任务。

**核心区分：单个元素内部的指令级并行（ILP）与不同元素之间的数据并行，是两个不同的并行维度。**

---

## 4. Multicore：用多个独立指令流处理不同元素

### 4.1 复制的是什么？

两个 Core 可以分别维护取指/解码、执行单元和寄存器状态，运行不同线程。真实 CPU 的某些 Cache 私有、某些共享，并非每一种存储资源都完整复制。

~~~text
Core 0 / Worker 0: x[0 .. middle) -> y[0 .. middle)
Core 1 / Worker 1: x[middle .. N) -> y[middle .. N)
~~~

记号 [begin,end) 表示包含 begin、不包含 end。输出区间没有重叠，所以各线程不写同一个 y[i]。

课程展示了用 C++ std::thread 分成两半的实现，以及一种叫 **forall** 的**概念性语法**：只声明哪些迭代独立，让编译器或 Runtime 决定如何使用处理器。**课程课件里的 forall 不是标准 C/C++ 关键字**。

若程序写死两个线程，即使机器拥有 16 Core，也可能只有两个线程在计算。Runtime 自适应的抽象更有扩展性，但独立性需要程序本身保证。

### 4.2 完整 C++17 多核实验

下方代码使用固定输入和 Taylor 递推，并同时验证“并行输出与串行输出一致”及“近似接近 std::sin”。代码刻意将线程创建纳入计时，后续可以研究线程池如何减少开销。

保存为 **parallel_sine.cpp**：

~~~cpp
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <thread>
#include <vector>

double approx_sin(double x, int terms) {
    double term = x;
    double sum = x;
    for (int k = 1; k <= terms; ++k) {
        term *= -x * x / ((2.0 * k) * (2.0 * k + 1.0));
        sum += term;
    }
    return sum;
}

void serial(const std::vector<double>& x,
            std::vector<double>& y, int terms) {
    for (std::size_t i = 0; i < x.size(); ++i)
        y[i] = approx_sin(x[i], terms);
}

void parallel(const std::vector<double>& x,
              std::vector<double>& y,
              int terms, unsigned workers) {
    workers = std::max(1U, workers);
    std::size_t chunk = (x.size() + workers - 1) / workers;

    auto work = [&](unsigned w) {
        std::size_t begin = w * chunk;
        std::size_t end = std::min(begin + chunk, x.size());
        for (std::size_t i = begin; i < end; ++i)
            y[i] = approx_sin(x[i], terms);
    };

    std::vector<std::thread> threads;
    for (unsigned w = 1; w < workers; ++w)
        threads.emplace_back(work, w);
    work(0);
    for (auto& t : threads) t.join();
}

int main(int argc, char** argv) {
    unsigned workers = argc > 1
        ? static_cast<unsigned>(std::stoul(argv[1])) : 4U;
    constexpr std::size_t n = 1 << 19;
    constexpr int terms = 8;
    std::vector<double> x(n), baseline(n), result(n);

    for (std::size_t i = 0; i < n; ++i)
        x[i] = 2.0 * static_cast<double>(i % 1024) / 1023.0 - 1.0;

    auto start = std::chrono::steady_clock::now();
    serial(x, baseline, terms);
    auto split = std::chrono::steady_clock::now();
    parallel(x, result, terms, workers);
    auto end = std::chrono::steady_clock::now();

    double max_diff = 0.0, max_math_error = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        max_diff = std::max(
            max_diff, std::abs(baseline[i] - result[i]));
        max_math_error = std::max(
            max_math_error, std::abs(result[i] - std::sin(x[i])));
    }

    double ts = std::chrono::duration<double, std::milli>(
        split - start).count();
    double tp = std::chrono::duration<double, std::milli>(
        end - split).count();

    std::cout << std::fixed << std::setprecision(3)
              << "workers=" << workers
              << " serial_ms=" << ts
              << " parallel_ms=" << tp
              << " speedup=" << (ts / tp) << "x\n"
              << "max_diff=" << max_diff
              << " max_sin_error=" << max_math_error << "\n";

    bool ok = max_diff < 1e-12 && max_math_error < 1e-12;
    std::cout << "correct=" << (ok ? "yes" : "NO") << "\n";
    return ok ? 0 : 1;
}
~~~

在 Linux / macOS 的 C++17 工具链上编译：

~~~bash
c++ -O2 -std=c++17 -pthread parallel_sine.cpp -o parallel_sine
./parallel_sine 1
./parallel_sine 2
./parallel_sine 4
./parallel_sine 8
~~~

**预期检查：** 每种 Worker 数量都应打印 correct=yes。串行与并行执行时间取决于机器、负载和 Compiler，**不能根据本章规定一个固定 Speedup**。

该代码已在 Linux/x86_64 以 4 Worker 编译运行并通过正确性检查。不同 Worker 只读同一输入 x、写自己独占的 y 区间；主线程也执行一个 Chunk，随后 join 确保所有 Worker 结束。

如果算法改成 y[i]=y[i-1]+x[i]，各迭代就存在真实依赖，不能如此简单地并行化。**数据并行不由 for 循环的外观决定，而由依赖决定。**

---

## 5. SIMD：一条指令同时处理许多数据

### 5.1 什么被复制，什么被共享？

Multicore 复制的是能够执行不同指令流的 Core。SIMD 则让一个指令控制多个数据 Lane，摊薄指令获取和控制成本：

~~~text
                VADD（一个向量加法指令）
                             |
                       Fetch/Decode
                             |
         +----------+--------+-------+----------+
         |          |                |          |
       Lane 0     Lane 1           ...       Lane 7
       a0+b0      a1+b1                     a7+b7
~~~

如果一个 float32 是 32 bits，而 AVX2 Vector Register 有 256 bits：

```math
V=\frac{256\ \mathrm{bits}}{32\ \mathrm{bits/float}}=8\ \mathrm{floats}
```

因此一条相应的 AVX2 向量乘法或加法，可以处理 8 个 float。真实微架构中每周期能执行多少向量指令，还取决于执行端口、指令类别与数据是否就绪。

### 5.2 两种机制可以相乘，但结果仍只是理想上限

如果有 16 个 Core，每个 Core 在某个周期能发出一条 8-wide 浮点算术指令：

```math
16\times8=128\ \text{元素算术操作/周期（理想上限）}
```

如果有 4 个 Core，每 Core 理想情况下能同时执行 3 条独立的 8-wide 算术指令：

```math
4\times3\times8=96\ \text{元素算术操作/周期（理想上限）}
```

这些数字不是程序一定能达到的 FLOP/s：它们没有考虑数据带宽、指令依赖、Cache Miss、执行端口限制、实际频率和不同运算的吞吐率。

### 5.3 直接运行 AVX2 向量乘法

下面使用 AVX2 Intrinsic 操作 8 个 float，处理 19 个元素时最后 3 个由 Scalar Loop 补齐；不支持 AVX2 的编译环境可编译普通标量版本。

保存为 **avx2_multiply.cpp**：

~~~cpp
#include <cmath>
#include <iostream>
#include <vector>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

void multiply(const float* a, const float* b, float* out, int n) {
    int i = 0;
#if defined(__AVX2__)
    for (; i + 7 < n; i += 8) {
        __m256 va = _mm256_loadu_ps(a + i);
        __m256 vb = _mm256_loadu_ps(b + i);
        __m256 vc = _mm256_mul_ps(va, vb);
        _mm256_storeu_ps(out + i, vc);
    }
#endif
    for (; i < n; ++i)
        out[i] = a[i] * b[i];
}

int main() {
    constexpr int n = 19;
    std::vector<float> a(n), b(n), out(n);
    for (int i = 0; i < n; ++i) {
        a[i] = static_cast<float>(i + 1);
        b[i] = 2.0f;
    }
    multiply(a.data(), b.data(), out.data(), n);
    for (int i = 0; i < n; ++i) {
        if (std::fabs(out[i] - 2.0f * (i + 1)) > 1e-5f)
            return 1;
    }
    std::cout << "correct=yes n=19 vector_lane_width="
#if defined(__AVX2__)
              << 8
#else
              << 1
#endif
              << "\n";
}
~~~

先编译普通版本：

~~~bash
c++ -O2 -std=c++17 avx2_multiply.cpp -o multiply_scalar
./multiply_scalar
~~~

**仅在确认 x86/x86_64 CPU 支持 AVX2 时**，再运行向量版本：

~~~bash
c++ -O2 -mavx2 -std=c++17 avx2_multiply.cpp -o multiply_avx2
./multiply_avx2
~~~

预期输出分别为：

~~~text
correct=yes n=19 vector_lane_width=1
correct=yes n=19 vector_lane_width=8
~~~

这两个版本已在 Linux/x86_64 编译运行、通过正确性测试。Apple Silicon 不能直接执行 AVX2 指令。这里使用 unaligned load/store，因此没有额外的 32-byte 对齐要求。数据量只有 19，**不应把这个实验当作有效的性能 Benchmark**；此外普通版本也可能被编译器自动向量化。

**Explicit SIMD** 可以通过 Intrinsic 或 Compiler 生成的向量指令实现；在 GPU 的 **SIMT / Implicit SIMD** 模型中，程序员通常编写多个逻辑线程，硬件再将它们组织成共同执行的组。CPU AVX Register 与 GPU Warp 有联系，但不属于完全相同的编程抽象。

---

## 6. SIMD 最大的现实难题之一：Divergence

### 6.1 一个 8-wide 分组里出现不同 if 分支

假设一个 8-wide SIMD 组的条件结果是：

~~~text
Lane index:   0 1 2 3 4 5 6 7
Condition:    T T F T F F F F

执行 if：     X X . X . . . .
执行 else：   . . X . X X X X
~~~

其中 X 代表有效 Lane，点代表 Mask 掉的 Lane。若同一批计算资源需要先执行 if 路径、再执行 else 路径，部分 Lane 在某些阶段就没有做有用工作。

称同组工作需要相似指令流为 **Coherent Execution**；不同 Lane 需要不同路径为 **Divergence**。只有足够的控制流一致性，SIMD 的宽向量计算资源才容易得到有效利用。

### 6.2 用数字计算有效 Lane-Instruction 利用率

假设 V 个 Lane 中 n 个走 if，其他走 else；if 路径有 A 条向量算术指令，else 有 B 条。假设两条路径分别执行且没有额外优化，则一个教学用利用率模型为：

```math
U=\frac{nA+(V-n)B}{V(A+B)}
```

分子是真正需要完成的 Lane-Instruction 数量；分母是执行两条路径时使用的总 Lane Capacity。

例如 V=8、n=3、A=3、B=2：

```math
U=\frac{3\times3+5\times2}{8(3+2)}
=\frac{19}{40}=47.5\%
```

这是简化的 Mask 模型，不是所有真实 CPU/GPU 上的性能计数器数值。

### 6.3 课堂提问：如何接近 1/8 的最低利用率？

关键不是让 1 个 Lane 走 if、7 个走 else 就自动达到 1/8；还必须考虑**两条分支的成本**。

设只有 1 Lane 执行很长的 if 路径（100 条指令），7 Lane 执行极短的 else（1 条）：

```math
U=\frac{1\times100+7\times1}{8(100+1)}
=\frac{107}{808}\approx13.24\%
```

当昂贵路径相对更长时，利用率趋近于 1/8=12.5%。如果两条路径成本一样，不能从“1 个 Lane 走 if”直接推断出 1/8 的整体利用率。

使用 Predication 或把条件变成 0/1 乘法也不是无成本的万能优化：如果依然执行两套昂贵运算，改写语法并不能减少有用计算之外的指令占用。

**真正需要优化的是：同组工作是否执行相似计算，以及为解决分歧而重新组织数据是否值得其搬运成本。**

---

## 7. Hardware Multithreading：用其他线程的计算隐藏访存延迟

到这里，我们已经了解如何让 CPU 拥有更多 Core，或让一个 Core 用 SIMD 同时处理更多数据。但还有一项约束：**如果指令需要的数据尚未准备好，再多的 ALU 也可能无法完成有效计算。**

### 7.1 什么是 Latency Hiding？

**Memory Latency** 指一次特定内存访问获得结果所需的时间。**Latency Hiding（隐藏延迟）**不是把这次访问的真实物理延迟从 200 周期改成 10 周期，而是在等待期间继续执行其他不依赖该结果的工作。

教授用洗衣服和烧水作生活类比：洗衣机正在运行时，你可以先准备下一件事情，而不是持续盯着它。处理器也可以这样安排指令流。

让一个 Core 保留多个线程上下文（Execution Context）：

~~~text
                       Core 0
            +---------------------------+
            | Fetch/Decode + ALU        |
            |                           |
            | Context A: PC, Registers  |
            | Context B: PC, Registers  |
            | Context C: PC, Registers  |
            | Context D: PC, Registers  |
            +---------------------------+
                         |
                     Memory
~~~

**PC（Program Counter）**是下一条待执行指令的位置；寄存器保存各线程自己的计算状态。

假设 A 遇到一次漫长的 Load 等待：

~~~text
时间向右流逝：

Thread A:  计算 | 等待内存................ | 可运行
Core ALU:  [A]  [B] [B] [C] [C] [D] [D]  [A]
                      ↑
               利用其他线程做有用工作
~~~

A 的访存并没有变快，但 Core 不必因 A 的 Stall 而长时间空闲。

### 7.2 Hardware Thread 与 std::thread 不是一回事

在上一节，C++ 的 std::thread 创建软件执行线程，由操作系统和硬件进行调度。软件线程可能分布在不同物理 Core 上，也可能竞争同一 Core。

**Hardware Multithreading** 则是处理器架构本身支持在一个 Core 内保留多个线程的硬件执行状态。一个支持两条硬件线程的 Core 并不等价于两个完整物理 Core，也**不意味着拥有两份相同的 ALU**。

这个区分解释了为什么机器显示“8 个 Logical CPUs”，不一定有 8 个完全独立的物理 Core。

### 7.3 重要算例：3 周期计算 + 12 周期等待

课程 Slides 提供一个很适合手算的模型，必须把它弄懂。

假设一个虚构 Core：

- 每周期执行一个算术操作；
- 某线程连续执行 C 个算术周期；
- 然后该线程因 Load 等待 L 个周期；
- 同一个 Core 可以从其他就绪线程中选择指令；
- 忽略线程切换、Load 指令本身的执行开销、共享内存争用和其他执行限制。

**单线程**的理论算术忙碌率：

```math
U_1=\frac{C}{C+L}
```

令 C=3、L=12：

```math
U_1=\frac{3}{3+12}=20\%
```

也就是说，ALU 每 15 个周期只执行约 3 周期的有用算术，其余周期都可能因为等待而闲置。

如果安排 5 个线程，每个线程计算 3 周期：

| 周期区间 | 核心执行 |
| --- | --- |
| 0–2 | Thread 0 的算术 |
| 3–5 | Thread 1 的算术 |
| 6–8 | Thread 2 的算术 |
| 9–11 | Thread 3 的算术 |
| 12–14 | Thread 4 的算术 |
| 15–17 | Thread 0 再次就绪并计算 |

此时 Thread 0 从周期 3 起等待 12 周期，到周期 15 时可以重新运行；其他四个线程的计算正好填满了空档。

一个很直观的玩具模型估计式是：

```math
N_{\mathrm{threads}}\ge
\left\lceil\frac{C+L}{C}\right\rceil
=1+\left\lceil\frac{L}{C}\right\rceil
```

其中 **ceil** 代表向上取整。

- C=3、L=12 → 至少 **5 个 Threads**；
- 如果同样等待 12 周期，但一个线程能先连续执行 C=6 周期，则需要：

```math
N_{\mathrm{threads}}\ge\left\lceil\frac{6+12}{6}\right\rceil=3
```

这分别对应 Slides 中“五个线程可达到满利用率”和“更高计算/等待比只需三个线程”的课堂练习。

**模型边界：** 现实中的指令发射端口、Pipeline、SMT、Load Queue、Cache、Memory Bandwidth、寄存器占用都会影响可运行线程数。这个式子帮助建立直觉，不能直接当成所有 CPU 或 GPU 的 Occupancy Calculator。

### 7.4 为什么要保留更多线程，不等于总是变快？

每个驻留线程都需要保存执行状态。这会消耗有限的寄存器或其他片上存储。线程越多，每线程可获得的资源可能越少，并且更多线程也可能共同争用 Cache 和访存带宽。

此外，**Latency 与 Throughput 是不同的优化目标**：

- **Latency**：一个线程或一次请求从开始到完成需要多少时间。
- **Throughput**：整个机器每秒完成多少单位工作。

如果 Thread 0 的内存数据已经准备好，但当前正执行 Thread 2，那么 Thread 0 仍可能等待调度。这样整个 Core 的空闲时间减少了，单位时间完成的总工作变多了，但 Thread 0 自己的完成时间未必更短。

### 7.5 Interleaved 与 Simultaneous Multithreading

**Interleaved Multithreading（交错多线程）**：在不同周期选择不同线程的指令，以隐藏某一线程的停顿。课程前面的单 ALU 例题主要展示这种直觉。

**Simultaneous Multithreading（SMT，同时多线程）**：Superscalar Core 可以在同一周期从多个线程中选择独立指令，使用不同的空闲执行单元。Intel Hyper-Threading 是 SMT 的经典例子之一。

两者都尝试提高资源利用率，但并不复制一整套完整计算核心。对 SIMD 和 GPU 而言，硬件线程、Warp 和执行单元的关系还需结合具体架构理解，不能把 SMT 的行为直接套用到 CUDA。

### 7.6 GPU 的 Warp Context：更多驻留工作不等于更多 ALU

官方 Slides 还给出两个非常有启发性的硬件例子。

**例子 A：16 Core 的虚构芯片**

假设 16 个 Cores，每 Core 有 8 个 SIMD Lanes，并能驻留 4 个硬件线程上下文：

- 每 Core 的同时计算 Lane 数量为 8；
- 16 个 Core 合计 16×8=**128 个计算 Lane**；
- 16×4=**64 个可驻留的硬件线程指令流**；
- 如果每个指令流处理 8 个并行数据元素，总共可维护 **64×8=512 个逻辑待处理工作位置**。

这绝不表示每周期有 512 个独立 ALU 可以工作：计算单元仍是 128 Lane。其余上下文使处理器在数据尚未就绪时仍有其他工作可以调度。

**例子 B：NVIDIA V100（2017 年发布、用于 2023 课程示例）**

课程以 V100 为例，假设最多有 80 个 SM，每个 SM 可驻留最多 64 个 Warps，一个 Warp 有 32 个 CUDA Threads。

```math
80\ \mathrm{SM}\times64\ \mathrm{warps/SM}\times32\ \mathrm{threads/warp}
=163{,}840\ \mathrm{resident\ thread\ positions}
```

这里数的是**理论上可驻留的线程位置上限**，不是一个周期同时完成 163,840 次浮点运算。真实驻留数量还受寄存器、Shared Memory、Block 大小和其他资源限制；Warp 发射和 ALU 数量也与驻留线程数不同。

这正是理解 CUDA **Occupancy**、**Latency Hiding** 与 **GPU Peak Throughput** 必须先区分的三个层次。以上是官方课件里的历史硬件示例，不应当作 2026 年 GPU 型号规格表。

### 7.7 课程的最后一句性能思想

高吞吐计算机需要：

1. **足够多的独立工作**，覆盖多个 Core 与执行单元；
2. **执行相似逻辑的数据组**，有效使用 SIMD；
3. **比瞬时 ALU 处理能力更多的就绪工作**，在部分任务等待内存时继续计算。

这三个条件都在强调：硬件峰值能力只有在任务结构允许时才会转化为有效性能。

---

## 8. 四种机制放在一起比较

| 机制 | 并行工作来自哪里 | 它改变了什么 | 主要限制 |
| --- | --- | --- | --- |
| Superscalar / ILP | 同一指令流中彼此独立的指令 | 一个 Core 同时执行多个指令 | 指令依赖、执行端口和调度窗口 |
| Multicore | 不同线程或任务的指令流 | 多个 Core 各自执行工作 | 独立任务数、同步、共享资源 |
| SIMD | 数据元素执行相同操作 | 一条指令控制多个 Lane | Divergence、数据布局、访存模式 |
| Hardware Multithreading | 同 Core 内其他就绪线程 | 保留更多执行上下文以隐藏 Stall | 上下文存储、Cache/带宽竞争 |

它们可在一台机器中同时出现：

~~~text
CPU/GPU Chip
 |
 +-- Core 0
 |     +-- Superscalar issue resources
 |     +-- SIMD lanes / vector execution
 |     +-- Thread context A
 |     +-- Thread context B
 |
 +-- Core 1
 |     +-- Superscalar / SIMD resources
 |     +-- Other execution contexts
 |
 +-- ... memory hierarchy (private + shared levels)
~~~

**不要把所有维度机械相乘。** 两条 SMT 线程不代表 Core 的 ALU 翻倍；SIMD Lane 不等于独立 CPU Core；一项工作能否用满这些资源还取决于数据是否就绪、计算能否并行及资源是否互相争用。

---

## 9. 怎样做真正可信的 Performance Benchmark？

正确性与性能是两件事。我们已经有三个独立实践：

- Python Cache Simulator：验证 LRU 与局部性；
- C++17 Multicore Taylor：验证线程分工与正确结果；
- AVX2 向量乘法：验证 Vector Lanes 与 Scalar Tail。

**Prediction → Measurement → Explanation** 应当成为固定工作流程。

### 9.1 Prediction：先提出原因

针对 C++ 多核程序可以预测：

- 计算负载足够大、可用物理 Core 足够多时，多线程可能缩短总运行时间；
- 输入太小、计算太轻时，线程创建与 join 成本可能盖过收益；
- 线程数超过有意义的并发资源时，扩展性可能饱和；
- 某些编译器本来就能自动向量化循环，多线程的增益不一定只来自多个 Core。

### 9.2 Measurement：明确比较边界

重复执行各个 Worker 数的程序，例如 1、2、4、8，每个组合测量多次并取中位数。

| Workers | 正确性 | 中位数 ms | Speedup | 备注 |
| --- | --- | --- | --- | --- |
| 1 | pass/fail | 自行测量 | 1.00× | Baseline |
| 2 | pass/fail | 自行测量 | T1/T2 | |
| 4 | pass/fail | 自行测量 | T1/T4 | |
| 8 | pass/fail | 自行测量 | T1/T8 | |

必须保留 CPU 型号、核心数、输入 N、Taylor 迭代次数、编译选项、运行时其他负载等信息。示例 C++ 代码计时包括新建和 Join 线程；如研究常驻线程执行成本，需要将线程池初始化移出计时区间。

### 9.3 Explanation：数据支持哪一种瓶颈？

- 如果 1→2 Threads 没有提升：任务可能太小、线程开销大，或者 CPU 资源不足。
- 如果 4→8 Threads 没有提升：可能是物理 Core 不足，也可能是共享资源已饱和。
- 如果 AVX2 没有明显收益：可能是编译器已把普通循环自动向量化，或数据集太小，或实际瓶颈不在算术吞吐率。

**千万不要用“代码中写了 8 Lane”直接推断加速 8 倍。** 即使正确性测试通过，也仍需单独设计有统计意义的性能实验。

---

## 10. 面向 AI Infrastructure 的连接（课外延伸）

以下是将本讲性能模型用于当代 AI/ML 系统的独立扩展，**不应误认为 2023 年 Lecture 2 逐字教授了这些具体技术**。

**GPU Tensor Kernel**：数值运算中有大量同构数据，适合 SIMD/SIMT；但如果数据访问不规则或控制流发散，实际有效吞吐可能远低于峰值。

**GPU Warp Scheduling**：有足够多的 Ready Warps 时，可以在一部分 Warps 等待 HBM 数据期间执行其他 Warps，利用的是类似 Hardware Multithreading 的 Latency Hiding 思想。

**LLM Prefill 与 Decode**：同一模型的两种阶段具有不同的 Tensor Shape、Batch 结构和数据访问模式，因此 Compute、Bandwidth、Latency 与调度的相对重要性可能不同。

**CPU Preprocessing / Inference Serving**：Tokenizer、数据准备、请求预处理可能受多核并行和 Cache Locality 影响。增加软件线程可能提高吞吐，但也可能引入调度开销、共享缓存争用或内存带宽瓶颈。

**KV Cache 和 GPU Shared Memory**：可借用“减少重复的数据移动”这一大方向来理解其优化目标，但 **CPU Cache Line/LRU、GPU Shared Memory 与 LLM KV Cache 的具体管理机制完全不同**，不能仅因都有 Cache 一词就把它们视作一种硬件结构。

---

## 11. 练习与参考答案

可以先独立作答，再检查下面的推导。

### Q1. Cache Line 起点

若 Cache Line 是 16 字节，读取十进制地址 37，实际包含该地址的 Cache Line 起始地址是多少？覆盖范围是多少？

**答：** floor(37/16)=2，因此起点为 32，覆盖 32–47。

### Q2. Cache Hit / Miss

两行 Cache、每行 4 字节，LRU 且初始为空。访问：

~~~text
0, 1, 4, 8, 0
~~~

Hit 和 Miss 各有几次？

**答：** 地址 0 Miss；1 Hit；4 Miss；8 Miss 并逐出 0；最后 0 再次 Miss。**1 Hit、4 Miss。**

### Q3. 三种 Cache Miss

为什么第二个 Cache 示例最后一次读 0 称为 Capacity Miss，而不是 Cold Miss？如果缓存能保存四条 Line，结果会怎样？

**答：** 最后一次读 0 不是首次使用这条 Line，所以不属于 Cold Miss。它之前被逐出是因为容量太小；若四条 Line 都能驻留，最后会 Hit。

### Q4. 循环独立性

以下循环是否能直接让不同线程同时计算各次迭代？

~~~cpp
for (int i = 1; i < n; ++i)
    a[i] = a[i - 1] + b[i];
~~~

**答：** 不能直接按迭代独立方式处理，因为 a[i] 依赖 a[i-1]。需改写算法，例如使用适合的并行 Prefix Scan 方案。

### Q5. SIMD 宽度

一个 512-bit 向量指令处理 32-bit float，最多能同时容纳多少个 float 元素？

**答：** 512/32=16。它不保证机器每周期都能发射这样的指令，也不保证实际速度提升 16 倍。

### Q6. Divergence 计算

在 8-wide SIMD 中，2 个 Lane 走有 5 个算术操作的 if 分支，6 个 Lane 走有 3 个操作的 else 分支。在分支串行执行的简化模型下，利用率多少？

**答：**

```math
U=\frac{2\times5+6\times3}{8(5+3)}
=\frac{28}{64}=43.75\%
```

### Q7. 隐藏访存等待

某 Core 每次做 C=4 个周期计算，然后需要等待 L=12 个周期。理想模型中至少需要多少个硬件线程才能持续保持计算资源忙碌？

**答：**

```math
N_{\mathrm{threads}}\ge\left\lceil\frac{4+12}{4}\right\rceil=4
```

另外三个线程各计算 4 周期，可以填满前一个线程 12 周期的等待窗口。

### Q8. 多线程为什么不能让单次 Memory Load 更快？

**答：** Memory Load 的实际延迟受存储层级、地址、内存控制器等限制。多线程主要让别的线程在等待时执行工作，不改变那次 Load 本身所需的物理时间。

### Q9. 设计公平的性能实验

比较串行与四线程 Taylor Approximation，必须控制哪些条件？

**答：** 相同输入、Taylor 项数、正确性标准、编译器参数、硬件、测量边界；记录线程创建和 Join 是否包含在内，多轮测试并给出统计值。先确认结果正确，再讨论加速比。

---

## 12. 一页术语表

| 英文 | 中文与说明 |
| --- | --- |
| Instruction Stream | 指令流：可由 Core 处理的机器操作序列 |
| Execution Context | 执行上下文：PC、寄存器等运行状态 |
| Superscalar | 超标量：一个 Core 对同一流中的独立指令并行执行 |
| ILP | Instruction-Level Parallelism，指令级并行 |
| Multicore | 多核：芯片上有多个 Core |
| SIMD | 单指令多数据：一条指令控制多个数据 Lane |
| SIMT | 单指令多线程：GPU 常见的程序执行组织方式 |
| Lane | 向量运算中处理一个数据元素的逻辑位置 |
| Intrinsic | 让编译器生成特定指令集操作的接口 |
| Divergence | 同一组工作需要不同控制路径 |
| Coherent Execution | 一组工作保持相似指令流 |
| Cache Line | 缓存组织与搬运数据的基本单元之一 |
| Spatial/Temporal Locality | 空间/时间局部性 |
| Cold/Capacity/Conflict Miss | 首次访问/容量不足/映射冲突导致的未命中 |
| LRU | 最近最少使用，示例中的逐出策略 |
| Prefetching | 根据预测提前取回未来可能使用的数据 |
| Hardware Multithreading | 硬件保留多个线程的执行状态并调度 |
| SMT | 同时多线程：可以在同一周期使用多个线程的指令 |
| Latency | 完成单项操作所需时间 |
| Throughput | 单位时间完成多少工作 |
| Stall | 因依赖、访存或资源不足而无法继续执行 |

---

## 13. 资料来源、可靠性与编写边界

| 教学主题 | 对应官方 Slides（PDF 页码从 1 开始） | 资料核验 |
| --- | --- | --- |
| Processor、Instruction Stream、Superscalar | pp. 2–12 | Slides 文本 + 用户提供的自动 Transcript |
| Memory、Cache Line、LRU、Locality | pp. 13–19 | Slides 文本 + Transcript 中的讲解与纠错 |
| 正弦 Taylor 主案例与 Multicore | pp. 20–35 | Slides 文本 + Transcript |
| SIMD、AVX2、Divergence | pp. 36–50 | Slides 文本 + Transcript |
| 并行模式组合与芯片示例 | pp. 51–54 | Slides 文本 + Transcript |
| Prefetch、内存等待 | pp. 55–62 | Slides 文本 + Transcript |
| Hardware Multithreading、3/12 和 6/12 例题 | pp. 63–81 | Slides 文本；部分推导由教材补足 |
| 补充硬件结构图与总结 | pp. 82–103 | Slides；未将每张附加图误当作视频口述 |
| Python/C++ 练习、数值模型、AI Infra 延伸 | 本教材独立编写 | **非教授原话** |

**关于 Transcript：** 你上传的是 YouTubeToTranscript 的 Lecture 2 英文自动识别稿，覆盖本讲开头到硬件多线程结束，但**没有时间戳，也未与原声逐句校对**。本文在术语不清楚时采用官方 Slides 与计算机体系结构中明确的定义。例如自动识别中的 “cash” 应理解为 Cache，“super scaler” 为 Superscalar；Capacity Miss 与 Conflict Miss 的口头修正也已保留。

**代码核验范围：** Cache Python 实验得到 A=(6,2)、B=(12,5)；C++17 多核示例在 Linux/x86_64 使用 4 Worker 通过正确性检查；AVX2 示例的普通版本与 AVX2 版本也都编译、运行并通过结果验证。没有在你的机器上实测任何加速比。外部 Slides 与视频是核查资料，不是阅读本章的前置条件。

**版权：** 本章为依据课程材料原创组织的教学解释、例题、代码和练习，并非 Slides 的逐页翻译；不在公开 GitHub 仓库上传完整第三方字幕或官方 PDF。

---

## 本章结论

一个高吞吐处理器要把理论计算资源变成真实速度，通常需要同时满足：**足够多的独立工作（Multicore）、执行类似指令的数据组（SIMD）、等待内存时仍有可调度的工作（Hardware Multithreading）**。Cache、Locality 和 Prefetch 决定这些执行资源能否持续得到数据。

如果你可以不看 Slides，自己推导 Cache Miss 数量、SIMD Lane 利用率、5 个硬件线程如何隐藏 12 周期等待，并运行三段独立程序得到正确性结果，就已经完成了 Lecture 2 最重要的学习目标。
