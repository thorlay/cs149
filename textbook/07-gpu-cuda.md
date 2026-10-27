# 第 7 章：GPU 架构与 CUDA 编程

> Stanford CS149 · Fall 2023 · Lecture 7 — GPU Architecture and CUDA Programming
>
> **状态：自包含中文教材，扩写版。** 结合用户提供的完整英文自动文字稿、官方 73 页 Slides 与 NVIDIA 文档，独立编写讲解、推导和实验。文字稿已阅读全文，无时间码，含听不清与术语误识别，尚未逐句核验音频。课件文字结构已核对，关键图页已抽查，未逐页视觉复核。本文不是官方授权教材或逐字翻译。

**先修知识：** C/C++ 数组、下标、循环、函数与指针的基本含义。本章从头定义 CUDA 执行单位、内存与同步，不要求先看其他讲次。

**学习时间：** 阅读与纸笔推演约 2–3 小时，CPU 模型约 30–60 分钟；GPU 练习另需可用的 NVIDIA CUDA 环境。

**配套实验：** [第七章代码与复现说明](../labs/lecture07/README.md)。完整 Python 模型与 CUDA 程序均收录于本页。CPU 模型已经运行；本机为 macOS ARM64、无 nvcc，CUDA 程序尚未编译或在 NVIDIA GPU 上运行，不把预期输出当作实测。

## 0. 一百万个 CUDA 线程，是一百万个 CPU 线程吗？

假设一百万个输出点，每点取三个相邻输入的平均值。可以写一个函数，告诉 GPU 启动很多执行实例，并让每个实例根据编号负责一个输出。

这里的“线程”是 CUDA 的逻辑控制流，不是为每个输出创建一个操作系统线程。GPU 可以分批安排工作：一些 Block 驻留并执行，其他 Block 等待资源释放。程序要表达足够多的独立工作，同时正确表达需要合作的数据依赖。

本章围绕三个问题展开：**程序员创建了什么、线程如何合作、GPU 如何执行这些工作？** 把这三层分清，才能解释为什么不能删屏障、为什么线程多不等于同时执行，以及为什么资源限制会影响速度。

## 1. 从着色器到通用计算：改变的是启动计算的接口

### 1.1 图形任务为什么天然需要吞吐量？

实时图形把场景中的几何、材质、灯光与相机信息变成图像。一条重要计算路径是：先确定三角形覆盖哪些位置，再对相应片元计算颜色。**Shader（着色器）**是执行这类计算的程序；片元并不总与最终屏幕像素一一对应，但它提供了大量形式相似的计算工作。

以 3840×2160、60 帧/秒为例，仅按每像素一次计算估算，也有 497664000 次/秒。真实渲染还有多重覆盖、采样与其他阶段。GPU 因而倾向于把更多芯片资源用于并行算术与大量待执行状态，提高总吞吐，而非只把一条复杂控制流做得更快。

这不是“CPU 不会并行、GPU 才会并行”：二者都使用多核、向量运算与多线程，只是资源比例和接口不同。

### 1.2 早期通用 GPU 计算为何像绕路？

早期研究者把输出数组编码为图像，用覆盖屏幕的三角形产生大量着色调用，再让本来计算颜色的函数更新粒子或处理科学数据。程序想做的是数组计算，却需要通过图形命令发起。

课件介绍了 2004 年 Brook 流式编程工作：对集合应用函数，由编译器把较自然的计算表达转换为当时 GPU 能接受的图形操作。后来 CUDA 提供通用计算接口，不再要求用户用绘制三角形来表达数组任务。

这些历史例子说明的是抽象与硬件接口的演变。课堂当时的公司市值、芯片价格与“高端显卡”性能属于历史语境，本章不将其当作当前数据。

### 1.3 SPMD、SIMD 与 SIMT

| 名称 | 本章中的含义 |
| --- | --- |
| SPMD | 单程序多数据：多个逻辑实例运行同一份程序，用各自编号和数据决定行为 |
| SIMD | 单指令多数据：一条向量操作对多个数据位置执行同一种操作 |
| SIMT | NVIDIA 的线程执行模型：按线程描述程序，硬件按 Warp 等组织执行 |

CUDA Kernel 采用 SPMD 风格；GPU 的执行会利用类似 SIMD 的并行数据通路。不能因为“写的是一个线程的标量代码”，就推断芯片一次只处理一个数。

ISPC 的逻辑实例和 CUDA Thread 可以类比，但映射方式并不相同。CPU 上 ISPC 常编译成调用线程执行的向量指令；CUDA 的设备代码由 GPU 执行。类比用来帮助理解，不表示 ISPC Gang、CUDA Block 和 Warp 三者完全等价。

## 2. Host、Device 与 Kernel Launch

### 2.1 谁在执行哪一段代码？

**Host**通常指运行控制代码的 CPU 一侧，**Device**指执行 GPU 工作的一侧。**Kernel**是在 Device 上运行、可被启动的函数。一次启动形成一个 **Grid**；Grid 由 **Thread Blocks** 组成；Block 内包含 **CUDA Threads**。

```text
CPU / Host
  准备输入、分配设备内存、提交 Kernel、等待需要的结果
                          │
                          ▼
一次 Launch 的 Grid
  ├─ Block 0: Thread 0, Thread 1, ...
  ├─ Block 1: Thread 0, Thread 1, ...
  └─ ...
                          │ GPU 调度器安排
                          ▼
若干 SM：执行当前驻留 Block 中可运行的 Warps
```

Grid 和 Block 的形状是软件编号组织，不表示物理芯片按同样的二维格子排列。一个 `__global__` 声明标识 Kernel；普通主机函数不会因此自动运行在 GPU 上。`__device__` 常用于设备端调用的函数。

### 2.2 启动语法与实际完成要分开

以下为语法片段，完整程序见第 13 节：

```cpp
kernel<<<numBlocks, threadsPerBlock, sharedBytes>>>(deviceInput, deviceOutput, n);
```

第三个参数指定每 Block 的动态 Shared Memory 字节数，省略时为 0；还可指定 Stream，本章完整例子使用默认 Stream。

**Kernel 启动通常对 Host 异步。** CPU 从启动语句继续执行，不代表 GPU 已经算完，甚至不代表已开始运行。课件第 28 页的“调用返回时全部线程结束”以及第 38 页的相关简写不应作为真实 CUDA 启动语义使用。

在本章程序中，启动后先用 `cudaGetLastError()` 检查启动配置等错误，再用 `cudaDeviceSynchronize()` 等待并检查执行错误，然后复制结果。实际系统可采用更细的 Stream 或 Event 同步；不需要在每个 Kernel 后都把整个设备停下来。

### 2.3 同一 Stream 的顺序能提供阶段边界

若一个 Kernel 生产数据，下一个消费它，可以把二者提交到同一 Stream，让后者在前者完成后执行。Host 仍可能继续异步运行，直到它需要结果时才等待。

不同 Stream 之间需要显式依赖或适用的同步规则，不能把单 Stream 示例推广成“所有启动天然全局排队”。本章也不依赖不同默认 Stream 模式之间的隐含差异。

## 3. 用编号分配工作：一维、二维与尾部

### 3.1 一维映射及覆盖证明

设每 Block 有 B 个线程，Block 编号 b，Block 内线程编号 t，其中 0≤t<B。令全局元素下标：

$$
i=bB+t
$$

若有 N 个元素，启动 G=ceil(N/B) 个 Block，并仅在 i<N 时处理数据。

为何不会遗漏或重复？任意合法 i 都能唯一分解为 b=floor(i/B)、t=i mod B，所以恰好有一个逻辑线程负责它。反过来，最后的线程可能没有有效元素，必须先判断再访问。

N=1000、B=256 时，G=4，总逻辑线程 1024，多出 24 个。N=0 应由 Host 跳过启动，不能启动 0 个 Block。大尺寸的索引与取整还需要防止整数溢出；本章测试规模很小，代码使用 int 不承诺支持任意大数组。

### 3.2 二维案例：11×5 不是 72 个数据

令矩阵宽 Nx、高 Ny，行主序存储。Block 为 Bx×By，线程坐标为 (tx,ty)，Block 坐标为 (bx,by)：

$$
x=bx\,Bx+tx,\quad y=by\,By+ty,\quad \mathrm{offset}=y\,Nx+x
$$

每个维度分别向上取整，只有 x<Nx 且 y<Ny 时才能读写。

Nx=11、Ny=5、Bx=4、By=3：Grid 为 3×2，共 6 个 Block，每 Block 12 线程，合计 72 个逻辑线程；有效数据是 55 项，17 个线程不写输出。

例如 Block (2,1) 的 Thread (2,1) 得 x=10、y=4、offset=54，是最后一个合法元素；同一 Block 的 Thread (3,1) 得 x=11，已越过行宽，必须跳过。只检查扁平下标 `<Nx*Ny` 不能替代两个维度的边界检查，因为 x 越界可能别名到下一行。

### 3.3 三维线程如何分成 Warps？

Block 内线性线程号按 x 最快变化：

$$
t_{\mathrm{linear}}=tx+Bx\left(ty+By\,tz\right)
$$

理解这一点有助于安排连续访存。二维矩阵的“同行”是否落在同一个 Warp，取决于 Bx 与线程线性化，并非只看图上的空间邻近。

### 3.4 一个线程可以处理多个元素

**Grid-Stride Loop** 让线程依次处理 tid、tid+S、tid+2S…，S 是整个 Grid 的逻辑线程数。有效元素仍按对 S 的余数唯一分给线程。

本章直方图 Kernel 用这种分工。启动的逻辑线程数由配置决定，输入规模只在程序里决定循环次数；并不是 CUDA 自动保证“每个数据元素恰好创建一个线程”。

## 4. 内存：作用域、物理位置与可访问性

### 4.1 明确拷贝是最简单的起点

本章采用显式管理的教学路径：Host `std::vector` 保存输入，`cudaMalloc` 分配设备缓冲，`cudaMemcpy` 执行 H2D/D2H 数据传输，把设备指针传给 Kernel。

```text
Host 数组 x                Device 数组 dx
CPU 可访问                 GPU Kernel 可访问
      └──── H2D 拷贝 ───────→
                           Kernel 写 dy
      ←──── D2H 拷贝 ───────┘
CPU 检查结果
```

在这个使用方式下，不应在普通 CPU 代码里直接读取 `cudaMalloc` 返回的设备指针。也不能仅因 Host 有一个普通指针就假定 GPU 一定能访问其内容。

现代 CUDA 有统一虚拟寻址、Unified Memory、映射 Host 内存等能力；它们不等价。统一地址编号不保证任意指针都能在任意处理器解引用；Managed Memory 的迁移、系统内存支持与硬件一致性取决于平台。可访问同一数据也不保证没有通信成本，本章不把“普通指针可用”或“必然经过 PCIe”写成通则。

### 4.2 三类设备侧存储

| 类别 | 逻辑作用域与生命周期 | 物理实现提示 |
| --- | --- | --- |
| 线程私有变量 | 每线程自己的状态 | 可能在寄存器，也可能溢出或存放于 Local Memory |
| `__shared__` | 同一 Block 协作，Block 生命周期内有效 | 通常为 SM 上的软件管理存储，容量有限 |
| Global Memory | Grid 中线程可按访问规则读写 | 大容量设备存储，可经过 Cache |

CUDA 术语 **Local Memory** 表示线程私有的设备内存空间，不等于“就在最快的片上”。私有数组、寄存器不足等情况可能产生经缓存访问的设备内存流量。把“私有”理解成可见性，把“寄存器/DRAM”理解成存放位置，不要混为一个维度。

同一个 `__shared__` 声明为每个 Block 提供一份逻辑对象；不是每线程独立分配一份，也不是所有 Block 共享一份。它更不等同于 ISPC 的 uniform 值：uniform 表示实例之间值相同，Shared Memory 仍需要解决多线程写读与同步。

### 4.3 Shared Memory 与 Cache 不同

Cache 由硬件管理是否保存数据；Shared Memory 由程序显式决定装入什么、谁写、谁读、何时复用。某些架构两者共享物理容量，但不能把所有物理 L1 容量都算成可申请的 Shared Memory。

当 Block 结束，不能依赖它的 Shared Memory 留给下一个 Block。若使用循环反复装载同一 Tile 缓冲区，还需保证旧消费者全部读完后，下一轮生产者才覆盖它。

## 5. 三点平均：把 Block 协作完整推演一遍

### 5.1 先定义边界，避免两个题目混在一起

本章延续原有例子的定义：输入 x 有 N 项，输出 y 也有 N 项，越界输入按 0 处理：

$$
y_i=\frac{x_{i-1}+x_i+x_{i+1}}{3},\quad x_j=0\ \text{当}\ j<0\ \text{或}\ j\ge N
$$

课件使用输入 N+2 项、输出 N 项的形式 `(input[i]+input[i+1]+input[i+2])/3`。两者在把本章 x 左右各补一个 0 后可以对应，但不能直接把两种长度和下标混用。

以 x=[1,2,3,4,5] 为例，五项输出依次为 (0+1+2)/3、(1+2+3)/3、(2+3+4)/3、(3+4+5)/3、(4+5+0)/3，所以 y=[1,2,3,4,3]。

### 5.2 直接实现与共享 Tile

直接实现让每个有效线程读三个输入，再写一个输出。相邻线程重用输入，例如 x[1] 参与 y[0]、y[1]、y[2]。

若一个 Block 负责 B 个连续输出，其输入支持区有 B+2 项。让线程协作把这段输入放入 Shared Memory，等待装载完成后，再各自读取三个共享值。

```text
Block 起点 base，局部线程 t=0..B−1
共享槽位 q:    0       1       2       ...      B       B+1
对应全局输入: base−1  base    base+1    ...    base+B−1 base+B

线程 t 的输出使用共享槽位 [t, t+1, t+2]
```

在 B=128 的完整块上，直接版每线程三次标量读取，共 384 次；协作版装载 130 个标量，需 520 byte 共享存储。**130×4=520，不是口述反复出现的 512。**

384 与 130 比较的是线程级标量读取量，不是机器实际发出的指令条数，也不是 DRAM 事务数。直接版相邻读取可能命中 Cache 或合并，所以不能推导协作版必然快 384/130 倍。

### 5.3 通用装载循环，连 B=1 都有定义

完整程序使用 `q=t; q<B+2; q+=B` 装入支持区，每个 q 对 B 的余数对应唯一线程，因此每个共享槽位恰好由一个线程写。

全局输入下标 g=base+q−1，若 0≤g<N 则装入 x[g]，否则写 0。随后所有线程经过 `__syncthreads()`，只由 i<N 的线程写输出。

B=1 时，唯一线程依次装载 q=0、1、2，仍然完整；如果照搬“前两个线程各多装一项”的特殊写法，却允许 Block 只有一个线程，就可能遗漏数据。

### 5.4 最后一个 Block 的无效线程仍有工作

N=5、B=2 时：

| Block | base | 共享 Tile | 有效输出 |
| --- | --- | --- | --- |
| 0 | 0 | [0,1,2,3] | y0=1、y1=2 |
| 1 | 2 | [2,3,4,5] | y2=3、y3=4 |
| 2 | 4 | [4,5,0,0] | y4=3 |

最后一个 Block 中 t=1 没有输出，但仍参与装载与屏障。不能在本例中因为 i≥N 就提早返回：它可能负责有效线程需要的共享槽位，或者改变屏障的参与情况。

本实现把屏障放在所有线程共同经过的位置，边界判断只约束单次安全装载和最后写出。这样既容易证明，也能用 CPU 模型逐槽位检查。

## 6. 同步解决哪些问题，又没有解决哪些问题？

### 6.1 没有屏障的一次合法交错

设 B=4，线程 0 装载了自己的槽位 q=0、4，立刻尝试读 q=0、1、2 来计算输出。此时线程 1、2 可能尚未装载，q=1、2 未初始化。这就足以否定删除屏障后的正确性，不需要实际制造一个随机 GPU 失败。

`__syncthreads()` 为 Block 内阶段提供会合与相应内存可见性。它不能作为任意跨 Block 的全局屏障。条件分支中的屏障应确保所有需要参与的未退出线程以一致方式到达；本章不依赖线程提前退出的细节来规避同步要求。

同一个 Warp 中也不应凭“看起来一起执行”推断共享写读自动安全。需要相应的 Warp 同步时，应使用适用的 `__syncwarp` 等接口与正确参与掩码。本章示例使用整 Block 同步。

### 6.2 原子加保证一次更新完整，不保证所有更新结束

假设多线程都要把某个桶的计数加 1。普通读改写可能覆盖别人的结果；原子加把同一位置上的这次更新作为不可分割操作。

若输入只含 0…9、桶先清零，每个有效输入恰好执行一次原子加，等全部 Kernel 完成后，桶 k 就得到相应元素个数。这种直方图可以跨 Block 更新同一全局数组，不需要假设 Block 按编号执行。

原子加本身不是全局完成通知，也不自动为任意其他数据建立完整发布协议；涉及数据与标志的生产消费，需要合适的作用域、内存顺序与进展保证。本章直方图不靠原子标志发布额外数据。

### 6.3 为什么跨 Block 忙等可能死锁？

考虑只有一个 Block 驻留槽位的教学 GPU，不能依赖抢占救场：Block 0 写原子标志；Block 1 一直等标志变为 1。

```text
先运行 Block 0 → 设置标志 → 结束 → Block 1 读取成功
先运行 Block 1 → 等待标志 → 占着唯一槽位
                            Block 0 无法开始 → 无法保证进展
```

即使标志本身全部采用原子访问，也没有解决调度上的等待环。普通 Launch 不保证所有 Block 同时驻留，也不保证按编号启动。

简单的安全分阶段方式是拆成同 Stream 的前后两个 Kernel。CUDA 另有带条件与约束的合作启动等能力；这些特殊协议不能靠普通 Block 自旋代替。

### 6.4 为什么不能把一个大 Block 分两半跑到结束？

若一台假想机器只容纳 128 个线程状态，而请求的一个 Block 有 256 个线程，先让前 128 个跑到结束的想法会遇到屏障：前一半要等后一半，自己还没有结束，后一半又没有可用状态。

这个反例解释了 CUDA Block 的协作与资源约束。它不是说所有线程同一时钟都在执行，而是不能用“部分线程运行完才创建剩余线程”的方式普遍保持该 Block 的同步语义。实际合法性还要检查设备、函数和资源上限。

## 7. Warp 与 SM：逻辑线程怎样使用算术单元？

### 7.1 先分清四种数量

**SM（Streaming Multiprocessor）**是 GPU 上安排并执行线程组的硬件单元。**Warp** 是 NVIDIA GPU 中把同一 Block 的线程按线性编号组织起来的分组，本章以 32 线程/Warp 为对象。

| 数量 | 例子 | 不代表什么 |
| --- | --- | --- |
| Launch 总线程 | 8192 Block×128=1048576 | 不代表全部同时驻留 |
| 驻留线程 | 当前已分配状态、可以参与调度的线程 | 不代表每个线程都已就绪 |
| 就绪 Warp | 依赖已满足、可发射下一条指令的 Warp | 不代表都在同一周期发射 |
| 执行单元 | 完成某类操作的数据通路 | 不等于 CUDA 线程数 |

B=128 时，一个 Block 有 4 个 Warp；B=33 时有 2 个 Warp，第二个只含一个有效的 Block 线程，其余 Lane 没有对应线程。部分 Warp 的浪费与最后 Block 中 i≥N 的线程不是同一件事。

Warp 的知识不只是内部图示：CUDA 有 `warpSize`、Warp 级协作接口等。课件说“Warp 不属于编程模型”是为了强调基础 Thread/Block 抽象，不能理解为程序永远无法观察或使用它。

### 7.2 SIMT 执行与分支分歧

同一 Warp 中多个线程执行同一种操作时，可以高效利用并行数据通路。如果偶数 Lane 执行路径 A、奇数 Lane 执行路径 B，硬件可能分别对相应活跃线程执行两条路径，另一部分 Lane 被屏蔽。

在一个仅作教学的模型中，A 有 4 条、B 有 12 条同成本指令，32 个线程各半选择一条。两路都需执行时，共占 16 组指令位置，每组宽 32，共 512 个 Lane-指令槽位；有用工作为 16×4+16×12=256，利用率 50%。这个数字不含分支处理、重汇合或具体指令吞吐，不是实测惩罚。

如果整个 Warp 都选择同一路，Warp 内没有这种分歧；不同 Warp 选择不同路径本身也不产生同样的 Warp 内屏蔽。编译器还可能使用谓词化，所以不能只看到一个 `if` 就认定必须优化掉。

### 7.3 独立线程状态不等于可随便依赖执行次序

Volta 引入独立线程调度，维护更细的线程执行状态，但仍保留 Warp 分组与资源组织。不能把课堂“相同 PC 的线程一起执行”的直观解释，当作精确描述所有调度电路或保证自动把任意 Warp 的线程重新拼成一组。

**PC（程序计数器）**描述下一条要执行的指令位置。不同线程可以有各自的控制状态，但程序仍应按同步规则交流，避免依赖未保证的锁步细节。基础程序也不应把“这块芯片可能支持某种重排”当作正确性条件。

### 7.4 多线程隐藏延迟，而不是消灭延迟

当 Warp A 等待内存时，SM 可安排 Warp B 的就绪指令；若所有驻留 Warp 都在等待同一类资源，依旧会停顿。更多线程只有在提供更多独立、就绪的工作时才有帮助。

同一个 Warp 中也可能有多个独立操作，提供 **ILP（指令级并行）**。隐藏延迟需要多少 Warp 取决于指令依赖、延迟、发射能力与在途请求，不能给一个对所有 Kernel 都适用的固定最优数量。

## 8. V100 是一份具体实例，不是 CUDA 的永久规格

### 8.1 从课件数字复算峰值

课件采用 80 个 SM、每 SM 四组各 16 个 FP32 算术单元、时钟 1.245 GHz 的 V100 教学配置。若每单元每周期执行一个乘加，并按乘法与加法共 2 FLOP 计：

$$
80\times4\times16\times1.245\times10^9\times2
=12.7488\times10^{12}\ \mathrm{FLOP/s}
$$

即约 12.7 TFLOP/s。这不是所有 V100 型号/频率的统一实测，也不包含 Tensor Core 的另一种计算吞吐口径。

若每 SM 最多驻留 64 个 Warp，80×64×32=163840 个线程状态是理论驻留数量上界，不是每周期同时做 163840 次浮点运算。实际 Kernel 可能先受到其他资源限制。

### 8.2 Warp 宽度、发射间隔与指令延迟别混用

课件用每子分区 16 个 FP32 单元解释 32 线程 Warp 的工作如何跨多个周期经过数据通路。这里的“两个周期处理一条 Warp 的 FP32 工作”，不意味着任意指令从输入到结果的依赖延迟只有两个周期。

SM 有多个调度分区，可能安排不同 Warp 或不同类型操作重叠。它与 CPU 的超标量或硬件多线程有相似思想，但不能据此把 GPU 调度器描述成与复杂 CPU 乱序执行器完全一样。

### 8.3 两个必须修正的容量误读

第一，SM 最多驻留 64×32=2048 个线程，不等于一个 Block 可以含 2048 个线程。V100 的单 Block 上限是 1024；本章通用练习只用到 256。运行配置还受每维度限制、函数资源使用等约束，应查询目标设备与函数属性。

第二，课件 V100 图中 128 KiB 是 L1/Shared 等共用的物理存储；官方调优指南给出的每 SM Shared Memory 可配置容量最高为 96 KiB。单 Block 申请大于普通静态分配限制还可能需要动态存储与显式选择。本章不申请大容量共享内存，也不把整块物理存储都视为 Shared 配额。

不同代 GPU 的 SM 数、Warp 驻留上限、调度分区、寄存器与共享存储配额会变化；学习本例的目的在于理解约束怎样起作用，而不是靠背 V100 数字配置所有设备。

## 9. Block 驻留：先算资源能不能放下

### 9.1 一个保留单位的教学模型

设每 SM 可容纳 Tmax 个线程、Wmax 个 Warp、S 字节 Shared、R 个 32-bit 寄存器，最多 Kmax 个 Block。Kernel 每 Block 有 B 个线程，申请 s 字节 Shared，每线程使用 r 个寄存器。忽略分配粒度、保留量与分区限制，理想的驻留 Block 上界为：

$$
\begin{aligned}
K_T&=\left\lfloor\frac{T_{\max}}B\right\rfloor, & K_W&=\left\lfloor\frac{W_{\max}}{\lceil B/32\rceil}\right\rfloor\\
K_S&=\left\lfloor\frac Ss\right\rfloor, & K_R&=\left\lfloor\frac R{Br}\right\rfloor\\
K&\le\min(K_{\max},K_T,K_W,K_S,K_R)
\end{aligned}
$$

这里假设 s、r 均为正；没有使用某类资源时应去掉相应项，而非除以 0。真实 CUDA 的分配粒度与函数限制会使简单除法不够准确，可用官方占用率接口核算。

### 9.2 课件的小 GPU：线程够，Shared 不够

一台假想 SM 有 384 个线程状态、12 个 Warp 的容量，Shared 为 1536 byte。每 Block 128 线程、4 Warp、520 byte Shared，暂不考虑寄存器：

- 线程允许 floor(384/128)=3 个 Block。
- Warp 允许 floor(12/4)=3 个 Block。
- Shared 允许 floor(1536/520)=2 个 Block；第三个共需 1560 byte，放不下。

所以每 SM 只驻留 2 个，两个 SM 一共 4 个。某个 Block 结束后，它的资源被释放，调度器可放入下一块；后续 Block 不必等待整个 Grid 第一批全部结束。

这解释了为什么一百万逻辑线程不要求同时有一百万线程上下文。本章模型中的 1.5 KiB 明确为 1536 byte，避免单位模糊。

### 9.3 寄存器也是驻留约束

另设一台教学 SM 有 65536 个寄存器、2048 线程、64 Warp，其他资源足够。B=256，每线程 r=32 时，一个 Block 用 8192 个寄存器，最多 8 个 Block；r=64 时每 Block 用 16384 个，最多 4 个。

若 8 Warp/Block，则两种情况分别驻留 64 与 32 Warp。**Occupancy（占用率）**按驻留活跃 Warp 数相对于硬件上限的比例定义，本例为 100% 与 50%。它不等于算术单元忙碌率，也不等于运行速度。

更多寄存器可能减少溢出和重复加载，低 Occupancy 反而更快；强迫减寄存器也可能把数据挤到 Local Memory。优化需要看时间与实际瓶颈。

### 9.4 Block 太大、太小分别损失什么？

大 Block 会粗化资源分配，一点资源不足就可能少驻留整块；小 Block 则可能受到每 SM Block 数上限与部分 Warp 的浪费。GPU 上总 Block 数很少，还可能让很多 SM 无任务可做。

程序应暴露足够工作，让调度器适配不同规模的 GPU，但配置必须合法。不能在未查询设备和编译资源的情况下，假定“只要 SM 放得下线程，任何 Block 都能运行”。

## 10. 访存模式与性能：为什么 Tile 不保证更快？

### 10.1 同样 32 个数，可能触及不同数量的段

**Coalescing（合并访存）**关注同一 Warp 的地址能否由较少的内存事务服务。用一个简化模型说明：32 Lane 各读 4 byte，数据按 32 byte 对齐段统计，不模拟 Cache 或真实 DRAM。

- Lane l 读第 l 个 float，起始对齐：覆盖 128 byte，共 4 段。
- 整体偏移一个 float：覆盖 byte 4…131，共 5 段。
- Lane l 读第 32l 个 float：地址间隔 128 byte，共 32 段。

这三个数字是地址集合的计数，不是每次真实访问必定产生相同次数的 DRAM 操作。缓存命中、具体架构和访问种类仍会改变实现。

### 10.2 三点平均的数据流量模型

直接版每输出按逻辑读取 3 个 float、写 1 个，共 16 byte。完整 B 点的 Tile 装载 B+2 个 float、写 B 个输出，逻辑 Global 流量是 4(B+2)+4B=8B+8 byte，即每输出约 8+8/B byte。

但直接版相邻输出读取重叠，缓存与合并可能已经减少底层流量；Tile 版另外执行 Shared 读写、地址计算与屏障，且占用驻留资源。所以仅靠上面的逻辑比率不能保证提速。

Shared 访问还可能出现 **Bank Conflict（存储体冲突）**：同一组访问集中到相同存储体的不同地址，需更多服务步骤。具体 Bank 组织和广播规则依架构而定；本章不把一个简单取模口诀当作全部规则。

### 10.3 计算快不等于端到端快

设拷贝和其他固定成本共 120 μs，Kernel 从 10 μs 优化到 5 μs。Kernel 快 2 倍，整段却仅从 130 到 125 μs，约 1.04 倍。

如果把 Host 发射语句前后直接读时钟，可能只测到提交命令的成本。Kernel-only 通常使用同一 Stream 的 CUDA Event 等方法并等待完成；端到端则要明确是否包含分配、H2D、D2H 与同步。本章 CUDA 练习只验证结果，不输出没有实测基础的 GPU 性能数据。

## 11. Persistent Threads 与现代扩展的边界

课件补充页展示常驻 Block 循环领取任务的 Persistent 风格：把一部分调度转移到应用内部。它可能有助于减少调度开销或实现更灵活的任务粒度，但需要正确的任务计数、缓冲复用与退出协议。

不能简单按 SM 数乘一个估计 Block 数，然后假定所有 Block 一定同时执行，进而设计跨 Block 自旋屏障。寄存器、Shared、并发工作和实际执行环境都可能破坏这个假设。

课件第 70 页不是可直接运行的库：`atomicInc` 不能直接当作按块长递增的 `atomicAdd`；分配字节数、尾部、除以 3 和复用屏障等也要核查。本章不发布该示意为正确的 Persistent Kernel。合作启动与更现代的组织机制应按各自规范设计，不靠这份简图推导。

Tensor Core 也不是“把普通 FP32 ALU 数量再乘一个数”。它针对特定矩阵类操作、数据类型和布局提供吞吐，后续章节再讨论。本章 V100 峰值算例只计算普通 FP32 乘加路径。

## 12. 无 GPU 实验：运行一个确定性的语义模型

本程序使用 Python 标准库，不执行 CUDA、不模拟 GPU 时钟。它检查输出映射、Tile 写入覆盖、阶段依赖、资源算术和具体调度反例。

### 12.1 完整代码

保存为 `models.py`：

```python
"""CPU semantic models: not a CUDA emulator, compiler, or GPU benchmark."""
from collections import Counter
from math import ceil, isclose


def tiled_avg(x, threads, reverse=False):
    n = len(x)
    out = [None]*n
    visits = [0]*n
    blocks = list(range((n+threads-1)//threads))
    if reverse: blocks.reverse()
    for block in blocks:
        base = block*threads
        shared = [None]*(threads+2)
        writes = [0]*(threads+2)
        # Complete all cooperative loads before any output reads (barrier phase).
        for t in range(threads):
            for q in range(t, threads+2, threads):
                g = base+q-1
                shared[q] = x[g] if 0 <= g < n else 0.0
                writes[q] += 1
        assert writes == [1]*(threads+2)
        for t in range(threads):
            i = base+t
            if i < n:
                assert all(shared[q] is not None for q in (t,t+1,t+2))
                out[i] = (shared[t]+shared[t+1]+shared[t+2])/3
                visits[i] += 1
    assert visits == [1]*n
    return out


def reference(x):
    padded = [0.0]+x+[0.0]
    return [sum(padded[i:i+3])/3 for i in range(len(x))]


def matrix_coverage(nx, ny, bx, by):
    count = Counter()
    launched = 0
    for yb in range((ny+by-1)//by):
        for xb in range((nx+bx-1)//bx):
            for ty in range(by):
                for tx in range(bx):
                    launched += 1
                    x, y = xb*bx+tx, yb*by+ty
                    if x < nx and y < ny: count[(x,y)] += 1
    assert count == Counter({(x,y):1 for y in range(ny) for x in range(nx)})
    return launched


def sectors(offset, stride):
    # 32 lanes, each loading 4 bytes; abstract aligned 32-byte sectors.
    touched = set()
    for lane in range(32):
        address = 4*(offset+stride*lane)
        touched.update(range(address//32, (address+3)//32+1))
    return len(touched)


def resident_blocks(threads, shared, registers_per_thread,
                    max_threads, shared_bytes, registers, max_blocks, max_warps):
    # No allocation granularity, partitioning, or reserved resources modeled.
    return min(max_threads//threads, shared_bytes//shared,
               registers//(threads*registers_per_thread), max_blocks,
               max_warps//ceil(threads/32))


def flag_order(order):
    # One resident block, no preemption. Block 1 waits; block 0 produces flag.
    flag = 0
    for block in order:
        if block == 1 and flag == 0: return False
        if block == 0: flag = 1
    return True


def main():
    sizes = [0,1,2,3,5,31,32,33,127,128,129,257]
    blocks = [1,2,7,32,64,128,256]
    cases = 0
    for n in sizes:
        x = [(i%17-8)*0.25 for i in range(n)]
        want = reference(x)
        for t in blocks:
            for reverse in (False, True):
                got = tiled_avg(x,t,reverse)
                assert all(isclose(a,b,rel_tol=0,abs_tol=1e-12) for a,b in zip(got,want))
            cases += 1
    assert tiled_avg([1,2,3,4,5],2) == [1,2,3,4,3]
    print(f'avg3: cases={cases} two_block_orders=pass tile_writers=pass outputs=pass')
    matrix_cases = 0
    for nx,ny in [(0,0),(1,1),(11,5),(12,6),(17,9),(31,33)]:
        for bx,by in [(4,3),(8,4),(16,16)]:
            matrix_coverage(nx,ny,bx,by)
            matrix_cases += 1
    assert matrix_coverage(11,5,4,3) == 72
    print(f'matrix: cases={matrix_cases} exact_once=pass 11x5_launch=72 valid=55')
    for n in sizes:
        for launched in [1,7,32,128]:
            visits = [0]*n
            for tid in range(launched):
                for i in range(tid,n,launched): visits[i] += 1
            assert visits == [1]*n
    print('grid_stride: cases=48 exact_once=pass')
    # Thread 0 tries to read neighbors before other producers have run.
    shared = [None]*6
    for q in range(0,6,4): shared[q] = 1
    assert shared[1] is None
    print('missing_barrier: uninitialized_neighbor_counterexample=detected')
    assert [sectors(0,1),sectors(1,1),sectors(0,32)] == [4,5,32]
    print('sector_model: aligned=4 offset_one_float=5 stride32=32')
    count = resident_blocks(128,520,1,384,1536,65536,32,12)
    assert count == 2
    assert resident_blocks(256,520,64,2048,98304,65536,32,64) == 4
    assert resident_blocks(256,520,32,2048,98304,65536,32,64) == 8
    print('residency: toy_blocks_per_SM=2; register32=8 register64=4')
    assert flag_order([0,1]) and not flag_order([1,0])
    bins = [i%10 for i in range(101)]
    assert Counter(bins) == Counter(reversed(bins))
    print('cross_block: producer_first=complete consumer_first=deadlock; histogram_order=pass')
    assert 130*4 == 520 and 3*520 > 1536
    assert 80*64*32 == 163840
    assert isclose(80*4*16*1.245e9*2/1e12,12.7488)
    print('all_checks=pass')


if __name__ == '__main__':
    main()
```

### 12.2 运行与固定输出

从仓库根目录运行：

```bash
python3 labs/lecture07/models.py
```

本次实际输出：

```text
avg3: cases=84 two_block_orders=pass tile_writers=pass outputs=pass
matrix: cases=18 exact_once=pass 11x5_launch=72 valid=55
grid_stride: cases=48 exact_once=pass
missing_barrier: uninitialized_neighbor_counterexample=detected
sector_model: aligned=4 offset_one_float=5 stride32=32
residency: toy_blocks_per_SM=2; register32=8 register64=4
cross_block: producer_first=complete consumer_first=deadlock; histogram_order=pass
all_checks=pass
```

84 组来自 12 种 N 与 7 种 Block 大小，每组均按正序和倒序执行 Block。它证明这些配置在模型里不依赖这两种执行顺序，并验证每个 Tile 槽位与输出的单写者覆盖；并不是枚举了真实 GPU 的全部并发交错。

无屏障测试构造一次未初始化读取，不真的触发硬件竞争。跨 Block 模型只有一个驻留槽位，直接返回“不能推进”，不在电脑上启动无限循环。二维模型检查每个合法坐标恰好一次；它与完整 CUDA 程序中的数值检查相互补充。

## 13. CUDA 练习：直接版、Tile、二维加法与直方图

### 13.1 目标与验证状态

下面是完整 CUDA C++17 源文件，独立编写了主机初始化、设备分配、拷贝、Kernel、结果对照和清理。它需要 NVIDIA GPU、兼容驱动、支持该 GPU 的 CUDA Toolkit 与 nvcc。

**本次未编译，未进行 GPU 实机验证。** CPU 模型不能证明 nvcc 编译、设备端同步或驱动运行一定成功。这里提供待在目标环境验证的练习，不给未经执行的通过结论。

### 13.2 完整代码

保存为 `cuda_basics.cu`：

```cpp
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <utility>

void check(cudaError_t e) {
    if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));
}
template<class T> struct DeviceBuffer {
    T* p = nullptr;
    explicit DeviceBuffer(std::size_t n) {
        check(cudaMalloc(reinterpret_cast<void**>(&p),n*sizeof(T)));
    }
    ~DeviceBuffer() { if (p) cudaFree(p); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
};
__global__ void avg_direct(const float* x,float* y,int n) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if (i<n) {
        float left=i>0?x[i-1]:0.0f;
        float right=i+1<n?x[i+1]:0.0f;
        y[i]=(left+x[i]+right)/3.0f;
    }
}
__global__ void avg_tiled(const float* x,float* y,int n) {
    extern __shared__ float tile[];
    int t=threadIdx.x, width=blockDim.x, base=blockIdx.x*width;
    for (int q=t;q<width+2;q+=width) {
        int g=base+q-1;
        tile[q]=(g>=0 && g<n)?x[g]:0.0f;
    }
    __syncthreads(); // Every thread participates, including tail threads.
    int i=base+t;
    if (i<n) y[i]=(tile[t]+tile[t+1]+tile[t+2])/3.0f;
}
__global__ void matrix_add(const float* a,const float* b,float* c,int nx,int ny) {
    int x=blockIdx.x*blockDim.x+threadIdx.x;
    int y=blockIdx.y*blockDim.y+threadIdx.y;
    if (x<nx && y<ny) {
        int i=y*nx+x;
        c[i]=a[i]+b[i];
    }
}
__global__ void histogram(const int* x,int* bins,int n) {
    int tid=blockIdx.x*blockDim.x+threadIdx.x;
    int step=blockDim.x*gridDim.x;
    for (int i=tid;i<n;i+=step) atomicAdd(&bins[x[i]],1);
}
void compare(const std::vector<float>& got,const std::vector<float>& want) {
    if (got.size()!=want.size()) throw std::runtime_error("size mismatch");
    for (std::size_t i=0;i<got.size();++i)
        if (!std::isfinite(got[i]) || std::abs(got[i]-want[i])>1e-6f)
            throw std::runtime_error("output/tail mismatch");
}
void avg_case(int n,int threads) {
    if (n==0) return; // No zero-sized grid launch.
    std::vector<float> x(n),want(n+8,-999.0f),got(n+8),init(n+8,-999.0f);
    for (int i=0;i<n;++i) x[i]=(i%17-8)*0.25f;
    for (int i=0;i<n;++i) {
        float left=i>0?x[i-1]:0.0f, right=i+1<n?x[i+1]:0.0f;
        want[i]=(left+x[i]+right)/3.0f;
    }
    DeviceBuffer<float> dx(n),dy(n+8);
    check(cudaMemcpy(dx.p,x.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    int blocks=(n+threads-1)/threads;
    for (int mode=0;mode<2;++mode) {
        check(cudaMemcpy(dy.p,init.data(),init.size()*sizeof(float),cudaMemcpyHostToDevice));
        if (mode==0) avg_direct<<<blocks,threads>>>(dx.p,dy.p,n);
        else avg_tiled<<<blocks,threads,(threads+2)*sizeof(float)>>>(dx.p,dy.p,n);
        check(cudaGetLastError());
        check(cudaDeviceSynchronize());
        check(cudaMemcpy(got.data(),dy.p,got.size()*sizeof(float),cudaMemcpyDeviceToHost));
        compare(got,want);
    }
}
void matrix_case(int nx,int ny,int bx,int by) {
    int n=nx*ny;
    if (n==0) return;
    std::vector<float> a(n),b(n),want(n+8,-999.0f),got(n+8),init(n+8,-999.0f);
    for (int i=0;i<n;++i) { a[i]=(i%17-8)*0.25f;b[i]=0.5f;want[i]=a[i]+b[i]; }
    DeviceBuffer<float> da(n),db(n),dc(n+8);
    check(cudaMemcpy(da.p,a.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    check(cudaMemcpy(db.p,b.data(),n*sizeof(float),cudaMemcpyHostToDevice));
    check(cudaMemcpy(dc.p,init.data(),init.size()*sizeof(float),cudaMemcpyHostToDevice));
    dim3 block(bx,by),grid((nx+bx-1)/bx,(ny+by-1)/by);
    matrix_add<<<grid,block>>>(da.p,db.p,dc.p,nx,ny);
    check(cudaGetLastError()); check(cudaDeviceSynchronize());
    check(cudaMemcpy(got.data(),dc.p,got.size()*sizeof(float),cudaMemcpyDeviceToHost));
    compare(got,want);
}
void histogram_case(int n) {
    if (n==0) return;
    std::vector<int> x(n),want(10,0),got(10);
    for (int i=0;i<n;++i) { x[i]=i%10;++want[x[i]]; }
    DeviceBuffer<int> dx(n),bins(10);
    check(cudaMemcpy(dx.p,x.data(),n*sizeof(int),cudaMemcpyHostToDevice));
    check(cudaMemset(bins.p,0,10*sizeof(int)));
    histogram<<<2,128>>>(dx.p,bins.p,n);
    check(cudaGetLastError());check(cudaDeviceSynchronize());
    check(cudaMemcpy(got.data(),bins.p,10*sizeof(int),cudaMemcpyDeviceToHost));
    if (got!=want) throw std::runtime_error("histogram mismatch");
}
int main() {
    try {
        int devices=0;check(cudaGetDeviceCount(&devices));
        if (devices==0) throw std::runtime_error("A CUDA-capable NVIDIA GPU is required");
        check(cudaSetDevice(0));cudaDeviceProp prop{};check(cudaGetDeviceProperties(&prop,0));
        if (prop.maxThreadsPerBlock<256) throw std::runtime_error("Tests require 256 threads/block");
        int avg_cases=0,matrix_cases=0,histogram_cases=0;
        for (int n : {0,1,2,3,5,31,32,33,127,128,129,257}) {
            for (int t : {1,2,7,32,64,128,256}) { avg_case(n,t);++avg_cases; }
            histogram_case(n);++histogram_cases;
        }
        for (auto shape : {std::pair<int,int>{0,0},{1,1},{11,5},{12,6},{17,9},{31,33}})
            for (auto block : {std::pair<int,int>{4,3},{8,4},{16,16}}) {
                matrix_case(shape.first,shape.second,block.first,block.second);++matrix_cases;
            }
        std::cout<<"avg_cases="<<avg_cases<<" matrix_cases="<<matrix_cases
                 <<" histogram_cases="<<histogram_cases<<" tail=pass correct=yes\n";
    } catch (const std::exception& e) {
        std::cerr<<e.what()<<'\n';return 1;
    }
}
```

### 13.3 编译、运行与预期结果

在可用的 CUDA 环境从仓库根目录执行：

```bash
mkdir -p /tmp/cs149-l07-build
nvcc -O2 -std=c++17 labs/lecture07/cuda_basics.cu \
  -o /tmp/cs149-l07-build/cuda_basics
/tmp/cs149-l07-build/cuda_basics
```

若工具链版本需要显式指定 GPU 架构，应使用目标设备受支持的编译目标；不要把本章 V100 例子机械写成所有机器的选项。

设计上的预期输出，**不是本次实测**：

```text
avg_cases=84 matrix_cases=18 histogram_cases=12 tail=pass correct=yes
```

这些是输入配置计数：空输入由 Host 跳过，仍计入配置；平均值每个非空配置分别运行直接版和 Tile 版，因此不是总 Kernel 启动次数。

N 覆盖 0/1/2/3/5/31/32/33/127/128/129/257；Block 大小含 1/2/7/32/64/128/256。二维矩阵使用 6 种尺寸与 3 种 Block 形状，包含 11×5 的非整除边缘。输出后保留 8 个哨兵元素，检查尾部未被覆盖；输入只分配定义长度。

直方图输入限定 0…9，先清零桶，整数计数未接近溢出。若输入含负数或大于 9，必须另加验证/过滤，不能直接索引。

### 13.4 设备端检测与性能实验另行完成

在安装 Compute Sanitizer 的 GPU 环境，可分别运行：

```bash
compute-sanitizer --tool memcheck /tmp/cs149-l07-build/cuda_basics
compute-sanitizer --tool racecheck /tmp/cs149-l07-build/cuda_basics
compute-sanitizer --tool synccheck /tmp/cs149-l07-build/cuda_basics
```

本次没有运行这些工具，不能声称“设备端无竞争”。哨兵只能发现部分写越界，不能替代地址检查；模型输出正确也不能代替 Barrier 的设备检查。

验证通过后再扩大规模，预热、重复计时，报告 GPU、编译选项、Block、Shared 字节数和输入。应分别测 Kernel 与端到端时间，比较实际带宽/计数器，并保留直接版作为基线。现有 [SAXPY Lab](../labs/README.md) 可作后续计时练习，不是本章缺少正确性步骤的替代品。

## 14. 练习与参考答案

### 练习 1：72 是什么？

11×5 矩阵，Block 4×3，多少 Block、多少逻辑线程、多少无效线程？

**答：** Grid 3×2，6 个 Block，72 线程，55 个有效，17 个无输出。必须分别检查二维坐标。

### 练习 2：启动返回可以读结果吗？

提交 Kernel 后立刻在 Host 读输出，为什么不一定正确？

**答：** 启动通常对 Host 异步；要建立正确的完成等待，并确保 CPU 读取的是可访问位置或已复制回的数据。发射错误检查不等于执行完成。

### 练习 3：线程编号推算

Bx=8、By=4，Thread (3,2,0) 的 Block 内线性编号是多少？

**答：** 3+8×2=19，在本章 32 线程 Warp 组织下属于该 Block 第 0 个 Warp。

### 练习 4：支持区大小

一个完整 Block 更新 256 个三点平均输出，需要多少输入、多少 float32 Shared 字节？

**答：** 258 个输入，1032 byte，不是 1024。直接版有 768 次线程级标量读取，不能据此宣布真实 DRAM 事务一定是 768。

### 练习 5：无效线程是否没有用？

N=5、B=2 的最后 Block，t=1 没有输出，为什么仍参与加载与屏障？

**答：** 在协作装载中，它写入其他输出可能需要的槽位；整 Block 必须按协议完成阶段。无输出不等于无协作责任。

### 练习 6：Shared 与 uniform

每个线程声明一个私有变量 v，和 Block 共用一个 Shared 数组，是否只要所有线程写相同值就安全？

**答：** 私有 v 各有自己的状态；Shared 是同一逻辑对象，多写者/消费者需要满足同步规则。相同数值不自动取消数据竞争，Shared 也不等同于 ISPC uniform 类型。

### 练习 7：驻留限制

假想 SM 可放 384 线程、1536 byte Shared，每 Block 128 线程和 520 byte Shared，其他资源足够，放几个？

**答：** 线程允许 3 个，Shared 只允许 2 个，所以 2。三块需 1560 byte。

### 练习 8：2048 个线程的误解

某 SM 可驻留 2048 个线程，能否直接启动一个 2048 线程 Block？

**答：** 不能据此判断。每 Block 有独立上限，V100 为 1024；还要检查各维度、函数和资源限制。每 SM 总容量可由多个 Block 分享。

### 练习 9：Warp 有多少？

一个 Block 有 33 个线程，占几个 Warp？与 33 个有效数据项完全等价吗？

**答：** 2 个 Warp。有效数据还取决于映射与 N；最后一个 Warp 的剩余 Lane 根本没有对应 Block 线程，区别于已经创建却没有输出的尾部线程。

### 练习 10：同 Warp 的分支

整个 Warp 的线程都满足同一个 if，与偶数 Lane 满足有什么区别？

**答：** 前者在该分支没有 Warp 内分歧；后者可能需要分路屏蔽执行。实际成本还取决于编译、路径和架构。

### 练习 11：原子保证进展吗？

Block 1 使用原子读等 Block 0 的标志，为什么仍可能挂住？

**答：** 原子保护访问的不可分割性，不保证 Block 0 得到驻留资源；若 Block 1 占据唯一槽位等待，生产者可能无法启动。

### 练习 12：占用率下降是否一定变慢？

寄存器翻倍使理想驻留 Warp 从 64 降到 32，是否必然慢两倍？

**答：** 不一定。更多寄存器可能减少溢出与重复读取。Occupancy 是资源比率，不是吞吐或运行时间。

### 练习 13：合并访存计数

32 Lane 各读 4 byte 连续数据，首地址相对 32 byte 段偏移 4 byte，抽象模型覆盖几段？

**答：** byte 4…131，跨 0…4 号段，共 5 段。这不直接等于硬件 DRAM 事务数。

### 练习 14：端到端收益

H2D/D2H 等固定 80 μs，Kernel 从 20 降到 10 μs，整体加速多少？

**答：** 100/90≈1.111 倍，Kernel 本身是 2 倍。需说明是否包含分配和初始化。

### 练习 15：CPU 模型能证明什么？

模型在正序和倒序 Block 执行下都正确，能否宣布 CUDA 设备运行无竞争？

**答：** 不能。模型验证给定映射与分阶段算法，没有执行 GPU 指令或全部并发交错；CUDA 编译、运行和设备检查仍需单独完成。

### 练习 16：下一步怎么测？

Shared 版在一个尺寸上比直接版慢，应立即删除它吗？

**答：** 先确认正确性与计时范围，再扫描尺寸和 Block，检查缓存复用、屏障成本、指令和驻留资源。单个小尺寸不足以推断所有场景，但也不能先入为主认为手写 Shared 必须更快。

## 15. 术语与层次速查

| 术语 | 本章含义 |
| --- | --- |
| Kernel | 可在 Device 上启动的函数 |
| Grid | 一次 Launch 的 Block 集合 |
| Block | 能使用 Block 内 Shared 与同步的一组线程 |
| CUDA Thread | 具有自身编号与控制状态的逻辑执行实例 |
| Warp | 本章 NVIDIA 组织下的 32 线程分组 |
| SM | 承载和执行驻留 Block/Warps 的硬件单元 |
| H2D / D2H | Host-to-Device / Device-to-Host 传输 |
| Halo | 计算块边缘输出所需的额外邻居输入 |
| Occupancy | 活跃驻留 Warp 数相对硬件最大 Warp 数的比例 |
| Coalescing | 把 Warp 的地址访问组织为较少内存服务事务 |

## 16. 与 AI Infrastructure 的联系（作者延伸）

一个 Tensor 算子从数学表达式到执行，要决定 Tile 与线程分工、数据布局、片上复用、同步和数值要求。理解这些层次，有助于读懂 CUDA 或其他 GPU DSL；不能仅凭某种语言的一个程序实例就断言对应一个物理 Core。

融合减少中间 Tensor 搬运，却可能提高寄存器或 Shared 使用量；本章资源模型解释了为什么“少访存”与“更多驻留”可能形成权衡。矩阵类加速单元还有数据类型与布局限制，不能直接套用普通逐元素 Kernel 的峰值模型。

端到端推理还包含输入准备、批处理、状态管理与数据传输。Kernel-only 的提升需要放回完整请求路径评估，尤其要区分吞吐、单请求延迟和尾延迟。本节是迁移解释，不声称文字稿逐项介绍了当前框架实现。

## 17. 来源、修正与验证范围

| 来源 | 使用范围 | 状态 |
| --- | --- | --- |
| [Stanford 第 7 讲课程页](https://gfxcourses.stanford.edu/cs149/fall23/lecture/gpucuda/) | 讲次与主题 | 已核对 |
| [官方 73 页课件](https://gfxcourses.stanford.edu/cs149/fall23content/media/gpucuda/07_gpuarch.pdf) | 历史、CUDA 抽象、卷积、V100、调度与同步 | 全部文字结构已核对；视觉抽查第 28、30、37、38、50、53、60、69 页，未逐页视觉复核 |
| 用户提供自动英文文字稿 | 开场图形历史到跨 Block 标志等待结尾 | 全文已阅读，无时间码，未逐句音频校验 |
| [课程录像](https://www.youtube.com/watch?v=qQTDF0CBoxE) | 对应本讲录像入口 | 未编造时间点，未完成逐句音频对照 |
| [NVIDIA CUDA C++ 入门](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/intro-to-cuda-cpp.html) | 声明、编号、启动、完成等待 | 官方语义参考，本章代码为独立教学实现 |
| [NVIDIA SIMT Kernel 指南](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html) | Shared、Block 同步与访存 | 官方接口参考，不把课堂简写当成全部规范 |
| [NVIDIA 统一与系统内存](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/understanding-memory.html) | UVA、Managed、Host 内存支持的区别 | 用于限定简化地址空间模型 |
| [NVIDIA Volta 调优指南](https://docs.nvidia.com/cuda/volta-tuning-guide/index.html) | Warp 调度、Shared 容量与寄存器资源 | 对照 V100 历史实例，非当前 GPU 通用规格 |
| [NVIDIA 架构比较表](https://developer.nvidia.com/blog/nvidia-ampere-architecture-in-depth/) | V100 每 Block 最大 1024 线程 | 核对历史硬件限制，区别 SM 总驻留容量 |
| [NVIDIA 高级 Kernel 编程](https://docs.nvidia.com/cuda/cuda-programming-guide/03-advanced/advanced-kernel-programming.html) | 独立线程执行等语义边界 | 延伸参考，不声称实现了高级合作协议 |

本章修正启动异步性、520 byte 与 512 byte、每 SM 驻留与每 Block 上限、L1/Shared 物理容量与可用配额的混淆；课件部分示意省略了字节乘数、边界与除以 3，未直接当作完整实现使用。原有三点平均的零边界定义予以保留，并与课件 N+2 输入版本明确对应。

原创 CPU 模型已运行：84 组三点平均配置（各两个 Block 次序）、18 组二维映射、48 组 Grid-Stride 覆盖及具体同步反例通过；资源、段地址与峰值算术已复算。模型不执行 GPU，不是 CUDA 编译或实机运行证明。

完整 CUDA 源文件提供初始化、直接/Shared 两版、二维加法、原子直方图、边界哨兵和错误检查，但本机无 nvcc 与 NVIDIA GPU，**未编译、未运行、未跑 Compute Sanitizer、未做 GPU Benchmark**。来源和限制详见 [第 7 讲核验记录](../sources/lecture-07-audit.md)。公开仓库只保存原创教材、代码和来源链接，不提交原始全文、官方 PDF 或构建产物。
