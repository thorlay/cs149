# Lecture 02 来源核验记录（公开版）

**教材：** [第 02 章：A Modern Multi-Core Processor](../textbook/02-modern-multicore-processor.md)  
**课程：** Stanford CS149 Fall 2023  
**原始资料：** [官方课程页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/multicore/) · [103 页 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/multicore/02_basicarch_xX3ssOi.pdf) · [公开视频](https://www.youtube.com/watch?v=CKmNpAO5rS4)

## 材料状态

- **Slides：** 已核对官方 103 页 PDF 的文字、教学案例、课次与章节顺序，未完成全部图页的逐张视觉复核。
- **Transcript：** 用户提供 YouTubeToTranscript 提取的、从开场持续到讲课结尾的英文自动转写。已阅读、与 Slides 主题对照，但原文为 **Timestamp OFF**，且未经逐句音频核对。
- **公开边界：** 不保存或上传第三方 Transcript 全文、不重发官方 PDF；教材仅采用独立编写的解释、例题、练习及引用链接。

## 从两类资料共同确认的主线

1. 从 Processor Model、Superscalar / ILP 和 Memory Abstraction 开始。
2. Cache Line、LRU、Spatial / Temporal Locality、Cold / Capacity / Conflict Miss。口头讲解中教授自己更正了 Capacity 与 Conflict 的术语混用。
3. 使用逐元素的 sin(x) Taylor 近似，比较一个 Instruction Stream、两个 C++ Threads、抽象 forall 循环与 SIMD 的映射方式。
4. 8-wide SIMD、Control Flow Divergence 和执行 Lane Mask；最坏的 1/8 利用率需要额外说明不同路径的成本。
5. 通过另一条就绪的 Instruction Stream 在访存 Stall 期间继续工作，即 Hardware Multithreading。
6. 官方 Slides 有具体的硬件线程计算题：连续 C=3 周期计算、等待 L=12 周期需要 5 个线程；C=6、L=12 时仅需要 3 个（简化模型）。该推导在教材正文中补全。

## 代码核验

| 独立实验 | 运行结果 | 测试范围 |
| --- | --- | --- |
| cache_lines.py | A: (6 Hit, 2 Miss)，B: (12 Hit, 5 Miss) | Python 3，Linux |
| parallel_sine.cpp | 4 Worker，correct=yes | Linux/x86_64，C++17 + pthread |
| avx2_multiply.cpp | Scalar correct=yes；AVX2 correct=yes | Linux/x86_64 且支持 AVX2 |

没有使用这些测试数字推断其他硬件的实际性能。Chapter 的 Divergence 利用率公式、近似 sin 函数的递推版本、代码、练习及 AI Infra 扩展属于作者自己编写的教学材料。

## 仍待完成的 QA

- 获取相同视频的带时间码 Transcript，再给具体论点附精确时间点；
- 逐页视觉检查重要 PDF 图表；当前核对重点是文本结构和公式；
- 在更多架构和编译器组合运行样例；AVX2 不适用于 Apple Silicon；
- 若对代码执行速度提出结论，应另外提供硬件信息、Warm-up 和多次测量。
