# 第 04 章｜并行编程基础：从程序语义到分解、同步与网格求解

> Stanford CS149 · Fall 2023 · Lecture 4 — Parallel Programming Basics
>
> **状态：自包含中文教材，第一版。** 本章结合用户提供的英文自动转写、官方 51 页 Slides、ISPC 官方手册与 C++ 并发语义，独立编写解释、算例与实验。文字稿已阅读全文，无时间码，含听不清和术语误识别，尚未与原始音频逐句核验。已核对课件文字结构并抽查关键图页，并非所有页都完成了视觉复核。本文不是官方授权教材或完整逐字稿。

**先修知识：** 变量、数组、循环、函数和基本 C++ 语法。本章重新定义 ISPC 实例、任务、线程、锁、屏障和归约；不要求先读其他章节，也不需要 GPU 或数值分析背景。

**学习时间：** 阅读与纸笔练习约 2–3 小时；运行 Python、C++ 与可选 ISPC 实验约 1–2 小时。

**配套实验：** [第四章完整代码与说明](../labs/lecture04/README.md)。所有核心代码也完整收录于本页。官方来源、测试环境与未核验部分列于章末。

## 0. 本章的问题：程序说的“并行”，到底是哪一层？

你看见一个循环，每次迭代更新数组的一个位置。它能并行吗？如果每个位置只依赖自己的输入，可能可以；如果更新值需要前一个位置刚计算出的结果，就不能随意改变顺序。

再看一个“8 个程序实例”的 ISPC 函数。这是否表示操作系统创建 8 个线程、占用 8 个 Core？不是。逻辑实例可能由同一线程发出的向量指令完成。

再看一个所有线程都能访问的共享变量。它是否意味着每个线程都能随时读写，并自动看到正确结果？也不是。共享地址空间提供访问能力，不替你维护所有数据依赖。

本章要把这些问题连接起来：先判断程序要求计算什么，再找出可并行的工作，决定谁负责什么，安排通信与同步，最后讨论如何映射到硬件。贯穿全章的例子是一个简单二维迭代求解器；即使不打开课件，也能手算一轮并运行完整校验程序。

## 1. 语义和实现：先确定答案，再讨论执行方式

### 1.1 一份程序可以有不止一种合法实现

**Semantics（语义）**描述程序必须产生的效果，以及执行必须满足的约束；**Implementation（实现）**决定怎样利用具体硬件产生这些效果。

例如任务是对每个 i 计算 y[i]=|x[i]|。只要输入输出布局满足约定、各迭代没有冲突，按顺序做、分给多核做、用 SIMD 做，都可能实现相同结果。

**SIMD（单指令多数据）**用一条向量指令控制多个数据位置，位置常称为 Lane。**Core（核心）**则能执行指令流，可能含多个执行单元。Lane、Core、软件线程与逻辑程序实例，分别属于不同层次，不能因为它们都“处理一些数据”就混用名称。

### 1.2 ISPC 的 Gang 和程序实例

ISPC 采用 **SPMD（单程序多数据）**抽象：写一份程序，由一组逻辑实例共同运行。这个组称为 Gang，`programCount` 是组内实例数，`programIndex` 是当前实例编号，从 0 到 programCount−1。

调用一个普通 ISPC 导出函数，可以把它理解为这个 Gang 完成相应工作后返回调用者。在本章 CPU 路径中，编译器通常把 Gang 编译成调用线程执行的 SIMD 指令，不为每个实例创建一个操作系统线程。

```text
C++ 调用者：一个软件线程
       │ 普通函数调用与返回
       ▼
ISPC 的逻辑 Gang：实例 0、实例 1、……
       │ 编译器组织向量指令和掩码
       ▼
当前 CPU Core 的 SIMD 执行资源
```

对完全独立的逐元素任务，逐个模拟实例可以帮助理解结果；但一般 ISPC 还允许跨实例操作，并有控制流、可见性与收敛规则，不能推论任意 Gang 都可把各实例整段串行跑完而保持相同语义。

### 1.3 Gang 比物理向量宽，会怎样？

若一次物理向量操作只能容纳 4 个 float，而 Gang 中有 8 个逻辑实例，编译器可以用多条向量指令实现同一逻辑步骤，而不是因此自动创建两个软件线程。

更多实例有时提供更多独立指令，帮助硬件利用 **ILP（指令级并行）**；也可能增加寄存器压力、掩码和尾部处理开销。不能把“Gang 更宽可能更快”写成必然单调提速。本章会在 Apple Silicon 上分别编译 4 与 8 实例版本，只检查正确性，不宣称哪种一定更快。

## 2. 把迭代交给谁：手动下标与 foreach

### 2.1 同一轮各 Lane 的地址很重要

设 N=32、Gang 宽 W=8。交错分配让实例 p 处理 p、p+8、p+16、p+24；连续分块则让实例 p 处理 [4p,4p+4)。第一轮访问下标如下：

| 实例 p | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 交错，第一轮 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| 分块，第一轮 | 0 | 4 | 8 | 12 | 16 | 20 | 24 | 28 |

交错时，一个实例沿时间看在跳步，但同一条向量操作的各 Lane 访问连续元素，往往更便于连续向量加载。分块时，每个实例自己连续，同一轮的 Lane 却相隔更远，可能需要 Gather，即从分散地址聚集数据。

Cache Line（缓存行）是缓存搬运与管理的一块连续数据。地址分散可能触及更多缓存行，但“分散访问”不等于一定发生多个缺页：TLB 缓存的是地址翻译，TLB Miss、Cache Miss 与 Page Fault 是不同层次的事件，不能互相当作同义词。

### 2.2 foreach 是整个 Gang 的工作范围

以下是 ISPC 语法片段，完整程序见第 14 节：

```c
foreach (i = 0 ... n) {
    y[i] = abs(x[i]);
}
```

它要求整个 Gang 合作完成 n 个迭代，不是每个实例各自执行 n 次。编译器安排哪个实例做哪个 i，并处理尾部不足一个 Gang 的情况。

你应首先问“这些迭代真的可以独立执行吗”，再分析编译器怎样分配。把独立工作留给较高层抽象，有助于以后更换硬件或编译器；显式 `programIndex` 等低层机制则允许程序员在确有需要时更精确地控制映射。

### 2.3 一个正确的例子：绝对值写两次

对于每个输入 x[i]，计算绝对值并写到 y[2i]、y[2i+1]。例如输入 [−2,3,−1]，输出是 [2,2,3,3,1,1]，输出容量必须至少为输入的两倍。

为什么独立？迭代 i 写入集合 {2i,2i+1}；若 i≠j，这个集合与 {2j,2j+1} 不相交。假设输入与输出不重叠，不同迭代也不会通过写输出破坏别人的输入。

这类读写集合检查，比“循环长得像可以并行”更可靠。

### 2.4 一个错误的例子：按符号向左写

假设伪代码规定：若 i>0 且 x[i]<0，写 y[i−1]=x[i]；否则写 y[i]=x[i]。输入 [2,−3] 时，迭代 0 想写 y[0]=2，迭代 1 想写 y[0]=−3。

如果任意调度这两次写，无法把某个固定结果当成程序承诺。编译器没有发现或没有报错，也不证明程序安全；数据依赖有时取决于运行时下标，自动分析并不总能解决。

本章不会通过运行存在数据竞争的 C++ 代码来“演示稳定的错误输出”，而是用明确的读写冲突和调度轨迹解释问题。

## 3. 归约：很多份局部结果怎样成为一个答案？

### 3.1 uniform 与 varying 并不是“有锁”和“没锁”

`varying` 数值表示每个实例有自己的逻辑值；`uniform` 表示整个 Gang 使用同一个值。普通局部浮点变量通常是 varying。uniform 可以变化，但更新后仍必须是全 Gang 的单一值。

假如 8 个实例各维护一个 `sum`，最后得到的是 8 份部分和，不能直接当作一个 C++ 返回值。另一方面，把变量改为 `uniform`，也不会自动把 8 个输入加起来。

下面是**故意展示编译错误的 ISPC 片段**，不是正确可运行的求和方法：

```c
uniform float sum = 0.0f;
foreach (i = 0 ... n) {
    sum += x[i];
}
```

`x[i]` 在各实例中可能不同，为 varying；把它累加到 uniform 变量无法满足类型规则。本次 ISPC 1.32.0 实际拒绝了这个程序，报告无法在 `+=` 中把 varying float 转为 uniform float。

课堂口述把这个例子宽泛地称作 race。教材区分两件事：这个直接赋值形式当前会在编译时被拒绝；通过指针让多个实例修改同一内存位置，才可能构造出能通过编译却具有竞争的另一类程序。

### 3.2 先局部累加，再跨实例合并

设数据为 [9,2,7,1,4,3,8,6,5,10]，W=4，按交错方式分配：

| 实例 | 读到的数据 | partial |
| --- | --- | --- |
| 0 | 9、4、5 | 18 |
| 1 | 2、3、10 | 15 |
| 2 | 7、8 | 15 |
| 3 | 1、6 | 7 |

再把四份部分和合并，得到 18+15+15+7=55。这个“多值变一值”的过程叫 **Reduction（归约）**。ISPC 的 `reduce_add(partial)` 对当前活动实例的值求和，返回 uniform 结果。

### 3.3 实现可以用向量累加，但输出仍是一个值

一种 SIMD 实现是：每次加载一个向量，逐 Lane 加入 partial 向量；循环结束后，再把 partial 的各 Lane 横向合并。跨 Lane 的合并不等于为每个 Lane 建一条软件线程。

浮点加法存在舍入，改变归约树或迭代分配可能改变最低位。实际校验应按需求使用合理误差界；本章小型 ISPC 实验使用可精确表达的 1/4 倍数，方便做精确比较，不把它推广成所有浮点和都应逐位相等。

## 4. Task、线程池与两种“切换”

### 4.1 多核是另一层任务分配

ISPC 的 `foreach` 把迭代映射到 Gang 内的实例。Task（任务）则可以描述一份交给某个 Gang 完成的工作；运行时可将多个 Task 分配给多个 Worker 线程，每个线程再使用 SIMD。

```text
很多 Task
    │ 任务运行时安排
    ├── Worker 0：执行一个 Gang，再领下一 Task
    ├── Worker 1：执行一个 Gang，再领下一 Task
    └── Worker 2：执行一个 Gang，再领下一 Task
```

任务数量与 Worker 数量不相等。一个线程池可以处理十万个任务，不必创建十万个操作系统线程。实际池大小由运行时、平台和配置决定，不承诺永远等于逻辑处理器数。

### 4.2 为什么空任务可能串行更快？

调用一个几乎不做事的函数，只需很少的有用工作。为每个调用创建和回收线程，或者让多个 Worker 同步领取它，都可能比直接调用更贵。

设 N 个任务各有用成本 c，串行成本约为 Nc；P 个 Worker 的理想有用成本为 Nc/P，但线程池启动、分发和同步还要额外花 H 时间。这个粗模型中，想获得收益需要：

$$
Nc\left(1-\frac{1}{P}\right)>H
$$

它没有包含负载失衡、Cache、带宽或动态竞争，只用于解释“任务太小时并行不划算”。课堂提到的几百倍或几十倍差异是特定演示结果，不是任何机器都应复现的常数。

增加每任务的计算量，有机会摊薄管理成本；但不应加入无用计算来制造漂亮的加速比，优化目标仍是更快完成原任务。

### 4.3 操作系统上下文切换不等于硬件多线程

**软件上下文切换**由操作系统改变哪些软件线程获得执行机会，需要维护运行状态与调度；**硬件多线程**是在处理器已经保存的多个上下文中选择就绪指令。

两者粒度与成本不同，不能把操作系统换线程当成每次 Cache Miss 都触发的低成本机制。文字稿中“一周期”“十万周期”等说法用于强调量级差异，并不是所有现代处理器和操作系统的固定实测值。

大量线程在 I/O 阻塞型程序中可能有意义；本讲主要考虑 CPU 计算型工作，不能因此推出“任何应用都不得多于逻辑处理器数的线程”。

## 5. 四个步骤：分解、分配、协同、映射

### 5.1 把一串术语变成四个具体问题

| 步骤 | 英文 | 要回答的问题 | 本章例子 |
| --- | --- | --- | --- |
| 分解 | Decomposition | 哪些工作可以独立进行？ | 同色网格点能否并发更新 |
| 分配 | Assignment | 每个 Worker 负责哪份工作？ | 连续分配若干行 |
| 协同 | Orchestration | 怎样访问数据、通信并保持依赖？ | 局部变化量归约、红黑阶段间屏障 |
| 映射 | Mapping | 逻辑参与者落到什么硬件位置？ | 软件线程由 OS 调度，实例由编译器映射到 SIMD |

“我创建了 8 个线程”只回答了一部分实现问题，还没有说明工作是否独立、每人做什么、结果何时可用。

### 5.2 谁承担这些职责？

程序员常负责识别可并行的算法结构；语言、编译器或运行时可以负责具体分配与部分同步；硬件和操作系统负责底层执行与线程安排。

例如手写 C++ 区间划分是在程序里决定任务分配；ISPC `foreach` 让编译器处理 Gang 内分配；任务系统让空闲 Worker 获取下一 Task，则把另一层分配交给运行时。

“让系统处理”不表示不需要理解它，只表示接口承担了相应责任。程序员仍要保证所表达的独立性真实成立。

### 5.3 两个线程也未必对应两个独立 Core

操作系统可能把两个软件线程放在不同 Core，或放在同一 Core 的两个硬件上下文。前者通常提供更多独立执行资源，后者共享部分资源；共享数据、节能策略和机器负载又可能影响选择。

因此不能把“开了两个线程却没快两倍”直接判定为并行概念错误。分解、分配、同步、映射和数据访问都会影响最终结果。

## 6. Amdahl 定律：剩下一小段串行，会限制多少？

### 6.1 从固定工作量推导公式

设某个固定输入的串行时间为 T₁，比例 S 的工作在当前算法中必须串行，其余比例 1−S 可以在 P 个同速处理器上完美均分，忽略额外开销。

串行部分仍要 ST₁，并行部分至少要 (1−S)T₁/P，所以：

$$
T_P\ge T_1\left(S+\frac{1-S}{P}\right)
$$

加速比是同一任务的串行时间与并行时间之比：

$$
\operatorname{Speedup}(P)=\frac{T_1}{T_P}\le\frac{1}{S+(1-S)/P}
$$

当 S>0、P 趋向无限，上界趋向 1/S；S=0 时，这个理想模型不提供有限的串行上限，但真实机器仍有其他约束。

### 6.2 具体数字比“只有一点串行”更直观

| 串行比例 S | P=8 的理想加速上界 | P=64 的理想加速上界 | P→∞ |
| --- | --- | --- | --- |
| 1% | 7.477 | 39.264 | 100 |
| 10% | 4.706 | 8.767 | 10 |
| 50% | 1.778 | 1.969 | 2 |

即使 S=0.1%=0.001，无限处理器也只能到 1000 倍；它不支持“加几亿算术单元，就得到几亿倍加速”的推理。ALU 数量也不等于可以无损运行相同数量独立完整处理器。

S 是相对于串行基线的工作或时间比例，不是某次并行运行中“看到只有一个线程活动”的墙钟比例。只讨论改变处理器数量、固定算法与问题规模的理想上界，不把它当成换算法后永远不能突破的限制。

### 6.3 图像增亮后求平均：漏掉归约会怎样？

设图像为 N×N，像素数量 M=N²。为了教学，假定增亮每像素需 1 单位工作，累加求平均也每像素需 1 单位工作，忽略常数边界与最后除法。原程序约需 2M 时间。

只并行增亮、平均仍串行，时间约为 M/P+M，因此：

$$
\operatorname{Speedup}\le\frac{2M}{M/P+M}=\frac{2}{1+1/P}<2
$$

N 再大，也不能让这一版摆脱接近 2 的上限。问题不是图片不够大，而是后半部分没被并行化。

### 6.4 局部和改变了串行部分

让每个 Worker 对自己负责的像素计算部分和，最后用一个 Worker 合并 P 个部分和。教学时间模型变成：

$$
T_P\approx\frac{M}{P}+\frac{M}{P}+P=\frac{2N^2}{P}+P
$$

N=1024、P=8 时，原时间约 2097152 单位，只并行增亮约 1179648 单位；加上部分和后约 262152 单位，加速接近 8。

最后合并部分和也能使用树形归约，理想 Span 可由 O(P) 降到 O(log P)，但要付出相应通信与同步。不能说任意求和都本质上只能由一个线程逐项执行。

若 P 相对于 N 过大，P 项合并、任务开销和数据传输就不再可忽略。前面模型接近线性加速的条件，是最后一项相对主体足够小，而不是“只要是并行就线性”。

## 7. 网格求解器：把数据依赖找出来

### 7.1 明确数据、边界和更新规则

用一个 (N+2)×(N+2) 网格，内部 N×N 个点需要更新，外圈是固定边界。下标 i、j 从 1 到 N 表示内部，0 和 N+1 表示边界。

本章保持课件的更新形式：

$$
u_{i,j}\leftarrow\frac{u_{i,j}+u_{i-1,j}+u_{i+1,j}+u_{i,j-1}+u_{i,j+1}}{5}
$$

右侧包含自己原来的值和上下左右四个邻居，不是另一个常见的“四邻居平均”版本。把它写成系数 0.2，是相同的教学规则。

每次完整更新遍历称为 **Sweep（扫描）**。可以统计所有更新的绝对变化量之和 diff，再以 diff/N² 是否低于阈值判断是否停止。

这是一种数值迭代方法。课件称其为 Gauss-Seidel 求解示例；更精确地说，这个带自身旧值的形式可看作带松弛的邻域更新，不能把所有 Gauss-Seidel 公式都等同于这一行。

### 7.2 原地顺序扫描中，新值与旧值混在一起

如果按行从左到右、从上到下，并直接写回同一个数组，那么更新 (i,j) 时，上方和左方通常已是本轮新值，下方和右方仍是旧值。

因此 (i,j+1) 读取的左邻居，依赖刚更新的 (i,j)；下一行又依赖上一行的新值。只因为输出下标不同，就把所有点放进并行循环，会破坏原程序的读取版本。

**In-place（原地）**指直接修改原数据；它可以节省另一个网格，却也把更新顺序变成了算法含义的一部分。

### 7.3 双缓冲能消除写入冲突，但改变了算法

如果所有点从旧网格读、写入新网格，下一轮再交换两份网格，它们就不再读取本轮刚产生的邻居值。这是 Jacobi 式更新思路，不能说它逐步等价于前面的原地顺序扫描。

双缓冲是一种重要手段，但必须先确认任务允许改变数值迭代方法。是否达到相同目标、要多少轮、误差怎样界定，都要重新检查。

### 7.4 保留原扫描语义的波前执行

原地扫描的上下、左右依赖可以沿 i+j 相同的反对角线分层：先更新 (1,1)，再更新 (1,2) 与 (2,1)，再更新下一条反对角线。

```text
同一数字是同一条波前，可在相应依赖满足后一起做：
1 2 3 4
2 3 4 5
3 4 5 6
4 5 6 7
```

每点都先等上方和左方更新，右方与下方保持尚未更新的旧值，能遵守该扫描的数据版本要求。N×N 个点需要 2N−1 个波前，最宽处有 N 个点；若每点单位成本且忽略归约，工作为 N²、Span 约为 2N−1。

它有并行机会，但开始和结束阶段很窄，还可能每条波前都同步、访存不连续。是否值得实现，要比较同步和数据访问成本，不能仅凭图上存在两条并行边就判断性能很好。

## 8. 红黑更新：允许改变算法时，换一种更易并行的顺序

### 8.1 棋盘着色为什么产生独立集合？

把 (i+j) 为偶数的点叫红点，为奇数的点叫黑点。上下左右每移动一步都会改变奇偶性，所以红点的四邻居全是黑点，黑点的四邻居全是红点。

```text
R B R B
B R B R
R B R B
B R B R
```

先固定所有黑点，更新全部红点；再固定已经更新的红点，更新全部黑点。同一颜色的不同点互不读取对方，分别写入自己的位置，因此在该阶段可并行。

更新式仍读取自己的旧值，这不会制造跨线程依赖：只要每个点由唯一 Worker 更新，就没有另一个 Worker 同时写它。

### 8.2 同色独立，不表示红黑阶段也独立

黑点需要红点本轮的新值。某个 Worker 红点算完了，不代表别人的红点也已经可供读取；需要满足跨 Worker 的阶段依赖，再开始黑点阶段。

黑点完成后，下一轮红点又需要这些黑点的值。因此完整迭代是“所有红点完成 → 所有黑点完成 → 下一轮”，而不是各线程任意独立地重复自己局部的红黑更新。

这是 **Orchestration** 的典型问题：已经找到了独立子集，还得安排子集之间的通信与可见性。

### 8.3 一轮手算：三种顺序不是同一个序列

设内部只有 2×2，初始内部均为 0；上边界都为 1，其余边界为 0，角点不影响内部点的四邻居读取。

按行原地更新：

- (1,1)=0.2×(0+1+0+0+0)=0.2；
- (1,2)=0.2×(0+1+0+0.2+0)=0.24；
- (2,1)=0.2×(0+0.2+0+0+0)=0.04；
- (2,2)=0.2×(0+0.24+0+0.04+0)=0.056。

Jacobi 全从旧网格读，只得到第一行 [0.2,0.2]，第二行 [0,0]。

红黑先更新 (1,1) 与 (2,2)，得到 0.2 和 0；再更新 (1,2)、(2,1)，得到 0.24 和 0.04：

| 方法 | 第一次完整 Sweep 后的内部网格 |
| --- | --- |
| 按行原地扫描 | [[0.2,0.24],[0.04,0.056]] |
| Jacobi 双缓冲 | [[0.2,0.2],[0,0]] |
| 红黑扫描 | [[0.2,0.24],[0.04,0]] |

如果用原扫描的一轮结果去测试红黑的一轮结果，就会把合法的算法变化误判为并行实现错误。正确测试应先比较“相同红黑算法的串行版与并行版”。

### 8.4 相同固定点，不等于相同收敛过程

若迭代达到不再变化的固定点 u*，更新式满足 5u*=u*+四邻居和，即：

$$
4u^*_{i,j}-u^*_{i-1,j}-u^*_{i+1,j}-u^*_{i,j-1}-u^*_{i,j+1}=0
$$

这给出本章固定边界问题的离散平衡方程。不同合法迭代可能逼近同一个平衡解，但过程、轮数和舍入不同。

这里不证明任意方程、任意网格或任意更新权重下都收敛，也不承诺红黑方法总比原顺序需要更多或更少轮次。课堂允许换算法，需要数值领域知识；实际应用也应由问题的数学条件和误差要求支持。

## 9. 分配影响通信：为什么在 Core 之间可能更喜欢分块？

### 9.1 连续行可以减少跨 Worker 的邻接关系

让每个 Worker 拿一段连续行，段内部的上下邻居大多仍归自己；与其他 Worker 的交换集中在块边界。

例如 N=8、P=4、每 Worker 两行，内部行之间共有 7 条行分界。连续分块只有 3 条分界跨 Worker，每条横跨 8 列，共 24 条跨 Worker 的纵向相邻边；轮流分行时，7 条分界都跨 Worker，共 56 条。

这是计算数据依赖切割数量的简单示例，不是实际内存总线字节的精确计数。共享内存 CPU 的缓存一致性、缓存行和预取，或分布式机器的显式消息，都会改变真实代价。

### 9.2 SIMD 内和 Core 间，优化的对象不同

第 2 节的交错分配让同一向量指令访问连续元素；这里的 Core 间分块，强调让一个 Worker 的邻域数据尽量留在较少的共享边界内。

二者可以组合：先给不同 Core 分连续行块，再在每个块内部让相邻 SIMD Lane 处理相邻元素。不要从“ISPC 交错访存常很好”推出“整个网格也应把每一行轮流放在不同处理器上”。

### 9.3 共享地址空间仍然在通信

线程直接读另一个线程刚写的数据，表面没有 send/receive，但底层可能仍要在存储层级或缓存间移动数据。共享地址空间把通信表达成 Load/Store，并没有让通信变成零成本。

本章的多线程程序使用同一块内存，不实现分布式 Halo Exchange；Halo 是一个分区为了更新本地边界而需要的邻居数据区域。这个术语用于理解依赖，不要求读者配置集群。

## 10. 锁与屏障：回答的是两个不同问题

### 10.1 锁保证临界区互斥

若所有线程都执行共享 `diff += myDiff`，一次更新概念上包含读取、相加、写回。两个线程可能都读到旧值，各自加完后写回，其中一份贡献丢失。

```text
初始 diff=0；线程 A 要加 2，线程 B 要加 3。
A 读到 0；B 读到 0；A 写入 2；B 写入 3。
概念交错模型最终得到 3，而需要的结果应为 5。
```

互斥锁让同一时刻只有一个线程执行受保护的读改写，避免这种交错。C++ 中对共享普通变量缺少必要同步的数据竞争会导致未定义行为，上表只是解释风险的概念模型，不是 C++ 保证只会出现的错误结果。

### 10.2 锁不会替你等待所有贡献完成

即使每次累加都加锁，某个线程释放锁后马上读取 diff，也可能只读到目前已经提交的部分结果。锁保证更新没有互相覆盖，不保证所有线程已经算完。

**Barrier（屏障）**让参与者都抵达某个阶段边界后，才允许继续，并提供正确使用所需的内存可见性。因此“互斥修改共享和”与“等待所有修改都完成”是不同需求。

反过来，在循环结尾放一个 Barrier，也不能修复之前已经发生的无保护并发累加。屏障不会把丢失的贡献重新算回来。

### 10.3 私有化减少共享更新次数

原始做法若每更新一个网格点都锁一次，每轮大约需要 N² 次受保护累加。改成每 Worker 先算私有 `myDiff`，阶段结束后每人只合并一次，共享累加次数就变成约 P 次。

还可以让每个 Worker 写自己的 `partial[p]`，屏障后由一个线程按固定顺序汇总；这避免共享浮点累加上的锁。汇总是串行管理工作，但通常比每点都争同一个位置便宜。

它不意味着锁消失了所有成本：屏障本身也要协调，数组布局也可能导致缓存行竞争。先验证正确性，再通过测量决定是否需要继续优化。

## 11. 课堂的三个 Barrier：清零、汇总、读取跨越了不同轮次

### 11.1 一个经过单写者整理的教学时序

下面是**只讨论一轮贡献归约的伪代码，不是完整红黑求解器**：

```text
重复每一轮：
  指定的线程 0 将 global_diff 清零。
  Barrier A：确保所有人都等到清零完成。
  每个线程计算自己的 my_diff。
  加锁，将 my_diff 加入 global_diff，再解锁。
  Barrier B：确保所有人的贡献都合并完毕。
  每个线程读取最终 global_diff，保存本轮继续/停止判断。
  Barrier C：确保所有人都读完，再允许下一轮清零。
  根据保存的判断继续或退出。
```

A 防止有人累加后又被清零；B 防止有人读取尚不完整的和；C 防止快线程开始下一轮、覆盖慢线程还没读的结果。

课件是伪语言示意，某些行让所有线程都写同一个 `diff=0` 或 `done=true`。如果翻成普通 C++，即使同时写相同数值也可能构成数据竞争。可运行版本应安排单写者或使用符合语义的同步手段，不能仅凭“大家写的一样”证明安全。

### 11.2 什么时候可以减少屏障？

上面有些依赖来自复用同一个 global_diff 存储位置，而不是数学任务天然需要。保存不同轮次的 diff，可以减少覆盖旧结果造成的等待。

一种三槽位的教学协议是：所有槽位预先清零；轮次 t 向 diff[t mod 3] 受保护地累加；线程 0 清零下一轮 diff[(t+1) mod 3]；大家在这一轮的 Barrier 汇合后读取当前槽位，再决定是否继续。

关键安全理由是：线程进入轮次 t，意味着上一轮 Barrier 已完成，所有线程至少完成了轮次 t−2 的读取。下一轮的槽位与 t−2 模 3 相同，可安全复用；却与可能仍被慢线程读取的 t−1 不同。

这里“一轮一个屏障”只针对该归约协议，不能因此删除完整网格算法中真实需要的红到黑、黑到下一轮红的数据依赖。三槽位协议还依赖相同轮次推进、单写者清零和正确可见性，不能脱离前提照搬。

### 11.3 本章实际求解器也有三个屏障，但含义不同

后面的完整红黑程序每个 Sweep 使用：B1 等所有红点完成；B2 等黑点和各 Worker 的 partial 完成；B3 等线程 0 发布停止决定。

它不复用一个需要每轮全局清零的累加变量，所以没有课堂 Barrier A 的对应位置。两个程序恰好都出现三个屏障，不代表它们在证明同一件事。判断同步是否必要，应对照依赖，而不是数关键字。

## 12. 收敛测试：小变化量不自动等于正确解

### 12.1 停止条件与方程残差分别检查什么？

平均更新量定义为：

$$
\Delta=\frac{1}{N^2}\sum_{i,j}|u^{\mathrm{after}}_{i,j}-u^{\mathrm{before}}_{i,j}|
$$

它观察一次 Sweep 改变了多少。残差则检查当前值是否满足目标方程。本章固定点方程的最大绝对残差为：

$$
r_{\max}=\max_{i,j}|4u_{i,j}-u_{i-1,j}-u_{i+1,j}-u_{i,j-1}-u_{i,j+1}|
$$

如果程序漏更新了一半点，或者丢失部分变化量，平均变化可能很小，却不能据此宣称已经求出正确解。实际测试还应检查边界是否保持、值是否有限，以及与可信基线是否一致。

### 12.2 两类校验不能混在一起

**固定轮次校验：** 串行红黑和并行红黑做相同轮数，比较整个网格。这主要检查分配、阶段同步与数学计算是否一致。

**收敛校验：** 使用阈值运行，检查最终网格、边界和残差。这检查停止逻辑与最终数值质量。不同归约顺序可能导致阈值附近轮数略有差异，所以不能无条件要求所有算法都以相同轮数停止。

本章实验使用 double，不开启放松浮点规则的编译选项；只对小型明确边界的测试问题作验证，不把这些误差阈值作为任意 PDE 的精度保证。

## 13. Python：独立复算公式与算法差异

以下程序只依赖 Python 3 标准库，用来验证 Amdahl 数字、三种更新的一轮结果、局部和，以及行区间覆盖和同色邻接独立性。

保存为 `models.py`：

```python
"""Paper-and-pencil models for parallel programming basics."""
from math import isclose


def amdahl(serial_fraction, processors):
    return 1/(serial_fraction+(1-serial_fraction)/processors)


def initial(n):
    a = [[0.0]*(n+2) for _ in range(n+2)]
    a[0] = [1.0]*(n+2)
    return a


def value(a, i, j):
    return .2*(a[i][j]+a[i-1][j]+a[i+1][j]+a[i][j-1]+a[i][j+1])


def sweep(a, scheme):
    n = len(a)-2
    out = [row[:] for row in a]
    for color in ([0, 1] if scheme == 'redblack' else [None]):
        for i in range(1, n+1):
            for j in range(1, n+1):
                if color is None or (i+j) % 2 == color:
                    source = a if scheme == 'jacobi' else out
                    out[i][j] = value(source, i, j)
    return [row[1:-1] for row in out[1:-1]]


def check_assignments():
    for n in [1, 2, 3, 5, 8]:
        for workers in [1, 2, 4, 8]:
            groups = [list(range(1+p*n//workers, 1+(p+1)*n//workers))
                      for p in range(workers)]
            assert sorted(i for g in groups for i in g) == list(range(1, n+1))
        for color in [0, 1]:
            cells = {(i, j) for i in range(1, n+1) for j in range(1, n+1)
                     if (i+j) % 2 == color}
            for i, j in cells:
                assert not ({(i-1,j),(i+1,j),(i,j-1),(i,j+1)} & cells)


def main():
    for fraction in [.01, .1]:
        print(f'S={fraction:.2f} P=64 speedup={amdahl(fraction,64):.3f}')
    assert isclose(amdahl(.001, 10**9), 1000, rel_tol=1e-5)
    expected = {
        'rowmajor': [[.2, .24], [.04, .056]],
        'jacobi': [[.2, .2], [0., 0.]],
        'redblack': [[.2, .24], [.04, 0.]],
    }
    for scheme in expected:
        result = sweep(initial(2), scheme)
        assert all(isclose(x,y,abs_tol=1e-12)
                   for r,s in zip(result,expected[scheme]) for x,y in zip(r,s))
        print(scheme + ': ' + repr([[round(x,3) for x in r] for r in result]))
    first = [9, 2, 7, 1, 4, 3, 8, 6, 5, 10]
    partials = [sum(first[p::4]) for p in range(4)]
    assert partials == [18, 15, 15, 7] and sum(partials) == 55
    print(f'partials={partials} sum={sum(partials)}')
    check_assignments()
    print('row_coverage=pass color_independence=pass all_checks=pass')


if __name__ == '__main__':
    main()
```

从仓库根目录运行：

```bash
python3 labs/lecture04/models.py
```

固定输出：

```text
S=0.01 P=64 speedup=39.264
S=0.10 P=64 speedup=8.767
rowmajor: [[0.2, 0.24], [0.04, 0.056]]
jacobi: [[0.2, 0.2], [0.0, 0.0]]
redblack: [[0.2, 0.24], [0.04, 0.0]]
partials=[18, 15, 15, 7] sum=55
row_coverage=pass color_independence=pass all_checks=pass
```

它是语义与算术模型，不测线程速度，也不模拟完整缓存系统。把三种网格结果并排，目的是提醒我们：换读写版本或更新顺序时，先检查是否已换了算法。

## 14. 可选 ISPC 实验：真正编译 Gang 与归约

### 14.1 完整 ISPC 代码

保存为 `basics.ispc`：

```c
export uniform int lesson_gang_size() {
    return programCount;
}

export void absolute_repeat(uniform int n,
                            uniform float x[], uniform float y[]) {
    foreach (i = 0 ... n) {
        float v = abs(x[i]);
        y[2*i] = v;
        y[2*i+1] = v;
    }
}

export uniform float lesson_sum(uniform int n, uniform float x[]) {
    float partial = 0.0f;
    foreach (i = 0 ... n)
        partial += x[i];
    return reduce_add(partial);
}
```

输出数组容量是 2n，而 `lesson_sum` 的 partial 是每实例私有值，最后通过 `reduce_add` 合成一个返回值。这里没有 ISPC Task，也不自动启用多核线程池。

### 14.2 完整 C++ 调用程序

保存为 `ispc_main.cpp`：

```cpp
#include <cmath>
#include <iostream>
#include <vector>
#include "basics_ispc.h"

int main() {
    for (int n:{0,1,3,4,5,8,9,19,32}) {
        std::vector<float> x(n+8,0), y(2*n+8,12345.0f);
        float total=0;
        for (int i=0;i<n;++i) {
            x[i]=(i-9)*.25f;
            total+=x[i];
        }
        ispc::absolute_repeat(n,x.data(),y.data());
        for (int i=0;i<n;++i)
            if (y[2*i]!=std::abs(x[i]) || y[2*i+1]!=std::abs(x[i])) return 1;
        for (int i=2*n;i<2*n+8;++i)
            if (y[i]!=12345.0f) return 2;
        if (ispc::lesson_sum(n,x.data())!=total) return 3;
    }
    std::cout<<"gang_size="<<ispc::lesson_gang_size()
             <<" sizes_checked=9 absolute_repeat=pass reduction=pass tail=pass\n";
}
```

输入是小规模的 1/4 倍数，其求和在本测试范围内可精确表达。输出末尾的 8 个哨兵位置用于检查常见越界写，不能替代所有内存安全检查。

### 14.3 编译与结果

需要 ISPC 编译器及 C++17 工具链。以下命令假设 `ispc` 已在 PATH；官方获取链接位于章末，若没有安装可跳过此节，其他理论与实验均不依赖它。

Apple Silicon，从仓库根目录执行：

```bash
mkdir -p /tmp/cs149-l04-build
ispc labs/lecture04/basics.ispc --arch=aarch64 --target=neon-i32x4 -O2 \
  -h /tmp/cs149-l04-build/basics_ispc.h -o /tmp/cs149-l04-build/basics.o
c++ -O2 -std=c++17 -I/tmp/cs149-l04-build labs/lecture04/ispc_main.cpp \
  /tmp/cs149-l04-build/basics.o -o /tmp/cs149-l04-build/ispc_basics
/tmp/cs149-l04-build/ispc_basics
```

本次 ISPC 1.32.0 的实际结果：

```text
gang_size=4 sizes_checked=9 absolute_repeat=pass reduction=pass tail=pass
```

把目标改成 `neon-i32x8`，重新编译目标文件并链接，实际得到相同正确性检查通过、gang_size=8。它没有因此创建 8 个软件线程。

编译器为两个跨步输出写入给出 Scatter 性能提示，即把结果分散写到地址；这不表示程序错误，也不是实测慢了多少倍。是否有更好的交错存储实现，需要看编译器生成和目标机器。

这里仅在 macOS ARM64 上执行，未在 x86 机器测试；不能把 NEON 目标产物拿到 x86 直接执行。

## 15. 完整 C++17 红黑求解器：持续线程、私有 partial 与阶段同步

### 15.1 为什么选择这个实现？

程序先固定 Worker 数，整个求解过程中复用这些线程，避免每个点或每个 Sweep 都创建线程。每个 Worker 持有连续行区间，同色阶段只写自己的点。

为了兼容普通 C++17 工具链，本例用 mutex、condition_variable（条件变量）与 generation（阶段代号）实现可复用 Barrier，不要求标准库支持 C++20 的 `std::barrier`。

条件变量允许线程等待状态变化；wait 必须带谓词检查，因为线程可能被唤醒却尚未满足条件。阶段代号确保“上一次大家到齐”和“这一次大家到齐”不会混淆。

### 15.2 完整源代码

保存为 `redblack.cpp`：

```cpp
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <numeric>
#include <stdexcept>
#include <thread>
#include <vector>

class Barrier {
    std::mutex mutex;
    std::condition_variable changed;
    const unsigned expected;
    unsigned arrived = 0;
    unsigned generation = 0;
public:
    explicit Barrier(unsigned count) : expected(count) {}
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        unsigned my_generation = generation;
        if (++arrived == expected) {
            arrived = 0;
            ++generation;
            changed.notify_all();
        } else {
            changed.wait(lock, [&] { return generation != my_generation; });
        }
    }
};

struct Grid {
    int n, stride;
    std::vector<double> data;
    explicit Grid(int size) : n(size), stride(size+2), data(stride*stride, 0.0) {
        for (int j=0; j<stride; ++j) at(0,j)=1.0;
    }
    double& at(int i,int j) { return data[i*stride+j]; }
    double at(int i,int j) const { return data[i*stride+j]; }
};

// Update only one color and one worker's row interval [lo,hi).
double update(Grid& a, int color, int lo, int hi) {
    double diff=0.0;
    for (int i=lo; i<hi; ++i)
        for (int j=1; j<=a.n; ++j)
            if ((i+j)%2==color) {
                double old=a.at(i,j);
                double next=.2*(old+a.at(i-1,j)+a.at(i+1,j)
                                   +a.at(i,j-1)+a.at(i,j+1));
                a.at(i,j)=next;
                diff+=std::abs(next-old);
            }
    return diff;
}

int serial(Grid& a, int limit, double tolerance) {
    for (int step=1; step<=limit; ++step) {
        double diff=update(a,0,1,a.n+1);
        diff+=update(a,1,1,a.n+1);
        if (diff/(a.n*a.n)<tolerance) return step;
    }
    return limit;
}

int parallel(Grid& a, unsigned workers, int limit, double tolerance) {
    Barrier barrier(workers);
    std::vector<double> partial(workers,0.0);
    bool done=false;
    int completed=0;
    auto worker=[&](unsigned p) {
        int lo=1+p*a.n/workers, hi=1+(p+1)*a.n/workers;
        for (int step=1; step<=limit; ++step) {
            double local=update(a,0,lo,hi);
            barrier.wait(); // B1: every red value is ready for black readers
            local+=update(a,1,lo,hi);
            partial[p]=local;
            barrier.wait(); // B2: black grid and all partials are ready
            if (p==0) {
                double diff=std::accumulate(partial.begin(),partial.end(),0.0);
                completed=step;
                done=diff/(a.n*a.n)<tolerance || step==limit;
            }
            barrier.wait(); // B3: publish the single writer's stop decision
            if (done) break;
        }
    };
    std::vector<std::thread> threads;
    for (unsigned p=1; p<workers; ++p) threads.emplace_back(worker,p);
    worker(0);
    for (auto& t:threads) t.join();
    return completed;
}

double residual(const Grid& a) {
    double result=0;
    for (int i=1;i<=a.n;++i)
        for (int j=1;j<=a.n;++j)
            result=std::max(result,std::abs(4*a.at(i,j)-a.at(i-1,j)
                 -a.at(i+1,j)-a.at(i,j-1)-a.at(i,j+1)));
    return result;
}

void compare(const Grid& a,const Grid& b,double tolerance) {
    for (std::size_t i=0;i<a.data.size();++i)
        if (!std::isfinite(b.data[i]) || std::abs(a.data[i]-b.data[i])>tolerance)
            throw std::runtime_error("Grid mismatch");
    Grid boundary(a.n);
    for (int i=0;i<a.stride;++i)
        for (int j=0;j<a.stride;++j) {
            if (i==0 || j==0 || i==a.n+1 || j==a.n+1)
                if (b.at(i,j)!=boundary.at(i,j))
                    throw std::runtime_error("Boundary changed");
            if (b.at(i,j)<0 || b.at(i,j)>1)
                throw std::runtime_error("Out of expected range");
        }
}

int main() {
    try {
        int cases=0;
        double worst_residual=0;
        for (int n:{1,2,3,5,8})
            for (unsigned p:{1,2,4,8}) {
                for (int steps:{1,2,7,31}) {
                    Grid reference(n), candidate(n);
                    serial(reference,steps,0);
                    int completed=parallel(candidate,p,steps,0);
                    if (completed!=steps) throw std::runtime_error("Lost phase");
                    compare(reference,candidate,1e-12);
                    ++cases;
                }
                Grid reference(n),candidate(n);
                serial(reference,5000,1e-9);
                int steps=parallel(candidate,p,5000,1e-9);
                compare(reference,candidate,1e-8);
                double r=residual(candidate);
                if (steps==5000 || r>1e-7)
                    throw std::runtime_error("Did not converge");
                worst_residual=std::max(worst_residual,r);
                ++cases;
            }
        std::cout<<"cases="<<cases
                 <<" fixed_sweeps=pass convergence=pass boundaries=pass\n"
                 <<"worst_residual="<<worst_residual<<"\ncorrect=yes\n";
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
```

### 15.3 屏障与共享变量为什么安全？

`update` 在一个颜色中不读取其他同色点，因此多个 Worker 更新互不重叠的行，不会一边读邻居、一边被另一个同色 Worker 改写邻居。B1 确保黑点开始读取前，所有红点都完成；B2 确保所有黑点和 partial 写完，线程 0 才归约。

每个 Worker 只写 partial[p]，线程 0 在 B2 之后读取全部值。done 和 completed 仅由线程 0 更新；其他 Worker 在 B3 之后读取 done。下一轮再次修改停止决定前，所有参与者还必须经过下一轮的阶段屏障，因此不会与上一次的读取重叠。

Barrier 的 mutex 与等待过程不仅管理计数，也建立跨线程的可见性链。不能把它换成对普通整数的无保护递增，或把 `notify_all` 本身当作全部内存同步协议。

程序允许 Worker 比内部行数更多：某些 Worker 的区间为空，它们仍然必须参加所有阶段屏障。若“没领到行就提前退出”，其他线程会一直等不到齐。

### 15.4 编译和预期输出

从仓库根目录执行：

```bash
mkdir -p /tmp/cs149-l04-build
c++ -O2 -std=c++17 -pthread labs/lecture04/redblack.cpp \
  -o /tmp/cs149-l04-build/redblack
/tmp/cs149-l04-build/redblack
```

本次在 macOS ARM64、Apple Clang 16 上的实际结果：

```text
cases=100 fixed_sweeps=pass convergence=pass boundaries=pass
worst_residual=8.65416e-09
correct=yes
```

100 个组合包括 N=1、2、3、5、8，Worker 数为 1、2、4、8；对每组分别测试 1、2、7、31 次固定 Sweep，再测试一次阈值停止，共 5×4×5=100。

固定轮次网格误差要求不超过 1e-12；阈值版本要求最终结果接近串行红黑、保持固定边界、未达到 5000 轮保护上限，并且残差不超过 1e-7。保护上限用于避免错误程序无限迭代，不是收敛理论的一部分。

本次还用 ThreadSanitizer 编译并执行同一组测试，通过且没有报告数据竞争。可选复现命令是：

```bash
c++ -O1 -g -std=c++17 -pthread -fsanitize=thread labs/lecture04/redblack.cpp \
  -o /tmp/cs149-l04-build/redblack-tsan
/tmp/cs149-l04-build/redblack-tsan
```

ThreadSanitizer 是运行时竞争检测工具；一次运行无报告，不构成所有输入和调度下的形式化证明。它也会改变运行成本，不应把其时间拿来与普通优化构建比较性能。

### 15.5 这不是性能 Benchmark

本例网格很小、主要用于发现同步错误，线程协调成本很可能远大于每个点的计算。不能要求它在四线程下必然比串行快四倍。

要研究速度，应在正确性确认后增加规模，明确是否计入线程创建、初始化、归约和收敛轮数，预热并重复测量。若比较不同算法，还要同时报告达到同等数值质量需要的轮数，而不是只比较一轮的时间。

## 16. 练习与参考答案

### 练习 1：四个步骤分别是什么？

“把网格按连续行分给线程”与“红点全部完成后再做黑点”，分别主要属于哪一步？

**答：** 前者是 Assignment，后者是 Orchestration。证明同色点独立属于 Decomposition；把线程调度到具体 Core 则属于 Mapping。

### 练习 2：Amdahl 上界

程序 5% 的串行基线时间无法并行，其余可完美分配。P=16 时上界是多少？无限处理器时呢？

**答：** 1/(0.05+0.95/16)≈9.143；无限处理器上界为 20。真实同步与访存成本可能让实际更低。

### 练习 3：只并行增亮的极限

两阶段各占原时间一半，只并行第一个阶段，使用 8 个处理器。理想加速是多少，为什么不是 8？

**答：** 1/(0.5+0.5/8)=16/9≈1.778，因为整个第二阶段仍然要串行完成。

### 练习 4：varying 为什么不能直接返回？

一个导出函数声明返回 uniform float，却返回每实例不同的 partial。修改 partial 为 uniform 是否就自动完成求和？

**答：** 不能把多个不同值直接转成一个 uniform 返回值；改类型也不执行归约。应先做私有部分和，再用跨实例归约得到一个返回值。

### 练习 5：输出翻倍是否安全？

迭代 i 写 y[2i]、y[2i+1]，输入长度 19。最小输出容量是多少？第 18 次迭代写哪里？

**答：** 38 个元素；i=18 写下标 36、37。安全还要求输入输出的重叠不会引入额外读写冲突。

### 练习 6：双缓冲改了什么？

原程序原地按行扫描，下一点读取刚更新的左邻居。改为从旧数组读、向新数组写，是否逐步等价？

**答：** 不等价。新的读版本不同，变成 Jacobi 式思路。可能仍能用于同一个数值目标，但需要另行验证收敛与误差。

### 练习 7：波前宽度与阶段数

4×4 个内部点按 i+j 的波前执行，有多少阶段？最宽阶段有几个点？

**答：** 2×4−1=7 个阶段，宽度依次为 1、2、3、4、3、2、1，最宽 4 个点。频繁阶段同步可能让实际效果比图上的并行机会差。

### 练习 8：红黑为什么能并行？

更新式还包含自己旧值，是否破坏同色点的独立性？

**答：** 不破坏。一个点只由唯一 Worker 写，同色其他点既不读取它，也不写它。上下左右邻居都是另一种颜色，同色阶段保持不变。若加入对角邻居，着色证明必须重新检查。

### 练习 9：锁和屏障能相互替代吗？

每次 diff 累加都加锁，但没有等待全部累加完成就判断收敛；或完全不加锁，只在循环末尾加屏障。这两种都正确吗？

**答：** 都不能保证正确。前者可能读到不完整的和；后者可能已发生不受保护的并发读改写，屏障不会修复丢失贡献或 C++ 数据竞争。

### 练习 10：空区间 Worker 可以退出吗？

N=3、P=8，某些 Worker 没有内部行。它们是否可以不进入红黑阶段的 Barrier？

**答：** 不可以，除非重建了参与人数与整个同步协议。本章 Barrier 固定等待 P 个参与者，空 Worker 也必须到齐。

### 练习 11：变化量很小，为什么还测残差？

程序误把所有 update 都跳过，diff 每轮等于 0。是否已数值收敛？

**答：** 只是停止指标被误实现。边界影响尚未传播，方程残差可能仍很大；还要对照可信结果并检查任务覆盖。

### 练习 12：多个线程写相同布尔值安全吗？

所有线程都发现阈值满足，于是同时对共享普通 bool done 写 true。能因为“值一样”而视为安全 C++ 吗？

**答：** 不能。并发冲突访问仍须符合 C++ 内存模型；可安排单写者，再通过同步发布，或者使用正确设计的原子协议。算法层面的相同判断不替代语言层面的同步。

## 17. 面向 AI Infrastructure 的联系（课外延伸）

**算子与整段程序。** 一个张量算子变快，不表示端到端程序按相同比例变快。归约、数据准备、串行控制和通信都可能成为 Amdahl 模型中的剩余部分，应该测完整链路。

**逻辑任务与执行资源。** 批中的样本、运行时任务、CPU 线程和 GPU 执行单元是不同概念。表达更多独立工作有助于安排，但不等于实际创建同样多的昂贵执行上下文。

**算法改变要带数值标准。** 近似计算、分块归约、不同更新顺序可能改善并行性，也可能改变数值过程。比较时需要明确允许什么误差，以及最终质量是否达到同等要求。

**同步对应真实的数据依赖。** 提交异步工作不等于结果已完成；消费者需要在正确的完成边界后读取。提高吞吐不是删除所有等待，而是保留必要依赖、减少人为复用和不必要共享造成的等待。

这些是作者的迁移解释，不是对 2023 年课程逐句复述或当前某个训练框架实现的断言。

## 18. 来源、修正与验证范围

| 来源 | 范围 | 状态 |
| --- | --- | --- |
| [Stanford 第 4 讲页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/progbasics/) | 课程编号与主题 | 已核对 |
| [官方 51 页 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/progbasics/04_progbasics.pdf) | 第 3–21 页四步骤、Amdahl 与分配；第 23–34 页网格和红黑更新；第 36–49 页共享地址空间、锁与 Barrier；第 50–51 页总结 | 已核对文字，抽查第 7、9、24、26、28、34、37、38 页；未逐页视觉审查 |
| 用户提供英文自动转写 | 开场 ISPC 复习，到三屏障讨论和减少屏障的提示 | 全文已阅读，无时间码，未与原音逐句核验 |
| [第 4 讲录像](https://www.youtube.com/watch?v=0-ztm8SKq70) | 对应课程录像 | 不编造时间码，未逐句音频校对 |
| [ISPC 官方手册](https://ispc.github.io/ispc.html) | Gang、uniform/varying、foreach、归约与数据竞争 | 对照语义，并实际编译正确与被拒绝的示例 |
| [ISPC 官方编译器发布](https://github.com/ispc/ispc/releases) | 编译器获取 | 本次使用官方 ISPC 1.32.0 macOS ARM64 产物 |
| [C++ 数据竞争规则](https://eel.is/c++draft/intro.races) | 冲突访问、同步与可见性 | 用于区分伪语言讲解和可执行 C++ |
| [C++ Barrier 语义](https://eel.is/c++draft/thread.barrier.class) | 阶段同步概念 | 标准 Barrier 的参考；实际程序使用本页完整列出的 C++17 兼容实现 |

需要特别区分的修正：ISPC 对 uniform/varying 错误赋值的实际编译诊断；课件部分输出下标和变量名不一致；网格边界循环的简写；共享 done 与 diff 的多写者问题。可运行实现统一使用完整索引、单写者状态与阶段同步。

课件第 34 页只画红点半阶段，不能直接作为完整求解器运行。第 49 页提供减少屏障的三槽位方案，而用户文字稿在这一讲末尾主要留下提示；本章把相关推理作为课件补充和作者整理，不称作已逐句听到的原话。

Python 模型已验证。ISPC 的 4/8 实例目标各通过 9 种输入规模；错误 uniform 累加按预期编译失败。红黑 C++ 程序在 macOS ARM64、Apple Clang 16 通过 100 组合校验，并在 ThreadSanitizer 构建下通过同样测试且无竞争报告。未做性能 Benchmark、x86 实机验证或通用 PDE 收敛证明。

更细记录见 [Lecture 04 来源核验](../sources/lecture-04-audit.md)。公开仓库保留原创教材、代码和来源链接，不提交完整自动转写、官方 PDF 或编译器二进制。

当你能针对一段代码依次说明“什么能独立做、谁做什么、谁必须等谁、最终怎样使用硬件”，并为每个等待指出具体的数据依赖，就具备了继续分析并行程序性能的基础。
