# 第 8 章：数据并行思维——从 Scan 到不规则数据结构

> Stanford CS149 · Fall 2023 · Lecture 8 — Data-Parallel Thinking
>
> **状态：自包含中文教材，第一版。** 结合用户提供的完整英文自动文字稿、官方 51 页 Slides 与原始研究/官方文档，独立编写解释、推导与实验。文字稿已阅读全文，无时间码，含听不清与术语误识别；尚未逐句校对原音。已核对全部课件文字结构并抽查关键图页，未逐页视觉复核。本文不是官方授权教材或逐字翻译。

**先修知识：** 数组、下标、循环、函数与基本 C++ 语法。本章从头解释高阶函数、结合律、工作量、Scan 和稀疏矩阵存储；不要求有函数式编程、GPU 或分布式系统经验。

**学习时间：** 阅读和纸笔推演约 3 小时，运行 Python 与 C++ 实验约 1 小时。

**配套实验：** [第八章完整代码与说明](../labs/lecture08/README.md)。全部核心代码也收录于本页。本章 Python 算法在 CPU 上顺序模拟各并行阶段，C++ 分块 Scan 使用真实线程；不需要 CUDA，未在 GPU 运行或测量性能。

## 0. 换一个问题：输入经过哪些集合变换？

以往容易先问“我有几个线程，各自做什么”。本章先问：“要把输入集合变成什么输出？能否用几种有明确定义的操作完成？”

例如筛出正数并紧凑存储，可以分为判断每项是否保留、计算每项输出位置、写出；构建粒子网格，可以分为计算格子编号、按编号排序、找每组起止位置。

这样的表达把许多细粒度协调交给原语的实现者。它没有消除依赖，而是把依赖集中到 Reduce、Scan、Sort 等可分析的模式中。原语能并行，也不保证整条流水线一定快：中间数组、排序、短输入和串行阶段仍可能主导时间。

## 1. 序列、纯函数与 Map

### 1.1 序列是本章的抽象，不是某个语言类名

**Sequence（序列）**是有顺序的元素集合，例如 [3,1,4] 与 [1,3,4] 不相同。我们以长度、元素类型和允许的变换描述它，而不把任意位置的读写都暴露给每个计算实例。

本章的数学接口不表示 C++ 必须存在一个就叫 `Sequence` 的标准容器，也不表示 Python 数组禁止索引。程序实现仍可用普通数组，分析时则限制操作，使依赖更清楚。

若写 `f: A→B`，表示 f 接受一个 A 类型的值、返回一个 B。**高阶函数**是把函数作为参数或结果的函数。Map 接受 f 和输入序列，得到等长输出：

$$
\operatorname{map}(f,[x_0,\ldots,x_{N-1}])=[f(x_0),\ldots,f(x_{N-1})]
$$

例如 f(x)=x+10，输入 [2,1,3,4]，输出 [12,11,13,14]。若 f 把整数变成字符串，输出元素类型也随之改变。

### 1.2 独立性依赖无副作用，不是靠一个函数名保证

**纯函数/无副作用函数**在本章指结果由输入决定，不通过共享写、外部状态或隐含操作影响其他元素计算。这样处理第 i 项与第 j 项的先后顺序不改变答案；结果仍按原输入位置保存。

即使函数表面上只接收一个 x，C++ Lambda 仍可能捕获共享变量并修改它。因此“只给一个参数”不自动证明安全。普通无执行策略的 `std::transform` 也不承诺自动多核执行，原语含义与具体实现要分开。

一个简单并行实现是把输入分成 P 段，各 Worker 处理自己的一段并写互不重叠的输出。若 f 的成本差异很大，仍有负载平衡问题；如果 f 很轻，则可能受数据带宽或调度成本限制。

### 1.3 Zip 与融合

两个等长序列可按位置配对，称为 Zip。点积可表达为对 (ai,bi) 做乘法 Map，再把结果 Reduce 求和。

如果中间乘积不被其他地方使用，实现可以一边计算乘积、一边局部累加，减少临时数组。连续两个纯 Map 也可能融合为复合函数。融合是否保持数值/副作用语义，以及是否增加寄存器压力，仍要核对，不能仅凭“原语都很快”忽略多次扫描成本。

## 2. Fold 与 Reduce：先明确允许怎样改变括号

### 2.1 Fold-left 表达一种确定的依赖链

给定起始状态 z 和更新函数 f，左折叠依次计算：

$$
s_0=z,\qquad s_{i+1}=f(s_i,x_i),\qquad \operatorname{foldLeft}(z,f,x)=s_N
$$

状态类型可以与输入类型不同。若 z=10、f 为加法、输入 [2,1,3,4]，结果为 20。一般 f 可能把第 i 步的新状态作为第 i+1 步输入，不能无条件拆成平行部分。

### 2.2 结合律与交换律是不同条件

二元运算 ⊕ **满足结合律**，指改变括号不改变结果：(a⊕b)⊕c=a⊕(b⊕c)。**满足交换律**则要求 a⊕b=b⊕a。

保持元素顺序的树形归约只改变括号，不必交换元素，因此可以支持结合但不交换的运算。字符串连接就是例子：("a"+"b")+"c"="a"+("b"+"c")，但 "ab" 不等于 "ba"。

减法不结合：(8−3)−2=3，而 8−(3−2)=7。异或在正确的布尔/位运算定义下是结合的，不能沿用口述讨论把它当作非结合反例。

### 2.3 单位元与起始值不能重复使用

**单位元 e** 满足 e⊕x=x⊕e=x。加法是 0，字符串连接是空串，乘法是 1。具有结合运算与单位元的结构常称为 **Monoid（幺半群）**；本章不要求抽象代数背景，只使用这两条规则。

Reduce 的空输入在本章返回 e；非空输入按保持顺序的树合并。若需要额外起始值 z，可将它在合适位置只合并一次。

不要给每个分块重复使用 z=10。对 [2,1] 和 [3,4] 分别从 10 开始会得到 13、17，直接相加是 30；正确全序列 Fold 是 20。并行局部摘要应从 e=0 开始，最后只加一次 10。

### 2.4 一般 Fold 需要可组合的摘要

当输入 A、状态 B 类型不同，给一个 `combine: B×B→B` 还不够。设 H(S) 是序列 S 的摘要，需要保证：

$$
H([])=e_B,\qquad H(U\mathbin{+\!+}V)=\operatorname{combine}(H(U),H(V))
$$

这里 U++V 表示按顺序连接。combine 必须与局部更新规则兼容，并满足结合律，才能把“先在每段折叠，再合并摘要”解释为相同计算。

平均数提供一个实用例子：摘要保存 (sum,count)，合并时分别相加，最后 sum/count。不能简单平均两个分块的平均数，除非它们样本量相同或正确加权。空输入的平均数未定义，应另行处理。

某些看似顺序的状态更新还能转换为可组合的函数摘要，但函数合并的成本与表示大小也要分析。我们不声称任意黑盒 Fold 都有廉价并行实现。

### 2.5 浮点加法不是严格的结合运算

在常见双精度计算中，(10¹⁶+(−10¹⁶))+1 可以得到 1，而 10¹⁶+((−10¹⁶)+1) 可以得到 0。差异不一定只是“不重要的最后一位”。

因此浮点树形归约需要明确允许误差、数值稳定性与复现要求。不同库、设备或执行选项的确定性保证要分别查；不要默认换一次分组后位级结果一定相同。整数测试也要避免溢出，C++ 有符号整数溢出不能当作自动模运算。

## 3. Scan：为每个前缀产生一个结果

### 3.1 Inclusive 与 Exclusive 的精确定义

对有单位元 e 的结合运算，定义：

$$
\begin{aligned}
I_i&=x_0\oplus x_1\oplus\cdots\oplus x_i\\
E_0&=e,\qquad E_i=x_0\oplus\cdots\oplus x_{i-1}\quad(i>0)
\end{aligned}
$$

Inclusive 包含当前元素，Exclusive 不包含。两者输出长度都为 N；空输入都返回空序列。Reduce 只返回总结果，Scan 则保留每个前缀。

输入 [2,1,3,4]、加法单位元 0：

| 下标 i | 输入 xi | Exclusive Ei | Inclusive Ii |
| --- | --- | --- | --- |
| 0 | 2 | 0 | 2 |
| 1 | 1 | 2 | 3 |
| 2 | 3 | 3 | 6 |
| 3 | 4 | 6 | 10 |

### 3.2 两种形式如何互相转换？

有 Ei 时，Ii=Ei⊕xi，保持左右顺序即可。有非空 Inclusive 数组时，Exclusive 为 `[e,I0,I1,…,I(N−2)]`，即补入单位元并右移一位。

“用 Inclusive 减去原输入”只适用于具有相应逆运算且数值规则允许的特例。最大值 Scan、字符串连接等没有这种通用减法，浮点加减还可能受舍入影响。课件与口述的减法提示不能推广到任意结合运算。

### 3.3 从前缀值到内存位置

若每个任务要输出 ci 个元素，先对非负计数做 Exclusive Scan，得到任务 i 的起始位置 Ei。其拥有区间为 [Ei,Ei+ci)，总空间为最后一个 Ei+ci。

例如计数 [2,0,3,1]，起点 [0,2,2,5]，四个区间为 [0,2)、[2,2)、[2,5)、[5,6)。空任务拥有空区间；其余区间没有重叠。这正是并行筛选、可变长输出与稀疏数据布局常用的分配方式。

## 4. Work 与 Span：先定义计数模型

**Work W** 是执行全部计算需要的操作总量，**Span D** 是依赖图中最长的顺序操作链。假定每个结合运算为常数成本、存储操作理想、同层独立计算可并行，不计真实机器通信与启动开销。

P 个处理器至少需要：

$$
T_P\ge\max\left(\frac WP,D\right)
$$

在适当的调度与理想模型假设下，W/P+D 也能指导可实现时间的量级；真实机器还会受缓存、带宽、同步与资源限制。

顺序前缀链有 O(N) Work、O(N) Span。平衡树 Reduce 有 O(N) Work、O(log N) Span。我们希望 Scan 也能把深度缩短，但要比较是否为此额外做了很多工作。

字符串测试用来验证左右顺序，不意味着长字符串连接有常数成本。将代码的实际复杂对象操作数直接当成单位时间，会误用这个模型。

## 5. 距离倍增：Hillis–Steele 风格 Inclusive Scan

### 5.1 每轮扩展已知前缀的覆盖范围

初始 a=输入。每轮距离 d=1、2、4、8…：i<d 的位置保持不变，其余位置使用**上一轮**的 a[i−d]⊕a[i]。

下表展示输入 [2,1,3,4,2,0,5,1] 的全部阶段：

| 阶段 | 数组 |
| --- | --- |
| 初始 | [2,1,3,4,2,0,5,1] |
| d=1 | [2,3,4,7,6,2,5,6] |
| d=2 | [2,3,6,10,10,9,11,8] |
| d=4 | [2,3,6,10,12,12,17,18] |

为什么最终正确？初始每项覆盖自己；距离为 d 的一轮把相邻、按顺序排列的两个长度至多 d 的区间合并，因此覆盖范围翻倍。经过 ceil(log₂N) 轮，每项覆盖从 0 到自身的完整前缀。

### 5.2 一轮内不能随意读到新版本

若输入 [1,2,3,4]，d=1 时正确的新数组是 [1,3,5,7]。若顺序原地从左向右更新，会得到 [1,3,6,10]，因为后面读到的是本轮新值。

并行实现也必须维护上一轮快照：例如双缓冲，或在合适范围内先让所有读取完成，再覆盖共享存储。只在“写完之后加一个屏障”不自动解决本轮读写重叠。Python 版明确复制 old，表达逻辑阶段，而不靠顺序执行偶然得到答案。

### 5.3 精确操作数比只写 O(N log N) 更有帮助

N=2ᵏ 时，第 j 轮距离 2ʲ，有 N−2ʲ 次结合操作：

$$
W=\sum_{j=0}^{k-1}(N-2^j)=Nk-(N-1)
$$

因此 N=8 时 7+6+4=17 次、3 轮；N=32 时 129 次、5 轮。复制、边界检查与通信不计入这些结合次数。渐近 Work 为 O(N log N)，Span 为 O(log N)。

## 6. Blelloch Scan：先做树摘要，再传播前缀

### 6.1 用树的含义理解两个阶段

把叶子看作输入元素，每个内部节点代表一个连续区间。**Up-sweep（上扫）**自底向上保存区间总结果；**Down-sweep（下扫）**从根向下传“在这个区间之前已经累积了什么”。

```text
             区间 [0,4) 的总结果
                  /       \
         [0,2) 的摘要     [2,4) 的摘要
             /  \           /  \
            x0  x1         x2  x3

下扫进入一个节点时：
左子树收到父前缀 p
右子树收到 p ⊕ 左子树总结果
```

根的“区间之前”没有元素，所以传入单位元。注意右子树是 `父前缀 ⊕ 左总结果`，不能反过来。加法测试看不出左右颠倒，字符串测试能看出来。

### 6.2 四元素全流程

用数组的区间右端位置保存树摘要，输入 [2,1,3,4]：

| 操作 | 数组 |
| --- | --- |
| 初始 | [2,1,3,4] |
| 上扫长度 2 的区间 | [2,3,3,7] |
| 上扫长度 4 的区间 | [2,3,3,10] |
| 根改为单位元 | [2,3,3,0] |
| 下扫长度 4 的区间 | [2,0,3,3] |
| 下扫长度 2 的区间 | [0,2,3,6] |

最后每个叶位置得到进入该叶之前的全部前缀，也就是 Exclusive Scan。总和 10 在改根之前可保存；若需要 Inclusive，可按 Ei⊕xi 另行恢复。

### 6.3 非二次幂与空输入

若 N 不是 2 的幂，补到最小的 M=2ᵏ≥N，补入单位元，做完整树，再截取前 N 个输出。因为单位元不改变任何真正前缀，结果保持正确。

N=5 时 M=8；N=0 单独返回空序列，不能去访问 a[N−1]。长度 1 的输入只需返回 [e]，没有树结合操作。课件伪代码中的幂次、变量名和单位元需要在实现中写清楚，不能直接把排版后的示意当成可执行代码。

### 6.4 工作量与轮数

M 个叶子的满二叉树有 M−1 个内部节点，上扫每节点一次结合，下扫每节点一次结合，共 2(M−1)。上、下扫各 log₂M 轮，总计 2log₂M 轮，不含根赋值和其他数据移动。

| 输入长度 | 距离倍增结合次数/轮数 | Blelloch 结合次数/轮数 |
| --- | --- | --- |
| 8 | 17 / 3 | 14 / 6 |
| 32 | 129 / 5 | 62 / 10 |

N>0 时 M<2N（N 本身为二次幂时 M=N），因此补齐后仍为 O(N) Work、O(log N) Span。工作高效不代表每台机器都更快：两遍树、数据移动和闲置 Lane 都有常数成本。

## 7. 同一个 Scan，在不同层级使用不同实现

### 7.1 少量 CPU Worker：局部扫描、扫描摘要、加基址

对 P 个连续块，分别计算局部 Exclusive Scan Li 和块总摘要 ti；对所有块摘要做 Exclusive Scan，得到每块基址 bi；最后把块内结果转换为 bi⊕Li。

```text
原序列:       [2,1]        [3,4]
局部前缀:     [0,2]        [0,3]
块总和:         3            7
块基址:         0            3
应用基址:     [0,2]        [3,6]
```

所有全局更早的元素都在 bi 中，当前块更早的元素都在 Li 中；按这个顺序结合即得到正确前缀。局部阶段和应用阶段均可并行，摘要少时用一个线程顺序计算就很直接。

本章 C++ 代码采用这一方案，用两次 join 建立阶段完成关系。其工作量为 O(N+P)，在每次创建线程与摘要顺序扫描的实现下，不能声称拥有理想的 O(log N) Span；大致关键链包含 O(N/P+P)，另外还有实际线程管理开销。

### 7.2 Warp：较多标量工作可能换来较少指令阶段

32 Lane 的倍增 Scan 有 5 个主要距离阶段；Blelloch 有上、下扫共 10 个树层阶段。在锁定宽度的向量执行环境里，少做标量运算可能只是让更多 Lane 闲置，却增加执行阶段。

因此小组内可以采用倍增，在块间采用更节省工作和通信的摘要方案。这里的“5 对 10”是抽象阶段数，绝不是保证 5 或 10 个真实 GPU 时钟；Shuffle、依赖延迟、同步与指令实现都要计入。

### 7.3 跨 Block：局部结果之外还需全局基址

一个容易理解的 GPU 设计是：Kernel 1 扫描各 Block 并写摘要；Kernel 2 扫描摘要；Kernel 3 把基址传播回各 Block。若摘要仍太多，可以递归分层。

这是一种正确分阶段设计，不表示所有现代库都固定使用三次启动。生产库还有其他算法；不能根据课堂猜测声称当前 CUB/Thrust 内部一定如此。本章没有实现 CUDA Scan，也未测试库吞吐。

### 7.4 旧式 Warp 内存代码的同步问题

课件第 20–23 页展示直接读写共享 ptr 的 Warp Scan，没有为现代独立线程调度提供完整同步协议；Block 版本还把 Warp 摘要写回复用区域，覆盖前必须确保旧消费者结束读取。

不能只补一个括号，或加 `volatile`，就把它当成现代 CUDA 的安全实现。应使用满足参与掩码要求的同步 Warp 原语，或用清晰的存储区与读/写阶段同步。本章只用快照模型讲算法，并提供真实 CPU 分阶段实现，不发布该历史片段为可运行 GPU 答案。

此外，80×64×32=163840 是课件 V100 的理论驻留线程上界，页脚 163860 是笔误。它不是“输入至少 20 万元素才有效”的通用门槛；所需工作量取决于每线程计算、并发资源与目标 Kernel。

## 8. Filter 与 Compaction：前缀和生成无冲突输出地址

### 8.1 完整算例

**Filter** 保留满足谓词的元素；**Stable Compaction（稳定压紧）**把它们放到连续位置，并保持输入相对顺序。

输入 [7,2,9,4,5]，保留奇数，先得到 0/1 标志，再对标志做 Exclusive Scan：

| 输入位置 | 值 | 保留标志 | Exclusive 位置 | 写出 |
| --- | --- | --- | --- | --- |
| 0 | 7 | 1 | 0 | out[0]=7 |
| 1 | 2 | 0 | 1 | 不写 |
| 2 | 9 | 1 | 1 | out[1]=9 |
| 3 | 4 | 0 | 2 | 不写 |
| 4 | 5 | 1 | 2 | out[2]=5 |

总输出数为 2+1=3，输出 [7,9,5]。位置相同的第 1、2 项不会竞争，因为只有标志为 1 的项才写。

### 8.2 为什么保留项不会写到同一地址？

若 i<j 且两者均保留，则 j 的前缀计数包含 i 贡献的 1，所以 pos[j]≥pos[i]+1。保留项的目的地址严格递增，既保证单写者，也保证稳定顺序。

空输入输出为空；全不保留时长度为 0，不能访问不存在的最后一个前缀；全保留时输出与输入一致。整数计数的类型必须能表示总输出数。

本章程序显式计算输出长度、分配结果，再做带唯一位置的 Scatter。实际系统可能融合阶段，但不能在没有空间与位置协议时直接让多个线程“往尾部追加”。

## 9. Segmented Scan：把不等长子序列放到一个平面上

### 9.1 段起点标志

输入可能是一组邻接表、文档词列表或粒子邻居列表。每个子序列长度不同，只在外层并行可能导致工作量不均；平铺元素后再携带段边界，可以按总元素数组织工作。

例如子序列 [[1,2],[6],[1,2,3,4]]：

```text
data  = [1,2,6,1,2,3,4]
heads = [1,0,1,1,0,0,0]

Inclusive 分段加法 = [1,3,6,1,3,6,10]
Exclusive 分段加法 = [0,1,0,0,1,3,6]
```

每到一个段头就重新从单位元开始。Exclusive 的转换也要识别段头：段头为 e，其余位置取前一项的分段 Inclusive，不能把整条数组简单右移后不重置。

起点标志能标出已有元素从哪里开始，却无法表示夹在中间的空段。要保留空段身份，需要偏移数组或额外的段元数据。

### 9.2 把“遇到边界就重置”封装为结合运算

把值与布尔头标志组成二元组 (v,h)。对左摘要 (a,ha) 与右摘要 (b,hb)，定义新运算：

$$
(a,h_a)\star(b,h_b)=\left(\begin{cases}b&h_b=1\\a\oplus b&h_b=0\end{cases},\ h_a\lor h_b\right)
$$

直觉是：如果右区间内部已出现新段头，它保留的末段结果 b 就与左区间无关；否则把左摘要接到它前面。布尔位记录整个合并区间是否出现过段头。

为什么结合？若最右区间含段头，所有左边摘要都被截断；否则看中间区间是否含段头；若都没有，就退化为底层 ⊕ 的结合律。三种情况与先合并哪两个区间无关。单位元是 (e,false)。

于是可以对这些二元组运行普通结合 Scan，再取数值分量。Python 实现使用 Blelloch Exclusive 后按前缀与当前二元组合并，得到分段 Inclusive；本章不会只说“改几个 if”而留下不可执行算法。

### 9.3 更多元素级并行，也有额外代价

若共有 M 个子序列、总 N 个元素，只把每个子序列当一个任务可能仅有 M 个任务；平铺后可以让 N 个元素参与计算，更适合长度差别很大的情况。

但平铺、标志、Scan 与结果提取增加读写。若每个子序列本来很短、外层任务已足够多，逐段处理可能更直接；若只需要每段总和，Segmented Reduce 也可能比输出全部前缀更省流量。

## 10. 稀疏矩阵乘向量：Gather → Map → 分段聚合

### 10.1 完整 CSR 表示，包括空行

稀疏矩阵大部分为 0，**CSR（Compressed Sparse Row，压缩稀疏行）**只记录存储项及其列号，并用行偏移区分各行。本章给出 6 行、4 列例子：

```text
A = [3 0 1 0]
    [0 0 0 0]
    [0 2 0 0]
    [0 0 4 0]
    [0 2 6 8]
    [0 0 0 0]

values = [3,1,2,4,2,6,8]
cols   = [0,2,1,2,1,2,3]
rowptr = [0,2,2,3,4,7,7]
x      = [1,2,3,4]
```

若有 M 行，rowptr 长度为 M+1，第 r 行存储项区间为 [rowptr[r],rowptr[r+1])。第一项必须为 0，最后一项为存储项数 nnz，偏移单调不减。相等的相邻偏移表示空行。

cols 的每项必须是合法列号，values 与 cols 等长。这里存储的都是非零；实际 CSR 格式也可能保留显式零。本章不假定“列数组长度等于列数”。

### 10.2 逐步算出结果

先按 cols 从 x 抽取输入，即 Gather：

```text
x[cols]  = [1,3,2,3,2,3,4]
products = [3,3,4,12,4,18,32]
heads    = [1,0,1,1,1,0,0]
分段 Inclusive = [3,6,4,12,4,22,54]
```

非空行取本段最后一项，空行直接输出 0，得到 y=[6,0,4,12,54,0]。

最后一条非空行应计算 2x₁+6x₂+8x₃。课件第 32 页在后面的表达式把 8x₃ 误写为 8x₂，本章保留正确列号并用整数结果验证。

这里操作是 **SpMV：稀疏矩阵乘稠密向量**，不是两个稀疏矩阵相乘。后者的数据结构与工作量问题更复杂。

### 10.3 为什么不能直接取每行 `end−1`？

对于 rowptr[r]=rowptr[r+1] 的空行，`end−1` 可能指向上一行或为 −1。Python 负下标还可能静默读取尾部，使错误不易被发现。

本章先判断 lo<hi，再读取 prefix[hi−1]。整个矩阵没有存储项时，products 与 heads 均为空，所有行得到 0。只有起点标志无法区分连续空行，因此保留 rowptr 是必要的。

### 10.4 并行机会不等于固定速度

这个表达把工作分配到 nnz 个存储项上，可能比每行一个线程更能平衡长短行；同时还要处理 M 个输出行，整体不应只写成与 nnz 有关而忽略行数组。

Gather 地址可能离散，额外 products 和 prefix 数组也会增加流量。实现可以融合 Gather 与乘法，并使用更专门的分段归约。声称“所有阶段都能并行，所以总时间一定好”会漏掉带宽和数据布局。

Cache Miss、TLB Miss 与 Page Fault 不是同义词：离散索引可能触及很多缓存行或地址翻译，但不必然为每个元素触发缺页异常。

## 11. Gather、Scatter 与带冲突的聚合

### 11.1 谁提供地址，谁写结果？

Gather 定义为 out[i]=input[index[i]]；每个输出位置有唯一写者，允许重复读取同一个输入。Scatter 定义为 out[index[i]]=input[i]；若多个 i 指向同一个输出，就必须约定冲突处理。

```text
input = [A,B,C], index = [2,0,1]
Scatter → [B,C,A]
```

当 index 是完整置换，按目标索引给数据排序可实现同样的 Scatter，也可构造逆置换再 Gather。若索引重复或有空洞，就不是这个特殊情况；不能把任意 Scatter 当作简单排序。

本章 `scatter_unique` 明确拒绝重复与越界索引，对未写位置保留 None。Gather 也拒绝负下标，避免 Python 的负索引语义改变数学定义。

### 11.2 带操作的 Scatter：先排序，再分段合并

假设 values=[5,2,7,1]，目标 key=[1,0,1,0]，输出桶初始为 0，要求按 key 求和。按 (key,原始下标) 排序：

```text
sorted keys   = [0,0,1,1]
sorted values = [2,1,5,7]
heads         = [1,0,1,0]
分段 Inclusive = [2,3,5,12]
只让段末写出 → out = [3,12]
```

现在每个目标只由一个段末写入，不再为每个输入争抢同一原子更新。排序并不是免费：比较排序通常有 O(N log N) 工作；整数 Radix Sort 另有位宽、轮数与存储成本。

本程序按原始下标打破相同 key 的平局，以固定组内次序。若底层运算不交换，必须保持所需逻辑顺序；不能宣布结果一定等于某次任意原子执行顺序。若输出桶起始不是单位元，还要按规定把已有值合并一次。本章 `scatter_sum` 只实现零初始的整数和。

### 11.3 GroupBy 是结果形状，不代表唯一实现

**GroupBy** 把相同 key 的值组织到一起。排序后识别相邻 key 的边界是一种实现，哈希分组、计数分桶等也可能适用。

是否保留组的顺序、组内顺序、是否有空 key、重复值如何处理，都应是接口约定。不能用一个 `groupBy` 名称跳过这些要求。

## 12. 粒子网格：用排序把共享追加变成唯一边界写

### 12.1 问题与坐标约定

有 N 个二维粒子，希望对 K 个格子建立粒子 ID 列表，用于后续邻域搜索。令位置在半开单位正方形 [0,1)×[0,1)，网格 Nx×Ny，K=NxNy。

格子编号为 `floor(y*Ny)*Nx+floor(x*Nx)`。位于 1.0 的坐标在本题中无效，需要另行定义边界策略，不能不加判断地越界写桶。

### 12.2 五种方案的实际取舍

| 方案 | 好处 | 可能代价 |
| --- | --- | --- |
| 每粒子加全局锁追加 | 简单 | 共享热点把追加串行化 |
| 每格子一把锁 | 不同格子可独立 | 集中到一个格子时仍争用 |
| 每格子遍历所有粒子 | 每列表唯一拥有者 | O(KN) 次判断，K 小时任务少 |
| Worker/Block 私有列表再合并 | 减少日常共享争用 | 私有存储和合并成本 |
| 按格子 key 排序并找边界 | 输入级并行，边界唯一写者 | 排序、多次扫描与临时存储 |

“16 个格子意味着 16 倍改善”只有在分布与成本等假设下才可能近似成立；如果粒子全在一个格子，细粒度锁也无法消除这个热点。排序方案同样不保证对小输入或任何分布都胜过原子计数/局部聚合。

### 12.3 一个可复算的 4×3 网格

六个粒子的位置依次为 (.6,.4)、(.3,.1)、(.55,.5)、(.1,.1)、(.99,.99)、(.4,.1)。计算并排序：

```text
原始 ID       = [0,1,2,3,4,5]
原始 cell     = [6,1,6,0,11,1]
排序后 cell   = [0,1,1,6,6,11]
排序后 ID     = [3,1,5,0,2,4]
```

为每个非空 cell 保存半开区间：cell 0 为 [0,1)，cell 1 为 [1,3)，cell 6 为 [3,5)，cell 11 为 [5,6)。取一个 cell 时，按区间到**排序后的 ID 数组**中找原粒子 ID，再读取粒子数据，不是直接把排序位置当原粒子 ID。

每个 run 的第一个元素写 starts[key]，最后一个写 ends[key]。同一个 key 只有一个起点和一个终点，所以每个边界字段有唯一写者；前提是排序阶段已经完成、数组大小合法。

### 12.4 空格子与空输入必须有表示

本章把所有 starts/ends 初始化为 0，空格子为 [0,0)。有粒子的第一个格子也可能从 0 开始，但 end>start，仍能区分。

这份表示允许直接用 end−start 计数；它不是完整单调的 CSR 偏移数组，不能对相邻 cell 的 start 简单做差。若要统一 CSR 风格偏移，可先计算全部桶计数，再 Scan 得到 K+1 个偏移。

N=0 时排序数组为空、所有区间为空。密集边界数组仍需 O(K) 初始化空间与工作；当 K 极大而非空格子很少，可能更适合保存稀疏的 key/区间列表。

### 12.5 邻域网格不消除所有二次工作

若二维正方格边长等于查询半径 R，在适当距离定义下，可以先检查自身与周围格子，再做精确距离筛选；格子越界、周期边界和实际坐标域都需处理。

若所有粒子挤在很小区域，候选对数仍可能接近 N²。数据结构改善查询组织，不是对任意输入都保证线性物理模拟。

## 13. 直方图：空桶无需靠分段求和才能正确计数（课件补充）

用户文字稿明确把直方图细节留作课后材料；本节结合课件第 47–49 页展开，不称作课堂逐句讲过的内容。

直方图只需每个桶的数量。将 bin key 排序，找到每个非空 run 的起点和终点，计数等于 end−start；空桶输出 0。若已有第 12 节的区间，根本无需额外 Segmented Sum 才能得到普通计数。

例如 keys=[0,0,3,3,3,7]，8 个桶计数为 [2,0,0,3,0,0,0,1]。若只记录 start，不能用下一个桶的 start 直接相减，因为相邻桶可能为空。

课件方案从当前非空桶向后找下一个非空桶。每个空隙只被前一个非空桶向后搜索一次，整体搜索工作可按 O(K) 摊销，而不是简单说成所有桶做满 K 步的 O(K²)；但最大空隙会形成较长的顺序链。直接让每个 run 的末项写 end，可以避免这一向后搜索。

对于加权直方图，桶内权重需要相加，才是第 11 节按 key 分段聚合的情形。高冲突原子操作、局部直方图与排序方案都值得按工作量、内存和分布比较，本章只核验结果，不给固定速度结论。

## 14. Python：完整算法与流水线实验

### 14.1 程序覆盖什么？

程序提供保持顺序的树形 Reduce、距离倍增 Inclusive、Blelloch Exclusive、稳定筛选、由结合二元组构成的分段 Inclusive、Gather、唯一目标 Scatter、CSR SpMV、粒子 cell 映射、排序分桶和加权 Scatter Sum。

它顺序执行各层，以便检查算法语义、阶段快照与运算次序。Python 大整数避免小例子的溢出；程序没有创建 GPU 或声称解释器循环是并行实现。

### 14.2 完整代码

保存为 `primitives.py`：

```python
"""Deterministic data-parallel algorithms executed sequentially on the CPU."""
from collections import Counter
from random import Random


def serial_exclusive(xs, op, identity):
    out, acc = [], identity
    for x in xs:
        out.append(acc)
        acc = op(acc, x)
    return out


def tree_reduce(xs, op, identity):
    level = list(xs)
    while len(level) > 1:
        level = [op(level[i],level[i+1]) if i+1 < len(level) else level[i]
                 for i in range(0,len(level),2)]
    return level[0] if level else identity


def hillis_inclusive(xs, op):
    out, distance, work, rounds = list(xs), 1, 0, 0
    while distance < len(out):
        old = out[:]
        for i in range(distance, len(out)):
            out[i] = op(old[i-distance], old[i])
            work += 1
        distance *= 2
        rounds += 1
    return out, work, rounds


def blelloch_exclusive(xs, op, identity):
    n = len(xs)
    if n == 0: return [], 0, 0
    m = 1 << (n-1).bit_length()
    a = list(xs)+[identity]*(m-n)
    width, work, rounds = 2, 0, 0
    while width <= m:
        for right in range(width-1, m, width):
            left = right-width//2
            a[right] = op(a[left], a[right])
            work += 1
        width *= 2
        rounds += 1
    a[m-1] = identity
    width = m
    while width >= 2:
        for right in range(width-1, m, width):
            left = right-width//2
            left_total, incoming = a[left], a[right]
            a[left] = incoming
            a[right] = op(incoming, left_total)  # prefix BEFORE left subtree
            work += 1
        width //= 2
        rounds += 1
    return a[:n], work, rounds


def compact(xs, predicate):
    flags = [int(predicate(x)) for x in xs]
    positions, _, _ = blelloch_exclusive(flags, lambda a,b:a+b, 0)
    count = positions[-1]+flags[-1] if flags else 0
    out, writes = [None]*count, [0]*count
    for i, keep in enumerate(flags):
        if keep:
            out[positions[i]] = xs[i]
            writes[positions[i]] += 1
    assert writes == [1]*count
    return out


def segmented_inclusive(xs, heads, op, identity):
    if len(xs) != len(heads) or (xs and not heads[0]):
        raise ValueError('heads must match data and mark the first element')
    def combine(left, right):
        a, ha = left
        b, hb = right
        return (b if hb else op(a,b), ha or hb)
    pairs = list(zip(xs, map(bool, heads)))
    prefix, _, _ = blelloch_exclusive(pairs, combine, (identity, False))
    return [combine(p,x)[0] for p,x in zip(prefix,pairs)]


def gather(xs, indices):
    if any(i < 0 or i >= len(xs) for i in indices): raise ValueError('bad gather index')
    return [xs[i] for i in indices]


def scatter_unique(xs, indices, size):
    if len(xs) != len(indices) or len(set(indices)) != len(indices):
        raise ValueError('scatter requires one value per unique destination')
    if any(i < 0 or i >= size for i in indices): raise ValueError('bad scatter index')
    out = [None]*size
    for i,x in zip(indices,xs): out[i] = x
    return out


def spmv(values, columns, rowptr, x):
    if not rowptr or rowptr[0] != 0 or rowptr[-1] != len(values):
        raise ValueError('bad row pointers')
    if len(values) != len(columns) or any(a > b for a,b in zip(rowptr,rowptr[1:])):
        raise ValueError('bad CSR lengths or row order')
    products = [a*b for a,b in zip(values,gather(x,columns))]
    heads = [False]*len(values)
    for lo,hi in zip(rowptr,rowptr[1:]):
        if lo < hi: heads[lo] = True
    prefix = segmented_inclusive(products,heads,lambda a,b:a+b,0)
    return [prefix[hi-1] if lo < hi else 0 for lo,hi in zip(rowptr,rowptr[1:])]


def cell_ids(points, nx, ny):
    if nx < 1 or ny < 1: raise ValueError('bad grid dimensions')
    if any(not (0 <= x < 1 and 0 <= y < 1) for x,y in points):
        raise ValueError('points must lie in the half-open unit square')
    return [int(y*ny)*nx+int(x*nx) for x,y in points]


def bin_ranges(keys, bins):
    if bins < 1 or any(k < 0 or k >= bins for k in keys): raise ValueError('bad bin')
    pairs = sorted((k,i) for i,k in enumerate(keys))
    starts, ends = [0]*bins, [0]*bins
    for j,(key,_) in enumerate(pairs):
        if j == 0 or key != pairs[j-1][0]: starts[key] = j
        if j+1 == len(pairs) or key != pairs[j+1][0]: ends[key] = j+1
    return [i for k,i in pairs], starts, ends


def scatter_sum(values, keys, bins):
    if len(values) != len(keys): raise ValueError('length mismatch')
    order, _, _ = bin_ranges(keys,bins)
    sorted_keys = [keys[i] for i in order]
    heads = [i == 0 or k != sorted_keys[i-1] for i,k in enumerate(sorted_keys)]
    prefix = segmented_inclusive([values[i] for i in order],heads,lambda a,b:a+b,0)
    out = [0]*bins
    for i,k in enumerate(sorted_keys):
        if i+1 == len(order) or k != sorted_keys[i+1]: out[k] = prefix[i]
    return out


def main():
    add = lambda a,b:a+b
    scan_cases = 0
    def check_scan(xs, identity):
        expected = serial_exclusive(xs,add,identity)
        got, work, rounds = blelloch_exclusive(xs,add,identity)
        inc, hwork, hrounds = hillis_inclusive(xs,add)
        assert got == expected
        assert tree_reduce(xs,add,identity) == (add(expected[-1],xs[-1]) if xs else identity)
        assert inc == [add(p,x) for p,x in zip(expected,xs)]
        if xs:
            m = 1 << (len(xs)-1).bit_length()
            assert work == 2*(m-1) and rounds == 2*(m.bit_length()-1)
        else: assert (work,rounds) == (0,0)
        assert hwork == sum(len(xs)-(1<<k) for k in range(hrounds))
    for n in list(range(66))+[127,128,129,257]:
        check_scan([(i%13)-6 for i in range(n)],0)
        check_scan([chr(97+i%4) for i in range(n)],'')
        scan_cases += 2
    rng = Random(149)
    for _ in range(200):
        xs = [rng.randrange(-9,10) for _ in range(rng.randrange(130))]
        check_scan(xs,0)
        scan_cases += 1
        assert compact(xs,lambda x:x%3 != 0) == [x for x in xs if x%3 != 0]
        assert compact(xs,lambda x:False) == []
        assert compact(xs,lambda x:True) == xs
        heads = [i == 0 or rng.random() < .3 for i in range(len(xs))]
        expected, acc = [], 0
        for x,h in zip(xs,heads):
            acc = x if h else acc+x
            expected.append(acc)
        assert segmented_inclusive(xs,heads,add,0) == expected
        keys = [rng.randrange(16) for x in xs]
        order,starts,ends = bin_ranges(keys,16)
        assert sorted(order) == list(range(len(xs)))
        for k in range(16):
            assert order[starts[k]:ends[k]] == [i for i,x in enumerate(keys) if x == k]
        assert [b-a for a,b in zip(starts,ends)] == [Counter(keys)[k] for k in range(16)]
        expected = [sum(x for x,k in zip(xs,keys) if k == b) for b in range(16)]
        assert scatter_sum(xs,keys,16) == expected
    for _ in range(100):
        rows, cols = rng.randrange(12), rng.randrange(1,9)
        dense = [[rng.choice([0,0,0,-2,1,3]) for c in range(cols)] for r in range(rows)]
        x = [rng.randrange(-4,5) for c in range(cols)]
        values,columns,rowptr = [],[],[0]
        for row in dense:
            for c,v in enumerate(row):
                if v: values.append(v);columns.append(c)
            rowptr.append(len(values))
        assert spmv(values,columns,rowptr,x) == [sum(a*b for a,b in zip(row,x)) for row in dense]
    assert spmv([],[],[0],[]) == []
    assert spmv([],[],[0,0,0],[]) == [0,0]
    assert spmv([3,1,2,4,2,6,8],[0,2,1,2,1,2,3],[0,2,2,3,4,7,7],[1,2,3,4]) == [6,0,4,12,54,0]
    assert segmented_inclusive(['a','b','c','d'],[1,0,1,0],add,'') == ['a','ab','c','cd']
    points = [(.6,.4),(.3,.1),(.55,.5),(.1,.1),(.99,.99),(.4,.1)]
    assert cell_ids(points,4,3) == [6,1,6,0,11,1]
    assert bin_ranges(cell_ids(points,4,3),12)[0] == [3,1,5,0,2,4]
    assert bin_ranges([],16) == ([],[0]*16,[0]*16)
    assert scatter_sum([1]*10,[5]*10,16) == [0]*5+[10]+[0]*10
    assert scatter_unique(['A','B','C'],[2,0,1],3) == ['B','C','A']
    for action in [lambda:gather([1],[-1]),lambda:scatter_unique([1,2],[0,0],1),
                   lambda:spmv([],[],[1],[]),lambda:bin_ranges([16],16),lambda:cell_ids([(1.0,0.5)],4,3)]:
        try: action()
        except ValueError: pass
        else: raise AssertionError('invalid input accepted')
    a = [2,1,3,4]
    print('exclusive=',blelloch_exclusive(a,add,0)[0], 'inclusive=',hillis_inclusive(a,add)[0])
    print(f'scan_cases={scan_cases} integer_and_noncommutative_strings=pass')
    print('random_pipelines=200 compact_three_predicates=pass segmented=pass bins=pass scatter_sum=pass')
    print('spmv_random=100 empty_rows_example=[6, 0, 4, 12, 54, 0] invalid_inputs=pass')
    print('N=8: Hillis combines=17 rounds=3; Blelloch combines=14 rounds=6')
    print('all_checks=pass')


if __name__ == '__main__': main()
```

### 14.3 运行与实测输出

```bash
python3 labs/lecture08/primitives.py
```

本次输出：

```text
exclusive= [0, 2, 3, 6] inclusive= [2, 3, 6, 10]
scan_cases=340 integer_and_noncommutative_strings=pass
random_pipelines=200 compact_three_predicates=pass segmented=pass bins=pass scatter_sum=pass
spmv_random=100 empty_rows_example=[6, 0, 4, 12, 54, 0] invalid_inputs=pass
N=8: Hillis combines=17 rounds=3; Blelloch combines=14 rounds=6
all_checks=pass
```

固定测试长度包含 0…65、127、128、129、257，整数与字符串各一次，共 140；另有固定种子 200 组随机整数 Scan，共 340。每组检查两种 Scan、树形 Reduce 与顺序参考，并核对 Scan 的结合次数和轮数。

200 组随机流水线分别验证三种筛选谓词、分段结果、分桶排列与加权聚合；SpMV 另有 100 组随机稀疏矩阵，对照直接稠密乘法，并测试包含连续空行与末尾空行的例子。程序还拒绝负 Gather 索引、重复 Scatter 目标、非法 CSR 起点、越界桶和网格边界坐标。

这些是指定输入的算法验证，不是所有代数结构、硬件调度或任意超大输入的证明。

## 15. C++17：真实线程上的分块 Exclusive Scan

### 15.1 两次完成等待，三个逻辑阶段

各 Worker 在自己的连续区间计算局部前缀并写一个 total；join 后，主线程按块顺序生成 bases；再并行把 base 放在局部前缀左侧合并，等待所有 Worker 结束。

局部写入区间互不重叠，totals 各槽有唯一写者，bases 在第二批线程启动前已准备完毕。空区间 total=单位元，允许 Worker 数大于元素数，不需要共享自旋标志或复杂 Barrier。

### 15.2 完整代码

保存为 `chunk_scan.cpp`：

```cpp
#include <cstdint>
#include <functional>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

template<class F> void workers(unsigned p,F job) {
    std::vector<std::thread> pool;
    for (unsigned r=1;r<p;++r) pool.emplace_back(job,r);
    job(0);
    for (auto& t:pool) t.join();
}
template<class T,class Op>
std::vector<T> exclusive_scan(const std::vector<T>& input,unsigned p,T identity,Op op) {
    if (p<1 || p>64) throw std::invalid_argument("workers must be 1..64");
    std::size_t n=input.size();
    std::vector<T> out(n),totals(p,identity),bases(p,identity);
    workers(p,[&](unsigned r) {
        std::size_t lo=r*n/p,hi=(r+1)*n/p;
        T acc=identity;
        for (auto i=lo;i<hi;++i) { out[i]=acc;acc=op(acc,input[i]); }
        totals[r]=acc;
    }); // join publishes every local prefix and total
    T acc=identity;
    for (unsigned r=0;r<p;++r) { bases[r]=acc;acc=op(acc,totals[r]); }
    workers(p,[&](unsigned r) {
        for (std::size_t i=r*n/p;i<(r+1)*n/p;++i)
            out[i]=op(bases[r],out[i]); // left base, then local prefix
    });
    return out;
}
template<class T> void verify(const std::vector<T>& x,unsigned p,T identity) {
    auto got=exclusive_scan(x,p,identity,std::plus<T>{});
    T acc=identity;
    for (std::size_t i=0;i<x.size();++i) {
        if (got[i]!=acc) throw std::runtime_error("prefix/order mismatch");
        acc=acc+x[i];
    }
}
int main() {
    try {
        int cases=0;
        for (int n : {0,1,2,3,5,7,8,31,32,33,127,257})
            for (unsigned p : {1,2,3,4,8}) {
                std::vector<std::int64_t> x(n);
                std::vector<std::string> words(n);
                for (int i=0;i<n;++i) {
                    x[i]=i%13-6;
                    words[i]=std::string(1,static_cast<char>('a'+i%4));
                }
                verify(x,p,std::int64_t{0});++cases;
                verify(words,p,std::string{});++cases;
            }
        std::mt19937 rng(149);
        for (int test=0;test<100;++test) {
            std::vector<std::int64_t> x(rng()%513);
            for (auto& v:x) v=static_cast<int>(rng()%19)-9;
            verify(x,1+rng()%8,std::int64_t{0});++cases;
        }
        bool rejected=false;
        try { exclusive_scan(std::vector<int>{1},0,0,std::plus<int>{}); }
        catch (const std::invalid_argument&) { rejected=true; }
        if (!rejected) throw std::runtime_error("invalid worker count accepted");
        auto demo=exclusive_scan(std::vector<int>{2,1,3,4},3,0,std::plus<int>{});
        std::cout<<"exclusive:";
        for (auto v:demo) std::cout<<' '<<v;
        std::cout<<"\ncases="<<cases
                 <<" integer_and_string=pass empty_partitions=pass invalid_workers=pass correct=yes\n";
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
```

### 15.3 编译与实际结果

从仓库根目录运行：

```bash
mkdir -p /tmp/cs149-l08-build
c++ -O2 -std=c++17 -pthread -Wall -Wextra -pedantic \
  labs/lecture08/chunk_scan.cpp -o /tmp/cs149-l08-build/chunk_scan
/tmp/cs149-l08-build/chunk_scan
```

本次 macOS ARM64、Apple Clang 16 的输出：

```text
exclusive: 0 2 3 6
cases=220 integer_and_string=pass empty_partitions=pass invalid_workers=pass correct=yes
```

12 种固定长度、5 种 Worker 数、整数/字符串两类，共 120；另有 100 组固定种子随机整数案例。包含空输入、非整除分块、Worker>N，以及结合但不交换的字符串连接。小整数的范围避免 int64 溢出。

本次还实际运行了 ThreadSanitizer 构建，同样通过且没有竞争报告：

```bash
c++ -O1 -g -std=c++17 -pthread -fsanitize=thread \
  labs/lecture08/chunk_scan.cpp -o /tmp/cs149-l08-build/chunk_scan-tsan
/tmp/cs149-l08-build/chunk_scan-tsan
```

此实现每阶段重新创建线程，适合展示完成关系，不是高性能线程池。没有 Benchmark、CPU 绑定或 GPU 实验；不能用 220 组小输入的正确性结果声称多线程一定加速。一次检测无报告也不构成所有输入与调度的证明。

## 16. 练习与参考答案

### 练习 1：函数作为参数

Map 接受 int→string 的纯函数和长度 N 的整数序列，输出类型与长度是什么？

**答：** 长度 N 的字符串序列；输出第 i 项对应输入第 i 项。可改变处理先后，不改变输出位置的定义。

### 练习 2：非交换运算

字符串连接结合但不交换，树形归约和 Scan 能否使用？

**答：** 可以，只要保持输入顺序、只改变括号。下扫时右子树收到“父前缀连接左摘要”，不能颠倒。

### 练习 3：起始值被多算

从 10 开始对 [2,1,3,4] 求和，分成两块都从 10 开始再相加，错在哪里？

**答：** 起始值计算了两次，得到 30 而非 20。块内从单位元 0 开始，额外的 10 只加入一次。

### 练习 4：由 Inclusive 得到 Exclusive

对 max 运算、单位元 −∞，输入 [2,1,5]，两种 Scan 是什么？能减原数组转换吗？

**答：** Inclusive=[2,2,5]，Exclusive=[−∞,2,2]。通用方法是补单位元后右移，不能用减法撤销最大值。

### 练习 5：倍增的快照

[1,2,3,4] 在 d=1 时，为什么顺序原地从左向右改写会错？

**答：** 第 2 个更新之后后续项读到了本轮新值，形成 [1,3,6,10]，应为 [1,3,5,7]。并行阶段同样需要旧版本读取规则。

### 练习 6：比较 Work 与轮数

N=16 时，倍增 Scan 与 Blelloch 分别有多少结合操作、多少轮？

**答：** 倍增为 16×4−15=49 次、4 轮；Blelloch 为 2×15=30 次、8 轮。暂不统计复制、屏障等成本，不能只据其中一个数判定实测快慢。

### 练习 7：非二次幂

N=9 的 Blelloch 应补齐到多少项？加法与字符串应分别补什么？

**答：** M=16；分别补 0 和空串。做完后截取前 9 项。使用单位元还能使补齐后的总摘要等于原序列归约，便于与归约或分层实现共用。

### 练习 8：稳定筛选

输入 [8,3,7,2]，保留大于 5 的项，给出 flags、Exclusive 位置和输出。

**答：** flags=[1,0,1,0]，位置 [0,1,1,2]；只让保留项写位置 0、1，输出 [8,7]，长度 2。

### 练习 9：空段如何保留？

[[4],[],[2,3]] 平铺后的起点标志为什么不足以恢复全部三个段？

**答：** data=[4,2,3]，heads=[1,1,0] 只能看见两个非空段。可用偏移 [0,1,1,3] 保留中间空段。

### 练习 10：空行提取

某行 rowptr[r]=rowptr[r+1]=0，为什么不能读 prefix[end−1]？

**答：** 该行无数据，−1 不指向本行结果；Python 还可能把它解释为尾项。应直接输出 0。

### 练习 11：重复 Scatter

values=[4,9]、目标 [1,1]，普通 Scatter 是否有唯一答案？如何变成有定义的求和？

**答：** 没有冲突规则就没有唯一输出。可约定按目标分组求和，零初始时桶 1 得 13，再由唯一段末写入。

### 练习 12：稀疏行手算

某行非零为列 0 的 3 与列 2 的 1，x=[1,2,3,4]，输出是什么？第 4 条非空行 [0,2,6,8] 呢？

**答：** 前者 3×1+1×3=6；后者 2×2+6×3+8×4=54，最后一个系数使用 x3 而非 x2。

### 练习 13：网格排序后 ID

cell=[2,0,2,0]，按 (cell,原始 ID) 排序后 ID 是什么，cell 2 的范围是什么？

**答：** ID=[1,3,0,2]，排序 key=[0,0,2,2]；cell 2 为 [2,4)，范围访问的是排序 ID，不是原粒子数组位置 2…3 的直接含义。

### 练习 14：直方图空桶

sorted keys=[1,1,5]，6 个桶，计数如何得到？

**答：** [0,2,0,0,0,1]。非空 run 直接用终点减起点；仅存 starts 时，不能把空桶的默认值拿来相减。

### 练习 15：分块 Scan 的关键依赖

为何主线程不能在局部扫描线程尚未结束时读取 totals？

**答：** 会读到未完成或并发修改的值。第一次 join 确保局部写入完成；第二批线程读取已经固定的 bases，最后 join 确保完整输出可见。

### 练习 16：阶段数就是周期数吗？

32 Lane 的倍增 Scan 有 5 个距离阶段，能保证 5 个 GPU 时钟完成吗？

**答：** 不能。每阶段可能含数据交换、指令依赖、分支和同步；5 是抽象算法阶段，不是硬件计时。

### 练习 17：只优化原语够吗？

每个 Map/Sort/Scan 都很快，整条流水线是否必然高效？

**答：** 不一定。中间结果、内存流量、启动、排序成本和短阶段都可能限制整体速度，应测端到端并考虑融合与专门算法。

### 练习 18：设计性能比较

比较排序分桶与原子直方图，需要固定并记录哪些因素？

**答：** 相同输入与桶数、同样计数/溢出要求、相同初始化与计时范围、硬件和编译选项；至少测均匀与集中分布，记录临时内存和多次运行，而不只挑一个热点极重的案例。

## 17. 面向 AI Infrastructure 的迁移（作者延伸）

Token 筛选与可变长数据打包，可以先生成保留标志或输出长度，再由 Scan 分配位置；路由到不同专家/分片的索引组织，也可以用 key 分组与区间表示。是否采用排序、计数、原子或分层聚合，要结合目标规模和分布。

稀疏张量运算常把结构信息与值分离：索引决定 Gather/Scatter，值执行 Map，行或段完成聚合。暴露更多元素级并行可能改善负载，却会增加元数据与通信；不能把“稀疏”直接等同于“运行一定更快”。

数据处理库和分布式系统也提供集合变换，但不同接口的顺序、失败恢复与副作用规则不同。课堂以 Spark 作类比，不表示任意分布式集合都承诺本章本地序列的全部位置顺序语义；具体契约留到相应系统再核对。

这些是作者的工程联系，不是 2023 年文字稿逐项介绍了当前推理框架。核心原则仍是：先定义结果与依赖，再选择原语与表示，最后检查总工作、数据移动和实际执行时间。

## 18. 来源、修正与验证范围

| 来源 | 使用范围 | 状态 |
| --- | --- | --- |
| [Stanford 第 8 讲课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/dataparallel/) | 讲次与主题 | 已核对 |
| [官方 51 页课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/dataparallel/08_dataparallel.pdf) | Map/Fold、Scan、分段扫描、SpMV、粒子分组与直方图 | 全部文字结构已核对；视觉抽查第 11、15、16、17、20、23、32、46、49 页，未逐页视觉复核 |
| 用户提供自动英文文字稿 | 开场数据并行模型到最后 Thrust/Spark 总结 | 全文已阅读，无时间码，未逐句核验音频 |
| [课程录像](https://www.youtube.com/watch?v=Ba3TqxSgnTk) | 对应本讲录像入口 | 未编造时间码，未逐句校对原音 |
| [Blelloch：Prefix Sums and Their Applications](https://www.cs.cmu.edu/afs/cs.cmu.edu/project/scandal/public/papers/CMU-CS-90-190.html) | 原作者报告与 Scan 来源索引 | 作者文献记录；本章推导、图表与代码独立编写 |
| [NVIDIA GPU Gems：Parallel Prefix Sum](https://developer.nvidia.com/gpugems/gpugems3/part-vi-gpu-computing/chapter-39-parallel-prefix-sum-scan-cuda) | 历史 Scan 教学与应用参考 | 不将历史设备代码直接视为现代同步正确性保证 |
| [NVIDIA Volta 调优指南](https://docs.nvidia.com/cuda/volta-tuning-guide/index.html) | 独立线程调度与显式同步要求 | 用于限定课件 Warp 内存示例 |
| [NVIDIA CUB DeviceScan 文档](https://nvidia.github.io/cccl/unstable/cub/api/structcub_1_1DeviceScan.html) | 结合/非交换操作与生产库实现边界 | 官方文档参考，所链接为开发版；未运行库，不固定描述所有版本的内部算法 |
| [NVIDIA Thrust API 索引](https://nvidia.github.io/cccl/unstable/thrust/api/index.html) | 高层原语的延伸入口 | 接口索引，不声称已经执行 GPU API |

修正与限定包括：种子不可在分块中重复计算；Fold 的摘要必须满足兼容规则；Inclusive 转 Exclusive 不能普遍用减法；下扫必须保持运算左右次序；旧 Warp 代码缺少现代同步；163860 的线程数笔误；SpMV 末项应为 8x3；空段/空行/空桶必须保留定义；阶段数不等于 GPU 周期数；直方图计数可直接取 run 长度，无需强制分段求和。

Python 通过 340 组 Scan/Reduce、200 组随机应用流水线与 100 组随机 SpMV；C++17 在 macOS ARM64、Apple Clang 16 通过 220 组真实线程检查，ThreadSanitizer 同样通过且未报告竞争。未做 GPU、Thrust/CUB 或分布式实机实验，未做性能 Benchmark，不提供固定加速比。

原创案例、代数条件证明、空行扩展、稳定筛选、完整程序和练习为作者补充；直方图细节明确来自课件补充页。详细核验见 [第 8 讲来源记录](../sources/lecture-08-audit.md)。公开仓库只提交原创教材、实验和来源链接，不上传用户文字稿全文、官方 PDF 或临时构建。
