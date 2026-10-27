# 第 6 章：局部性、通信与竞争

> Stanford CS149 · Fall 2023 · Lecture 6 — Performance Optimization II: Locality, Communication, and Contention
>
> **状态：自包含中文教材，第一版。** 结合用户提供的英文自动转写与官方 69 页 Slides，独立编写解释、推导和实验。文字稿已阅读全文，无时间码，含听不清和术语误识别；尚未与音频逐句核验。已核对课件文字结构并抽查关键图页，未完成每页的视觉复核。本文不是官方授权教材或逐字翻译。

**先修知识：** 数组、循环、函数与基本 C++ 语法；知道程序需要读取输入并写出结果。本章重新解释缓存、地址空间、消息、红黑更新和性能单位，不要求先读其他章节，也不要求有 GPU 或集群。

**学习时间：** 阅读与纸笔计算约 2–3 小时，运行模型和 CPU 实验约 1 小时。

**配套实验：** [第六章完整代码与说明](../labs/lecture06/README.md)。两份程序的完整代码也收录于本章；来源与验证范围列于章末。

## 0. 工作分得一样多，为什么仍然很慢？

设 16 个 Worker 每人更新同样多的网格点。一种分工让邻居数据几乎都在自己手里，另一种分工让每处理一行都要向别人索取两行。两者负载完全均衡，数据搬运量却可能相差几十倍。

同样，即使只有一个线程，同一个矩阵也可能因遍历顺序不同而反复从内存读取。增加线程无法自动消除这些重复搬运，反而可能让多个线程争抢同一个内存接口。

本章沿着三条问题展开：**数据要从哪里来、必须搬多少、什么时候搬？** 最后用 Roofline 把计算量与通信量合成一个可以复算的性能上界。

## 1. 共享地址空间没有消除通信

### 1.1 一条 load 指令背后的路径

**地址空间**是程序能用地址标识的一组存储位置。共享地址空间模型让多个线程可以引用同一个数组元素，但“都能访问”不等于“访问成本一样”。

CPU 的寄存器直接供指令使用；**Cache（缓存）**保存一部分近期访问过的数据；**DRAM（主存）**容量较大，通常离计算核心更远。缓存常按固定大小的 **Cache Line（缓存行）**搬运数据。一次读取若没有在某级缓存中找到相应行，称为该级 Cache Miss。

下面是概念路径，不保证每台处理器都严格串行经过每一步：

```text
Core 请求地址 X
  ├─ 本地 L1 命中 → 取到数据
  └─ 未命中 → 更远缓存 / 片上互连
                 ├─ 某个缓存副本可提供数据
                 └─ 内存控制器 → DRAM → 数据返回
```

**缓存一致性**解决多个缓存副本之间的协调问题；它并不让所有访问都变成零成本，也不能替代程序需要的同步。共享变量上的并发访问是否正确，与硬件怎样搬运缓存行，是两个层次的问题。

### 1.2 NUMA：同一个地址，从不同位置访问

**NUMA（非均匀内存访问）**强调访问成本依赖执行位置与数据位置。在一个双 CPU 插槽的教学例子中，某块内存连接在插槽 A 的控制器上。A 上的 Core 可以走本地路径；B 上的 Core 可能要先经过插槽间互连。

因此决定性能的不只是“命中缓存了吗”，还可能包括：哪个缓存切片、哪个内存节点、走哪条链路，以及其他请求是否正在占用它。一个插槽内部也可能有距离差异，但不要把这种差异直接等同于操作系统一定暴露了多个 NUMA 节点。

课件用历史 Intel 环形互连与 UltraSPARC 交叉开关说明互连的面积和复杂度。它们是具体架构示例，不能推成“今天所有 Intel CPU 都使用同一种环”或“任意交叉开关都把每对 Core 直接接线”。交叉开关连接哪些端口，取决于具体实现。

### 1.3 编程模型与实现可以交叉组合

| 层次 | 需要回答的问题 | 示例 |
| --- | --- | --- |
| 编程模型 | 程序如何表达通信？ | 读写共享数组；发送和接收消息 |
| 运行时实现 | 如何搬运与同步？ | 本机队列、共享内存通道、网络传输 |
| 硬件 | 数据实际走哪里？ | Cache、片上网络、DRAM、网卡 |

可以在一台共享内存机器上使用消息传递，也可以在消息传递的 Worker 中使用本地线程。工作队列解决“谁做哪项任务”，消息传递解决“如何交换信息”，二者可以组合。

## 2. 消息传递：把隐含的数据移动写出来

### 2.1 私有地址空间与消息匹配

本章的纯消息模型中，每个参与者拥有自己的数组，不能直接读取另一个参与者的私有数组。这里称参与者为 **Rank**，只表示编号，不保证它对应一个物理 Core。

发送方给出本地缓冲区、接收方和消息标记 Tag；接收方给出来源、Tag 与接收缓冲区。相同数值的指针在两个进程里不必表示同一份数据。

```text
Rank 0 私有数组 A           Rank 1 私有数组 B
A[3] = 7
  └─ 发送 {目标=1, tag=边界, 数据=7} ─→ 接收匹配消息 → B[0] = 7
```

消息传递仍可能在运行时内部使用锁；“没有共享应用数据需要加锁”并不意味着整个系统实现里没有锁。应用的等待关系则显式体现在消息协议中。

### 2.2 阻塞、同步模式与完成不是一个词

课件定义了一个简化的会合协议：发送必须等到接收方拿到数据并返回确认，发送调用才返回。本章的死锁模型使用这一语义。

实际 MPI 要分别看两个维度：调用是否阻塞，以及使用哪一种发送模式。

| 接口或模型 | 调用返回／请求完成能说明什么？ |
| --- | --- |
| 本章简化的会合发送 | 匹配接收已发生，数据已交付，发送返回 |
| MPI 标准模式的阻塞 `MPI_Send` | 发送缓冲区可复用；数据可能仍在系统缓冲区中 |
| MPI 同步模式的阻塞 `MPI_Ssend` | 发送缓冲区可复用，匹配接收已启动并开始接收 |
| MPI 非阻塞 `MPI_Isend` | 启动操作并返回请求；此时缓冲区尚不一定可复用 |
| 非阻塞接收请求完成 | 接收数据可由应用访问 |

不能把 `MPI_Send` 返回解释成对端程序已经处理完消息；也不能把 MPI 同步发送完成解释成对端应用一定已从接收调用返回。正确的标准模式 MPI 程序不能依赖“系统总会替我缓冲消息”来保证不死锁。

### 2.3 两个人都先发送，为什么会卡住？

假设两边都执行“发送给对方；接收对方消息”，并且发送必须等待匹配接收：

```text
Rank 0: send(1) ──等待 Rank 1 的 receive
Rank 1: send(0) ──等待 Rank 0 的 receive

双方都无法走到下一条 receive → 死锁
```

这不是发送速度慢，而是没有任何可推进的操作。缓冲实现可能让小消息偶然通过，却在大消息时卡住；这类偶然成功不能证明协议正确。

### 2.4 一个可逐步检查的奇偶协议

把 Rank 排成没有首尾环接的一条链。缺少的邻居操作直接跳过：

| Rank | 与邻居通信的顺序 |
| --- | --- |
| 偶数 r | 向 r+1 发送并接收；再向 r−1 发送并接收 |
| 奇数 r | 从 r−1 接收并回复；再从 r+1 接收并回复 |

第一批边是 (0,1)、(2,3)、(4,5)，各对内部一边发送、一边接收。完成后，下一批边 (1,2)、(3,4) 也能匹配。单个配对内，第一次传送结束后双方反向操作，所以也不会双双发送。

这份论证针对上述链与具体调用次序。换成环、增加其他消息或改变顺序，都需要重新检查。MPI 的 `Sendrecv` 把发送与接收合在一次调用中，可用于邻居移位；它同样要求来源、目标、Tag 和缓冲区正确。

### 2.5 非阻塞通信把责任移到了缓冲区生命周期

非阻塞操作把“启动”和“完成”分开。请求句柄是之后等待或查询状态的凭证。

```text
启动接收 → 得到请求 R
启动发送 → 得到请求 S
执行不依赖这些缓冲区的工作
等待 R 完成 → 可以读接收内容
等待 S 完成 → 可以改写或释放发送缓冲区
```

发送前填好的数组，在发送请求完成前不能改写或释放；接收缓冲区在接收完成前不能由应用访问。把数组指针交给网卡以减少 CPU 拷贝，也不会取消这个要求。

还要匹配每条消息的来源、阶段和数据类型。异步本身不保证任意顺序都正确，也不保证所有库都让通信自动在后台取得进展。本章不把课堂抽象中的“消息可能乱序”当作 MPI 的完整排序规范。

## 3. 幽灵行：在本地保存远端邻居的副本

### 3.1 定义一个完整的红黑网格问题

内部有 N×N 个点，外圈固定，实际数组为 (N+2)×(N+2)。内部行列编号均为 1…N；第 0 行全为 1，其余边界为 0（上方两角随第 0 行为 1）。初始内部为 0。

每个点按下面规则原地更新：

$$
u_{i,j}\leftarrow 0.2\left(u_{i,j}+u_{i-1,j}+u_{i+1,j}+u_{i,j-1}+u_{i,j+1}\right)
$$

包含自身旧值与四邻居，共五项。颜色由 (i+j) mod 2 定义：先更新颜色 0，再更新颜色 1，合起来为一个完整 Sweep。四个直接邻居均为另一种颜色，因此同色阶段中各点不互相读取正在被修改的点。

这与按行从上到下逐点更新的算法不逐轮相同；不能只改变通信，就声称保留了任意原地算法的每一步结果。

### 3.2 全局行号与本地行号

将内部行连续分给 P 个 Rank，要求 1≤P≤N，以保证每人至少一行。令：

$$
\ell_r=\left\lfloor\frac{rN}{P}\right\rfloor,\quad h_r=\left\lfloor\frac{(r+1)N}{P}\right\rfloor-\ell_r
$$

Rank r 拥有全局行 ℓr+1…ℓr+hr，本地数组有 hr+2 行，每行 N+2 项。本地行 i 对应全局行 ℓr+i；本地行 0 和 hr+1 保存上、下邻居副本，叫 **Ghost Rows／Halo（幽灵行／晕区）**。

以 N=8、P=2 为例：

```text
Rank 0 本地行              Rank 1 本地行
0: 固定上边界              0: 全局行 4 的副本
1..4: 全局行 1..4          1..4: 全局行 5..8
5: 全局行 5 的副本          5: 固定下边界

Rank 0 最后一条拥有行 ─→ Rank 1 上幽灵行
Rank 1 第一条拥有行   ─→ Rank 0 下幽灵行
```

幽灵行只是副本，不由本地 Rank 更新成自己的新解。全局最上、最下 Rank 的外侧行是物理边界，必须初始化，不能以“没有接收消息”为理由留下未初始化数据。

### 3.3 每个颜色阶段前交换，保持数据版本正确

一个直接、容易验证的实现是：

1. 交换当前拥有区域的首行和末行，完成所有接收。
2. 更新颜色 0，只写自己拥有的点。
3. 再交换边界行，确保收到颜色 0 的新值。
4. 更新颜色 1，只写自己拥有的点。
5. 若要继续迭代，下一轮步骤 1 会传递颜色 1 的新值。

颜色判断必须使用全局行号 `(ℓr+i+j)%2`。如果仅用本地 `(i+j)%2`，当 ℓr 为奇数时就会把该 Rank 的颜色反过来。

为了协议简单，每次发送整行 N+2 项，包括边界列与当前并不全需要的另一种颜色。若只打包有用颜色可以减少载荷，但增加了打包和索引成本；不能一边发送整行，一边按半行字节量报告实测。

对于 N=8、P=2，一次交换有两个方向，各 10 项，共 20 项；一轮有两次交换，共 40 项。本章模型逐颜色与串行红黑参考解比较，验证每次交换得到的版本确实正确。

### 3.4 收敛判断是另一条通信依赖

若以所有更新的绝对变化量之和 diff 除以 N² 判断停止，每个 Rank 先计算自己的局部和，再归约到一个 Rank。归约者收到全部 P−1 份结果后决定是否结束，并把决定发送给所有人。

没有显式 `barrier()` 不代表没有同步：等局部和、等停止消息已经构成等待关系。但这不是说消息传递所有通信都天然等价于全局屏障；邻居交换只约束相关的参与者。

实际可用树形归约或集体通信，避免全部请求同时挤到一个根节点。还需约定最大轮数、停止条件和异常处理。本章的幽灵行程序执行固定轮数，用来隔离通信语义；它不实现 MPI 收敛协议或容错系统。

### 3.5 为什么没有直接照抄课件伪代码？

课件第 19、23 页用于展示消息结构，但有省略与笔误：归约/广播循环漏掉最后一个 Rank；局部行循环边界前后不一致；变量名和消息名存在拼写问题；代码没有完整表达红黑两阶段。

教材采用明确边界、非整除行分配、全局着色、两次 Halo 交换和独立参考解。若 P>N，应使用活跃 Rank 子通信域或定义空分块转发协议；本实验明确排除它，不能直接向“空块的首行”发消息。

## 4. 通信成本：延迟、带宽、重叠

### 4.1 一条消息的简化模型

令 α 为每条消息的固定启动成本，单位秒；q 为载荷字节数；B 为持续传输带宽，单位 byte/s。无排队、无重叠的近似为：

$$
T_{\mathrm{msg}}\approx\alpha+\frac{q}{B}
$$

例如 α=5 μs、B=10 GB/s，采用十进制 GB。发送 1000 条各 1024 byte 的消息，若必须逐条串行，约需 5000+102.4=5102.4 μs；合成一条同样总载荷的消息，约需 5+102.4=107.4 μs。

这说明摊薄启动成本的潜力，不是任何网络上的实测。消息若本来能够并行传输，或合并需要等待很久，实际收益会不同；实时请求还要计入组批等待延迟。

### 4.2 增加并发只能隐藏一部分延迟

**Latency**是一次访问完成要等多久；**Bandwidth**是稳态每秒能搬多少字节。设 L 为访问延迟，B 为目标带宽，要持续供给数据，系统需要大约 B×L 字节在途。

若 B=100 GB/s、L=100 ns，则 B×L=10000 byte。按 64 byte/请求估算，约需 157 个独立在途请求才能覆盖这个量级。它是平均流量模型，不是某台 CPU 一定具有的请求容量。

当独立请求足够多、传输通道已经持续繁忙时，进一步增加延迟未必降低稳态吞吐；一旦在途容量不足，就会产生传输空洞，延迟重新影响吞吐。课件流水图中的“只由带宽决定”必须带上足够并发和可隐藏延迟的前提。

### 4.3 用内部区域覆盖邻居交换

在网格中，距离分块边缘至少一行的内部点不需要新到达的幽灵行，可以先计算它们：启动边界接收和发送 → 计算本地内部 → 等待通信 → 计算依赖 Halo 的边界。

若独立计算耗时 Tc、通信耗时 Tm、不能重叠的边界工作 Tb，理想阶段时间从 Tc+Tm+Tb 降至 max(Tc,Tm)+Tb。启动、完成检查与资源竞争仍可能增加成本。

在红黑原地更新中还要特别留意：若异步发送直接引用整条拥有行，发送未完成前就更新该行的任一元素，会破坏发送缓冲区约束。可先完成发送再改边缘，或使用独立打包缓冲区。本章模型使用快照复制并完成交换后再更新，没有声称实现真实通信重叠。

## 5. 先分清“必须搬”与“实现额外搬”

**Inherent Communication（内在通信）**是给定算法与工作分配之后，为满足跨所有者数据依赖而必须进行的数据交换。改变分工会改变这个量，所以“内在”不表示无论怎么改程序都无法减少。

**Artifactual Communication（实现引入的额外通信）**来自有限缓存、传输粒度、写分配等机制。例如只用一个 4 byte 数却载入 64 byte 行，或刚用过的数据因缓存装不下而重新载入。

两者取决于分析层次。在 Rank 之间统计边界数据、在 L1 与 L2 之间统计缓存行、在 DRAM 接口统计总字节，是三种不同的问题。一个优化减少网络流量，不保证减少 DRAM 流量；后面的算术强度始终要注明分母所在层级。

## 6. 用区域形状减少跨 Worker 通信

### 6.1 保留常数，比较单个内部块

考虑 N×N 点、P 个 Worker，每人工作约 N²/P；每次交换只统计收到的边界元素，忽略物理边界、角点、消息头与颜色筛选。每个输出点工作相同，因此暂用“处理点数/接收元素数”比较通信效率，它还不是 FLOP/byte。

连续行条带厚度 N/P，内部 Worker 需上下各一行，收到约 2N 项。若逐行循环分配、相邻行属于不同 Worker（P>1），每人 N/P 行通常都需上下邻行，收到约 2N²/P 项。

二维划分令 P=s²，每人是边长 N/√P 的正方形，内部 Worker 从四边收到约 4N/√P 项。

| 分配 | 每人处理点数 | 每人收到元素数（内部块） | 点数/接收元素 |
| --- | --- | --- | --- |
| 连续行条带 | N²/P | 2N | N/(2P) |
| 循环交错行 | N²/P | 2N²/P | 1/2 |
| 二维方块 | N²/P | 4N/√P | N/(4√P) |

二维块改善的是随 P 增长的缩放关系；从这个表保留常数后，它相对条带的比率为 √P/2，不能把省略常数的 O(√P) 直接说成某个 P 下精确的速度提升。

### 6.2 总流量的精确例子

为了避免“内部块近似”与外边界混淆，另算有限正方形区域的总载荷。把网格分成 R 行、C 列矩形块，RC=P，每个内部界面交换双向数据，不发送四角：

$$
Q_{\mathrm{values}}=2N(R-1)+2N(C-1)
$$

解释：R−1 条横向切分线，每条长度 N，每个方向发一份；纵向 C−1 条线同理。这个 Q 是一次 Halo 交换的所有发送元素总数；同时又等于所有接收元素总数。不要再把发送加接收重复统计为链路载荷。

N=1024、P=16：

- 16×1 条带：Q=2×1024×15=30720 项。
- 4×4 方块：Q=2×1024×(3+3)=12288 项。
- 按 float32 算分别为 122880 与 49152 byte，有限区域总量比为 2.5。

这个精确比率不同于单个内部块的近似比率，原因是边缘 Worker 没有四个邻居。也不同于省略常数后的 √P。

### 6.3 为什么正方形好，为什么也不一定最快？

若一个矩形块面积固定为 A=hw，周长是 2(h+w)。因为 (h−w)²≥0，可得 h+w≥2√(hw)，所以在矩形中 h=w 时周长最小。这说明就近邻通信量而言，应尽量避免细长块。

圆虽然在连续平面中有不同的等周性质，但规则网格要无缝划分、索引和打包，矩形通常更自然。任意 P 可选接近平方根的因数，非正方形全局网格还需按长宽比选择 R、C。

边界量少并不充分：二维分块增加邻居数；行主序数组的列边界可能需要打包或派生数据类型；不规则工作量又可能失衡。与大量小消息的启动成本结合后，最少字节的方案未必有最小墙钟时间。

## 7. 有限缓存：同一个数为什么读了又读？

### 7.1 空间局部性与时间局部性

**空间局部性**是访问相邻地址，使载入的一整行多数都被用到。**时间局部性**是在数据仍留在近处时再次使用它。

行主序二维数组的一行连续存储，但“按行连续访问”不能保证全部时间复用：计算下一行还需要上一行附近的数据。若整行很宽，回到左侧时，先前左侧的行可能已经被后面的访问挤走。

课件第 38–43 页用每缓存行 4 个网格元素、容量 6 行的理想图说明这一点。课堂的“每 4 个输出载入 3 行”与分块后“每 6 个输出载入 2 行”是特定示意下的稳态计数，不是任意缓存和数组宽度下的定律。

### 7.2 用可独立执行的小例子理解 LRU

本章采用 **LRU（最近最少使用淘汰）**模型：一次命中把该行标成最近使用，缓存满时淘汰最久没访问的一行。真实 CPU 不必实现精确 LRU。

若容量为两行，访问缓存行编号 `[0,1,2,0,1,2]`，每次都会 Miss，共 6 次；改为 `[0,0,1,1,2,2]`，则每行第二次都命中，共 3 次。访问的不同数据和次数都未变，改变的是重复使用间隔。

这不是说任意程序都能随便交换循环：必须先证明重排不违反依赖。

### 7.3 分块缩短复用距离

按窄列条带遍历：先在宽度 b 的一段列上完成多行，再移动到下一段列。与扫描完整宽行相比，相邻行所需的活跃数据范围更小，可能留在缓存中。

```text
完整行扫描：
第 1 行 [-------------------------------]
第 2 行 [-------------------------------]

列条带扫描：
          先处理这里       再处理这里
第 1 行 [------]         [------] ...
第 2 行 [------]         [------] ...
第 3 行 [------]         [------] ...
```

若一个数据窗口近似需要三段行、每段 b+2 个输入，粗略活跃输入量为 3(b+2)×元素字节数。实际还要为输出、行对齐、集合冲突和其他变量留空间。不能把这条粗略容量式当作精确 Miss 预测。

教材 Python 实验规定：N=30、物理行宽 N+2=32、每行 4 项、全相联 LRU 容量 6 行；只统计双缓冲五点模板的输入读取，输出假定独立缓存。完整行扫描有 720 次输入 Miss，列条带 b=4 有 480 次。b=1 反而有 1380 次，因此块越小并不总越好。此模型不包含输出写分配、硬件预取或真实 Cache 的相联度。

### 7.4 重排正确性的边界

双缓冲 **Jacobi** 从旧数组读，向独立新数组写；同一轮各输出独立，重排输出次序不会改变数学结果。红黑算法则可以重排同一颜色内部的点，但必须保留两颜色之间的依赖。

按行原地 Gauss-Seidel 依赖已更新的上方和左方，任意改成块内扫描可能改变迭代顺序。更不能在一个块里连续做好几轮，再不交换新边界就进入下一个块，并声称与原来逐轮同步相同。

本章 C++ 实验验证的是**空间分块的双缓冲 Jacobi**；Python Halo 实验验证的是**分布区域的红黑更新**。两者在代码、参考解和用途上分别说明，不混作相同算法的两种性能版本。

## 8. 循环融合：保留计算，减少中间数组

### 8.1 逐元素表达式的三次扫描

对互不重叠的 float32 数组计算 E=D+(A+B)×C。拆成三个全数组操作需要：tmp1=A+B，tmp2=tmp1×C，E=tmp2+D。

每项都是两次读、一次写，共 9 次标量访存；三次算术操作不变。若每次访存 4 byte，**逻辑流量**为 36 byte/元素，算术强度为 3/36=1/12 FLOP/byte。

融合成单循环，在一个元素上连续完成整条表达式，读取 A、B、C、D，写 E，逻辑流量为 20 byte/元素；算术强度为 3/20=0.15 FLOP/byte。

| 实现 | 算术操作/元素 | 读写标量次数 | 逻辑 byte/元素 | FLOP/byte |
| --- | --- | --- | --- | --- |
| 三次扫描 | 3 | 9 | 36 | 0.08333 |
| 单次融合 | 3 | 5 | 20 | 0.15 |

课件的 1/3 与 3/5 用的是“操作/标量访存次数”，尚未除以 float 的 4 byte。把它们直接写成 FLOP/byte，会差 4 倍。口述中“融合减少 math”也不适用于这个例子：减少的是中间结果读写，算术仍是 3 次。

### 8.2 1.8 倍是有条件的流量预测

若两个版本均受同一带宽限制、有效带宽相同、无额外流量且其余成本可忽略，预测加速比为 36/20=1.8。

若中间数组本就留在 Cache，则 DRAM 实际节省可能更少；写分配、写回、预取、缓存容量和编译器优化也会影响实测。不能把“逻辑字节数/时间”称为内存控制器实际带宽。

对 N=100 万元素，这个逻辑模型是 36 MB 对 20 MB；不是“少做了 16 MB 的算术”。融合还减少临时空间和可能的调用成本，但过度融合会增大寄存器压力，甚至妨碍向量化或降低 GPU 并行度。

### 8.3 还要保留语义与数值要求

输入输出有重叠时，不同元素之间可能出现依赖；临时结果被其他消费者使用时，也未必能完全删除。浮点融合乘加可能改变舍入，虽然在理想实数中公式相同。

本实验各数组互不重叠，输入为小规模二进制可精确表示的数，并使用 `-ffp-contract=off` 保持该示例的运算步骤，逐元素精确比较与独立 double 参考。一般浮点程序仍需按误差要求验证，不能把本实验的精确相等推广到任意输入。

## 9. Roofline：把 FLOPs 与字节合成性能上界

### 9.1 先定义单位，再推导

设同一个任务的计算量为 F FLOP，在指定内存层级跨界传输 Q byte；算术强度 I=F/Q，单位 FLOP/byte。机器在匹配精度与指令类型下的计算上限为 π FLOP/s，该层级可持续带宽为 β byte/s。

计算至少需要 F/π 秒，通信至少需要 Q/β 秒。即使两者完美重叠，也必须等较慢的一方：

$$
T\ge\max\left(\frac{F}{\pi},\frac{Q}{\beta}\right)
$$

用完成的计算量除以时间，吞吐 P=F/T，因此：

$$
P\le\min\left(\pi,\beta\frac{F}{Q}\right)=\min(\pi,\beta I)
$$

这是一条上界，不是每个程序一定达到的曲线。串行依赖、访存延迟不足以隐藏、负载不均、分支、指令混合和同步都可能让点落在上界下方。

FMA 通常按乘法和加法共 2 FLOP 计。计算量、峰值、数据类型和带宽的口径必须匹配；不能用整数操作数除以浮点峰值，也不能用单 Core 的带宽配整机计算峰值。

### 9.2 原创教学图与可复算数表

假设 π=1000 GFLOP/s、β=100 GB/s，均为十进制单位，并非本机指标。转折点 I*=π/β=10 FLOP/byte。

```text
可达吞吐上界 P
1000 |                    /────────────────── 计算上界
     |                  /           I ≥ 10: P = 1000
     |                /
 400 |        /                     I < 10: P = 100 I
     |      /
 100 |  /
   0 +------------------------------------------------ I
        1     4          10          20    FLOP/byte
       （形状示意；精确坐标见下表）
```

| I（FLOP/byte） | βI（GFLOP/s） | min(π,βI) | 上界由谁限制？ |
| --- | --- | --- | --- |
| 0.25 | 25 | 25 | 带宽 |
| 1 | 100 | 100 | 带宽 |
| 4 | 400 | 400 | 带宽 |
| 10 | 1000 | 1000 | 转折点 |
| 20 | 2000 | 1000 | 计算 |

在线性坐标中，带宽线 P=βI 的斜率是 β；双对数坐标中，这段线的斜率为 1，β 表现为截距/垂直位置。不要把课件双对数图的几何斜率直接读成 GB/s。

### 9.3 算力增加四倍，转折点也会移动

若 β 不变而 π 从 1000 增至 4000 GFLOP/s，转折点从 10 变成 40 FLOP/byte。I=4 的程序仍只能被相同的带宽上界限制在 400 GFLOP/s，新增算术单元无法凭空得到操作数。

这也解释了为什么更大的并行机器要求更好的数据复用。分块和融合减少 Q、提高 I，常能把程序沿带宽段向右上移动；但不同算法的工作量 F 也可能改变，所以不能只盯着横坐标。

### 9.4 吞吐高，不一定完成得快

真正的完成时间是 **T=F/P**，不是 F×P。假设旧算法 F=100 GFLOP、P=100 GFLOP/s，时间为 1 s；新算法只做 10 GFLOP，即使吞吐降至 50 GFLOP/s，也只需 0.2 s，快了 5 倍。

反过来，给表达式添加没有用途的算术，可能提高 I 和报告的 FLOP/s，却延长完成时间。优化目标应是相同任务、相同正确性要求下的墙钟时间，或明确说明的吞吐/延迟指标。

### 9.5 图上的低点不是完整诊断

若 I=20、测得 200 GFLOP/s，上界为 1000，说明还存在未解释的差距；不能仅据此断言“必定是锁”或“绝对没有内存问题”。可能是 I 只按源代码估算、真实 Q 更大，也可能是串行依赖或带宽根本没有被足量请求喂满。

同一个 Kernel 可以建立 DRAM Roofline、L2 Roofline 等不同层级的模型，每个层级都要重新配对 Q 和 β。把 Cache 命中的逻辑读都算作 DRAM 字节，会得到错误的强度。

## 10. Contention：总量相同，集中到达也会变慢

### 10.1 排队时间与服务时间分开

一个服务者每个问题要 5 分钟，每人走到办公室需 5 分钟。四个人同时出发，5 分钟后一起到达，服务者从此连续处理。各自完成时间为出发后 10、15、20、25 分钟，平均 17.5 分钟。

若四人按预约错峰出发，每人仍只花 10 分钟走路加服务；从第一人出发到最后一人完成的跨度仍可为 25 分钟。预约降低每人的排队，不是把服务者的处理能力从每 5 分钟 1 人提高成 4 人。

CPU 的共享锁、内存控制器、网络端口也会排队。因此通信总字节相同不代表延迟相同；还要看请求是否集中在同一资源、同一时间段。

### 10.2 分片、局部聚合与树

大量 Worker 向一个共享计数器逐次加值，会形成热点。每人先局部累加，最后合并，可以把每元素一次共享更新降为每 Worker 一次。若根节点仍拥挤，可采用多级树形合并。

树并非处处更好：增加了层数与中间步骤，无竞争时可能比直接发到根节点更慢。分片队列减少日常共享访问；复制数据能减少读热点，却增加内存占用和更新副本的成本。

**False Sharing（伪共享）**是另一个扩展示例：两个线程写不同变量，但变量处在同一缓存行上，仍可能反复交接该行。它与“两个线程写同一个普通变量”的正确性问题不同；调整布局可能减少交接，但应在目标机器测量。

随机错峰可能减轻短时热点，却不保证公平、最小尾延迟或最优吞吐；等待/随机化本身也有成本。不能把“加点随机延迟”当作通用修复。

## 11. 从模型走到测量：怎样知道还该优化哪里？

### 11.1 建立一份能比较的记录

先保存简单、正确的基线，定义输入、输出、数值误差和停止要求。记录硬件、系统、编译器、选项、线程数、计时范围；预热，重复运行，报告分布或中位数。

随后计算可复算的工作量与逻辑流量，必要时使用性能计数器核查实际 Cache Miss、内存流量、指令等。操作系统显示 CPU 100%，只说明执行上下文很忙，不说明算术单元已跑满；等待内存的线程也可能被统计为忙。

对于本章融合例子，F=3N，逻辑 Q 分别为 36N 与 20N。测得 t 后可以报告 F/t 和 Q/t，但后者应命名为“逻辑带宽”，除非另有真实内存流量测量。

### 11.2 删掉一部分工作，是诊断探针

课件补充页建议尝试增加计算、减少计算、集中数据访问、移除同步等“高水位”实验，以观察程序对哪个成本敏感。这些修改可以改变答案，因此只能作为独立诊断版本。

例如把全部访问改为 A[0] 后大幅变快，支持“访问模式可能重要”的假设，但编译器也可能把表达式提到循环外。删掉锁后快很多，不能说明最终版本可以不加锁；数据竞争甚至会让程序行为失去定义。

这些实验不能无条件提供最终正确实现的严格上界。必须让输出仍被观察、检查生成工作是否被删除，并把诊断结论与可发布优化分开。增加计算没有使时间成比例增长，也只说明有部分余量或重叠，不能证明每个阶段都受单一瓶颈控制。

### 11.3 一次只改一个可解释的因素

先验证输出，再改 Tile 大小或是否融合；不要同时更换算法、精度、线程数和输入。若速度提升，检查是字节量少了、有效带宽变了、调用少了，还是计算量/停止标准改变了。

若需要公平比较收敛求解器，应比较达到同样残差或误差所需的总时间，而不仅是一轮速度。课堂网格程序改变了更新次序后，迭代次数也可能变化。

## 12. 问题规模与机器规模要一起看（课件补充）

本节来自课件最后的补充材料及作者推导；用户文字稿结束于 Roofline 提问，不能据此声称课堂口述详细讲过本节。

### 12.1 强扩展与弱扩展

**强扩展**固定总问题规模，增加 Worker，看同一任务能否更快完成。二维网格分块中，每人工作随 N²/P 下降，每人边界约随 N/√P 下降，所以通信相对工作越来越突出。

**弱扩展**增加 Worker 时同时增加问题，让每人工作近似固定。例如令 N 随 √P 增长，每人 N²/P 近似固定，二维块的边长 N/√P 也近似固定。这个模型只说明近邻几何量；全局归约、网络拓扑和工作分布仍可能恶化。

### 12.2 超线性加速不一定是数学奇迹

若单 Core 的工作集装不下 Cache，而分散到多个 Core 后每人子集能留在本地 Cache，总内存流量可能显著下降。此时与原单 Core 基线相比，加速可能超过 P，原因是资源与访问行为改变了。

若小机器甚至要换页到磁盘，增加总内存的机器可能表现得更夸张。必须解释基线、容量与算法，不能据此宣称每个 Core 本身变快了。

### 12.3 先复算课件数字

第 66 页把 258×258 网格分到 32 个处理器后的数量写成约 310 格/人，与直接除法不符：258²/32=2080.125。若 258 是含边界的尺寸，内部 256²/32=2048，也不是 310。

这里保留“小问题可能无法有效利用大机器”的概念，修正算术，不猜测原数字究竟来自哪份数据。对于 N=1024 的内部网格，N²/32=32768，约 32K 格/人。

## 13. Python 实验：死锁、幽灵行、通信量与缓存

这是一份只依赖 Python 标准库的确定性模型。它不会创建集群、运行 MPI 或测量网络速度。

- 会合调度器只有匹配的发送/接收才能同时推进；若全部程序未完成却没有匹配，则检测为死锁，不会真的挂住进程。
- 幽灵行使用独立二维列表与显式快照复制，完成交换后再更新；每种颜色后与全局串行红黑参考数组逐项比较。
- 缓存模型明确使用输入专用的全相联 LRU，不拿它替代真实 CPU 性能计数器。

### 13.1 完整代码

保存为 `models.py`：

```python
"""Deterministic teaching models, not MPI or a hardware performance simulator."""
from collections import OrderedDict
from math import isclose


def rendezvous(p, parity):
    programs = [[] for _ in range(p)]
    def pair(a, b, first):
        programs[a].extend([(first, b), ('R' if first == 'S' else 'S', b)])
    for rank in range(p):
        if not parity:
            peers = [q for q in (rank-1, rank+1) if 0 <= q < p]
            programs[rank] = [('S', q) for q in peers] + [('R', q) for q in peers]
        elif rank % 2 == 0:
            for q in (rank+1, rank-1):
                if 0 <= q < p: pair(rank, q, 'S')
        else:
            for q in (rank-1, rank+1):
                if 0 <= q < p: pair(rank, q, 'R')
    pos = [0]*p
    while True:
        if all(pos[r] == len(programs[r]) for r in range(p)): return True
        progress = False
        for r in range(p):
            if pos[r] == len(programs[r]): continue
            op, q = programs[r][pos[r]]
            if pos[q] == len(programs[q]): continue
            other, peer = programs[q][pos[q]]
            if peer == r and op != other:
                pos[r] += 1
                pos[q] += 1
                progress = True
        if not progress: return False


def grid(n):
    a = [[0.0]*(n+2) for _ in range(n+2)]
    a[0] = [1.0]*(n+2)
    return a


def update(a, i, j):
    return 0.2*(a[i][j]+a[i-1][j]+a[i+1][j]+a[i][j-1]+a[i][j+1])


def halo_case(n, p, sweeps):
    # p <= n: each rank owns at least one row. lo is a zero-based interior offset.
    reference = grid(n)
    ranks = []
    for r in range(p):
        lo, hi = r*n//p, (r+1)*n//p
        local = [row[:] for row in reference[lo:hi+2]]
        ranks.append((lo, hi-lo, local))
    total_values = 0
    for _ in range(sweeps):
        for color in (0, 1):
            # Snapshot every sender before delivering: this models a completed exchange.
            outgoing = [(a[1][:], a[h][:]) for lo, h, a in ranks]
            for r, (lo, h, a) in enumerate(ranks):
                if r > 0:
                    a[0] = outgoing[r-1][1][:]
                    total_values += n+2
                if r+1 < p:
                    a[h+1] = outgoing[r+1][0][:]
                    total_values += n+2
            for lo, h, a in ranks:
                for i in range(1, h+1):
                    for j in range(1, n+1):
                        if (lo+i+j) % 2 == color: a[i][j] = update(a, i, j)
            for i in range(1, n+1):
                for j in range(1, n+1):
                    if (i+j) % 2 == color: reference[i][j] = update(reference, i, j)
            for lo, h, a in ranks:
                assert a[1:h+1] == reference[lo+1:lo+h+1]
                assert all(a[i][0] == a[i][-1] == 0 for i in range(1, h+1))
            assert ranks[0][2][0] == [1.0]*(n+2)
            assert ranks[-1][2][-1] == [0.0]*(n+2)
    assert total_values == 4*(p-1)*(n+2)*sweeps
    return total_values


def remote_values(n, rows, cols):
    # Directed halo payload across all internal rectangular partition interfaces.
    return 2*n*(rows-1) + 2*n*(cols-1)


def cache_misses(n, width):
    # Only input reads of a double-buffered stencil; output has a separate cache.
    # Fully associative LRU, 6 lines, 4 scalar elements/line, stride n+2.
    cache = OrderedDict()
    misses = 0
    for jj in range(1, n+1, width):
        for i in range(1, n+1):
            for j in range(jj, min(jj+width, n+1)):
                for x, y in [(i,j),(i-1,j),(i+1,j),(i,j-1),(i,j+1)]:
                    line = (x*(n+2)+y)//4
                    if line not in cache:
                        misses += 1
                        if len(cache) == 6: cache.popitem(last=False)
                    cache[line] = None
                    cache.move_to_end(line)
    return misses


def main():
    for p in range(2, 10):
        assert not rendezvous(p, False)
        assert rendezvous(p, True)
    print('rendezvous: 8 send-first deadlocks detected; 8 parity schedules complete')
    cases = 0
    for n in [1, 2, 3, 5, 8, 11]:
        for p in range(1, min(n, 4)+1):
            for sweeps in [1, 2, 7]:
                halo_case(n, p, sweeps)
                cases += 1
    print(f'halo: cases={cases} every_color=pass boundaries=pass payload=pass')
    assert halo_case(8, 2, 1) == 40
    n, p = 1024, 16
    strip, tile = remote_values(n, p, 1), remote_values(n, 4, 4)
    assert (strip, tile) == (30720, 12288)
    print(f'partition N=1024 P=16: strip={strip} tile={tile} values/exchange')
    row, blocked = cache_misses(30, 30), cache_misses(30, 4)
    assert blocked < row
    print(f'LRU input-only N=30: row={row} strip_width4={blocked} misses')
    f, q1, q2 = 3, 36, 20
    assert isclose((f/q2)/(f/q1), 1.8)
    peak, bandwidth = 1000, 100  # GFLOP/s and GB/s; decimal prefixes cancel.
    assert peak/bandwidth == 10
    for intensity in [0.25, 1, 4, 10, 20]:
        print(f'roofline I={intensity:g}: {min(peak, bandwidth*intensity):g} GFLOP/s')
    assert 258*258/32 == 2080.125
    print('fusion: 36 -> 20 logical bytes/element; ideal bandwidth-only speedup=1.8')
    print('all_checks=pass')


if __name__ == '__main__':
    main()
```

### 13.2 运行与结果

从仓库根目录运行：

```bash
python3 labs/lecture06/models.py
```

预期输出：

```text
rendezvous: 8 send-first deadlocks detected; 8 parity schedules complete
halo: cases=54 every_color=pass boundaries=pass payload=pass
partition N=1024 P=16: strip=30720 tile=12288 values/exchange
LRU input-only N=30: row=720 strip_width4=480 misses
roofline I=0.25: 25 GFLOP/s
roofline I=1: 100 GFLOP/s
roofline I=4: 400 GFLOP/s
roofline I=10: 1000 GFLOP/s
roofline I=20: 1000 GFLOP/s
fusion: 36 -> 20 logical bytes/element; ideal bandwidth-only speedup=1.8
all_checks=pass
```

54 组 Halo 来自 N=1/2/3/5/8/11、P=1…min(N,4) 以及 1/2/7 轮。覆盖没有邻居、单行分块和非整除行数；不覆盖 P>N，不实现异步缓冲区或归约停止协议。会合协议测试 P=2…9，结果验证这些具体程序的确定性匹配，不是对所有通信程序的证明。

## 14. C++17 实验：完整融合与空间分块

### 14.1 测试设计

融合部分比较三次扫描、单次融合与独立算术参考，覆盖空数组、短数组和非整齐长度。空间分块部分采用双缓冲 Jacobi，按完整行的参考实现与 Tile 实现比较每轮结果，同时检查边界和值域。

不需要线程、GPU 或 MPI。这里单线程同样能展示局部性优化；并行调度不会自动替你消除临时数组。

### 14.2 完整代码

保存为 `locality.cpp`：

```cpp
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using Vec = std::vector<float>;
using Clock = std::chrono::steady_clock;

void separate(const Vec& a, const Vec& b, const Vec& c, const Vec& d,
              Vec& t1, Vec& t2, Vec& out) {
    for (std::size_t i=0; i<a.size(); ++i) t1[i]=a[i]+b[i];
    for (std::size_t i=0; i<a.size(); ++i) t2[i]=t1[i]*c[i];
    for (std::size_t i=0; i<a.size(); ++i) out[i]=d[i]+t2[i];
}
void fused(const Vec& a, const Vec& b, const Vec& c, const Vec& d, Vec& out) {
    for (std::size_t i=0; i<a.size(); ++i) out[i]=d[i]+(a[i]+b[i])*c[i];
}
void inputs(Vec& a, Vec& b, Vec& c, Vec& d) {
    for (std::size_t i=0; i<a.size(); ++i) {
        a[i]=static_cast<int>(i%17)-8;
        b[i]=0.25f*static_cast<int>(i%7);
        c[i]=0.5f; d[i]=1.0f;
    }
}
struct Grid {
    int n, stride;
    Vec x;
    explicit Grid(int size):n(size),stride(size+2),x(stride*stride,0) {
        std::fill(x.begin(),x.begin()+stride,1);
    }
    float& at(int i,int j) { return x[i*stride+j]; }
    float at(int i,int j) const { return x[i*stride+j]; }
};
void reference_step(const Grid& in, Grid& out) {
    for (int i=1; i<=in.n; ++i)
        for (int j=1; j<=in.n; ++j)
            out.at(i,j)=0.2f*(in.at(i,j)+in.at(i-1,j)+in.at(i+1,j)
                                  +in.at(i,j-1)+in.at(i,j+1));
}
void stencil(const Grid& in, Grid& out, int tile) {
    for (int ii=1; ii<=in.n; ii+=tile)
        for (int jj=1; jj<=in.n; jj+=tile)
            for (int i=ii; i<std::min(ii+tile,in.n+1); ++i)
                for (int j=jj; j<std::min(jj+tile,in.n+1); ++j)
                    out.at(i,j)=0.2f*(in.at(i,j)+in.at(i-1,j)+in.at(i+1,j)
                                          +in.at(i,j-1)+in.at(i,j+1));
}
void check() {
    int fusion_cases=0, stencil_cases=0;
    for (int n : {0,1,2,3,7,16,31,33,257}) {
        Vec a(n),b(n),c(n),d(n),t1(n),t2(n),x(n),y(n);
        inputs(a,b,c,d);
        separate(a,b,c,d,t1,t2,x); fused(a,b,c,d,y);
        if (x!=y) throw std::runtime_error("fusion mismatch");
        for (int i=0; i<n; ++i) {
            double expected=double(d[i])+(double(a[i])+b[i])*c[i];
            if (x[i]!=expected) throw std::runtime_error("reference mismatch");
        }
        ++fusion_cases;
    }
    for (int n : {1,2,3,7,16,31})
        for (int tile : {1,2,3,8,64})
            for (int steps : {1,2,7}) {
                Grid a(n),b(n),x(n),y(n);
                for (int s=0; s<steps; ++s) {
                    reference_step(a,b); stencil(x,y,tile);
                    std::swap(a.x,b.x); std::swap(x.x,y.x);
                    if (a.x!=x.x) throw std::runtime_error("stencil mismatch");
                }
                for (int i=0; i<n+2; ++i)
                    for (int j=0; j<n+2; ++j) {
                        float v=x.at(i,j);
                        if (!std::isfinite(v)||v<0||v>1)
                            throw std::runtime_error("invalid grid value");
                        if ((i==0 && v!=1) || (i==n+1 && v!=0) ||
                            (i>0 && (j==0||j==n+1) && v!=0))
                            throw std::runtime_error("boundary changed");
                    }
                ++stencil_cases;
            }
    std::cout<<"fusion_cases="<<fusion_cases<<" stencil_cases="<<stencil_cases
             <<" boundaries=pass correct=yes\n";
}
double checksum(const Vec& x) {
    double sum=0;
    for (float v:x) sum+=v;
    return sum;
}
void bench(std::size_t n) {
    Vec a(n),b(n),c(n),d(n),t1(n),t2(n),x(n),y(n);
    inputs(a,b,c,d);
    separate(a,b,c,d,t1,t2,x); fused(a,b,c,d,y);
    if (x!=y) throw std::runtime_error("warmup mismatch");
    std::vector<double> times[2];
    double observed=0;
    for (int rep=0; rep<7; ++rep)
        for (int order=0; order<2; ++order) {
            int mode=(rep+order)%2;
            auto start=Clock::now();
            if (mode==0) separate(a,b,c,d,t1,t2,x);
            else fused(a,b,c,d,y);
            double seconds=std::chrono::duration<double>(Clock::now()-start).count();
            times[mode].push_back(seconds);
            // Observe every timed output outside the timed region.
            observed+=checksum(mode==0 ? x : y);
            if (x!=y) throw std::runtime_error("timed output mismatch");
        }
    std::cout<<std::fixed<<std::setprecision(3);
    for (int mode=0; mode<2; ++mode) {
        std::sort(times[mode].begin(),times[mode].end());
        double t=times[mode][3];
        std::cout<<(mode==0?"separate":"fused")<<" n="<<n
                 <<" median_ms="<<t*1000
                 <<" logical_GB_per_s="<<(mode==0?36.0:20.0)*n/t/1e9<<'\n';
    }
    std::cout<<"observed_checksum="<<observed<<" correct=yes\n";
}
int main(int argc,char** argv) {
    try {
        check();
        if (argc>1) {
            if (std::string(argv[1])!="--bench" || argc>3)
                throw std::runtime_error("usage: locality [--bench [elements]]");
            auto n=argc==3?std::stoull(argv[2]):4194304ULL;
            if (n<1 || n>16777216) throw std::runtime_error("elements must be 1..16777216");
            bench(n);
        }
    } catch (const std::exception& e) {
        std::cerr<<e.what()<<'\n'; return 1;
    }
}
```

### 14.3 编译与正确性检查

```bash
mkdir -p /tmp/cs149-l06-build
c++ -O2 -ffp-contract=off -std=c++17 -Wall -Wextra -pedantic \
  labs/lecture06/locality.cpp -o /tmp/cs149-l06-build/locality
/tmp/cs149-l06-build/locality
```

固定输出：

```text
fusion_cases=9 stencil_cases=90 boundaries=pass correct=yes
```

90 组来自 6 种内部尺寸、5 种 Tile、3 种轮数，涵盖 Tile 大于网格、非整除边缘以及多轮交换。Jacobi 输出都由旧缓冲区读取，边界从初始化后不再写入。

还可用 AddressSanitizer 和 UndefinedBehaviorSanitizer 检查测试路径上的越界与部分未定义行为：

```bash
c++ -O1 -g -ffp-contract=off -std=c++17 -fsanitize=address,undefined \
  labs/lecture06/locality.cpp -o /tmp/cs149-l06-build/locality-sanitize
/tmp/cs149-l06-build/locality-sanitize
```

### 14.4 可选计时与解释边界

```bash
/tmp/cs149-l06-build/locality --bench 4194304
```

预热后对融合两版本各测 7 次，交替先后顺序，报告中位数。每次计时后观察完整输出校验和并比较结果；内存分配、初始化与校验不计入计时。该规模 8 个 float 数组共约 128 MiB。

本次 macOS ARM64、Apple Clang 16、上述 O2 选项的一次运行，三次扫描约 1.547 ms，融合约 0.788 ms。它只表明本机该输入的观察，不规定固定加速倍数。计时与比例会随系统负载、CPU 频率和缓存驻留改变。

程序字段 `logical_GB_per_s` 由 36N/t 或 20N/t 计算，未测 DRAM 实际字节，也未确认该输入完全来自 DRAM。观察到的时间比约 1.96，不应硬套成模型的 1.8；有效带宽、缓存及其他成本并非必然相同。

本程序不测 Tile 的性能，不绑定 CPU，不提供 NUMA 或集群通信性能结论。若扩展实验，先固定相同数学工作，再独立扫描 Tile 大小和矩阵尺寸。

## 15. 练习与参考答案

### 练习 1：共享是否等于本地？

两个线程能引用同一个数组，为什么访问时间仍可能不同？

**答：** 共享地址空间只提供可访问性；缓存副本、切片距离、内存节点和请求排队都会改变路径与成本。还需单独保证并发访问正确。

### 练习 2：发送完成意味着什么？

`MPI_Send` 返回能证明接收方应用已经使用数据吗？

**答：** 不能。它首先保证发送缓冲区可复用，数据可能已进入系统缓冲区。对端处理完成需要额外的应用级协议。

### 练习 3：奇数偏移的颜色

N=5、P=2、Rank 1 的 ℓ=2，本地行 1、列 2 是什么颜色？如果 ℓ=3 呢？

**答：** 按 (ℓ+i+j)%2，前者为 (2+1+2)%2=1；后者为 0。因此只用本地下标可能把颜色颠倒。

### 练习 4：为什么 Halo 要再交换？

一轮开始交换一次，然后直接完成红色与黑色，能保证与串行红黑逐轮一致吗？

**答：** 一般不能。黑色边缘点需要邻居刚更新的红值，最初幽灵行仍是旧版本。需要红后交换，或另一个能提供同版本数据的协议。

### 练习 5：异步发送缓冲区

启动发送一整行后，只修改行里本轮的红点，是否安全？

**答：** 若请求未完成且发送缓冲区就是该行，则不安全；“只改一半”仍在改发送缓冲区。先等待完成或使用独立打包副本。

### 练习 6：有限网格总载荷

N=120、P=12，比 12×1 与 3×4 划分的一次交换总元素数。

**答：** 前者 2×120×11=2640；后者 2×120×(2+3)=1200。比率 2.2；不包括角点、消息头及额外全行边界列。

### 练习 7：消息合并

α=2 μs、B=1 GB/s，逐条串行发送 100 条各 100 byte 与合成一条分别多久？

**答：** 总载荷 10000 byte，传输需 10 μs；分别为 200+10=210 μs 与 2+10=12 μs，尚未计入组批等待和打包。

### 练习 8：融合单位

若改用 float64，三次扫描与融合的逻辑强度是多少？算术仍为每元素 3 FLOP。

**答：** 72 与 40 byte/元素，强度为 1/24 与 3/40 FLOP/byte。在相同带宽限制假设下，流量比仍为 1.8；这不保证两精度达到同样带宽或峰值。

### 练习 9：读 Roofline

π=2 TFLOP/s、β=200 GB/s、I=2 FLOP/byte，上界与转折点是多少？

**答：** 转折为 2000/200=10 FLOP/byte；上界 min(2000,400)=400 GFLOP/s。若实测 50，仍需查真实流量、并发、依赖与同步，不能只说带宽已经饱和。

### 练习 10：高 FLOP/s 一定更快吗？

旧算法 80 GFLOP、吞吐 400 GFLOP/s；新算法 20 GFLOP、吞吐 200 GFLOP/s，谁先完成？

**答：** 旧 0.2 s，新 0.1 s，新算法快 2 倍，尽管报告的 FLOP/s 更低。

### 练习 11：块越大越好？

把 Tile 不断增大，既减少循环管理，又一定减少 Miss 吗？

**答：** 不一定。工作集可能超出缓存，或形成冲突；很小的块也可能反复读取 Halo。应在满足依赖和容量约束后测量多个大小。

### 练习 12：错峰解决了什么？

四人同时排队与按预约错峰，服务者每人均需 5 分钟。为什么每人等待可减少，但总服务能力没有提升？

**答：** 错峰减少到达时已有队列，单位时间仍最多处理同样数量。它改变响应延迟与等待位置，没有减少服务工作量。

### 练习 13：扩展到更大的网格

P 增加四倍时，要让二维块中每人点数不变，N 应怎样变化？

**答：** N 增加两倍，因为 (2N)²/(4P)=N²/P；每块边长 N/√P 也不变。全局归约成本不因此必然固定。

### 练习 14：设计下一项实验

本章模型 b=4 比 b=1 Miss 少，能据此宣布本机最优 Tile 为 4 吗？

**答：** 不能。模型省略输出和预取等因素，真实缓存与数据类型也不同。应在同样输入和正确性要求下运行目标程序，扫描 Tile 与尺寸，记录时间和实际流量，避免只测一个有利案例。

## 16. 与 AI Infrastructure 的联系（作者延伸）

算子融合把中间 Tensor 的读写缩短为寄存器或近处缓存中的生产与消费，但要权衡活跃值、寄存器、片上容量与执行并发。它保留了本章“减少 Q，再看整体时间”的思路，不能从源代码表达式数量直接推断某个框架实际启动了多少 Kernel。

多设备任务的分配也要兼顾负载和通信：分工均衡却需要交换大量激活或状态，未必比稍不均匀但局部性好的分配更快。集合通信分桶可以摊薄启动成本，却可能增加等待，必须看关键路径与尾延迟。

CPU 数据读取、设备内存、主机与设备链路、跨节点网络各有不同的 Q 与 β。推理的批大小和序列长度也会改变计算量与工作集。应逐层建模，而不是把一个 DRAM Roofline 数字套给整个服务系统。

## 17. 来源、修正与核验范围

| 来源 | 采用内容 | 核验状态 |
| --- | --- | --- |
| [Stanford 第 6 讲课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/perfopt2/) | 讲题、课次 | 已核对 |
| [官方 69 页课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/perfopt2/06_progperf2.pdf) | 第 3–9 页地址空间与 NUMA；10–24 页消息；25–44 页通信和局部性；45–52 页竞争；53–69 页分析与扩展 | 已核对文字结构，视觉抽查第 19、23、34、35、40、43、44、56、66 页，未逐页复核 |
| 用户提供英文自动文字稿 | 从本讲开场到 Roofline 末尾提问 | 全文已阅读，无时间码，未逐句核对音频 |
| [课程录像](https://www.youtube.com/watch?v=Mhdny2JNhmc) | 对应本讲的视频来源 | 未编造时间点，未完成逐句音频校验 |
| [MPI Forum：通信模式](https://www.mpi-forum.org/docs/mpi-4.1/mpi41-report/node67.htm) | 发送模式、完成语义与缓冲依赖 | 对照规范，修正课堂简化与 MPI 的区别 |
| [Open MPI：Sendrecv](https://docs.open-mpi.org/en/main/man-openmpi/man3/MPI_Sendrecv.3.html) | 邻居交换与调用次序 | 用于接口说明；本章没有运行 MPI |
| [Open MPI：Isend](https://docs.open-mpi.org/en/main/man-openmpi/man3/MPI_Isend.3.html) | 非阻塞请求与发送缓冲区生命周期 | 用于接口说明；不声称实现了异步传输 |
| [Williams、Waterman、Patterson：Roofline 原始论文记录](https://zenodo.org/records/1236156) | Roofline 模型与原始出处 | 原始作者文献索引；本章图与数字为独立教学推导 |

保留常数的边界流量、Halo 逐颜色校验、LRU 模型、原创图表、全部练习及 AI Infra 说明为作者补充。修正了课件伪代码漏收最后 Rank、行边界与红黑阶段省略、258²/32 算术错误；区分每标量操作比率与 FLOP/byte，并把墙钟时间写为工作量除以吞吐。

Python 模型已运行；C++17 在 macOS ARM64、Apple Clang 16 上完成 9 组融合与 90 组空间分块检查，另运行融合计时及地址/未定义行为检测。结果只覆盖指定输入和执行路径，不是所有协议调度或一般数值求解的证明。

没有运行 MPI、多机网络、NUMA 绑定或 GPU 实验，未采集真实硬件缓存和 DRAM 计数器。只提交原创教材、实验与来源记录；原始字幕、官方 PDF 和构建产物不进入公开仓库。详细记录见 [第 6 讲来源核验](../sources/lecture-06-audit.md)。
