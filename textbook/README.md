# CS149 中文教材｜讲次导航

这是原创中文教程，目标是 **脱离视频仍可系统学习**，同时保留回查 Stanford 官方课件和公开视频的能力。

**教材的正式验收标准是 [Self-contained 中文教材规范](./SELF-CONTAINED-STANDARD.md)：一章读到底，应当能独立理解概念、完成计算、复现最小例子、验证答案。** Slides、Transcript、视频是出处核验与延伸资源，不是必读前置条件。

**编写状态（2026-10-26）**：L01–L07 已使用用户提供的无时间戳自动 Transcript，结合官方 Slides 编写成可独立阅读的详细中文教材；自动文字稿均未与原始音频逐句校对。L10 为自包含初稿、仍缺完整 Transcript 核验；其余讲次尚未编写正文。

## 已写的章节

- [第 1 章：为什么需要并行计算？（Transcript + Slides 详细版）](./01-why-parallelism.md)
- [第 2 章：现代多核处理器——Cache、Multicore、SIMD 与硬件多线程](./02-modern-multicore-processor.md)
- [第 3 章：多核架构进阶——延迟、带宽与 ISPC](./03-multicore-ispc.md)
- [第 4 章：并行编程基础——分解、同步与网格求解](./04-parallel-programming-basics.md)
- [第 5 章：工作分配与调度——负载平衡、任务粒度与工作窃取](./05-work-distribution-scheduling.md)
- [第 6 章：局部性、通信与竞争——幽灵行、分块、融合与 Roofline](./06-locality-communication-contention.md)
- [第 7 章：从 CUDA 线程抽象到真实 GPU 执行](./07-gpu-cuda.md)
- [第 10 章：DNN 的 GPU 优化、Fusion 与 Attention](./10-dnn-gpu.md)

## 全部课程路线图

| 主题讲次 | 课程内容 | 原始资料 | 教材 |
| --- | --- | --- | --- |
| 01 | Why Parallelism? Why Efficiency? | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/whyparallelism/01_whyparallelism_huXfOJ4.pdf) · [视频](https://www.youtube.com/watch?v=V1tINV2-9p4) | [详细版](./01-why-parallelism.md) |
| 02 | A Modern Multi-Core Processor | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/multicore/02_basicarch_xX3ssOi.pdf) · [视频](https://www.youtube.com/watch?v=CKmNpAO5rS4) | [自包含详细版](./02-modern-multicore-processor.md) |
| 03 | Multi-core Arch Part II + ISPC | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/multicore2-ispc/03_multicore2-ispc.pdf) · [视频](https://www.youtube.com/watch?v=F4bVSyz_jxo) | [自包含详细版](./03-multicore-ispc.md) |
| 04 | Parallel Programming Basics | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/progbasics/04_progbasics.pdf) · [视频](https://www.youtube.com/watch?v=0-ztm8SKq70) | [自包含详细版](./04-parallel-programming-basics.md) |
| 05 | Performance Optimization I: Work Distribution and Scheduling | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/perfopt1/05_progperf1.pdf) · [视频](https://www.youtube.com/watch?v=mmO2Ri_dJkk) | [自包含详细版](./05-work-distribution-scheduling.md) |
| 06 | Performance Optimization II: Locality, Communication, and Contention | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/perfopt2/06_progperf2.pdf) · [视频](https://www.youtube.com/watch?v=Mhdny2JNhmc) | [自包含详细版](./06-locality-communication-contention.md) |
| 07 | GPU Architecture and CUDA Programming | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/gpucuda/07_gpuarch.pdf) · [视频](https://www.youtube.com/watch?v=qQTDF0CBoxE) | [自包含详细版](./07-gpu-cuda.md) |
| 08 | Data-Parallel Thinking | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/dataparallel/08_dataparallel.pdf) · [视频](https://www.youtube.com/watch?v=Ba3TqxSgnTk) | 待编写 |
| 09 | Distributed Data-Parallel Computing Using Spark | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/spark/09_spark.pdf) · [视频](https://www.youtube.com/watch?v=jaMWmLq422U) | 待编写 |
| 10 | Efficiently Evaluating DNNs on GPUs | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/dnneval/10_dnneval.pdf) · [视频](https://www.youtube.com/watch?v=qbKtU0X6-WU) | [自包含初稿](./10-dnn-gpu.md) |
| 11 | Cache Coherence | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/cachecoherence/11_coherence.pdf) · [视频](https://www.youtube.com/watch?v=lrCfG2CPDEw) | 待编写 |
| 12 | Memory Consistency | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/locksconsistency/12_consistency.pdf) · [视频](https://www.youtube.com/watch?v=nFXWmo9MFiY) | 待编写 |
| 13 | Fine-Grained Synchronization and Lock-Free Programming | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/finegrained/13_lockfree.pdf) · [视频](https://www.youtube.com/watch?v=GA1ObImqaMo) | 待编写 |
| 14 | Domain Specific Programming Languages | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/dsl/14_dsl.pdf) · [视频](https://www.youtube.com/watch?v=sRuyBNxCkGQ) | 待编写 |
| 15 | Transactional Memory 1 | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/transactions1/15_transactionalmem.pdf) · [视频](https://www.youtube.com/watch?v=rFFf3WIJ7BA) | 待编写 |
| 16 | Transactional Memory 2 | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/transactions2/16_heterogeneity.pdf) · [视频](https://www.youtube.com/watch?v=Tbk1vnYLQqI) | 待编写 |
| 17 | Hardware Specialization | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/hwaccel/17_heterogeneity_Spatial_wWfLWLq.pdf) · [视频](https://www.youtube.com/watch?v=2tAb3EgyjNw) | 待编写 |
| 18 | Accessing Memory + Course Wrap Up | [Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/wrapup/18_wrapup.pdf) · [视频](https://www.youtube.com/watch?v=J7v_ubArrno) | 待编写 |
| Review | Midterm Review | [视频](https://www.youtube.com/watch?v=nHPKVtLz5Ko) | 待编写专题复习 |

**编号注意：** Stanford 网站将复习课单列，不占主题讲次编号。YouTube 播放列表把它排在主题 L13 和 L14 之间，所以它是录播第 14 段，后面的录播序号比主题讲次大 1。

## 我们的写作标准

每章都应具有独立的讲解逻辑，并包含（具体检查项见 [自包含规范](./SELF-CONTAINED-STANDARD.md)）：
1. 目标与背景；
2. 概念与直观解释；
3. 数学模型 / 推导；
4. **自己写的**代码和实例；
5. 常见错误与边界；
6. 实验与性能分析；
7. 练习及参考答案；
8. 2023 官方 Slides、视频链接与准确的可核对出处。

**取材边界：** 不逐字粘贴讲课字幕，不大段翻译原 Slides，不转载完整课件截图。允许链接原始资料；只有核实的页码和时间点才能写成确切引用。不要把现代 AI Infra 延伸内容误称为 2023 年教授原话。

## 教材与笔记有什么区别？

原有 [notes/](../notes/) 是速查与练习笔记；本目录的章节是连续叙述、适合独立阅读的教材。遇到教材与速记不一致时，优先检查 [Stanford 2023 官方材料](https://gfxcourses.stanford.edu/cs149/fall23/)。

[来源状态清单](../sources/README.md) · [制作流程](../tools/README.md) · [章节模板](./CHAPTER-TEMPLATE.md) · [Markdown 自动检查](../tools/check_textbook.py)
