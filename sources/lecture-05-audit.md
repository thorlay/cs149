# Lecture 05 来源核验记录（公开版）

**教材：** [第五章：工作分配与调度](../textbook/05-work-distribution-scheduling.md)

**课程：** Stanford CS149 Fall 2023 Lecture 5

**来源：** [官方页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/perfopt1/) · [62 页 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/perfopt1/05_progperf1.pdf) · [录像](https://www.youtube.com/watch?v=mmO2Ri_dJkk)

## 文字稿范围

用户提供英文自动转写，从上讲网格迭代与三个 Barrier 的复习开始，到 Greedy Join 与 Cilk 总结结束。已阅读全文并与课件主题对照，无时间码且未逐句核验音频。按官方编号属于第 5 讲；所复习的迭代与屏障内容详见 [第四章](../textbook/04-parallel-programming-basics.md)。

不保存或提交完整第三方字幕、官方 PDF 或编译器；原始资料仅供本地核查。

## 课件核查

PDF 共 62 页，已核对文本结构、代码示意和主要公式。第 4、14、29、44、49、60 页作视觉抽查，未逐页审图。

| PDF 页码（从 1 开始） | 内容 | 本章处理 |
| --- | --- | --- |
| 2–4 | 简单基线、测量与失衡 | 定义 Work/Span、负载效率，使用原创数字展开 |
| 5–9 | 静态、交错和半静态分配 | 给覆盖证明和周期成本反例 |
| 10–15 | 动态队列与任务粒度 | 原子领取、非整除尾部、领取成本模型 |
| 16–18 | 大任务长尾与成本顺序 | 15 个短任务加 1 个长任务的完整算例 |
| 19–21 | 分布式队列与依赖 | DAG 就绪计数与结束检测 |
| 22–33 | Fork-Join、Cilk 与线程池 | 区分逻辑并行、线程与当前工具链 |
| 34–43 | Child/Continuation 与平坦循环 | 解释两种策略与串行生成链 |
| 44–49 | Deque、Victim 与递归生成 | 固定两端约定，注明随机结果的理论前提 |
| 50–62 | sync、描述符、Greedy Join | 解释逻辑等待、Worker 协助与继续执行的唯一性 |

开场多版本 diff 是对上一讲的复习，不能在本讲 62 页中伪造出处页码。教材三槽位协议是作者整理的、具有明确前提的归约示意，不声称替代完整网格算法。

## 修正与限定

1. 自动转写中的 silk/sink/steel 按上下文分别理解为 Cilk/sync/steal；conversion 按迭代上下文解释为 convergence。未把听不清片段补写成确定的原话。
2. 第 14 页块内示意循环使用 j，却仍访问 i；可运行程序按当前元素下标计算。
3. 第 49 页中点缺少 start 偏移；教材使用 lo+(hi-lo)/2，并检查非零起点的递归区间覆盖。
4. 快排示意的 last/end 命名不一致、边界表达不适合直接复制；教材给清晰半开区间伪代码，不宣称原示意可直接编译。
5. 课堂总时间与有用时间的口述对比不能不加定义地用于跨线程求和；教材区分墙钟和 Worker 累计时间，未照抄相减口径。
6. “现代 C++ 编译器都有 Cilk”不当作当前事实；对照 OpenCilk 官方教程和安装说明，实际实验仅依赖标准 C++17。
7. 从 Deque 队首偷较早子树通常得到更多工作，不是对所有任务精确选择最大成本；两端操作不自动让普通容器并发安全。
8. 随机工作窃取的期望复杂度注明 Fully Strict 结构与模型条件，不扩展成任意 DAG、阻塞、异构或实时场景的保证。

## 额外一手来源

- [OpenCilk 并行任务教程](https://www.opencilk.org/doc/tutorials/introduction-to-cilk-programming/)：spawn、同步范围及现代 cilk_scope。
- [OpenCilk 工作窃取术语](https://www.opencilk.org/doc/reference/glossary/work-stealing/)：运行时概念。
- [Blumofe / Leiserson，Scheduling Multithreaded Computations by Work Stealing](https://www.cs.cornell.edu/courses/cs612/2006sp/papers/blumofe94.pdf)：1994 年原始论文及 Fully Strict 分析范围。
- [OpenCilk 安装说明](https://www.opencilk.org/doc/users-guide/install/)：平台与专用工具链。

## 代码验证

| 程序 | 范围 | 验证结果 |
| --- | --- | --- |
| scheduling_models.py | 静态/循环分配、动态长尾、DAG、环检测、区间偷取轨迹、槽位关系 | 全部断言通过 |
| scheduling.cpp | macOS ARM64、Apple Clang 16、C++17；6 种规模 × 3 种线程数 × 6 配置 | 108 组合通过；每项恰好执行一次，结果与串行一致 |
| scheduling.cpp 观察模式 | N=128、4 Worker、三类策略和四种动态块长 | 正常运行，打印工作量、领取次数和时间；不发布固定加速比 |

没有运行 Cilk/OpenCilk 程序，没有实现无锁 Deque 或真正的 continuation-stealing 运行时，没有做 GPU 或分布式实验。Python 的偷取轨迹是固定顺序模拟，不是随机算法性能定理的实证。
