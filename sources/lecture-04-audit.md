# Lecture 04 来源核验记录（公开版）

**教材：** [第四章：并行编程基础](../textbook/04-parallel-programming-basics.md)

**课程：** Stanford CS149 Fall 2023 Lecture 4

**来源：** [官方课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/progbasics/) · [51 页 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/progbasics/04_progbasics.pdf) · [录像](https://www.youtube.com/watch?v=0-ztm8SKq70)

## 文字稿与课件范围

用户提供的英文自动转写从 ISPC 语义复习开始，到三个 Barrier 的用途和减少到一个的提示结束。全文已阅读，无时间码，含听不清和 ASR 术语问题，未与音频逐句校对。

开场 ISPC 绝对值复制、求和、Gang/Task 等复习主要延续上一讲材料，不给它们虚构本讲 PDF 页码；对照 [ISPC 官方手册](https://ispc.github.io/ispc.html) 和此前已核查的 [第 3 讲课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/multicore2-ispc/03_multicore2-ispc.pdf)。

本讲 PDF 共 51 页，已核对文字结构，抽查第 7、9、24、26、28、34、37、38 页图示，未逐页视觉复核。

| 页码（从 1 开始） | 内容 | 教材处理 |
| --- | --- | --- |
| 3–4 | 分解、分配、协同、映射 | 独立术语表、职责分层 |
| 5–12 | 依赖与 Amdahl、图像两阶段 | 展开公式和具体数字，区分改变算法与只增加资源 |
| 13–21 | 分配、任务、协同与映射 | 区分软件线程、实例和执行资源 |
| 23–26 | 原地网格扫描与波前 | 保留 0.2×自身加四邻居的规则，给 2×2 手算 |
| 27–31 | 改算法、红黑与通信 | 不宣称逐轮结果等价，区分 Core 分块与 Lane 连续访存 |
| 32–37 | 两种编程模型、红阶段伪代码 | 完整实现补上黑阶段，明确半阶段示意不等于求解器 |
| 38–44 | 共享地址空间、锁与原子性 | 区分概念交错与 C++ 数据竞争未定义行为 |
| 45–49 | 私有部分和、Barrier 与三槽位 | 单写者清零/停止，说明存储复用依赖与真实阶段依赖 |
| 50–51 | 模型对照与总结 | 回到四个步骤 |

## 实际修正与限定

1. uniform 变量直接接收 varying 累加，在 ISPC 1.32.0 实际是编译错误；不只沿用口述中的 race 描述。
2. 同一共享 bool 或 float 上的多线程写，即使值相同，也不能自动当作安全 C++；实现采用单写者与同步发布。
3. 部分课件 ISPC 输出下标、C++ 名称和标点有简化或不一致；教材实验独立编写，完整编译校验。
4. 课件网格下标和边界循环为示意；本章明确内部 1..N、外圈 0/N+1，用半开行区间防止遗漏非整除行。
5. 课件自身也说明数据并行伪代码只展示红阶段；本章 C++ 包含完整红黑阶段与停止条件。
6. 三槽位第 49 页是课件补充，文字稿只留下提示；减少归约屏障不意味着可删除红黑阶段真实依赖。
7. 同一停止阈值不自动证明不同算法逐步一致或达到同等误差，校验分为固定红黑轮次与残差/边界检查。
8. 上下文切换周期数、线程创建演示倍数均不作为通用硬件常数；更宽 Gang 不保证单调提速。

## 一手语义参考

- [ISPC 官方手册](https://ispc.github.io/ispc.html)：uniform/varying、Gang、foreach、归约和竞争。
- [C++ 数据竞争规范草案](https://eel.is/c++draft/intro.races)：冲突访问与 happens-before。
- [C++ Barrier 规范草案](https://eel.is/c++draft/thread.barrier.class)：阶段同步与可见性。代码实际提供 C++17 mutex/condition_variable 兼容实现。

## 代码核验

| 程序 | 环境与输入 | 结果 |
| --- | --- | --- |
| models.py | Python 3，Amdahl、2×2 三算法一轮、局部和、行覆盖、着色 | 全部断言通过 |
| basics.ispc + ispc_main.cpp | macOS ARM64，ISPC 1.32.0，NEON 4/8 实例各 9 种规模 | 绝对值复制、归约与尾部哨兵通过 |
| 故意错误的 uniform 累加 | 仓库外临时诊断例 | 编译按预期失败，提示 varying float 不能在 += 中转成 uniform float |
| redblack.cpp | macOS ARM64，Apple Clang 16，5 种 N × 4 种 Worker × 5 种检查 | 100 组通过，边界不变，最差残差约 8.65e-9 |
| redblack.cpp ThreadSanitizer 构建 | 同一 100 组 | 通过，无竞争报告 |

测试不是通用 PDE 收敛证明，也不是所有并发调度的证明；未做性能 Benchmark 或 x86 实机验证。原始全文、官方 PDF、构建产物与第三方工具保留仓库外，不上传公开仓库。
