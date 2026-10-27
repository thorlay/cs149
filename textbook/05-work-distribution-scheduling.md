# 第 05 章｜工作分配与调度：负载平衡、任务粒度与工作窃取

> Stanford CS149 · Fall 2023 · Lecture 5 — Performance Optimization I: Work Distribution and Scheduling
>
> **状态：自包含中文教材，第一版。** 本章结合用户提供的英文自动转写、官方 62 页 Slides、OpenCilk 官方文档与相关原始论文，独立编写解释、算例和实验。文字稿已阅读全文并对照主题，但无时间码、含听不清与术语误识别，尚未与原音逐句核验。已核对 PDF 文本结构并抽查关键图页，不声称完成了每一页的视觉复核。本文不是官方授权教材或逐字翻译。

**先修知识：** 数组、循环、函数、递归与基础 C++。本章从头解释线程、任务、锁、Barrier 与依赖图；不要求先读其他章节，也不要求有 GPU 或 Cilk 编译器。

**学习时间：** 阅读和纸笔自测约 2–3 小时；运行模型与 C++ 实验约 1 小时。

**概念衔接：** 本讲开场复习了 [第四章](./04-parallel-programming-basics.md) 的网格迭代与屏障案例；本文仍会独立解释所需概念，第四章可作延伸阅读。

**配套实验：** [Python 模型与 C++17 调度实验](../labs/lecture05/README.md)。全部核心实验代码也收录于本章，来源与核验边界见章末。

## 0. 四个 Worker 都有任务，为什么三个先闲下来？

假设有 16 个独立任务，每个任务对应处理一个输入。前 4 个各耗费 9 单位时间，后 12 个各耗费 1 单位时间。现在有 4 个同速 Worker，也就是实际执行任务的工作线程；每个 Worker 同时只执行一个任务，暂不考虑任何额外开销。

如果按数组连续分成四块，每个 Worker 都得到 4 个任务，看起来完全均分：

| Worker | 任务编号 | 有用工作量 |
| --- | --- | --- |
| 0 | 0–3 | 36 |
| 1 | 4–7 | 4 |
| 2 | 8–11 | 4 |
| 3 | 12–15 | 4 |

总工作量为 48，但程序要等最后一个 Worker 完成，因此完成时间是 36。后三个 Worker 在时刻 4 就闲下来了。

如果改成轮流分配，Worker p 处理 p、p+4、p+8、p+12，每个 Worker 刚好得到一个重任务和三个轻任务，总量都是 12，整个程序在时刻 12 完成。

**同样数量的任务，不等于同样数量的工作。** 本讲研究的是怎样把可做的工作交给执行资源，让负载更平衡，同时不为了分工本身付出过多开销。

## 1. 任务、线程与工作量：先说明自己在数什么

### 1.1 Task 不等于 Thread

**Task（任务）**是需要完成的一段工作，可以是一个数组元素、一行像素、一个区间或一次递归子问题。**Thread（线程）**是执行代码的控制流，拥有自己的执行状态，由操作系统和运行时调度。

一个固定大小的线程池可以执行成千上万个任务。给 8 个线程准备 1000 个任务，不表示机器要同时保存 1000 个操作系统线程；它表示做完一个任务的 Worker 还有其他任务可选。

**Decomposition（分解）**回答“工作切成什么片”；**Assignment（分配）**回答“每片交给谁”；**Scheduling（调度）**还要决定“什么时候执行、按什么顺序执行”。好的任务分解不必绑定唯一的调度策略。

### 1.2 Work、Span 和两个无法绕过的下界

把程序看成一张带方向的依赖图：节点代表一段工作，边 A→B 表示 B 必须等 A 完成后才能开始。没有环的图叫 **DAG（有向无环图）**。

定义 T₁ 为整个并行算法的总工作量，单位可以是理想同速处理器上的时间；定义 T∞ 为依赖图最长路径的工作量，称为 **Span（关键路径长度）**。下标 ∞ 表示即使有无限处理器，也不能跨过这条依赖链。

若 P 个同速处理器执行时间为 TP，忽略额外开销时必有：

$$
T_P\ge\max\left(\frac{T_1}{P},T_\infty\right)
$$

第一个下界来自总量守恒，第二个来自依赖。它们只给下界，不保证存在达到下界的调度，也不包含真实硬件的访存与同步成本。

对章首 16 个不可再分的独立任务，T₁=48，T∞=9，P=4 时下界为 max(12,9)=12。轮流分配恰好达到 12；连续分块的 36 则是分配造成的损失。

算法的理论并行度定义为 T₁/T∞。它描述依赖图提供多少并行机会，不等于任务总数，也不保证硬件获得同样倍数的加速。

### 1.3 怎样量化负载不平衡？

若没有任务间依赖，Worker p 的有用工作量为 Wp，各 Worker 同时开始、同速执行，那么完成时间为 max(Wp)。一个简单的理想负载效率是：

$$
E_{\mathrm{balance}}=\frac{\sum_{p=0}^{P-1}W_p}{P\max_p W_p}
$$

章首连续分块的效率为 48/(4×36)=1/3；轮流分配为 48/(4×12)=1。这里衡量的是这个模型中的空闲容量，不能直接当成真实 CPU 的硬件计数器利用率。

如果有依赖、异构 Core、内存竞争或不同运行频率，执行时间不再只取决于每人领到多少算术工作。要保留模型的适用范围。

### 1.4 并行运行时间的一半，只剩一个人工作，等于 50% 串行比例吗？

不一定。课件用四份工作量 [1,1,1,2] 说明这个区别：总工作量为 5，四个 Worker 的完成时间为 2。在后半段运行时间内，确实只剩最后一个 Worker 在做事；但这一段只完成 1 单位工作，占单处理器总工作量的 1/5，也就是 20%。

Amdahl 模型中的串行比例，是相对于串行总工作来定义的。若用 S 表示必须串行的工作比例，其余部分可以在 P 个同速处理器上理想并行，则加速比上界为：

$$
\operatorname{Speedup}(P)\le\frac{1}{S+(1-S)/P}
$$

不能把某次并行运行中“只有一个 Worker 工作的墙钟占比”直接代成 S。更要区分原算法必需的串行依赖，与当前分配人为制造的串行尾部：如果那份 2 的工作可以重新拆分，失衡是可以改进的，不是算法永久存在 20% 串行部分的证明。

## 2. 开场复习：重复使用一个变量，怎样制造额外等待？

### 2.1 Barrier 保证了什么？

**Barrier（屏障）**让一组参与线程到齐后才能越过某个阶段边界。正确的屏障还要提供相应的内存可见性，使屏障前写入的数据能按规则被屏障后的线程读取。

考虑迭代计算：每个线程更新自己负责的数据、计算局部变化量，把变化量加到全局 `diff`，然后所有线程读 `diff` 判断是否继续。若每轮都复用同一个 `diff`，就出现三个阶段约束：

1. 必须先清零，再有人累加这一轮的变化量；
2. 必须所有人累加完，再读最终值；
3. 必须所有人读完，才能清零下一轮。

这些约束中，“所有贡献完成后才能判断”是真实依赖；另一些等待则来自让同一存储位置承载不同轮次的数据。

### 2.2 每人一份局部和，减少累加争用

多个线程不能对共享普通浮点数直接做没有协调的 `diff += local`。这不是不可分割的单一动作：读取、相加、写回可能互相覆盖。

**Mutex（互斥锁）**让同一临界区一次只由一个线程进入；**Atomic Operation（原子操作）**保证相应操作不会被其他线程看成半完成状态。使用它们可以保护共享累加，但每个元素都同步一次通常很贵。

更好的第一步是每个线程先在私有变量中累加一整个区间，最后才把局部结果合并。它不消除最终归约，只减少共享位置被反复访问的次数。

### 2.3 每轮不同版本，减少跨轮存储依赖

最直观的方案是为每一轮保留一个 `diff[t]`。线程在轮次 t 读取最终结果时，轮次 t+1 使用另一个位置，不必覆盖仍可能被别人读取的旧值。

开场还讨论了循环复用三个槽位。不能只说“开三个数组就能删除两个屏障”，必须给出复用时序。下面是作者整理的简化协议，**只讨论变化量归约，不是完整网格算法的可运行实现**：

```text
开始前：三个 diff 槽位全部清零；所有线程从 t=0 开始。
每轮 t：
  每个线程计算 local_diff，并以受保护方式累加到 diff[t % 3]。
  线程 0 清零下一轮要用的 diff[(t + 1) % 3]。
  所有线程进入本轮唯一的 Barrier。
  每个线程读取 diff[t % 3]，得到相同的继续/停止判断。
  若继续，进入 t+1；否则退出。
```

为什么清零下一轮不会覆盖一个慢线程还在看的值？在线程 0 进入轮次 t 时，大家至少已经到过轮次 t−1 的屏障。因此所有人已完成轮次 t−2 的结果读取。下一轮槽位 t+1 与 t−2 在模 3 下相同，此时可安全复用；但它与可能仍被慢线程读取的 t−1 槽位不同。

用两个槽位则有问题：(t+1) mod 2 与 (t−1) mod 2 相同，快线程可能清掉慢线程仍在读的上一轮结果。

这个推理要求所有线程按同样轮次经过屏障、停止判断一致、累加受保护、清零由指定线程完成、且底层网格更新没有额外未满足的依赖。若修改数据流或同步结构，必须重新证明，而不是沿用“三槽位足够”的口号。本章模型代码只检验槽位关系，不声称做了真实并发协议验证。

## 3. 静态分配：在执行前决定谁负责什么

### 3.1 Static 不等于编译时写死

**Static Assignment（静态分配）**是根据已有信息先决定任务归属，执行时不根据谁先完成来反复调整。它可以在运行时根据 N 个元素与 P 个 Worker 计算，不要求编译时就知道 N、P。

连续分块的一种通用写法，是让 Worker p 处理半开区间：

$$
\left[\left\lfloor\frac{pN}{P}\right\rfloor,\left\lfloor\frac{(p+1)N}{P}\right\rfloor\right)
$$

区间首尾相接，覆盖 [0,N)，每块长度最多相差 1。轮流分配则让 p 处理 p+kP，其中 k 从 0 开始、下标小于 N。

一旦归属确定，每个 Worker 通常可以只根据自己的编号计算下标，不需要每做一个任务都去抢共享队列。这是静态方案开销小的原因。

### 3.2 什么情况下静态方案已经很好？

若任务成本接近，等分元素往往就能等分工作。即使单个任务成本有变化，只要每个 Worker 拿到的任务组合足够相似，也可能达到较好平衡。

分形图像中，附近像素的迭代次数可能相近。把相邻行轮流分给不同 Worker，有时能让大家都分到昂贵区域与便宜区域。这个效果利用的是输入结构，不是轮流分配的无条件保证。

反例：N=16、P=4，恰好下标 0、4、8、12 全是重任务。此时循环分配把所有重任务都给 Worker 0，而连续分块可能每人一份重任务。若成本和下标周期相关，所谓“平均会抵消”就可能失败。

不要针对一张固定图片手工裁出看似完美的区域后，就宣称方案对任意输入都有效。可以利用可泛化的结构，也可以测量成本，但需要写明使用了哪些先验信息。

### 3.3 半静态分配

**Semi-static Assignment（半静态分配）**在一段时间内保持分工不变，定期利用最近测得的成本重新分配。

例如模拟网格缓慢变化，当前昂贵的区域在短期内仍可能昂贵：每次重分配有成本，所以不必每个任务都动态决定，也不必整个长程序永远沿用第一次分工。

它依赖“近期成本对近期未来有预测力”。若任务分布瞬间改变，旧统计会失效；若重分配太频繁，统计、迁移和同步本身又可能抵消收益。

## 4. 动态分配：做完的人继续领下一份

### 4.1 一个数组和计数器，也可以是工作队列

**Dynamic Assignment（动态分配）**按运行时进度给空闲 Worker 分配工作。最简单的独立数组任务队列不需要链表：输入数组已经保存了工作描述，用一个共享 `next` 表示下一个未领取的下标即可。

```text
队列逻辑：任务 0、1、2、……、N-1
共享状态：next，初始为 0
每个 Worker：
  原子地取得 next 的旧值，并把 next 增加 1
  如果旧值 >= N，则退出
  否则处理该编号任务，再回来领取
```

原子递增保证不同领取操作拿到不同旧值。计数器单调增加，合法范围内每个编号都能被领到一次。Worker 数是 P，任务数是 N，二者不必相等。

原子递增负责唯一分配，不代表所有其他共享数据都自动安全：任务结果写在哪、结果何时对消费者可见、是否还有生产者，仍需分别处理。

### 4.2 为什么通常需要比 Worker 更多的任务？

如果只把输入切成 P 个不可再分的大任务，就算采用动态队列，每人领一个以后也几乎没有调整余地。某个大任务很慢时，其他人做完了仍然只能等。

切成更多、大小适当的任务，让短任务先完成的 Worker 可以多领几份，处理长任务的 Worker 少领几份，以完成速度适配负载。

这叫给调度器留出 **Parallel Slack（并行余量）**。它没有通用的固定最佳倍数：课件提到的经验比例不是语言保证，也不是所有机器都应照抄的参数。

### 4.3 多任务并不自动解决长尾

有 15 个成本为 1 的任务，以及最后一个成本为 13 的任务，共 4 个 Worker，队列按输入顺序处理，忽略领取开销。

前 12 个短任务在前三个时间单位分三轮完成。时刻 3，最后四份工作被领取：三个 Worker 各做一个短任务，另一个领到大任务并运行到时刻 16。于是完成时间是 16。

若事先知道成本，把 13 的任务放在最前面：一个 Worker 从时刻 0 一直运行到 13，另外三个在时刻 5 前完成 15 个短任务，整体用时 13。

| 顺序 | 总工作量 | 最长单任务 | 完成时间 |
| --- | --- | --- | --- |
| 大任务最后 | 28 | 13 | 16 |
| 大任务最先 | 28 | 13 | 13 |

这个例子中，下界 max(28/4,13)=13，所以大任务先做恰好最优。一般情形中，成本预测不准确、排序本身有开销，还可能有任务依赖；“最长先做”是有用策略，不是对所有问题的最优算法。

如果最长任务内部真的有独立子问题，也可以继续拆分；如果它本来就是一条串行依赖链，调度器无法仅靠换顺序把它切短。

## 5. 粒度：小到能平衡，大到值得调度

### 5.1 把每次领取改成一个区间

设 **Granularity（任务粒度）**为一次领取的元素数 g。Worker 原子地取出旧 `next`，把它增加 g，然后处理 [begin,min(begin+g,N))。

领取到的区间彼此不重叠，最后一个区间可能不足 g 个元素。忽略越界后的退出领取，实际有用任务块数量为：

$$
K=\left\lceil\frac{N}{g}\right\rceil
$$

g 从 1 提高到 10，有用领取次数约降为十分之一，但一次领走的大块也更难在 Worker 间重新平衡。若 g 大到只剩两块，给 8 个 Worker 也不能同时提供 8 份工作。

注意块内循环必须处理下标 j，而不是一直处理 begin。官方第 14 页示意在块内使用了循环变量 j，却仍把读写下标写为 i；本文实验修正这个错误，不照抄重复计算同一元素的版本。

### 5.2 用一个成本模型理解两个方向

设每次领取的管理成本为 h，块内每元素平均有用成本为 c。暂不考虑竞争、负载变化与依赖，一块任务中领取成本所占比例是：

$$
r=\frac{h}{h+gc}
$$

假设 h=1 微秒、c=0.05 微秒：g=1 时 r≈95.24%，g=200 时 r≈9.09%。若想让这个局部比例不超过 5%，要求 gc≥19h，即 g≥380。

这只是解释数量级的假想模型，不是本机对原子操作或真实任务的测量。它还没算排队和长尾，不能据此把最佳块长定成 380。

如果所有 Worker 争用同一个串行服务的领取位置，K 次领取还可能形成 Kh 级别的串行管理瓶颈。不能总把所有管理开销机械除以 P。合理下界至少要同时考虑总工作、关键路径和无法并行的领取服务。

### 5.3 调度越聪明，成本也可能越高

使用全局优先队列、实时预测任务长度、迁移任务和追踪依赖，都可能改善分配，也都需要额外的计算、存储或同步。

因此本讲的第一条工程原则是：先实现最简单的正确方案，再用测量决定下一步。静态连续分块、循环分配、共享原子计数器，都是可以认真评估的基线，不需要为了使用新名词而立刻写复杂调度器。

## 6. 计时：别拿线程时间之和直接减墙钟时间

### 6.1 两个时间量有不同含义

**Wall-clock Time（墙钟时间）**是从程序开始到结束经过多久。每个 Worker 在各任务中记录的时间之和，则描述该 Worker 花在这些区间内的时间；再跨 Worker 相加，得到的是累计 Worker 时间，多个区间可以重叠。

例如四个 Worker 同时各算 5 秒，程序墙钟可能约为 5 秒，累计任务时间却是 20 秒。用 5−20 得到“负的调度开销”显然没有意义。

课堂用总时间与有用时间作对比，意图是定位管理成本。做真实多线程测量时，要明确比较对象：可记录每个 Worker 自己的工作、取任务、等待和空闲时间；或者在一致的 P×T 时间容量模型中观察总体使用率。不能把未定义清楚的不同口径相减。

### 6.2 优化空间应该如何估计？

如果针对某一条决定完成时间的执行路径，测得总长 5.9 秒，其中确定有 5.75 秒是暂不改变的有用计算，那么仅删除剩余开销，最多也只能接近 5.75 秒，理想改进倍数约为 5.9/5.75≈1.026。

若有用部分只有 2.5 秒，才说明路径上可能有更大比例的管理或等待值得研究。但“不是有用计算”不等于“全是锁”：还可能有依赖等待、线程创建、系统抢占、内存停顿或测量误差。

这个估计只讨论不改变有用工作及其关键路径的局部优化。换算法、提高向量化或改变任务分解，可能改变那些原先被当作固定的部分，不能把 1.026 当成程序永远无法突破的上限。

### 6.3 本章实验怎样保持口径清楚？

后面的 C++ 程序报告总墙钟、每个 Worker 完成任务数、内部迭代总数和逐任务计时。总墙钟包含创建和加入线程；输入初始化、串行参考答案和最终校验在计时之外。

逐任务计时本身有开销，并可能包含线程被系统暂停的时间。程序用于观察分配和建立测量意识，不据一次短运行宣称某个调度器在任何机器上都快多少倍。

## 7. 有依赖的任务：在队列里不等于现在能做

### 7.1 Ready Queue 只保存已就绪工作

考虑如下独立设计的 DAG，节点时间分别为 A=2、B=3、C=5、D=1：

```text
       ┌── B：3 ──┐
A：2 ──┤          ├── D：1
       └── C：5 ──┘
```

B、C 都依赖 A；D 同时依赖 B、C。T₁=2+3+5+1=11；关键路径 A→C→D 长度为 2+5+1=8。

用两个 Worker：时刻 0–2 执行 A；2–5 执行 B，同时 2–7 执行 C；7–8 执行 D。完成时间为 8，达到下界 max(11/2,8)=8。

D 虽然很早就可以被“提交”，但不能因此马上执行。**Ready（就绪）**表示所有前置依赖已满足；**Pending（待定）**表示已知存在、尚未可执行。区分两者是任务系统正确性的核心。

### 7.2 依赖计数如何推进？

一种基本实现是给每个任务记录未完成前驱数量：A 为 0，B、C 各为 1，D 为 2。只把计数为 0 的任务放入就绪队列。

A 完成后降低 B、C 的计数，它们变成 0 并入队；B 完成时 D 从 2 变成 1；C 完成时 D 从 1 变成 0，才允许入队。

多个前驱可能同时完成，因此计数更新、就绪发布和结果可见性都需要正确协调。不能让两个前驱都把同一任务发布一次，也不能让消费者先见到“可以运行”却还看不到前驱的输出。

### 7.3 空队列不一定表示程序结束

如果所有就绪队列暂时为空，但某个 Worker 正在执行一个会产生后继任务的节点，程序还没结束。对于会动态创建任务的系统，需要同时跟踪正在运行、尚未完成的工作以及未来可能发布工作的生产者。

如果没有任何任务运行、仍有待定节点、而没有可用的就绪节点，可能是依赖图有环、漏报了完成事件或缺失了前驱。后面的 Python 模型会报告这种状态；真实系统还应区分外部 I/O 等待等合法阻塞来源。

## 8. Fork-Join：递归逐步揭示并行工作

### 8.1 为什么快排适合这个讨论？

Quicksort（快速排序）先选择一个 Pivot（划分基准），把数组分成较小元素和较大元素的两部分，然后分别排序。假设本层 Partition（划分）已经完成，两边写入的是互不重叠的区域，递归调用就可以独立进行。

```text
              划分整个数组
               /       \
          排序左边     排序右边
           /   \       /   \
         子问题 子问题 子问题 子问题
```

刚开始只有一次划分；递归进行后，越来越多子问题被发现。它与“一开始就有一百万个独立数组元素”不同，工作描述本身是逐步产生的。

**Fork-Join（分叉—汇合）**把这种结构表达为：创建可以并发的子工作，然后在需要完整结果的位置等待它们完成。

### 8.2 分治也受关键路径约束

如果每次划分比较均衡、划分本身串行且成本为 Θ(n)，则总工作满足 W(n)=2W(n/2)+Θ(n)，为 Θ(n log n)。关键路径则沿一个分支向下：

$$
S(n)=S(n/2)+\Theta(n)=\Theta(n)
$$

因为 n+n/2+n/4+… 小于 2n。这个版本的理论并行度只有 Θ(log n)，不能看到二叉树就断言 Span 为 Θ(log n)：树每层的节点成本不是常数。

若基准选择极差、不断产生几乎同样大的子问题，总工作和关键路径都可能退化。工作窃取不能自动修复算法本身的坏划分。

### 8.3 小任务回到串行

设一个 Cutoff（截断阈值）：区间足够小时，用串行排序或直接循环完成，不继续创建子任务。只要保留正确的数学计算，这个阈值主要影响性能，而不改变最终排序结果。

它与第 5 节的块长是同一个成本权衡：拆得更细有助于分配，却可能让调度成本比实际工作更贵。

## 9. Cilk 的语义：spawn 提供机会，sync 施加依赖

### 9.1 先看一个最小控制流

下面是用于解释历史 Cilk Plus 语义的代码片段，**不是完整的标准 C++ 可运行程序**：

```cpp
cilk_spawn foo();
bar();
cilk_sync;
baz();
```

`cilk_spawn foo()` 表示 foo 可以与调用方后续工作并发；`bar()` 是调用方接下来正常执行的函数；`cilk_sync` 确保本同步区域内相应的子调用完成，再进入 baz。

因此 foo 与 bar 有并发机会，baz 必须等它们需要满足的依赖完成。但语义没有要求 foo 必须立刻开跑、必须使用另一个物理 Core，或必须先于 bar 完成。

本讲按历史课件讨论 Cilk Plus 的函数内 spawn/sync。现代 OpenCilk 还提供 `cilk_scope` 明确界定同步范围。它们都不表示“全系统所有任务一起过一个 Barrier”；同步的集合有作用域。历史 Cilk Plus 中，含 spawn 的函数返回前还有隐式同步，所以递归函数省略显式 sync，不代表允许子工作在该函数已经返回后任意使用失效的局部状态。

### 9.2 为什么直接按顺序执行也可能合法？

对本章这种没有竞争、没有依赖并发才能取得进展的 Fork-Join 程序，删除 spawn/sync 并按普通函数调用顺序运行，是一种合法的串行投影：先 foo，再 bar，再 baz。

如果分别给 foo、bar 分配 Worker，等待两者完成后再执行 baz，也可以满足相同的依赖。算法表达的是可并发工作与必要约束，运行时选择具体调度。

不能从“串行投影结果正确”推出并行版本一定无竞争。例如两个可并发子任务都做共享 `counter++`，串行投影可能每次得到预期值，并行版本仍然有数据竞争。

也不能在两个子任务之间设计必须同时运行才能解除的互相等待，再指望 spawn 保证它们一定同时占到处理器。这破坏了该抽象容许串行执行的前提。

### 9.3 一个 spawn 不等于创建一个操作系统线程

如果递归每产生一个小任务都创建一个新线程，可能出现线程远多于 Core、创建和切换开销很大、栈内存膨胀的问题。

常见运行时保留一个 Worker 池，让这些线程不断执行轻量任务。池的大小由平台和配置决定，不必等于任务数，也不应把逻辑处理器数当作永远最佳线程数。

文字稿中关于“大多数当前 C++ 编译器都有 Cilk”的宽泛说法不适合作为今天的安装说明。普通 Apple Clang 或通用 C++17 编译器不应被默认当成支持 `cilk_spawn`；要运行真正的 Cilk 程序，需要匹配的 OpenCilk 等工具链。本章的实际线程实验使用标准 C++17，不依赖额外安装大型编译器。

## 10. Child 和 Continuation：究竟把什么放进队列？

### 10.1 给剩下的工作一个名字

对上一节代码，foo 是 **Child（子调用）**；spawn 之后调用方还要做的 bar、sync、baz 等控制流程，构成 **Continuation（后续计算）**。

Continuation 不只是一个函数名，它还需要描述从哪里继续、局部状态是什么，以及遇到同步点时如何处理。真实运行时需要编译器与栈帧管理配合，不能随意把普通 C++ 调用栈交给另一个线程直接执行。

### 10.2 两种合法执行方向

| 策略 | 当前 Worker 先做 | 留给队列的工作 |
| --- | --- | --- |
| Child-first | foo | Continuation |
| Continuation-first | 调用方后续工作 | foo |

本讲重点分析 Child-first、可窃取 Continuation 的方式。若没有其他 Worker 来取，当前线程完成 foo 后，就从自己的队列恢复后续计算，执行顺序接近普通串行调用。

这有利于常见串行路径保持较低管理成本。性能问题还包括缓存局部性和额外状态的规模，不只是“哪边先开跑”。

### 10.3 平坦的 spawn 循环会怎样？

假设调用方依次 spawn foo(0)、foo(1)、…、foo(N−1)。若 Continuation-first，调用方可能快速把所有子任务排队，自己继续生成工作；若 Child-first，当前 Worker 先执行 foo(0)，队列里只有“从 i=1 继续循环”的记录。

一个空闲 Worker 偷取这个记录后，会执行下一次生成，再留下“从 i=2 继续”的记录。工作生成可以在 Worker 之间移动，但依然沿一条逐个推进的控制链，N 个 spawn 的生成 Span 通常是 O(N)。它不是 N 个描述能够在第一瞬间自动同时产生。

### 10.4 分治循环怎样更快揭示工作？

可用如下明确的教学伪代码，区间均为半开区间：

```text
parallel_range(lo, hi):
  若 hi-lo <= g：
    顺序执行 lo 到 hi-1 的元素工作，返回
  mid = lo + floor((hi-lo)/2)
  spawn parallel_range(lo, mid)
  parallel_range(mid, hi)
  sync
```

每个大区间都能被不同 Worker 继续拆分，构成树形的任务生成。若各层拆分开销是常数、叶子大小约 g，则生成链的深度约为 log₂(N/g)，再加叶子串行成本，而不是 N 个逐一生成的链。

总任务管理工作仍有成本，没有凭空消失。官方第 49 页示意把中点写成 `(end-start)/2`，缺少 start 偏移；对于非零起点会出错。本文统一使用 `lo+(hi-lo)/2`，并在模型中验证非零起点子区间的完整覆盖。

## 11. Work Stealing：忙的人本地做，闲的人主动取

### 11.1 从一个共享队列变成每人一条 Deque

一个全局队列要求所有 Worker 领取任务时同步。若每个 Worker 都有自己的 **Deque（双端队列）**，平常可以优先操作自己的队列；只有本地没有可做工作时，才去其他 Worker 处取。

本讲统一约定：

```text
队首 head / top                                  队尾 tail / bottom
[ 较早留下的后续工作 | …… | 最近留下的后续工作 ]
       ↑ 其他 Worker 偷取                本地 Worker 推入/弹出 ↑
```

本地对队尾做后进先出，接近深度优先的串行执行；远端从队首拿较早留下的工作。不要把课件里的 dequeue 拼法误当成“出队操作”本身：这里讨论的数据结构是 deque。

### 11.2 为什么倾向偷较早的大子树？

假设正在处理区间 [0,25)，本地队列从早到晚存着 [100,200)、[50,100)、[25,50) 的后续工作。

空闲 Worker 从队首拿走 [100,200)，通常比拿走 [25,50) 更可能获得足够长的工作，也能自己进一步分裂，减少频繁跨线程交互。

这不是运行时先精确计算每项成本再选最大值。在典型比较均衡的递归里，越早的记录往往对应越大的子树；不规则树中，“较早”不一定等于“最贵”。

本地线程继续做最近的子问题，还可能使用刚访问过的数据。但被偷走的数据也可能需要迁移到另一 Core 的缓存，因此不能说窃取没有通信成本。

### 11.3 两头操作减少争用，但不等于不需要同步

本地和远端主要操作不同位置，能减少互相干扰。然而队列只剩最后一个元素时，双方仍可能同时争取它；还要处理扩容、内存可见性和对象生命周期。

高效的无锁 Deque 有专门算法，不能简单把 `std::deque` 放到多个线程中，一边 `pop_back`、一边 `pop_front` 就宣称安全。本章只提供串行调度轨迹模型，不伪造一个完整无锁 Cilk 运行时。

### 11.4 为什么随机选 Victim？

**Victim（被窃取者）**是一次偷取尝试选择的 Worker。总去找“看起来最忙”的人，需要维护或查询负载，还可能让许多空闲线程同时去争同一个队列；看到的统计也可能已经过时。

随机选择候选者可以避免复杂的全局决策，但可能选中空队列并失败，再试别处。因此“随机挑选”不等于“第一次就必然挑到有工作的人”。

经典结果对满足特定结构条件的计算给出保证：在其同速处理器与调度成本模型中，Fully Strict、结构化 Fork-Join 计算使用相应随机工作窃取调度器，期望时间为 O(T₁/P+T∞)。Fully Strict 可直观理解为子工作的完成沿合法的祖先/父子同步结构返回，而不是任意跨任务阻塞。

这说明在足够并行度下，期望调度效果能接近基本下界的常数因子，并不证明它对任意 DAG、异构机器、I/O 阻塞、实时截止时间或每一次随机结果都最优。更不意味着加上 work-stealing 标签的任意代码都自动继承这个定理。

## 12. sync 的实现直觉：等依赖，不必让 Worker 干等

### 12.1 没发生偷取时，常见路径可以很便宜

如果当前函数相关的工作都由同一个 Worker 按 Child-first 顺序做完，来到 sync 时，所需子工作已经完成，检查可以很快通过。

课件称这一情形为 no-op，强调不需要跨 Worker 等待。真实编译代码仍可能有检查和管理，不能把这句话理解为“所有 spawn 与 sync 在任何实现中成本绝对为零”。

### 12.2 后续工作先到 sync，可能还不能继续

若另一个 Worker 偷走 Continuation，就可能先完成 bar、先到 sync，而 foo 仍在原 Worker 上运行。此时 baz 不能开始。

这不要求到达 sync 的物理线程一直坐在那里。运行时可以保存尚未就绪的后续记录，让当前 Worker 去执行或偷取其他 Ready 工作；相关子工作都完成后，再恢复 baz。

因此“逻辑控制流等待”与“物理 Worker 空闲等待”不同。把嵌套任务简单放进固定线程池，然后让每个父任务阻塞等子任务，可能造成所有 Worker 都被父任务占住、子任务无人执行的死锁。能帮助推进其他工作的运行时处理与普通阻塞线程池并不一样。

### 12.3 计数与 Greedy Join 的一个轨迹

把一个同步区域称为 A。运行时需要知道与 A 相关的已发布工作、尚未完成工作，以及后续计算是否已经抵达汇合条件。

```text
时刻 1：Worker 0 执行 foo(0)，Worker 1 拿到循环后续。
时刻 2：更多 Worker 加入，区域 A 内有多个未完成子工作。
时刻 3：后续控制流到达 sync，但还有 foo(9) 未完成。
        保存 sync 之后的记录；有空闲的 Worker 去找其他工作。
时刻 4：foo(9) 完成，区域 A 的依赖全部满足。
        某个 Worker 获得继续执行 bar() 的资格。
```

课件的 Greedy Join 图例中，最后完成相关工作的 Worker 直接继续执行汇合后的代码。最初发起 spawn 的 Worker 不一定是执行 sync 之后代码的 Worker。

如果自己设计简化计数器，不能只写“计数减到 0 就继续”：必须防止生产者还没登记完任务时提前归零；新任务应先登记再发布；后续计算只能恢复一次；子任务的结果需要对后续可见。实际 Cilk 会使用更具体的栈帧、描述符和偷取管理，不是给一个普通整数加减就完成实现。

### 12.4 运行时结束检测也要区分就绪与未完成

一个 Worker 本地队列空，不代表全系统没有工作；全系统 Ready 队列此刻空，也不代表没有正在运行或尚待依赖的工作。错误的结束检测可能丢任务，错误的 sync 可能提前读取结果。

这正是工作窃取比“从别人队列拿一项”复杂的地方：取任务策略、依赖正确性、内存可见性和整体生命周期，必须一起成立。

## 13. 无需 GPU 的 Python 调度模型

### 13.1 模型覆盖什么？

下面的程序只依赖 Python 3 标准库。它在抽象时间单位中复算连续/循环分配、动态队列长尾、DAG 就绪性，并用多个 Deque 的串行事件轨迹验证区间分裂和偷取后的索引覆盖。

这是单进程确定性模拟，不是真实多线程运行时；偷取轨迹按固定顺序找候选者，**没有实现随机工作窃取定理所分析的调度器，也不能验证其性能保证**。它只让你看清队尾本地取、队首远端取与任务覆盖关系。

保存为 `scheduling_models.py`：

```python
"""Deterministic scheduling exercises; all times are abstract cost units."""
from collections import deque
from heapq import heappop, heappush


def static_loads(costs, workers, cyclic=False):
    groups = [list(range(p, len(costs), workers)) if cyclic else
              list(range(p*len(costs)//workers, (p+1)*len(costs)//workers))
              for p in range(workers)]
    assert sorted(i for g in groups for i in g) == list(range(len(costs)))
    return [sum(costs[i] for i in g) for g in groups]


def dynamic(costs, workers, chunk=1):
    ready = [(0, p) for p in range(workers)]
    visited = []
    while len(visited) < len(costs):
        start = len(visited)
        end = min(start+chunk, len(costs))
        time, p = heappop(ready)
        visited.extend(range(start, end))
        heappush(ready, (time+sum(costs[start:end]), p))
    assert visited == list(range(len(costs)))
    return max(time for time, _ in ready)


def dag_schedule(durations, parents, workers):
    pending = set(durations)
    done = set()
    running = []
    now = 0
    order = []
    while pending or running:
        for task in sorted(pending):
            if len(running) == workers:
                break
            if set(parents[task]) <= done:
                pending.remove(task)
                order.append((task, now))
                heappush(running, (now+durations[task], task))
        if not running:
            raise ValueError('Cycle or unsatisfied dependency')
        now = running[0][0]
        while running and running[0][0] == now:
            _, task = heappop(running)
            done.add(task)
    return now, order


def steal_trace(n, workers, cutoff):
    queues = [deque() for _ in range(workers)]
    queues[0].append((0, n))
    visits = []
    steals = 0
    while any(queues):
        for p in range(workers):
            if queues[p]:
                lo, hi = queues[p].pop()
            else:
                victim = next((q for q in range(workers) if queues[q]), None)
                if victim is None:
                    continue
                lo, hi = queues[victim].popleft()
                steals += 1
            if hi-lo <= cutoff:
                visits.extend(range(lo, hi))
            else:
                mid = lo+(hi-lo)//2
                queues[p].append((mid, hi))
                queues[p].append((lo, mid))
    assert sorted(visits) == list(range(n))
    return steals


def check_buffer_reuse():
    # After barrier t-1, nobody still needs to read the sum from t-2.
    for t in range(1, 20):
        assert (t+1) % 3 != (t-1) % 3
        assert (t+1) % 2 == (t-1) % 2


def main():
    costs = [9]*4 + [1]*12
    block = static_loads(costs, 4)
    cyclic = static_loads(costs, 4, True)
    assert block == [36, 4, 4, 4]
    assert cyclic == [12]*4
    print(f'static_block={block} static_cyclic={cyclic}')
    tail = [1]*15 + [13]
    late = dynamic(tail, 4)
    early = dynamic(sorted(tail, reverse=True), 4)
    assert (late, early) == (16, 13)
    print(f'long_task_last={late} long_task_first={early}')
    durations = dict(A=2, B=3, C=5, D=1)
    parents = dict(A=[], B=['A'], C=['A'], D=['B', 'C'])
    assert dag_schedule(durations, parents, 1)[0] == 11
    assert dag_schedule(durations, parents, 2)[0] == 8
    print('dag_work=11 dag_span=8 two_worker_time=8')
    try:
        dag_schedule(dict(A=1, B=1), dict(A=['B'], B=['A']), 2)
    except ValueError:
        pass
    else:
        raise AssertionError('Cycle was not detected')
    for n in [0, 1, 3, 19, 32, 257]:
        for p in [1, 2, 4, 8]:
            for chunk in [1, 4, 16]:
                assert dynamic([1]*n, p, chunk) >= n/p
                steal_trace(n, p, chunk)
    example_steals = steal_trace(32, 4, 4)
    assert example_steals > 0
    print('steal_trace_coverage=pass cycle_detection=pass')
    check_buffer_reuse()
    print('buffer_slot_arithmetic=pass all_checks=pass')


if __name__ == '__main__':
    main()
```

从仓库根目录运行：

```bash
python3 labs/lecture05/scheduling_models.py
```

预期输出：

```text
static_block=[36, 4, 4, 4] static_cyclic=[12, 12, 12, 12]
long_task_last=16 long_task_first=13
dag_work=11 dag_span=8 two_worker_time=8
steal_trace_coverage=pass cycle_detection=pass
buffer_slot_arithmetic=pass all_checks=pass
```

`dynamic` 用一个最小堆记录各 Worker 的下一次空闲时间，始终给最早空闲的人下一块任务。没有加入领取开销，所以它不能用来证明小块永远更好。

`dag_schedule` 只有在所有前驱出现在 done 集合后才安排节点；遇到无人运行却仍有待定节点的状态会报错。在这个没有外部事件的固定图模型中，它可以识别环或未满足的依赖。

`steal_trace` 把 [lo,hi) 分成 [lo,mid)、[mid,hi)，最后将访问下标排序并对照完整范围，检查没有遗漏或重复。它不包含实际排序的 Partition 成本，也不实现同步点计数，所以不应把它当成真实 Cilk 性能模拟。

## 14. C++17 实验：相同计算，三种实际分配

### 14.1 工作负载和验证目标

这个独立实验给前四分之一输入设置较长的内部循环，其余输入循环较短，比较连续分块、循环分配与共享原子计数器的动态分块。

Payload（实际任务计算体）是由无符号 64-bit 整数构成的确定性运算。无符号溢出按模运算定义，不依赖有符号整数溢出的未定义行为。每项结果与串行参考答案逐项比较，防止只看时间却算错结果。

程序没有用 `sleep` 假装 CPU 计算，也没有把 Python 线程的解释器行为当成 CPU 并行结论。它确实创建 C++ 工作线程，但并未固定它们绑定到哪些物理 Core。

### 14.2 完整代码

保存为 `scheduling.cpp`：

```cpp
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;
struct Stats {
    std::uint64_t iterations = 0;
    std::size_t tasks = 0, claims = 0;
    double task_ms = 0;
};

enum class Policy { block, cyclic, dynamic };

std::uint64_t payload(std::size_t i, unsigned rounds) {
    std::uint64_t value = i + 1;
    for (unsigned k = 0; k < rounds; ++k) {
        value ^= value >> 13;
        value *= UINT64_C(0x9e3779b97f4a7c15);
        value += k;
    }
    return value;
}

void run(std::size_t n, unsigned workers, std::size_t chunk,
         Policy policy, bool verify_only) {
    std::vector<unsigned> rounds(n, 4000);
    for (std::size_t i = 0; i < n/4; ++i) rounds[i] = 120000;
    std::vector<std::uint64_t> reference(n), result(n);
    for (std::size_t i = 0; i < n; ++i)
        reference[i] = payload(i, rounds[i]);
    std::vector<std::atomic<unsigned>> visits(n);
    for (auto& item : visits) item.store(0);
    std::vector<Stats> stats(workers);
    std::atomic<std::size_t> next{0};
    auto started = Clock::now();
    auto work = [&](unsigned p) {
        auto execute = [&](std::size_t i) {
            auto begin = Clock::now();
            result[i] = payload(i, rounds[i]);
            stats[p].task_ms += std::chrono::duration<double, std::milli>(
                Clock::now()-begin).count();
            stats[p].iterations += rounds[i];
            ++stats[p].tasks;
            if (verify_only) visits[i].fetch_add(1, std::memory_order_relaxed);
        };
        if (policy == Policy::block) {
            for (std::size_t i = p*n/workers; i < (p+1)*n/workers; ++i)
                execute(i);
        } else if (policy == Policy::cyclic) {
            for (std::size_t i = p; i < n; i += workers) execute(i);
        } else {
            for (;;) {
                auto begin = next.fetch_add(chunk, std::memory_order_relaxed);
                ++stats[p].claims;
                if (begin >= n) break;
                auto end = std::min(begin+chunk, n);
                for (auto i = begin; i < end; ++i) execute(i);
            }
        }
    };
    std::vector<std::thread> pool;
    for (unsigned p = 1; p < workers; ++p) pool.emplace_back(work, p);
    work(0);
    for (auto& thread : pool) thread.join();
    double elapsed = std::chrono::duration<double, std::milli>(
        Clock::now()-started).count();
    if (result != reference) throw std::runtime_error("Wrong output");
    std::size_t tasks = 0, claims = 0;
    for (auto& item : stats) { tasks += item.tasks; claims += item.claims; }
    if (tasks != n) throw std::runtime_error("Wrong task count");
    if (verify_only) {
        for (auto& item : visits)
            if (item.load() != 1) throw std::runtime_error("Repeated/missing task");
    }
    if (policy == Policy::dynamic && claims != (n+chunk-1)/chunk+workers)
        throw std::runtime_error("Wrong claim count");
    if (!verify_only) {
        const char* label = policy == Policy::block ? "block" :
                            policy == Policy::cyclic ? "cyclic" : "dynamic";
        std::cout << label << " chunk=" << chunk << " wall_ms=" << elapsed
                  << " claims=" << claims << " correct=yes\n";
        for (unsigned p = 0; p < workers; ++p)
            std::cout << "  worker=" << p << " tasks=" << stats[p].tasks
                      << " iterations=" << stats[p].iterations
                      << " task_ms=" << stats[p].task_ms << '\n';
    }
}

int main(int argc, char** argv) {
    try {
        std::cout << std::fixed << std::setprecision(3);
        if (argc > 1 && std::string(argv[1]) == "--check") {
            for (std::size_t n : {0, 1, 3, 19, 128, 257})
                for (unsigned p : {1, 2, 4}) {
                    run(n, p, 1, Policy::block, true);
                    run(n, p, 1, Policy::cyclic, true);
                    for (std::size_t chunk : {1, 4, 16, 64})
                        run(n, p, chunk, Policy::dynamic, true);
                }
            std::cout << "cases=108 exact_once=pass outputs=pass all_checks=pass\n";
        } else {
            unsigned p = argc > 1 ? std::stoul(argv[1]) : 4;
            if (p < 1 || p > 64) throw std::runtime_error("workers must be 1..64");
            run(128, p, 1, Policy::block, false);
            run(128, p, 1, Policy::cyclic, false);
            for (std::size_t chunk : {1, 4, 16, 64})
                run(128, p, chunk, Policy::dynamic, false);
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
```

### 14.3 怎样编译与运行？

需要 C++17 工具链。macOS Apple Silicon 和常见 Linux 环境都可用标准线程版本，不需要 OpenCilk 或 NVIDIA GPU。本次已在 macOS ARM64、Apple Clang 16 上实际编译运行。

从仓库根目录执行：

```bash
mkdir -p /tmp/cs149-l05-build
c++ -O2 -std=c++17 -pthread labs/lecture05/scheduling.cpp \
  -o /tmp/cs149-l05-build/scheduling
/tmp/cs149-l05-build/scheduling --check
/tmp/cs149-l05-build/scheduling 4
```

正确性检查的固定输出为：

```text
cases=108 exact_once=pass outputs=pass all_checks=pass
```

108 个组合来自 6 种规模、3 种 Worker 数和 6 种分配配置；包括 N=0、N<P、非整除尾部、块长大于 N。验证模式用原子访问计数记录每项被执行的次数；观察模式关闭这项逐元素计数，避免把验证开销误作调度成本。

普通运行报告 `wall_ms` 和每个 Worker 的 `tasks`、`iterations`、`task_ms`。具体时间会随硬件、系统负载和线程安排变化，不规定一个必须达到的加速比。

### 14.4 正确性的关键在哪里？

连续分块的区间首尾相接；循环分配按下标对 P 取余划分；动态分块则通过 `fetch_add` 取得互不重叠的块起点，再用 min 截住数组末尾。

`memory_order_relaxed` 在这里仅用于唯一领取编号：输入已在线程启动前初始化，结果写入互不重叠元素，主线程在 `join` 之后才检查结果。它不用于发布新任务或告知另一个 Worker 现在可以读取结果，不能把这一内存顺序照搬到依赖任务系统。

每个 Worker 只修改自己的一份 Stats。主线程等待全部 Worker 完成后再汇总，避免边写边读的统计竞争。结果数组是普通整数元素，不使用可能把多个布尔元素压在同一存储字中的 `vector<bool>`。

### 14.5 可以从结果中复算什么？

默认 N=128、P=4。前 32 项各执行 120000 次内部循环，后 96 项各执行 4000 次：

| 方案 | 每 Worker 的内部循环次数（理想归属） |
| --- | --- |
| 连续分块 | 3840000、128000、128000、128000 |
| 循环分配 | 每人 1056000 |
| 动态小块 | 每人根据实际完成速度领取，归属不固定 |
| 动态块长 64 | 只有两个有用块，最多给两个 Worker 有用任务 |

这些次数可由源码复算，不是时间预测。循环中的指令依赖、Core 性能和系统调度仍影响耗时。

对动态方案，有用领取数是 ceil(N/g)。每个 Worker 最后还要各领取一次越界编号才知道退出，所以本实验报告的总领取数为：

$$
\operatorname{claims}=\left\lceil\frac{N}{g}\right\rceil+P
$$

N=128、P=4 时，g=1、4、16、64 对应 132、36、12、6 次领取。它解释了管理次数如何下降，也解释了为什么“大块让队列更便宜”并不保证完成时间更短。

### 14.6 怎样把观察扩展成可信 Benchmark？

先检查输出，再预热和重复测量，报告中位数，并记录 CPU、操作系统、编译器、线程数和输入分布。若做参数比较，应保持相同数学任务、相同输入与相同计时边界。

这个程序每轮重新创建线程，也逐任务读时钟；用于教学时这能显示可观察行为，但对于非常短的任务会有明显额外扰动。更严肃的实验可以另做常驻线程池、批量计时或低扰动采样，并明确新计时边界。

本次 4 Worker 的运行中，连续分块明显有一个 Worker 负担更多；动态块长 64 只有两块，两个 Worker 没领到任务。小块和循环分配都获得了更均衡的工作量。但这只是本机该工作负载的观察，不发布固定速度倍数，也没有测试真正的 Cilk 工作窃取。

## 15. 练习与参考答案

### 练习 1：相等的任务数为何可能很差？

四个 Worker 分别拿到工作量 [2,2,2,10]，假设同速、同时开始、无额外开销。总工作、完成时间和理想负载效率分别是多少？

**答：** 总工作 16，完成时间 10；效率 16/(4×10)=40%。如果各块不可再分，增加领取策略不会自动拆开那个 10。

### 练习 2：写一个使循环分配失衡的输入

N=12、P=3，构造任务成本使 Worker 0 在循环分配下拿到全部重任务。

**答：** 令下标 0、3、6、9 的成本为 10，其余为 1。循环分配的三份工作量是 [40,4,4]。这说明轮流分配依赖成本分布，不能当作无条件的平衡保证。

### 练习 3：块长和领取次数

N=103、P=4、g=10，最后一个有用区间是什么？按照本章 C++ 程序，总领取次数是多少？

**答：** [100,103)，共 ceil(103/10)=11 个有用块，另有 4 个 Worker 各一次退出领取，总共 15 次。块内应使用当前循环下标，不能总写第 100 项。

### 练习 4：粒度的反例

8 个 Worker、N=100，若把 g 设为 100，是否能因领取只有一次而获得最佳性能？

**答：** 不能。有用工作只有一块，只有一个 Worker 能做；其余 Worker 很快退出。管理开销虽低，却失去了任务并行机会。

### 练习 5：DAG 的最短时间

A 成本 4；B、C 都依赖 A，成本分别为 2、6；D 成本 3，依赖 B、C。T₁、T∞ 是多少？两 Worker 能达到什么时间？

**答：** T₁=15，T∞=4+6+3=13。两 Worker 从 0–4 做 A，4–6 做 B、4–10 做 C，10–13 做 D，总长 13，达到下界。

### 练习 6：串行结果正确，能证明并行安全吗？

两个被 spawn 的函数都执行共享普通整数 `sum += 1`，删除 spawn 后得到 2。能否据此宣布原程序正确？

**答：** 不能。两个并发读改写可能互相覆盖，串行投影没有暴露竞争。需要独立结果后归约，或适合该语义的同步机制。

### 练习 7：为什么从队首偷？

某个递归 Worker 先留下大小约 1000 的后续子树，再留下大小约 500、250 的子树。自己通常拿哪项，偷取者通常拿哪项？这是不是每次都选择最贵任务的算法？

**答：** 本地从队尾取最近的约 250，偷取者从队首取较早的约 1000。策略利用常见递归结构，不是精确成本排序；不规则子树的实际成本可能不按规模单调变化。

### 练习 8：Worker 时间能否直接从总时间中扣除？

程序墙钟 3 秒，4 个 Worker 各报告任务累计 2.5 秒。是否说明开销为 3−10=−7 秒？

**答：** 不是。同一墙钟区间内不同 Worker 可以同时工作，累计任务时间是 10 Worker-秒。若所有 Worker 在同样 3 秒窗口内可用，可把 10 与 4×3=12 Worker-秒容量比较，但余下 2 Worker-秒也不能全部归因为锁。

### 练习 9：快排的关键路径

每次串行 Partition 成本为 n，左右规模各为 n/2，其他开销忽略。为什么关键路径不是 log₂n？

**答：** 关键路径经过一个规模 n 的划分、一个 n/2 的划分、一个 n/4 的划分等，成本为 n+n/2+n/4+…=Θ(n)。log₂n 只是层数，不是总时间。

### 练习 10：随机窃取的保证是什么？

能否引用期望 O(T₁/P+T∞) 直接保证含长时间网络阻塞、异构 Worker 和截止时间约束的任务系统永远接近最优？

**答：** 不能。应核对计算结构、处理器与调度成本假设，以及结果是期望而非每次保证。还要单独建模阻塞、异构资源和服务质量目标。

### 练习 11：为什么两个轮次槽位可能不够？

快线程进入轮次 t，准备清零下一轮 t+1 的槽位；慢线程还在读取 t−1 的结果。两个槽位与三个槽位分别会怎样？

**答：** 模 2 下 t+1 与 t−1 同槽，会覆盖；模 3 下不同槽。三槽协议仍须按第 2 节安排屏障与清零，不能只增加槽位就删除所有同步。

### 练习 12：最简单的改进实验

已知某静态方案分配不均，你会先写完整工作窃取运行时吗？

**参考答案：** 先比较连续分块、循环分配与共享计数器的动态块，测工作量分布、墙钟与管理次数，再扫描块长。只有共享队列竞争或递归工作分布确实成为瓶颈，才有证据考虑更复杂的运行时或现成库。

## 16. 面向 AI Infrastructure 的联系（课外延伸）

**请求长度不等。** 给每个 Worker 一样多的请求，不代表一样多的 Token 计算或服务时间。预测长度、动态分配和批处理都可以改善负载，但实际服务系统还要考虑等待时间、公平性和截止目标。

**预处理与数据加载。** 文件大小、解码复杂度和样本形状可能不一致。固定线程池加合适粒度的任务是一种基线；把每个像素拆成一个任务通常会把管理成本放大。

**计算图依赖。** 后继算子不能仅因已经提交就执行，必须等输入结果就绪。设备上的异步执行、流与事件还有各自的完成语义，不能把 CPU 入队完成误认为设备计算完成。

**多级资源。** CPU Worker、CPU SIMD Lane、GPU Block 和分布式节点是不同分配层次。一个层次的“任务数更多”可能在另一个层次引入开销或通信；需要明确正在平衡什么资源。

这些是作者结合本讲思想作的迁移说明，不代表 2023 年课堂逐项讨论了当前推理系统的具体实现。

## 17. 来源、修正与核验范围

| 来源 | 范围 | 状态 |
| --- | --- | --- |
| [Stanford 第 5 讲页面](https://gfxcourses.stanford.edu/cs149/fall23/lecture/perfopt1/) | 官方课次和讲题 | 已核对 |
| [官方 62 页 Slides](https://gfxcourses.stanford.edu/cs149/fall23content/media/perfopt1/05_progperf1.pdf) | 第 2–21 页分配与粒度；第 22–33 页 Fork-Join；第 34–49 页 Child/Continuation 与窃取；第 50–62 页 sync 与总结 | 已核对文字结构，抽查第 4、14、29、44、49、60 页图示，未逐页视觉复核 |
| 用户提供自动英文文字稿 | 开场轮次变量复用，到 Greedy Join 结尾 | 全文已阅读，无时间码，未逐句音频核验 |
| [第 5 讲录像](https://www.youtube.com/watch?v=mmO2Ri_dJkk) | 对应课程录像 | 未编造时间点，未逐句校对音频 |
| [OpenCilk 并行任务教程](https://www.opencilk.org/doc/tutorials/introduction-to-cilk-programming/) | spawn、作用域和逻辑并行 | 对照现代文档，区分历史 Cilk Plus 课堂代码 |
| [OpenCilk 工作窃取说明](https://www.opencilk.org/doc/reference/glossary/work-stealing/) | Worker 与窃取概念 | 术语参考 |
| [Blumofe 与 Leiserson 的原始论文](https://www.cs.cornell.edu/courses/cs612/2006sp/papers/blumofe94.pdf) | Fully Strict 计算的随机工作窃取分析 | 用于限定理论结果适用范围，不把定理扩展到任意任务系统 |
| [OpenCilk 安装说明](https://www.opencilk.org/doc/users-guide/install/) | 当前工具链与平台要求 | 供有需要者选读；本章实际实验无需安装 OpenCilk |

开场的三屏障与多版本 diff 是对上一讲的回顾，不给它虚构本讲 PDF 页码。三槽位时序、模型定义、Work/Span 展开、时间统计口径和全部练习均为作者独立教学补充。

修正的示意问题包括：第 14 页块内下标应使用循环变量；第 49 页中点应包含区间起点；快排示意中的 `last`/`end` 命名要一致。教材不将课件片段直接包装为可编译实现。

Python 模型已运行，覆盖空输入、非整除块、依赖环与区间偷取轨迹；C++17 程序已在 macOS ARM64、Apple Clang 16 编译执行，通过 108 种正确性组合，另运行 4 Worker 观察模式。未编译运行 Cilk 程序、未实现无锁 Deque、未做 GPU 或分布式调度性能验证。

更细的记录见 [Lecture 05 来源核验](../sources/lecture-05-audit.md)。公开仓库只提交原创教材、实验和来源链接，不上传完整自动字幕、官方课件或第三方编译器。

读完本章，你应能把一次调度选择解释成三件具体的事：它减少了哪些空闲、增加了哪些管理或通信、是否仍满足所有数据依赖。每一个性能判断都应能回到这三件事上验证。
